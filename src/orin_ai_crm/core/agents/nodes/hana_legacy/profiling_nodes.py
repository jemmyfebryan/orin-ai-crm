"""
Profiling Nodes - Customer profiling and data collection
"""

import os
from typing import Literal, Optional
from datetime import timedelta, timezone
from sqlalchemy import select
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage

from src.orin_ai_crm.core.models.database import AsyncSessionLocal, LeadRouting
from src.orin_ai_crm.core.models.schemas import AgentState, CustomerProfile
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.tools import (
    get_or_create_customer,
    update_customer_profile
)

logger = get_logger(__name__)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))

# Patterns that indicate contact_name is NOT a person's name
NON_NAME_PATTERNS = [
    "~", "-", "_", ".", "...", "#", "user", "guest", "unknown", "anonymous",
    "pt", "cv", "ud", "pd", "fakultas", "universitas", "institut",
    "toko", "store", "shop", "mart", "jaya", "maj", "trading", "corp",
    "corporation", "company", "ltd", "inc", "tbk", "persero"
]

HANA_PERSONA = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PERCAKAPAN:
- Bertanya SATU per SATU seperti manusia asli, jangan langsung kirim form lengkap
- Jika user memberikan info baru, update dan konfirmasi dengan sopan
- Contoh: "Oh dari Jakarta ya kak, kakak bisa sebutin nama kakak agar Hana bisa panggil dengan sopan?"
- Jangan meminta data lengkap dalam satu pesan
- Jika user menyebut "lainnya" atau "kantor" untuk jenis kendaraan, gunakan kata yang lebih natural seperti "kendaraan" atau "kebutuhan kantor"

INFORMASI PRODUK:
Kamu memiliki akses ke database produk lengkap. Jika user tanya tentang produk GPS, tanya kebutuhan mereka dulu (jenis kendaraan, preferensi fitur) baru berikan rekomendasi yang sesuai.
"""

# Mapping untuk vehicle_type agar lebih natural di response
VEHICLE_TYPE_MAPPING = {
    "lainnya": "kendaraan",
    "armada operasional/kantor": "kebutuhan kantor",
    "armada operasional": "kebutuhan kantor",
    "kantor": "kebutuhan kantor",
}


def get_natural_vehicle_type(vehicle_type: str) -> str:
    """Convert vehicle_type ke kata yang lebih natural untuk response"""
    if not vehicle_type:
        return "kendaraan"

    vehicle_lower = vehicle_type.lower().strip()
    return VEHICLE_TYPE_MAPPING.get(vehicle_lower, vehicle_lower)


def is_valid_person_name(contact_name: Optional[str]) -> bool:
    """
    Check if contact_name is a valid person's name (Indonesian or Western).

    Returns True if contact_name looks like a real person's name.
    Returns False if it looks like a company name, placeholder, or non-name string.

    Examples:
    - "Budi", "Siti", "Made", "John", "Sarah" -> True
    - "PT Astra Jaya", "CV Maju", "~", "-" -> False
    """
    if not contact_name:
        return False

    name = contact_name.strip()

    # Empty or very short
    if len(name) < 2:
        return False

    # Check for non-name patterns
    name_lower = name.lower()

    # Direct matches with non-name patterns
    if name_lower in NON_NAME_PATTERNS:
        return False

    # Contains company indicators
    for pattern in NON_NAME_PATTERNS:
        if pattern in name_lower:
            return False

    # Single character or special character only
    if len(name) <= 2 and any(c in name for c in "~-_#"):
        return False

    # All numbers or mostly special characters
    if any(c.isdigit() for c in name):
        # Contains numbers, likely not a name
        return False

    # Use LLM for more sophisticated validation if needed
    # For common Indonesian/Western names, this should work well
    return True


def get_user_identifier(state: AgentState) -> dict:
    """Return dict dengan phone_number dan/atau lid_number"""
    return {
        "phone_number": state.get('phone_number'),
        "lid_number": state.get('lid_number')
    }


async def extract_customer_info(messages: list, current_profile: dict, vehicle_matches: list[dict] = None) -> tuple[CustomerProfile, dict]:
    """
    Extract/update customer info dari pesan terakhir.
    Structured output akan mengisi field yang kosong dan mengupdate field yang sudah ada.
    For vehicle, will:
    1. Extract vehicle_alias from user message (raw text like "CRF", "Avanza")
    2. Search VPS DB for vehicle_id
    3. If found, store vehicle_id and vehicle_alias from VPS DB
    4. If not found, store vehicle_id=-1 and keep vehicle_alias for reference

    Args:
        messages: Conversation history
        current_profile: Current customer profile dict
        vehicle_matches: Optional list of vehicle dicts from previous clarification (helps LLM understand responses like "yang 6")
    """
    logger.info(f"extract_customer_info called - current_profile: {current_profile}, message_count: {len(messages)}, vehicle_matches: {len(vehicle_matches) if vehicle_matches else 0}")

    # Build vehicle context for LLM if clarification was asked
    vehicle_context = ""
    if vehicle_matches and len(vehicle_matches) > 0:
        vehicle_list = "\n".join([f"{i+1}. {v.get('name', '')}" for i, v in enumerate(vehicle_matches)])
        vehicle_context = f"""

KENDARAAN YANG SEDANG DITANYAKAN (dari pertanyaan sebelumnya):
User sebelumnya ditanya tentang pilihan kendaraan. Opsi yang tersedia:
{vehicle_list}

Jika user menjawab dengan nomor (contoh: "yang 1", "nomor 2", "yang 6"), extract nama kendaraan yang sesuai dari daftar di atas!
Contoh:
- "yang 1" → extract "{vehicle_matches[0].get('name', '')}"
- "yang 6" → jika ada, extract kendaraan ke-6
- "Ioniq5" → extract "Ioniq5" (langsung gunakan nama yang user sebutkan)
"""

    system_prompt = f"""Extract informasi customer dari pesan. Update info yang sudah ada.
Jangan mengarang info jika tidak disebutkan.

Profile saat ini:
- Nama: {current_profile.get('name', '-')}
- Domisili: {current_profile.get('domicile', '-')}
- Kendaraan: {current_profile.get('vehicle_alias', '-')}
- Jumlah Unit: {current_profile.get('unit_qty', 0)}
- B2B: {current_profile.get('is_b2b', False)}{vehicle_context}

Jika user mengoreksi info (contoh: "saya pindah ke Surabaya"), update field tersebut.
Jika user belum menyebutkan, biarkan kosong.

IMPORTANT untuk vehicle_alias:
- Extract nama/alias kendaraan yang user sebutkan (e.g., "CRF", "Avanza", "XMAX", "Fortuner", "motor", "mobil", dll)
- Jika user menjawab dengan NOMOR dari daftar kendaraan di atas, gunakan nama kendaraan yang sesuai!
- HANYA extract jika user jelas menyebutkan kendaraan MILIK mereka
- JANGAN extract kata-kata berikut: "orin", "gps", "tracker", "aplikasi", "sistem", "produk"
- JANGAN extract jika user hanya tertarik atau bertanya tentang produk
- Pastikan user membicarakan KENDARAAN mereka, bukan produk
- Jika tidak jelas, biarkan vehicle_alias kosong"""

    extractor_llm = llm.with_structured_output(CustomerProfile)
    result = extractor_llm.invoke([SystemMessage(content=system_prompt)] + messages)

    # Handle vehicle extraction
    if result.vehicle_alias and result.vehicle_alias.strip():
        # User mentioned a vehicle
        vehicle_alias = result.vehicle_alias.strip()

        # Search VPS DB for vehicle_id
        from src.orin_ai_crm.core.agents.tools.vps_tools import search_vehicle_by_name, get_vehicle_by_id

        vehicle_id, matches = await search_vehicle_by_name(vehicle_alias)

        logger.info(f"search_vehicle_by_name returned: vehicle_id={vehicle_id}, matches_count={len(matches) if matches else 0}")

        if vehicle_id is not None and vehicle_id > 0:
            # Exact match found in VPS DB - get full name
            vehicle_data = await get_vehicle_by_id(vehicle_id)
            result.vehicle_id = vehicle_id
            result.vehicle_alias = vehicle_data.get('name', vehicle_alias) if vehicle_data else vehicle_alias
            logger.info(f"Vehicle '{vehicle_alias}' found in VPS DB: ID={vehicle_id}, alias='{result.vehicle_alias}'")
        elif matches and len(matches) >= 1:
            # Multiple or single partial match found - need clarification if more than 1
            result.vehicle_id = -1
            result.vehicle_alias = vehicle_alias
            # NOTE: We can't add extra fields to Pydantic model (OpenAI structured output requires strict schema)
            # The extra data will be handled in the calling function via a separate dict
            logger.info(f"Found {len(matches)} match(es) for '{vehicle_alias}': {[m.get('name') for m in matches]} - needs_clarification={len(matches) > 1}")
            # Return result + extra_metadata as a tuple for the calling function to handle
            return result, {'vehicle_matches': matches, 'needs_vehicle_clarification': len(matches) > 1}
        else:
            # No matches found in VPS DB - store alias for reference
            result.vehicle_id = -1
            result.vehicle_alias = vehicle_alias  # Use alias as display name
            logger.info(f"Vehicle '{vehicle_alias}' NOT found in VPS DB - storing alias only (ID=-1)")
    else:
        # No vehicle mentioned, keep existing values
        if result.vehicle_id is None or result.vehicle_id == 0:
            result.vehicle_id = current_profile.get('vehicle_id', -1)
        if not result.vehicle_alias:
            result.vehicle_alias = current_profile.get('vehicle_alias', '')
        logger.info(f"No vehicle_alias extracted, keeping existing: ID={result.vehicle_id}, alias='{result.vehicle_alias}'")

    logger.info(f"extract_customer_info result: {result.model_dump()}")
    return result, {}  # Return (profile, extra_metadata) tuple


async def generate_profiling_question(
    messages: list,
    profile: CustomerProfile,
    field_name: str
) -> str:
    """
    Generate personalized profiling question menggunakan LLM.

    Args:
        messages: Conversation history
        profile: Current customer profile
        field_name: Field yang akan ditanya (name, domicile, vehicle_type, unit_qty)

    Returns:
        Generated question string
    """
    profile_data = profile.model_dump()

    # Build context prompt
    context_prompt = f"""{HANA_PERSONA}

CONVERSATION HISTORY:
{format_conversation_history_profiling(messages[-3:])}

CURRENT CUSTOMER PROFILE:
- Nama: {profile_data.get('name') or 'Belum diketahui'}
- Domisili: {profile_data.get('domicile') or 'Belum diketahui'}
- Kendaraan: {profile_data.get('vehicle_alias') or 'Belum diketahui'}
- Jumlah unit: {profile_data.get('unit_qty', 0)}

YOUR TASK:
Generate pertanyaan yang natural dan personalized untuk mendapatkan info: {field_name.upper()}

GUIDELINES PER FIELD:
"""

    # Add specific guidelines based on field
    field_to_guideline = {
        "name": """- Tanyakan nama dengan sopan
- Perkenalkan diri sebagai Hana dari ORIN GPS Tracker
- Jangan terlalu formal, gunakan bahasa natural
- Contoh: "Halo kak! Saya Hana dari ORIN GPS Tracker. Boleh tahu nama kakak agar Hana bisa panggil dengan sopan?"
""",
        "domicile": f"""- Gunakan nama customer: {profile_data.get('name') or 'Kak'}
- Tanyakan domisili/kota
- Jelaskan bahwa ini untuk penawaran yang lebih pas
- Natural dan tidak kaku
""",
        "vehicle_id": f"""- Gunakan nama & domisili customer: {profile_data.get('name') or 'Kak'} dari {profile_data.get('domicile') or 'kota kakak'}
- Tanyakan jenis dan nama kendaraan yang akan dipasang GPS (e.g., "Honda CRF", "Toyota Avanza", "XMAX", dll)
- Jelaskan bahwa sebut nama kendaraan agar kami bisa berikan rekomendasi yang pas
- Natural dan ramah
""",
        "unit_qty": f"""- Gunakan nama customer: {profile_data.get('name') or 'Kak'}
- Gunakan nama kendaraan: {profile_data.get('vehicle_alias') or 'kendaraan kakak'}
- Tanyakan berapa unit yang akan dipasang GPS
- Singkat dan natural
"""
    }

    context_prompt += field_to_guideline.get(field_name, "")

    context_prompt += """
RULES:
- Response HANYA dengan pesan yang akan dikirim (tanpa penjelasan tambahan)
- Personalized berdasarkan info yang sudah diketahui
- Gunakan emoji secara wajar
- Natural seperti chat WhatsApp asli
- Tidak perlu opsi jawaban
- Jangan ulang info yang sudah diketahui"""

    response = llm.invoke([SystemMessage(content=context_prompt)] + messages)
    return response.content


async def generate_vehicle_clarification_question(
    messages: list,
    profile: CustomerProfile,
    vehicle_matches: list[dict]
) -> str:
    """
    Generate a question to clarify which specific vehicle model when multiple matches found.

    Args:
        messages: Conversation history
        profile: Current customer profile
        vehicle_matches: List of vehicle match dicts from VPS DB

    Returns:
        Generated clarification question
    """
    customer_name = profile.name or 'Kak'
    vehicle_alias = profile.vehicle_alias or ''

    # Get vehicle matches from parameter (not from profile.model_extra)
    matches = vehicle_matches

    # Build list of vehicle names from matches
    vehicle_aliass = [v.get('name', '') for v in matches if v.get('name')]
    vehicle_list = ', '.join(vehicle_aliass[:5])  # Limit to first 5

    context_prompt = f"""{HANA_PERSONA}

CONVERSATION HISTORY:
{format_conversation_history_profiling(messages[-3:])}

CUSTOMER NAME: {customer_name}
USER SAID: "kendaraan saya {vehicle_alias}"

FOUND MULTIPLE MATCHES:
{vehicle_list}

YOUR TASK:
Generate a natural question untuk clarify which specific vehicle model customer has.

RULES:
- Tanyakan dengan sopan dan natural
- Jelaskan bahwa ada beberapa tipe {vehicle_alias} di database kami
- Sebutkan opsi-opsi yang tersedia
- Contoh: "Oh, {customer_name} dapat kami informasikan bahwa untuk {vehicle_alias} ada beberapa tipe: {vehicle_list}. Boleh tahu kakak pakai yang tipe yang mana?"
- Jangan terlalu formal, seperti chat WhatsApp asli
- Gunakan emoji secara wajar

Response HANYA dengan pesan yang akan dikirim ke customer."""

    response = llm.invoke([SystemMessage(content=context_prompt)] + messages)
    logger.info(f"Vehicle clarification generated for '{vehicle_alias}': {response.content[:100]}...")
    return response.content


async def generate_greeting_with_name(
    messages: list,
    name: str
) -> str:
    """
    Generate a greeting response when name is auto-filled from contact_name.
    This should be a natural greeting that welcomes the user and continues the conversation.

    Args:
        messages: Conversation history
        name: Customer's name (from contact_name)

    Returns:
        Generated greeting response string
    """
    context_prompt = f"""{HANA_PERSONA}

CONVERSATION HISTORY:
{format_conversation_history_profiling(messages[-3:])}

CUSTOMER NAME: {name}

YOUR TASK:
Generate a natural, friendly greeting response for this customer. The customer's name was automatically
detected from their WhatsApp contact name, so greet them by name and respond to their message naturally.

IMPORTANT:
- Use their name naturally in the greeting (e.g., "Iya halo {name}", "Halo kak {name}")
- Respond to their actual message/question from the conversation history
- Be friendly and helpful
- This is NOT a profiling question - just a natural greeting and response
- After the greeting, if needed, naturally ask what they need help with
- Response should be natural like WhatsApp chat

RULES:
- Response HANYA dengan pesan yang akan dikirim (tanpa penjelasan tambahan)
- Natural seperti chat WhatsApp asli
- Gunakan emoji secara wajar
"""

    response = llm.invoke([SystemMessage(content=context_prompt)] + messages)
    return response.content


def format_conversation_history_profiling(messages: list) -> str:
    """Format conversation history untuk profiling context"""
    if not messages:
        return "No conversation history"

    formatted = []
    for msg in messages:
        role = "Customer" if msg.type == "human" else "Hana"
        content = msg.content[:150]  # Limit untuk profiling context
        formatted.append(f"{role}: {content}")

    return "\n".join(formatted)


def determine_next_question(profile: CustomerProfile, name_from_contact: bool = False, extra_metadata: dict = None) -> tuple[str, str]:
    """
    Tentukan field berikutnya yang perlu ditanya.
    Return (empty_question, field_name) - question akan di-generate oleh LLM di node level.

    Args:
        profile: Current customer profile
        name_from_contact: If True, name was auto-filled from contact_name and should be confirmed with greeting
        extra_metadata: Dict with extra metadata like 'needs_vehicle_clarification' and 'vehicle_matches'
    """
    logger.info(f"determine_next_question called - profile: {profile.model_dump()}, name_from_contact: {name_from_contact}, extra_metadata: {extra_metadata}")

    # Get extra metadata for vehicle clarification data
    extra = extra_metadata or {}
    needs_clarification = extra.get('needs_vehicle_clarification', False)
    vehicle_matches = extra.get('vehicle_matches', [])

    # Prioritas pertanyaan: name → domicile → vehicle → unit_qty
    # Vehicle is considered "filled" if user provided vehicle_alias (even if vehicle_id=-1)

    if not profile.name:
        logger.info("Next question: NAME")
        return "", "name"

    # If name was just filled from contact_name, return greeting instead of next question
    if name_from_contact:
        logger.info(f"Name just filled from contact_name: {profile.name} -> should greet first")
        return "", "greeting_with_name"

    if not profile.domicile:
        logger.info(f"Next question: DOMICILE (for {profile.name})")
        return "", "domicile"

    # Check if vehicle clarification is needed (multiple matches found)
    if needs_clarification and vehicle_matches:
        logger.info(f"Next question: VEHICLE_CLARIFICATION for {profile.vehicle_alias} - {len(vehicle_matches)} matches")
        # Pass matches as extra context
        return "", "vehicle_clarification"

    # Vehicle is optional - only ask if user hasn't provided any vehicle info at all
    # Skip if vehicle_alias exists (user already mentioned their vehicle)
    if not profile.vehicle_alias:
        logger.info(f"Next question: VEHICLE (for {profile.name} from {profile.domicile})")
        return "", "vehicle_id"

    if profile.unit_qty == 0:
        logger.info(f"Next question: UNIT_QTY (for {profile.name}, vehicle: {profile.vehicle_alias or 'kendaraan'})")
        return "", "unit_qty"

    logger.info("Profiling COMPLETE - all fields filled")
    return "", "complete"


async def create_lead_routing(customer_id: int, route_type: str, notes: Optional[str] = None):
    """Buat lead routing record saat customer complete profiling"""
    logger.info(f"create_lead_routing called - customer_id: {customer_id}, route_type: {route_type}")

    async with AsyncSessionLocal() as db:
        # Check apakah sudah ada routing pending untuk customer ini
        query = select(LeadRouting).where(
            (LeadRouting.customer_id == customer_id) &
            (LeadRouting.status == "pending")
        )
        result = await db.execute(query)
        existing = result.scalars().first()

        if existing:
            logger.info(f"Lead routing already EXISTS for customer {customer_id} - skipping creation")
            return

        routing = LeadRouting(
            customer_id=customer_id,
            route_type=route_type,
            status="pending",
            notes=notes
        )
        db.add(routing)
        await db.commit()

        logger.info(f"New lead routing CREATED for customer {customer_id} -> {route_type}")


async def node_greeting_and_profiling(state: AgentState):
    logger.info("=" * 50)
    logger.info("ENTER: node_greeting_and_profiling")

    messages = state['messages']
    identifier = get_user_identifier(state)
    contact_name = state.get('contact_name')

    logger.info(f"State - phone_number: {identifier.get('phone_number')}, lid_number: {identifier.get('lid_number')}, contact_name: {contact_name}")

    # 1. Ambil atau buat customer dari database
    customer = await get_or_create_customer(identifier, contact_name)
    customer_id = customer.id

    # 2. Build current profile dari database
    # For vehicle_alias, use vehicle_alias if available, otherwise fetch from VPS DB if vehicle_id > 0
    vehicle_alias = ''
    if customer and customer.vehicle_alias:
        # Use vehicle_alias as display name
        vehicle_alias = customer.vehicle_alias
    elif customer and customer.vehicle_id and customer.vehicle_id > 0:
        # Fetch from VPS DB
        from src.orin_ai_crm.core.agents.tools.vps_tools import get_vehicle_by_id
        vehicle_data = await get_vehicle_by_id(customer.vehicle_id)
        if vehicle_data:
            vehicle_alias = vehicle_data.get('name', '')

    current_profile = {
        'name': customer.name if customer and customer.name else '',
        'domicile': customer.domicile if customer and customer.domicile else '',
        'vehicle_id': customer.vehicle_id if customer and customer.vehicle_id is not None else -1,
        'vehicle_alias': vehicle_alias,
        'unit_qty': customer.unit_qty if customer and customer.unit_qty else 0,
        'is_b2b': customer.is_b2b if customer else False
    }
    logger.info(f"Current customer profile from DB: {current_profile}")

    # 3. Check if contact_name is a valid person name and customer doesn't have a name yet
    name_from_contact = False
    if not current_profile['name'] and contact_name and is_valid_person_name(contact_name):
        logger.info(f"Valid contact_name detected: '{contact_name}' - using as customer name")
        current_profile['name'] = contact_name.strip()
        name_from_contact = True

    # 4. Extract/update info dari pesan terakhir
    # Get vehicle_matches from previous clarification if exists (for context)
    previous_vehicle_matches = state.get('customer_data', {}).get('vehicle_matches', [])
    extracted_data, extra_metadata = await extract_customer_info(messages, current_profile, vehicle_matches=previous_vehicle_matches)

    # Helper function to merge CustomerProfile with existing customer_data and extra metadata
    def build_customer_data(profile: CustomerProfile, existing: dict = None, extra: dict = None) -> dict:
        """
        Build customer_data dict by:
        1. Starting with existing customer_data (if provided)
        2. Updating with fields from profile (only overwrites fields that exist in CustomerProfile)
        3. Merging extra metadata

        This preserves any additional fields in existing customer_data that aren't in CustomerProfile schema.
        """
        # Start with existing customer_data or empty dict
        data = existing.copy() if existing else {}
        # Update with profile fields (only overwrites fields defined in CustomerProfile)
        data.update(profile.model_dump())
        # Merge extra metadata (with lower priority than profile fields)
        if extra:
            data.update(extra)
        return data

    # 5. Update database dengan data baru/berubah
    await update_customer_profile(customer_id, extracted_data)

    # 6. Tentukan field berikutnya yang perlu ditanya
    _, next_field = determine_next_question(extracted_data, name_from_contact=name_from_contact, extra_metadata=extra_metadata)

    # 7. Tentukan response
    if next_field == "complete":
        # Profiling complete, buat lead routing record
        qty = extracted_data.unit_qty or 0
        is_b2b = extracted_data.is_b2b
        route_type = "SALES" if (qty >= 5 or is_b2b) else "ECOMMERCE"

        logger.info(f"Profiling COMPLETE - Route: {route_type}, Qty: {qty}, B2B: {is_b2b}")

        await create_lead_routing(
            customer_id=customer_id,
            route_type=route_type,
            notes=f"Profiling complete. Vehicle: {extracted_data.vehicle_alias or 'Unknown'} (ID: {extracted_data.vehicle_id}), Qty: {qty}, B2B: {is_b2b}"
        )

        logger.info(f"EXIT: node_greeting_and_profiling -> step=profiling_complete, route={route_type}")
        logger.info("=" * 50)

        return {
            "messages": [],
            "step": "profiling_complete",
            "customer_data": build_customer_data(extracted_data, state.get('customer_data', {})),
            "customer_id": customer_id
        }

    # 8. Handle case where name was just filled from contact_name - send greeting
    if next_field == "greeting_with_name":
        logger.info(f"Name filled from contact_name: {extracted_data.name} - generating greeting response")

        greeting = await generate_greeting_with_name(
            messages=messages,
            name=extracted_data.name
        )

        logger.info(f"Generated greeting: {greeting[:100]}...")
        logger.info(f"EXIT: node_greeting_and_profiling -> step=greeting")
        logger.info("=" * 50)

        return {
            "messages": [AIMessage(content=greeting)],
            "step": "greeting",
            "customer_data": build_customer_data(extracted_data, state.get('customer_data', {})),
            "customer_id": customer_id
        }

    # 8. Handle vehicle clarification - when multiple matches found
    if next_field == "vehicle_clarification":
        logger.info("Generating vehicle clarification question")

        clarification_question = await generate_vehicle_clarification_question(
            messages=messages,
            profile=extracted_data,
            vehicle_matches=extra_metadata.get('vehicle_matches', [])
        )

        # Clear the clarification flag after asking, so we don't ask again
        # Build customer_data with extra metadata, preserving existing state
        customer_data_to_save = build_customer_data(extracted_data, state.get('customer_data', {}), extra_metadata)
        # Update to mark that we asked for clarification
        if 'vehicle_matches' in customer_data_to_save:
            customer_data_to_save['asked_vehicle_clarification'] = True
            customer_data_to_save['needs_vehicle_clarification'] = False

        logger.info(f"Generated clarification question: {clarification_question[:100]}...")
        logger.info(f"EXIT: node_greeting_and_profiling -> step=profiling")
        logger.info("=" * 50)

        return {
            "messages": [AIMessage(content=clarification_question)],
            "step": "profiling",
            "customer_data": customer_data_to_save,
            "customer_id": customer_id
        }

    # 9. Masih tahap profiling, generate dan kirim pertanyaan berikutnya
    logger.info(f"Profiling IN PROGRESS - Next field: {next_field}")

    # Generate personalized question using LLM
    question = await generate_profiling_question(
        messages=messages,
        profile=extracted_data,
        field_name=next_field
    )

    logger.info(f"Generated question: {question[:100]}...")
    logger.info(f"EXIT: node_greeting_and_profiling -> step=profiling")
    logger.info("=" * 50)

    return {
        "messages": [AIMessage(content=question)],
        "step": "profiling",
        "customer_data": build_customer_data(extracted_data, state.get('customer_data', {})),
        "customer_id": customer_id
    }


def router_logic(state: AgentState) -> Literal[
    "intent_classification",
    "sales_node",
    "ecommerce_node",
    "node_greeting_and_profiling",
    "__end__"
]:
    """
    Enhanced router logic with intent classification support.
    """
    step = state.get("step", "")
    classified_intent = state.get("classified_intent")
    logger.info(f"router_logic called - step: {step}, classified_intent: {classified_intent}")

    # Special routes for intent classification results
    if step in ["greeting", "complaint", "support", "product_qa", "handle_reschedule", "no_meeting_found", "need_identifier", "order_guidance", "general"]:
        logger.info(f"Special step: {step} → END (message sent)")
        return "__end__"

    # Check if wants_meeting flag is set
    if state.get("wants_meeting"):
        logger.info("Wants meeting flag set → route to sales_node")
        return "sales_node"

    # Check if existing_meeting_id is set
    if state.get("existing_meeting_id"):
        logger.info("Has existing meeting ID → route to sales_node")
        return "sales_node"

    # When profiling is in progress, END the conversation (waiting for user response)
    if step == "profiling":
        logger.info("Profiling in progress → END (waiting for user response)")
        return "__end__"

    # When profiling is complete, route to appropriate node
    if step == "profiling_complete":
        data = state["customer_data"]
        qty = data.get("unit_qty", 0)
        is_b2b = data.get("is_b2b", False)

        if qty >= 5 or is_b2b:
            logger.info(f"Route -> sales_node (qty={qty}, b2b={is_b2b})")
            return "sales_node"

        logger.info(f"Route -> ecommerce_node (qty={qty}, b2b={is_b2b})")
        return "ecommerce_node"

    # Default fallback
    logger.info("No matching route → END")
    return "__end__"
