import os
import json
from typing import Literal, Optional
from datetime import timedelta, timezone, datetime
from datetime import datetime as dt
from sqlalchemy import select
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from src.orin_ai_crm.core.models.database import (
    AsyncSessionLocal, Customer, ChatSession, LeadRouting, CustomerAction,
    CustomerMeeting, ProductInquiry
)
from src.orin_ai_crm.core.models.schemas import AgentState, CustomerProfile
from src.orin_ai_crm.core.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Setup WIB timezone (UTC+7)
WIB = timezone(timedelta(hours=7))

# Setup LLM
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))

HANA_PERSONA = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak).

ATURAN PERCAKAPAN:
- Bertanya SATU per SATU seperti manusia asli, jangan langsung kirim form lengkap
- Jika user memberikan info baru, update dan konfirmasi dengan sopan
- Contoh: "Oh dari Jakarta ya kak, kakak bisa sebutin nama kakak?"
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

# Helper function untuk mendapatkan identifier user
def get_user_identifier(state: AgentState) -> dict:
    """Return dict dengan phone_number dan/atau lid_number"""
    return {
        "phone_number": state.get('phone_number'),
        "lid_number": state.get('lid_number')
    }

async def get_or_create_customer(identifier: dict, contact_name: Optional[str] = None) -> Customer:
    """
    Ambil customer berdasarkan phone_number ATAU lid_number.
    Priority: phone_number dulu, lalu lid_number.

    PENTING: Setiap phone_number/lid_number yang BERBEDA akan create customer BARU.
    """
    logger.info(f"get_or_create_customer called - identifier: {identifier}, contact_name: {contact_name}")

    async with AsyncSessionLocal() as db:
        # Cari berdasarkan prioritas: phone_number dulu, lalu lid_number
        customer = None

        # 1. Cari by phone_number dulu (prioritas utama)
        if identifier.get('phone_number'):
            query = select(Customer).where(
                Customer.phone_number == identifier.get('phone_number')
            )
            result = await db.execute(query)
            customer = result.scalars().first()
            logger.info(f"Search by phone_number '{identifier.get('phone_number')}': {'FOUND' if customer else 'NOT FOUND'}")

        # 2. Jika tidak ketemu by phone, cari by lid_number
        if not customer and identifier.get('lid_number'):
            query = select(Customer).where(
                Customer.lid_number == identifier.get('lid_number')
            )
            result = await db.execute(query)
            customer = result.scalars().first()
            logger.info(f"Search by lid_number '{identifier.get('lid_number')}': {'FOUND' if customer else 'NOT FOUND'}")

        if customer:
            logger.info(f"Customer FOUND - id: {customer.id}, phone: {customer.phone_number}, lid: {customer.lid_number}")

            # Update identifier yang kosong (link phone & lid)
            need_update = False
            if identifier.get('phone_number') and not customer.phone_number:
                customer.phone_number = identifier.get('phone_number')
                need_update = True
                logger.info(f"Updating customer.phone_number to: {identifier.get('phone_number')}")
            if identifier.get('lid_number') and not customer.lid_number:
                customer.lid_number = identifier.get('lid_number')
                need_update = True
                logger.info(f"Updating customer.lid_number to: {identifier.get('lid_number')}")
            # Update contact_name dari payload (latest)
            if contact_name and contact_name != customer.contact_name:
                customer.contact_name = contact_name
                need_update = True
                logger.info(f"Updating customer.contact_name to: {contact_name}")

            if need_update:
                await db.commit()
                await db.refresh(customer)

            # Detach dari session agar tidak terus terikat
            db.expunge(customer)
            return customer

        # Create new customer (tidak ketemu sama sekali)
        logger.info(f"Customer NOT FOUND - Creating NEW customer")
        customer = Customer(
            phone_number=identifier.get('phone_number'),
            lid_number=identifier.get('lid_number'),
            contact_name=contact_name
        )
        db.add(customer)
        await db.commit()
        await db.refresh(customer)

        logger.info(f"New customer CREATED - id: {customer.id}")

        # Detach dari session
        db.expunge(customer)
        return customer

async def update_customer_profile(customer_id: int, profile: CustomerProfile) -> bool:
    """
    Update customer data dari extracted profile.
    Return True jika ada data yang berubah.
    """
    logger.info(f"update_customer_profile called - customer_id: {customer_id}, profile: {profile.model_dump()}")

    async with AsyncSessionLocal() as db:
        # Ambil customer fresh dari session baru
        query = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(query)
        customer = result.scalars().first()

        if not customer:
            logger.warning(f"Customer NOT FOUND for id: {customer_id}")
            return False

        need_update = False
        updates = []

        # Update field yang kosong atau berubah
        if profile.name and profile.name != customer.name:
            customer.name = profile.name
            need_update = True
            updates.append(f"name={profile.name}")

        if profile.domicile and profile.domicile != customer.domicile:
            customer.domicile = profile.domicile
            need_update = True
            updates.append(f"domicile={profile.domicile}")

        if profile.vehicle_type and profile.vehicle_type != customer.vehicle_type:
            customer.vehicle_type = profile.vehicle_type
            need_update = True
            updates.append(f"vehicle_type={profile.vehicle_type}")

        if profile.unit_qty and profile.unit_qty != customer.unit_qty:
            customer.unit_qty = profile.unit_qty
            need_update = True
            updates.append(f"unit_qty={profile.unit_qty}")

        if profile.is_b2b != customer.is_b2b:
            customer.is_b2b = profile.is_b2b
            need_update = True
            updates.append(f"is_b2b={profile.is_b2b}")

        if need_update:
            logger.info(f"Updating customer {customer_id}: {', '.join(updates)}")
            await db.commit()
            await db.refresh(customer)
            return True

        logger.info(f"No updates needed for customer {customer_id}")
        return False

async def save_message_to_db(customer_id: Optional[int], role: str, content: str):
    """Simpan pesan ke database dengan customer_id"""
    async with AsyncSessionLocal() as db:
        new_msg = ChatSession(
            customer_id=customer_id,
            message_role=role,
            content=content
        )
        db.add(new_msg)
        await db.commit()

async def get_chat_history(customer_id: int):
    """Mengambil riwayat chat dari database"""
    async with AsyncSessionLocal() as db:
        query = (
            select(ChatSession)
            .where(ChatSession.customer_id == customer_id)
            .order_by(ChatSession.created_at.asc())
            .limit(20)
        )
        result = await db.execute(query)
        rows = result.scalars().all()

        # Detach semua objects dari session
        for row in rows:
            db.expunge(row)

        return rows

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

async def get_or_create_customer_action(
    customer_id: int,
    action_type: str
) -> Optional[CustomerAction]:
    """
    Get existing pending action atau create baru.
    Return customer action object.
    """
    logger.info(f"get_or_create_customer_action called - customer_id: {customer_id}, type: {action_type}")

    async with AsyncSessionLocal() as db:
        # Cek apakah sudah ada action dengan type yang sama dan status pending
        query = select(CustomerAction).where(
            (CustomerAction.customer_id == customer_id) &
            (CustomerAction.action_type == action_type) &
            (CustomerAction.status == "pending")
        ).order_by(CustomerAction.created_at.desc())

        result = await db.execute(query)
        action = result.scalars().first()

        if action:
            logger.info(f"Existing action FOUND - id: {action.id}, type: {action_type}, status: {action.status}")
            # Return existing action
            db.expunge(action)
            return action

        # Create new action
        logger.info(f"Creating NEW action - customer_id: {customer_id}, type: {action_type}")
        action = CustomerAction(
            customer_id=customer_id,
            action_type=action_type,
            status="pending"
        )
        db.add(action)
        await db.commit()
        await db.refresh(action)

        logger.info(f"New action CREATED - id: {action.id}")

        # Detach dari session
        db.expunge(action)
        return action

async def update_customer_action(
    action_id: int,
    action_data: Optional[dict] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None
):
    """Update existing customer action"""
    async with AsyncSessionLocal() as db:
        query = select(CustomerAction).where(CustomerAction.id == action_id)
        result = await db.execute(query)
        action = result.scalars().first()

        if not action:
            return False

        if action_data:
            action.action_data = json.dumps(action_data)
        if status:
            action.status = status
        if notes:
            action.notes = notes

        await db.commit()
        return True

# Meeting Booking Tools
class MeetingInfo(BaseModel):
    """Extract meeting information dari chat"""
    has_meeting_agreement: bool = Field(description="True jika user sudah sepakat untuk booking meeting")
    wants_reschedule: bool = Field(default=False, description="True jika user ingin reschedule meeting yang sudah ada")
    meeting_date: Optional[str] = Field(default=None, description="Tanggal meeting dalam format DD/MM/YYYY atau natural seperti 'besok', 'Senin depan'")
    meeting_time: Optional[str] = Field(default=None, description="Jam meeting dalam format HH:MM atau natural seperti 'jam 2 siang', 'pagi', 'sore'")
    meeting_format: Optional[str] = Field(default="online", description="Format meeting: online, offline, atau belum ditentukan")
    notes: Optional[str] = Field(default=None, description="Catatan tambahan dari user")

async def get_pending_meeting(customer_id: int) -> Optional[CustomerMeeting]:
    """Get pending meeting untuk customer"""
    async with AsyncSessionLocal() as db:
        query = select(CustomerMeeting).where(
            (CustomerMeeting.customer_id == customer_id) &
            (CustomerMeeting.status.in_(["pending", "confirmed"]))
        ).order_by(CustomerMeeting.created_at.desc())

        result = await db.execute(query)
        meeting = result.scalars().first()

        if meeting:
            db.expunge(meeting)
            return meeting
        return None

async def create_meeting(
    customer_id: int,
    meeting_date: str,
    meeting_time: str,
    meeting_format: str = "online"
) -> CustomerMeeting:
    """Create new meeting record"""
    async with AsyncSessionLocal() as db:
        meeting = CustomerMeeting(
            customer_id=customer_id,
            meeting_datetime=None,  # Will be parsed and set
            meeting_format=meeting_format,
            status="pending",
            notes=f"Date: {meeting_date}, Time: {meeting_time}"
        )
        db.add(meeting)
        await db.commit()
        await db.refresh(meeting)
        db.expunge(meeting)
        return meeting

async def update_meeting(
    meeting_id: int,
    meeting_date: Optional[str] = None,
    meeting_time: Optional[str] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None
) -> bool:
    """Update existing meeting"""
    async with AsyncSessionLocal() as db:
        query = select(CustomerMeeting).where(CustomerMeeting.id == meeting_id)
        result = await db.execute(query)
        meeting = result.scalars().first()

        if not meeting:
            return False

        if notes:
            meeting.notes = notes
        if status:
            meeting.status = status

        await db.commit()
        return True

def extract_meeting_info(messages: list, customer_name: str, has_existing_meeting: bool = False) -> MeetingInfo:
    """
    Extract meeting info dari pesan user.
    Check apakah user sudah sepakat booking meeting dan extract tanggal/jam.
    Jika ada existing meeting, detect apakah user ingin reschedule.
    """
    logger.info(f"extract_meeting_info called for {customer_name}, has_existing_meeting: {has_existing_meeting}")

    existing_context = ""
    if has_existing_meeting:
        existing_context = "\nCustomer sudah punya meeting yang di-book. Detect apakah customer ingin:\n1. Reschedule (ganti jadwal)\n2. Confirm meeting\n3. Complain/tanya lain"

    system_prompt = f"""Extract informasi meeting dari percakapan dengan customer {customer_name}.{existing_context}

Check apakah:
1. Customer sudah SEPAKAT untuk booking meeting (bukan hanya tanya, tapi sudah fix)
2. Tanggal dan jam yang disepakati
3. Format meeting (online/offline)
4. Apakah customer ingin reschedule (jika has_existing_meeting=True)

Contoh agreement:
- "Boleh, booking meeting besok jam 2" → has_meeting_agreement: True
- "Oke, Senin depan jam 10 pagi" → has_meeting_agreement: True
- "Besok jam 2 siang" → has_meeting_agreement: True
- "Bisa gak jadwalnya diulang?" → has_meeting_agreement: False (masih negosiasi)

Contoh reschedule:
- "Saya mau ganti jadwal" → wants_reschedule: True
- "Besok tidak bisa, bisa diganti lusa?" → wants_reschedule: True, has_meeting_agreement: True (baru jadwal)

Return format:
- meeting_date: dalam format YYYY-MM-DD jika jelas, atau natural seperti "besok", "Senin depan"
- meeting_time: dalam format HH:MM jika jelas, atau natural seperti "jam 2 siang", "pagi", "sore"
- Jika time tidak spesifik (pagi/siang), set meeting_time to natural text agar AI bisa follow-up"""

    extractor_llm = llm.with_structured_output(MeetingInfo)
    result = extractor_llm.invoke([SystemMessage(content=system_prompt)] + messages)

    logger.info(f"extract_meeting_info result: agreement={result.has_meeting_agreement}, wants_reschedule={result.wants_reschedule}, date={result.meeting_date}, time={result.meeting_time}")
    return result

async def book_or_update_meeting(
    customer_id: int,
    meeting_info: MeetingInfo,
    existing_meeting: Optional[CustomerMeeting] = None
) -> dict:
    """
    Book new meeting atau update existing meeting.
    Return dict dengan status dan formatted meeting info.
    """
    logger.info(f"book_or_update_meeting called - customer_id: {customer_id}, existing_meeting: {existing_meeting.id if existing_meeting else None}")

    meeting_date = meeting_info.meeting_date
    meeting_time = meeting_info.meeting_time
    meeting_format = meeting_info.meeting_format

    # Check if time is specific enough
    needs_clarification = False
    clarification_msg = ""

    # Check apakah time perlu clarification (pagi/siang/sore tidak spesifik)
    vague_times = ["pagi", "siang", "sore", "malam", "morning", "afternoon", "evening"]
    if meeting_time and any(vt in meeting_time.lower() for vt in vague_times):
        needs_clarification = True
        clarification_msg = "\n\nKira-kira lebih spesifik jam berapa kak? Misalnya jam 9 pagi atau jam 2 siang?"

    if existing_meeting and meeting_info.wants_reschedule:
        # Reschedule existing meeting
        logger.info(f"Rescheduling meeting {existing_meeting.id}")
        await update_meeting(
            meeting_id=existing_meeting.id,
            meeting_date=meeting_date,
            meeting_time=meeting_time,
            status="rescheduled",
            notes=f"Rescheduled to: {meeting_date}, {meeting_time}. Original: {existing_meeting.notes}"
        )
        meeting_id = existing_meeting.id
        status = "rescheduled"
    elif existing_meeting:
        # Update existing meeting confirmation
        logger.info(f"Confirming existing meeting {existing_meeting.id}")
        await update_meeting(
            meeting_id=existing_meeting.id,
            status="confirmed",
            notes=f"Confirmed: {meeting_date}, {meeting_time}. {meeting_info.notes or ''}"
        )
        meeting_id = existing_meeting.id
        status = "confirmed"
    else:
        # Create new meeting
        logger.info(f"Creating new meeting for customer {customer_id}")
        meeting = await create_meeting(
            customer_id=customer_id,
            meeting_date=meeting_date,
            meeting_time=meeting_time,
            meeting_format=meeting_format
        )
        meeting_id = meeting.id
        status = "pending"

    logger.info(f"Meeting processed - id: {meeting_id}, status: {status}")

    # Format untuk response ke customer
    formatted_response = {
        "date": meeting_date,
        "time": meeting_time,
        "format": meeting_format,
        "needs_clarification": needs_clarification,
        "clarification_msg": clarification_msg
    }

    return formatted_response

# Product Inquiry Tools
class ProductInfo(BaseModel):
    """Extract product information dari chat"""
    product_type: Optional[str] = Field(default=None, description="Tipe produk: TANAM atau INSTAN")
    vehicle_type: Optional[str] = Field(default=None, description="Jenis kendaraan")
    unit_qty: Optional[int] = Field(default=0, description="Jumlah unit")

async def get_pending_inquiry(customer_id: int) -> Optional[ProductInquiry]:
    """Get pending product inquiry untuk customer"""
    async with AsyncSessionLocal() as db:
        query = select(ProductInquiry).where(
            (ProductInquiry.customer_id == customer_id) &
            (ProductInquiry.status == "pending")
        ).order_by(ProductInquiry.created_at.desc())

        result = await db.execute(query)
        inquiry = result.scalars().first()

        if inquiry:
            db.expunge(inquiry)
            return inquiry
        return None

async def create_product_inquiry(
    customer_id: int,
    product_type: str,
    vehicle_type: str,
    unit_qty: int
) -> ProductInquiry:
    """Create new product inquiry"""
    async with AsyncSessionLocal() as db:
        inquiry = ProductInquiry(
            customer_id=customer_id,
            product_type=product_type,
            vehicle_type=vehicle_type,
            unit_qty=unit_qty,
            status="pending"
        )
        db.add(inquiry)
        await db.commit()
        await db.refresh(inquiry)
        db.expunge(inquiry)
        return inquiry

async def update_product_inquiry(
    inquiry_id: int,
    product_type: Optional[str] = None,
    ecommerce_link: Optional[str] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None
) -> bool:
    """Update existing product inquiry"""
    async with AsyncSessionLocal() as db:
        query = select(ProductInquiry).where(ProductInquiry.id == inquiry_id)
        result = await db.execute(query)
        inquiry = result.scalars().first()

        if not inquiry:
            return False

        if product_type:
            inquiry.product_type = product_type
        if ecommerce_link:
            inquiry.ecommerce_link = ecommerce_link
        if status:
            inquiry.status = status
        if notes:
            inquiry.notes = notes

        await db.commit()
        return True

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
        question = "Halo kak, terima kasih sudah menghubungi ORIN GPS Tracker! Salam kenal, saya Hana 😊\n\nBoleh kakak sebutin nama kakak?"
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

async def node_sales(state: AgentState):
    logger.info("=" * 50)
    logger.info("ENTER: node_sales")

    messages = state['messages']
    data = state['customer_data']
    customer_id = state.get('customer_id')

    # Gunakan natural vehicle type untuk response
    natural_vehicle = get_natural_vehicle_type(data.get('vehicle_type', ''))
    customer_name = data.get('name', 'Kak')

    logger.info(f"Customer: {customer_name}, vehicle: {natural_vehicle}, qty: {data.get('unit_qty')}, b2b: {data.get('is_b2b')}")

    # 1. Check existing meeting
    existing_meeting = await get_pending_meeting(customer_id)
    has_existing = existing_meeting is not None
    logger.info(f"Existing meeting: {has_existing}, id={existing_meeting.id if existing_meeting else 'N/A'}")

    # 2. Cek apakah user sudah sepakat booking meeting atau ingin reschedule
    meeting_info = extract_meeting_info(messages, customer_name, has_existing)

    # 3. Handle reschedule request
    if meeting_info.wants_reschedule and existing_meeting:
        logger.info("Customer wants to RESCHEDULE meeting")

        if meeting_info.has_meeting_agreement:
            # Customer sepakat dengan jadwal baru
            meeting_details = await book_or_update_meeting(
                customer_id=customer_id,
                meeting_info=meeting_info,
                existing_meeting=existing_meeting
            )

            confirm_message = f"""Siap kak {customer_name}! 👍

Meeting sudah Hana update:
📅 Tanggal: {meeting_details['date']}
⏰ Jam: {meeting_details['time']}
📍 Format: {meeting_details['format'].title()}

{meeting_details.get('clarification_msg', '')}

Tim sales kami akan menghubungi kakak sesuai jadwal baru tersebut. Sampai jumpa di meeting ya kak! 🙏"""

            logger.info(f"EXIT: node_sales -> Meeting rescheduled")
            logger.info("=" * 50)

            return {
                "messages": [AIMessage(content=confirm_message)],
                "route": "SALES",
                "customer_id": customer_id
            }
        else:
            # Masih negosiasi jadwal baru
            prompt = f"""{HANA_PERSONA}

Customer: {customer_name} ingin mengganti jadwal meeting yang sudah ada.
Meeting lama: {existing_meeting.notes}

Tugas:
1. Acknowledge permintaan ganti jadwal
2. Tanyakan kapan waktu yang cocok untuk meeting baru (tanggal & jam yang spesifik)
3. Jika waktu tidak spesifik (pagi/siang/sore), tanya lebih detail: "Kira-kira jam berapa kak?"
4. Ramah dan membantu"""

            response = llm.invoke([SystemMessage(content=prompt)] + messages)

            logger.info(f"EXIT: node_sales -> Negotiating reschedule")
            logger.info("=" * 50)

            return {
                "messages": [AIMessage(content=response.content)],
                "route": "SALES",
                "customer_id": customer_id
            }

    # 4. Handle new meeting booking
    if meeting_info.has_meeting_agreement and not existing_meeting:
        logger.info("Meeting AGREED - booking new meeting")

        meeting_details = await book_or_update_meeting(
            customer_id=customer_id,
            meeting_info=meeting_info,
            existing_meeting=None
        )

        # Check if need clarification for time
        if meeting_details.get('needs_clarification'):
            confirm_message = f"""Siap kak {customer_name}! 👍

Meeting sudah Hana catat:
📅 Tanggal: {meeting_details['date']}
⏰ Jam: {meeting_details['time']}

{meeting_details['clarification_msg']}

Mohon info lebih spesifik ya kak, biar tim sales bisa persisp dengan jadwalnya."""

            logger.info(f"EXIT: node_sales -> Meeting booked, needs clarification")
            logger.info("=" * 50)

            return {
                "messages": [AIMessage(content=confirm_message)],
                "route": "SALES",
                "customer_id": customer_id
            }

        # Buat konfirmasi meeting
        confirm_message = f"""Siap kak {customer_name}! 👍

Meeting sudah Hana catat:
📅 Tanggal: {meeting_details['date']}
⏰ Jam: {meeting_details['time']}
📍 Format: {meeting_details['format'].title()}

Tim sales kami akan menghubungi kakak sesuai jadwal tersebut. Sampai jumpa di meeting ya kak! 🙏

Ada yang bisa Hana bantu sebelum meeting?"""

        logger.info(f"EXIT: node_sales -> Meeting confirmed, route=SALES")
        logger.info("=" * 50)

        return {
            "messages": [AIMessage(content=confirm_message)],
            "route": "SALES",
            "customer_id": customer_id
        }

    # 5. Meeting sudah ada, customer menghubungi lagi (bukan reschedule)
    if existing_meeting and not meeting_info.wants_reschedule:
        logger.info(f"Existing meeting found, handling other inquiry")

        meeting_info_str = f"📅 Tanggal: {existing_meeting.notes}"
        prompt = f"""{HANA_PERSONA}

Customer: {customer_name} sudah punya meeting yang di-book.
Meeting: {meeting_info_str}

Customer sekarang chat lagi (bukan untuk ganti jadwal).

Tugas:
1. Sapa dengan nama mereka
2. Remind meeting mereka yang sudah di-book dengan singkat: "Meeting kakak sudah Hana catat ya untuk [tanggal/jam]"
3. Tanya apakah ada yang bisa dibantu sebelum meeting
4. Jangan buat meeting baru
5. Ramah dan membantu"""

        response = llm.invoke([SystemMessage(content=prompt)] + messages)

        logger.info(f"EXIT: node_sales -> Existing meeting reminder")
        logger.info("=" * 50)

        return {
            "messages": [AIMessage(content=response.content)],
            "route": "SALES",
            "customer_id": customer_id
        }

    # 6. Belum sepakat, lanjutkan negosiasi meeting baru
    logger.info("Meeting NOT agreed - continuing negotiation")

    prompt = f"""{HANA_PERSONA}

User ini masuk kategori SALES (B2B atau butuh >= 5 unit).
Data customer:
- Nama: {customer_name}
- Domisili: {data.get('domicile')}
- Kendaraan: {natural_vehicle} (original: {data.get('vehicle_type')})
- Jumlah unit: {data.get('unit_qty')}
- B2B: {data.get('is_b2b')}

Tugas:
1. Sapa dengan nama mereka
2. Konfirmasi kebutuhan mereka
3. Tawarkan Meeting Online dengan tim sales untuk penawaran khusus
4. Tanyakan kapan waktu yang cocok untuk meeting (tanggal & jam yang SPESIFIK)
5. Jika customer menyebut "pagi", "siang", atau "sore", tanya jam berapa: "Kira-kira jam berapa kak?"
6. JANGAN gunakan placeholder [Link Booking Meeting]
7. Focus untuk dapatkan kesepakatan jadwal meeting"""

    response = llm.invoke([SystemMessage(content=prompt)] + messages)

    logger.info(f"AI response generated: {response.content[:100]}...")
    logger.info(f"EXIT: node_sales -> Negotiating, route=SALES")
    logger.info("=" * 50)

    return {
        "messages": [AIMessage(content=response.content)],
        "route": "SALES",
        "customer_id": customer_id
    }

async def node_ecommerce(state: AgentState):
    logger.info("=" * 50)
    logger.info("ENTER: node_ecommerce")

    messages = state['messages']
    data = state['customer_data']
    customer_id = state.get('customer_id')

    # Gunakan natural vehicle type untuk response
    natural_vehicle = get_natural_vehicle_type(data.get('vehicle_type', ''))
    customer_name = data.get('name', 'Kak')

    logger.info(f"Customer: {customer_name}, vehicle: {natural_vehicle}, qty: {data.get('unit_qty')}")

    # 1. Check existing inquiry
    existing_inquiry = await get_pending_inquiry(customer_id)
    has_existing = existing_inquiry is not None
    logger.info(f"Existing inquiry: {has_existing}, id={existing_inquiry.id if existing_inquiry else 'N/A'}")

    # 2. Extract product type dari conversation
    product_info = extract_product_type(messages, data)
    logger.info(f"Extracted product type: {product_info.product_type}, vehicle: {product_info.vehicle_type}, qty: {product_info.unit_qty}")

    # 3. Determine response based on context
    if existing_inquiry:
        # Already have inquiry, check if customer asking about product again
        logger.info("Existing inquiry found - providing product info")

        prompt = f"""{HANA_PERSONA}

Customer: {customer_name} sudah pernah tanya produk dan sudah Hana berikan rekomendasi.
Inquiry lama:
- Product Type: {existing_inquiry.product_type}
- Vehicle: {existing_inquiry.vehicle_type}
- Qty: {existing_inquiry.unit_qty}
- Link: {existing_inquiry.ecommerce_link or 'Belum diberikan'}

Customer sekarang chat lagi.

Tugas:
1. Sapa dengan nama mereka
2. Tanya apakah mereka ingin info tambahan atau ingin langsung order
3. Jika mereka tanya lagi tentang produk, berikan info singkat dan reminder link sudah diberikan
4. Ramah dan membantu
5. JANGAN buat inquiry baru"""

        response = llm.invoke([SystemMessage(content=prompt)] + messages)

        logger.info(f"EXIT: node_ecommerce -> Existing inquiry follow-up")
        logger.info("=" * 50)

        return {
            "messages": [AIMessage(content=response.content)],
            "route": "ECOMMERCE",
            "customer_id": customer_id
        }

    # 4. No existing inquiry, create new one with product recommendation
    logger.info("Creating new product inquiry")

    # Determine product type and generate link
    product_type = product_info.product_type or "TANAM"  # Default to TANAM
    vehicle = product_info.vehicle_type or data.get('vehicle_type', 'mobil')
    qty = product_info.unit_qty or data.get('unit_qty', 1)

    # Generate appropriate e-commerce link based on product type
    ecommerce_link = generate_ecommerce_link(product_type, vehicle, qty)
    logger.info(f"Generated e-commerce link: {ecommerce_link}")

    # Create product inquiry record
    inquiry = await create_product_inquiry(
        customer_id=customer_id,
        product_type=product_type,
        vehicle_type=vehicle,
        unit_qty=qty
    )

    # Update with ecommerce link
    await update_product_inquiry(
        inquiry_id=inquiry.id,
        ecommerce_link=ecommerce_link,
        status="link_sent"
    )

    # Generate response based on product type
    if product_type == "TANAM":
        product_desc = "OBU F & OBU V (Tipe TANAM - Tersembunyi, dipasang teknisi, bisa lacak + matikan mesin)"
    elif product_type == "INSTAN":
        product_desc = "OBU D, T1, atau T (Tipe INSTAN - Bisa pasang sendiri tinggal colok OBD, hanya lacak)"
    else:
        product_desc = f"{product_type}"

    confirm_message = f"""Siap kak {customer_name}! 👍

Berdasarkan kebutuhan {natural_vehicle} kakak ({qty} unit), Hana rekomendasikan:

📦 {product_desc}

{ecommerce_link}

Kakak bisa langsung order melalui link di atas ya. Kalau ada pertanyaan seputar produk atau butuh bantu pemesanan, bilang saja ke Hana! 😊"""

    logger.info(f"EXIT: node_ecommerce -> New inquiry created with link")
    logger.info("=" * 50)

    return {
        "messages": [AIMessage(content=confirm_message)],
        "route": "ECOMMERCE",
        "customer_id": customer_id
    }

def extract_product_type(messages: list, customer_data: dict) -> ProductInfo:
    """
    Extract product type (TANAM/INSTAN) dari conversation.
    """
    logger.info(f"extract_product_type called - customer_data: {customer_data}")

    system_prompt = f"""Extract product preference dari conversation.

Data customer:
- Vehicle: {customer_data.get('vehicle_type')}
- Unit Qty: {customer_data.get('unit_qty')}

Tipe produk:
1. TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin) - Lebih mahal tapi lebih lengkap
2. INSTAN: OBU D, T1, T (Colok OBD sendiri, hanya lacak) - Lebih murah, DIY installation

Extract:
- product_type: "TANAM" atau "INSTAN" (jika user tidak sebut, return null)
- vehicle_type: jenis kendaraan dari customer data atau conversation
- unit_qty: jumlah unit"""

    extractor_llm = llm.with_structured_output(ProductInfo)
    result = extractor_llm.invoke([SystemMessage(content=system_prompt)] + messages)

    logger.info(f"extract_product_type result: {result.model_dump()}")
    return result

def generate_ecommerce_link(product_type: str, vehicle_type: str, unit_qty: int) -> str:
    """
    Generate appropriate e-commerce link based on product type.
    Untuk production, ini bisa diupdate dengan link sebenarnya.
    """
    # Placeholder links - update dengan link Tokopedia/Shopee yang sebenarnya
    if product_type == "TANAM":
        return "🛒 Tokopedia: https://tokopedia.com/orin/gps-tanam\n🛒 Shopee: https://shopee.co.id/orin/gps-tanam"
    elif product_type == "INSTAN":
        return "🛒 Tokopedia: https://tokopedia.com/orin/gps-instan\n🛒 Shopee: https://shopee.co.id/orin/gps-instan"
    else:
        return "🛒 Tokopedia: https://tokopedia.com/orin\n🛒 Shopee: https://shopee.co.id/orin"
