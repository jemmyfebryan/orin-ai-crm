import os
from typing import Literal, Optional
from sqlalchemy import select, or_
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage

from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer, ChatSession
from src.orin_ai_crm.core.models.schemas import AgentState, CustomerProfile

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
- Contoh: "Oh dari Jakarta ya kak, kakak bisa sebutin nama kakak agar Hana bisa panggil dengan sopan?"
- Jangan meminta data lengkap dalam satu pesan
"""

# Helper function untuk mendapatkan identifier user
def get_user_identifier(state: AgentState) -> dict:
    """Return dict dengan phone_number dan/atau lid_number"""
    return {
        "phone_number": state.get('phone_number'),
        "lid_number": state.get('lid_number')
    }

async def save_message_to_db(identifier: dict, role: str, content: str):
    """Simpan pesan ke database dengan support phone_number atau lid_number"""
    async with AsyncSessionLocal() as db:
        new_msg = ChatSession(
            phone_number=identifier.get('phone_number'),
            lid_number=identifier.get('lid_number'),
            message_role=role,
            content=content
        )
        db.add(new_msg)
        await db.commit()

async def get_or_create_customer(identifier: dict) -> tuple[Optional[Customer], bool]:
    """
    Ambil customer berdasarkan phone_number atau lid_number.
    Return (customer, is_new)
    """
    async with AsyncSessionLocal() as db:
        # Cari berdasarkan phone_number atau lid_number
        query = select(Customer).where(
            or_(
                Customer.phone_number == identifier.get('phone_number'),
                Customer.lid_number == identifier.get('lid_number')
            )
        )
        result = await db.execute(query)
        customer = result.scalars().first()

        if customer:
            # Update identifier jika ada yang kosong
            if identifier.get('phone_number') and not customer.phone_number:
                customer.phone_number = identifier.get('phone_number')
            if identifier.get('lid_number') and not customer.lid_number:
                customer.lid_number = identifier.get('lid_number')
            await db.commit()
            return customer, False

        # Create new customer
        customer = Customer(
            phone_number=identifier.get('phone_number'),
            lid_number=identifier.get('lid_number'),
            contact_name=identifier.get('contact_name')
        )
        db.add(customer)
        await db.commit()
        await db.refresh(customer)
        return customer, True

def extract_customer_info(messages: list, current_profile: dict) -> CustomerProfile:
    """
    Extract/update customer info dari pesan terakhir.
    Structured output akan mengisi field yang kosong dan mengupdate field yang sudah ada.
    """
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
    return extractor_llm.invoke([SystemMessage(content=system_prompt)] + messages)

def determine_next_question(profile: CustomerProfile) -> tuple[str, str]:
    """
    Tentukan pertanyaan berikutnya berdasarkan profile yang sudah terisi.
    Return (question, field_name)
    """
    # Prioritas pertanyaan: name → domicile → vehicle_type → unit_qty

    if not profile.name:
        question = "Halo kak, terima kasih sudah menghubungi ORIN GPS Tracker! Salam kenal, saya Hana 😊\n\nBoleh kakak sebutin nama kakak agar Hana bisa panggil dengan sopan?"
        return question, "name"

    if not profile.domicile:
        question = f"Terima kasih kak {profile.name}! 👋\n\nBoleh tau kakak domisili di kota mana ya? Supaya Hana bisa bantu penawaran yang pas."
        return question, "domicile"

    if not profile.vehicle_type:
        question = f"Siap kak {profile.name} dari {profile.domicile}! 📍\n\nNah, yang ingin kakak pasang GPS-nya itu untuk apa ya?\n\n• Mobil pribadi\n• Motor\n• Alat berat\n• Armada operasional/kantor\n• Lainnya"
        return question, "vehicle_type"

    if profile.unit_qty == 0:
        vehicle = profile.vehicle_type.lower() if profile.vehicle_type else "kendaraan"
        question = f"Baik kak, untuk {vehicle} ya. 🚗\n\nKira-kira ada berapa unit yang ingin kakak pasang GPS?"
        return question, "unit_qty"

    return "", "complete"

async def node_greeting_and_profiling(state: AgentState):
    messages = state['messages']
    identifier = get_user_identifier(state)

    # 1. Ambil atau buat customer dari database
    customer, _ = await get_or_create_customer(identifier)

    # 2. Build current profile dari database
    current_profile = {
        'name': customer.name if customer and customer.name else '',
        'domicile': customer.domicile if customer and customer.domicile else '',
        'vehicle_type': customer.vehicle_type if customer and customer.vehicle_type else '',
        'unit_qty': customer.unit_qty if customer and customer.unit_qty else 0,
        'is_b2b': customer.is_b2b if customer else False
    }

    # 3. Extract/update info dari pesan terakhir
    extracted_data = extract_customer_info(messages, current_profile)

    # 4. Tentukan pertanyaan berikutnya
    question, next_field = determine_next_question(extracted_data)

    # 5. Update database jika ada data baru/berubah
    if customer:
        async with AsyncSessionLocal() as db:
            need_update = False

            # Update field yang berubah atau belum ada
            if extracted_data.name and extracted_data.name != customer.name:
                customer.name = extracted_data.name
                need_update = True
            if extracted_data.domicile and extracted_data.domicile != customer.domicile:
                customer.domicile = extracted_data.domicile
                need_update = True
            if extracted_data.vehicle_type and extracted_data.vehicle_type != customer.vehicle_type:
                customer.vehicle_type = extracted_data.vehicle_type
                need_update = True
            if extracted_data.unit_qty and extracted_data.unit_qty != customer.unit_qty:
                customer.unit_qty = extracted_data.unit_qty
                need_update = True
            if extracted_data.is_b2b != customer.is_b2b:
                customer.is_b2b = extracted_data.is_b2b
                need_update = True

            if need_update:
                await db.commit()

    # 6. Tentukan response
    if next_field == "complete":
        # Profiling complete, route ke sales/ecommerce
        return {
            "messages": [],
            "step": "profiling_complete",
            "customer_data": extracted_data.model_dump()
        }

    # Masih tahap profiling, kirim pertanyaan berikutnya
    return {
        "messages": [AIMessage(content=question)],
        "step": "profiling",
        "customer_data": extracted_data.model_dump()
    }

def router_logic(state: AgentState) -> Literal["sales_node", "ecommerce_node", "node_greeting_and_profiling"]:
    if state["step"] != "profiling_complete":
        return "node_greeting_and_profiling"

    data = state["customer_data"]
    qty = data.get("unit_qty", 0)
    is_b2b = data.get("is_b2b", False)

    if qty >= 5 or is_b2b:
        return "sales_node"
    return "ecommerce_node"

async def node_sales(state: AgentState):
    messages = state['messages']
    data = state['customer_data']

    prompt = f"""{HANA_PERSONA}

User ini masuk kategori SALES (B2B atau butuh >= 5 unit).
Data customer:
- Nama: {data.get('name')}
- Domisili: {data.get('domicile')}
- Kendaraan: {data.get('vehicle_type')}
- Jumlah unit: {data.get('unit_qty')}
- B2B: {data.get('is_b2b')}

Tugas:
1. Sapa dengan nama mereka
2. Konfirmasi kebutuhan mereka
3. Tawarkan Meeting Online dengan tim sales untuk penawaran khusus
4. Berikan instruksi booking meeting"""

    response = llm.invoke([SystemMessage(content=prompt)] + messages)
    return {"messages": [AIMessage(content=response.content)], "route": "SALES"}

async def node_ecommerce(state: AgentState):
    messages = state['messages']
    data = state['customer_data']

    prompt = f"""{HANA_PERSONA}

User ini masuk kategori E-COMMERCE (Pribadi/1-4 Unit).
Data customer:
- Nama: {data.get('name')}
- Domisili: {data.get('domicile')}
- Kendaraan: {data.get('vehicle_type')}
- Jumlah unit: {data.get('unit_qty')}

Tugas:
1. Sapa dengan nama mereka
2. Tanya apakah mereka butuh tipe TANAM (pasang teknisi, bisa matikan mesin) atau INSTAN (colok sendiri, hanya lacak)
3. Berikan rekomendasi produk yang cocok
4. Berikan link e-commerce yang relevan (Tokopedia/Shopee/Official Store)"""

    response = llm.invoke([SystemMessage(content=prompt)] + messages)
    return {"messages": [AIMessage(content=response.content)], "route": "ECOMMERCE"}
