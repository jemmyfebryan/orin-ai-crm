import os
from typing import Literal
from sqlalchemy import select
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage

from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer, ChatSession
from src.orin_ai_crm.core.models.schemas import AgentState, CustomerProfile

# Setup LLM
llm = ChatOpenAI(model="gpt-5.1-nano", api_key=os.getenv("OPENAI_API_KEY"))

HANA_PERSONA = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker. 
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak).
"""

async def save_message_to_db(phone: str, role: str, content: str):
    async with AsyncSessionLocal() as db:
        new_msg = ChatSession(phone_number=phone, message_role=role, content=content)
        db.add(new_msg)
        await db.commit()

async def node_greeting_and_profiling(state: AgentState):
    messages = state['messages']
    phone = state['phone_number']
    source = state['traffic_source']
    
    # Ekstraksi informasi dari pesan user
    extractor_llm = llm.with_structured_output(CustomerProfile)
    extracted_data = extractor_llm.invoke(messages)
    
    # Cek kelengkapan data
    if not extracted_data.name or not extracted_data.domicile or extracted_data.unit_qty == 0:
        if len(messages) <= 1: 
            if source == "freshchat":
                reply = "Halo kak, Salam kenal saya Hana dari ORIN GPS Tracker. Tim kami menginformasikan kalau kakak tertarik dengan produk ORIN. Boleh ceritakan sedikit kebutuhan atau kendala yang ingin disampaikan kak? :)"
            else:
                reply = "Halo kak, terima kasih sudah menghubungi ORIN GPS Tracker\nSalam kenal, saya Hana.\nSupaya informasinya lebih pas, mohon isi data singkat berikut:\n• Nama:\n• Domisili:\n• Yang ingin dilacak:\n• Jumlah unit:"
        else:
            prompt = f"{HANA_PERSONA}\nPelanggan belum melengkapi data. Tanya dengan ramah data yang kurang (Nama/Domisili/Kendaraan/Jumlah). Data saat ini: {extracted_data.model_dump()}"
            response = llm.invoke([SystemMessage(content=prompt)] + messages)
            reply = response.content
            
        return {"messages": [AIMessage(content=reply)], "step": "profiling", "customer_data": extracted_data.model_dump()}
    
    # Simpan ke DB jika data lengkap
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Customer).where(Customer.phone_number == phone))
        customer = result.scalars().first()
        if not customer:
            customer = Customer(
                phone_number=phone, name=extracted_data.name, domicile=extracted_data.domicile,
                vehicle_type=extracted_data.vehicle_type, unit_qty=extracted_data.unit_qty, is_b2b=extracted_data.is_b2b
            )
            db.add(customer)
            await db.commit()
            
    return {"step": "profiling_complete", "customer_data": extracted_data.model_dump()}

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
    prompt = f"{HANA_PERSONA}\nUser ini masuk kategori SALES (B2B atau butuh >= 5 unit). Konfirmasi kebutuhan mereka dan tawarkan Meeting Online."
    response = llm.invoke([SystemMessage(content=prompt)] + messages)
    return {"messages": [AIMessage(content=response.content)], "route": "SALES"}

async def node_ecommerce(state: AgentState):
    messages = state['messages']
    prompt = f"{HANA_PERSONA}\nUser ini masuk kategori E-COMMERCE (Pribadi/1-2 Unit). Tanya apakah butuh tipe TANAM atau INSTAN lalu berikan rekomendasi link e-commerce."
    response = llm.invoke([SystemMessage(content=prompt)] + messages)
    return {"messages": [AIMessage(content=response.content)], "route": "ECOMMERCE"}