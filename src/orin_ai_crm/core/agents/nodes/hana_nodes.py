import os
import json
from typing import Literal, Optional
from datetime import timedelta, timezone
from datetime import datetime as dt
from sqlalchemy import select
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from src.orin_ai_crm.core.models.database import (
    AsyncSessionLocal, Customer, ChatSession, LeadRouting, CustomerAction
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
    meeting_date: Optional[str] = Field(default=None, description="Tanggal meeting dalam format DD/MM/YYYY atau natural seperti 'besok', 'Senin depan'")
    meeting_time: Optional[str] = Field(default=None, description="Jam meeting dalam format HH:MM atau natural seperti 'jam 2 siang'")
    meeting_format: Optional[str] = Field(default="online", description="Format meeting: online, offline, atau belum ditentukan")
    notes: Optional[str] = Field(default=None, description="Catatan tambahan dari user")

def extract_meeting_info(messages: list, customer_name: str) -> MeetingInfo:
    """
    Extract meeting info dari pesan user.
    Check apakah user sudah sepakat booking meeting dan extract tanggal/jam.
    """
    logger.info(f"extract_meeting_info called for {customer_name}")

    system_prompt = f"""Extract informasi meeting dari percakapan dengan customer {customer_name}.

Check apakah:
1. Customer sudah SEPAKAT untuk booking meeting (bukan hanya tanya, tapi sudah fix)
2. Tanggal dan jam yang disepakati
3. Format meeting (online/offline)

Contoh agreement:
- "Boleh, booking meeting besok jam 2" → has_meeting_agreement: True
- "Oke, Senin depan jam 10 pagi" → has_meeting_agreement: True
- "Bisa gak jadwalnya diulang?" → has_meeting_agreement: False (masih negosiasi)

Return format:
- meeting_date: dalam format YYYY-MM-DD jika jelas, atau natural seperti "besok"
- meeting_time: dalam format HH:MM jika jelas, atau natural seperti "jam 2 siang"
"""

    extractor_llm = llm.with_structured_output(MeetingInfo)
    result = extractor_llm.invoke([SystemMessage(content=system_prompt)] + messages)

    logger.info(f"extract_meeting_info result: agreement={result.has_meeting_agreement}, date={result.meeting_date}, time={result.meeting_time}")
    return result

async def book_meeting(
    customer_id: int,
    action_id: int,
    meeting_info: MeetingInfo
) -> dict:
    """
    Update customer_action dengan meeting data yang sudah disepakati.
    Return dict dengan status dan formatted meeting info.
    """
    logger.info(f"book_meeting called - customer_id: {customer_id}, action_id: {action_id}")

    # Format meeting data untuk storage
    meeting_data = {
        "meeting_date": meeting_info.meeting_date,
        "meeting_time": meeting_info.meeting_time,
        "meeting_format": meeting_info.meeting_format,
        "booked_at": dt.now(WIB).isoformat()
    }

    logger.info(f"Meeting data: {meeting_data}")

    # Update action record
    await update_customer_action(
        action_id=action_id,
        action_data=meeting_data,
        status="booked",
        notes=f"Meeting booked. Date: {meeting_info.meeting_date}, Time: {meeting_info.meeting_time}. Notes: {meeting_info.notes or '-'}"
    )

    logger.info(f"Meeting BOOKED successfully - action_id: {action_id}")

    # Format untuk response ke customer
    formatted_response = {
        "date": meeting_info.meeting_date,
        "time": meeting_info.meeting_time,
        "format": meeting_info.meeting_format
    }

    return formatted_response

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

    # 1. Cek apakah user sudah sepakat booking meeting
    meeting_info = extract_meeting_info(messages, customer_name)

    # 2. Get or create action record
    action = None
    if customer_id:
        action = await get_or_create_customer_action(
            customer_id=customer_id,
            action_type="quote_requested"
        )
        logger.info(f"Customer action: id={action.id if action else 'N/A'}, type=quote_requested")

    # 3. Jika sudah sepakat meeting, book dan confirm
    if meeting_info.has_meeting_agreement and action:
        logger.info("Meeting AGREED - booking meeting now")

        meeting_details = await book_meeting(
            customer_id=customer_id,
            action_id=action.id,
            meeting_info=meeting_info
        )

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

    # 4. Belum sepakat, lanjutkan negosiasi
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
4. Tanyakan kapan waktu yang cocok untuk meeting (tanggal & jam)
5. JANGAN gunakan placeholder [Link Booking Meeting]
6. JANGAN buat action record baru - system sudah handle
7. Focus untuk dapatkan kesepakatan jadwal meeting"""

    response = llm.invoke([SystemMessage(content=prompt)] + messages)

    logger.info(f"AI response generated: {response.content[:100]}...")

    # Update notes dengan data terbaru
    if action:
        await update_customer_action(
            action_id=action.id,
            notes=f"Sales lead. Qty: {data.get('unit_qty')}, B2B: {data.get('is_b2b')}, Vehicle: {data.get('vehicle_type')}. Status: Negotiating meeting"
        )

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

    prompt = f"""{HANA_PERSONA}

User ini masuk kategori E-COMMERCE (Pribadi/1-4 Unit).
Data customer:
- Nama: {customer_name}
- Domisili: {data.get('domicile')}
- Kendaraan: {natural_vehicle} (original: {data.get('vehicle_type')})
- Jumlah unit: {data.get('unit_qty')}

Tugas:
1. Sapa dengan nama mereka
2. Tanya apakah mereka butuh tipe TANAM (pasang teknisi, bisa matikan mesin) atau INSTAN (colok sendiri, hanya lacak)
3. Berikan rekomendasi produk yang cocok
4. Berikan link e-commerce yang relevan (Tokopedia/Shopee/Official Store)
5. JANGAN buat action record baru - system sudah handle"""

    response = llm.invoke([SystemMessage(content=prompt)] + messages)

    logger.info(f"AI response generated: {response.content[:100]}...")

    # Get or create action record HANYA jika belum ada (cegah spam)
    if customer_id:
        action = await get_or_create_customer_action(
            customer_id=customer_id,
            action_type="product_inquiry"
        )
        logger.info(f"Customer action: id={action.id if action else 'N/A'}, type=product_inquiry")

        # Update notes dengan data terbaru
        if action:
            await update_customer_action(
                action_id=action.id,
                notes=f"Ecommerce inquiry. Vehicle: {data.get('vehicle_type')}, Qty: {data.get('unit_qty')}"
            )

    logger.info(f"EXIT: node_ecommerce -> route=ECOMMERCE")
    logger.info("=" * 50)

    return {
        "messages": [AIMessage(content=response.content)],
        "route": "ECOMMERCE",
        "customer_id": customer_id
    }
