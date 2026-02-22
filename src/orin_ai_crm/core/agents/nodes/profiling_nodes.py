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


def determine_next_question(profile: CustomerProfile) -> tuple[str, str]:
    """
    Tentukan pertanyaan berikutnya berdasarkan profile yang sudah terisi.
    Return (question, field_name)
    """
    logger.info(f"determine_next_question called - profile: {profile.model_dump()}")

    # Prioritas pertanyaan: name → domicile → vehicle_type → unit_qty

    if not profile.name:
        question = "Halo kak, terima kasih sudah menghubungi ORIN GPS Tracker! Salam kenal, saya Hana 😊\n\nBoleh kakak sebutin nama kakak agar Hana bisa panggil dengan sopan?"
        logger.info("Next question: NAME")
        return question, "name"

    if not profile.domicile:
        question = f"Terima kasih kak {profile.name}! 👋\n\nBoleh tau kakak domisili di kota mana ya? Supaya Hana bisa bantu penawaran yang pas."
        logger.info(f"Next question: DOMICILE (for {profile.name})")
        return question, "domicile"

    if not profile.vehicle_type:
        question = f"Siap kak {profile.name} dari {profile.domicile}! 📍\n\nNah, yang ingin kakak pasang GPS-nya itu untuk apa ya?\n\n• Mobil pribadi\n• Motor\n• Alat berat\n• Armada operasional/kantor\n• Lainnya"
        logger.info(f"Next question: VEHICLE_TYPE (for {profile.name} from {profile.domicile})")
        return question, "vehicle_type"

    if profile.unit_qty == 0:
        # Gunakan natural vehicle type untuk response
        natural_vehicle = get_natural_vehicle_type(profile.vehicle_type)
        question = f"Baik kak, untuk {natural_vehicle} ya. 🚗\n\nKira-kira ada berapa unit yang ingin kakak pasang GPS?"
        logger.info(f"Next question: UNIT_QTY (for {profile.name}, vehicle: {profile.vehicle_type})")
        return question, "unit_qty"

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

    # 3. Extract/update info dari pesan terakhir
    extracted_data = extract_customer_info(messages, current_profile)

    # 4. Update database dengan data baru/berubah
    await update_customer_profile(customer_id, extracted_data)

    # 5. Tentukan pertanyaan berikutnya
    question, next_field = determine_next_question(extracted_data)

    # 6. Tentukan response
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

    # Masih tahap profiling, kirim pertanyaan berikutnya
    logger.info(f"Profiling IN PROGRESS - Next field: {next_field}")
    logger.info(f"Question to send: {question[:100]}...")
    logger.info(f"EXIT: node_greeting_and_profiling -> step=profiling")
    logger.info("=" * 50)

    return {
        "messages": [AIMessage(content=question)],
        "step": "profiling",
        "customer_data": extracted_data.model_dump(),
        "customer_id": customer_id
    }


def router_logic(state: AgentState) -> Literal["sales_node", "ecommerce_node", "node_greeting_and_profiling"]:
    from src.orin_ai_crm.core.agents.nodes.sales_nodes import node_sales
    from src.orin_ai_crm.core.agents.nodes.ecommerce_nodes import node_ecommerce

    step = state["step"]
    logger.info(f"router_logic called - step: {step}")

    if step != "profiling_complete":
        logger.info("Route -> node_greeting_and_profiling")
        return "node_greeting_and_profiling"

    data = state["customer_data"]
    qty = data.get("unit_qty", 0)
    is_b2b = data.get("is_b2b", False)

    if qty >= 5 or is_b2b:
        logger.info(f"Route -> sales_node (qty={qty}, b2b={is_b2b})")
        return "sales_node"

    logger.info(f"Route -> ecommerce_node (qty={qty}, b2b={is_b2b})")
    return "ecommerce_node"
