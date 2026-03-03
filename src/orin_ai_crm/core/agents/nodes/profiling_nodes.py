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

ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak).

ATURAN PERCAKAPAN:
- Bertanya SATU per SATU seperti manusia asli, jangan langsung kirim form lengkap
- Jika user memberikan info baru, update dan konfirmasi dengan sopan
- Contoh: "Oh dari Jakarta ya kak, kakak bisa sebutin nama kakak agar Hana bisa panggil dengan sopan?"
- Jangan meminta data lengkap dalam satu pesan
- Jika user menyebut "lainnya" atau "kantor" untuk jenis kendaraan, gunakan kata yang lebih natural seperti "kendaraan" atau "kebutuhan kantor"
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


def extract_customer_info(messages: list, current_profile: dict) -> CustomerProfile:
    """
    Extract/update customer info dari pesan terakhir.
    Structured output akan mengisi field yang kosong dan mengupdate field yang sudah ada.
    """
    logger.info(f"extract_customer_info called - current_profile: {current_profile}, message_count: {len(messages)}")

    system_prompt = f"""Extract informasi customer dari pesan. Update info yang sudah ada.
Jangan mengarang info jika tidak disebutkan.

Profile saat ini:
- Nama: {current_profile.get('name', '-')}
- Domisili: {current_profile.get('domicile', '-')}
- Jenis Kendaraan: {current_profile.get('vehicle_type', '-')}
- Jumlah Unit: {current_profile.get('unit_qty', 0)}
- B2B: {current_profile.get('is_b2b', False)}

Jika user mengoreksi info (contoh: "saya pindah ke Surabaya"), update field tersebut.
Jika user belum menyebutkan, biarkan kosong."""

    extractor_llm = llm.with_structured_output(CustomerProfile)
    result = extractor_llm.invoke([SystemMessage(content=system_prompt)] + messages)

    logger.info(f"extract_customer_info result: {result.model_dump()}")
    return result


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
- Kendaraan: {profile_data.get('vehicle_type') or 'Belum diketahui'}
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
        "vehicle_type": f"""- Gunakan nama & domisili customer: {profile_data.get('name') or 'Kak'} dari {profile_data.get('domicile') or 'kota kakak'}
- Tanyakan jenis kendaraan yang akan dipasang GPS
- Berikan opsi: Mobil pribadi, Motor, Alat berat, Armada operasional/kantor, Lainnya
- Natural dan ramah
""",
        "unit_qty": f"""- Gunakan nama customer: {profile_data.get('name') or 'Kak'}
- Gunakan natural vehicle type: {get_natural_vehicle_type(profile_data.get('vehicle_type', ''))}
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
- Tidak perlu opsi jawaban (kecuali vehicle_type)
- Jangan ulang info yang sudah diketahui"""

    response = llm.invoke([SystemMessage(content=context_prompt)] + messages)
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


def determine_next_question(profile: CustomerProfile, name_from_contact: bool = False) -> tuple[str, str]:
    """
    Tentukan field berikutnya yang perlu ditanya.
    Return (empty_question, field_name) - question akan di-generate oleh LLM di node level.

    Args:
        profile: Current customer profile
        name_from_contact: If True, name was auto-filled from contact_name and should be confirmed with greeting
    """
    logger.info(f"determine_next_question called - profile: {profile.model_dump()}, name_from_contact: {name_from_contact}")

    # Prioritas pertanyaan: name → domicile → vehicle_type → unit_qty

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

    if not profile.vehicle_type:
        logger.info(f"Next question: VEHICLE_TYPE (for {profile.name} from {profile.domicile})")
        return "", "vehicle_type"

    if profile.unit_qty == 0:
        logger.info(f"Next question: UNIT_QTY (for {profile.name}, vehicle: {profile.vehicle_type})")
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
    current_profile = {
        'name': customer.name if customer and customer.name else '',
        'domicile': customer.domicile if customer and customer.domicile else '',
        'vehicle_type': customer.vehicle_type if customer and customer.vehicle_type else '',
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
    extracted_data = extract_customer_info(messages, current_profile)

    # 5. Update database dengan data baru/berubah
    await update_customer_profile(customer_id, extracted_data)

    # 6. Tentukan field berikutnya yang perlu ditanya
    _, next_field = determine_next_question(extracted_data, name_from_contact=name_from_contact)

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
            notes=f"Profiling complete. Vehicle: {extracted_data.vehicle_type}, Qty: {qty}, B2B: {is_b2b}"
        )

        logger.info(f"EXIT: node_greeting_and_profiling -> step=profiling_complete, route={route_type}")
        logger.info("=" * 50)

        return {
            "messages": [],
            "step": "profiling_complete",
            "customer_data": extracted_data.model_dump(),
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
            "customer_data": extracted_data.model_dump(),
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
        "customer_data": extracted_data.model_dump(),
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
