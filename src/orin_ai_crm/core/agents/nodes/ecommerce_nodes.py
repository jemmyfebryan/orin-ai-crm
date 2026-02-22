"""
Ecommerce Nodes - E-commerce flow with product inquiry management
"""

import os
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.nodes.profiling_nodes import get_natural_vehicle_type
from src.orin_ai_crm.core.agents.tools import (
    get_pending_inquiry,
    create_product_inquiry,
    update_product_inquiry,
    extract_product_type,
    generate_ecommerce_link,
    ProductInfo
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
    product_info: ProductInfo = extract_product_type(messages, data)
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
