"""
Ecommerce Nodes - E-commerce flow with product inquiry management using database products
"""

import os
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.tools import (
    get_pending_inquiry,
    create_product_inquiry,
    answer_product_question_from_db
)

logger = get_logger(__name__)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))

HANA_PERSONA = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PERCAKAPAN:
- Bertanya SATU per SATU seperti manusia asli, jangan langsung kirim form lengkap
- Jika user memberikan info baru, update dan konfirmasi dengan sopan
- Contoh: "Oh dari Jakarta ya kak, kakak bisa sebutin nama kakak agar Hana bisa panggil dengan sopan?"
- Jangan meminta data lengkap dalam satu pesan
- Jika user menyebut "lainnya" atau "kantor" untuk jenis kendaraan, gunakan kata yang lebih natural seperti "kendaraan" atau "kebutuhan kantor"

INFORMASI PRODUK:
Kamu memiliki akses ke database produk lengkap. Gunakan informasi tersebut untuk menjawab pertanyaan customer tentang:
- Fitur produk (lacak, matikan mesin, sadap suara, monitoring BBM, dll)
- Harga dan paket kuota
- Perbedaan tipe produk (yang perlu teknisi vs bisa pasang sendiri)
- Link e-commerce untuk pembelian
- Spesifikasi teknis dan garansi
"""


async def node_ecommerce(state: AgentState):
    """
    Ecommerce node that answers product questions and provides recommendations
    using database products instead of hardcoded values.
    """
    logger.info("=" * 50)
    logger.info("ENTER: node_ecommerce")

    messages = state['messages']
    data = state['customer_data']
    customer_id = state.get('customer_id')

    customer_name = data.get('name', 'Kak')
    logger.info(f"Customer: {customer_name}")

    # Get the last message from user
    last_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_message = msg.content
            break

    logger.info(f"Last message: {last_message[:100] if last_message else 'empty'}...")

    # Check if there's an existing inquiry for follow-up context
    existing_inquiry = await get_pending_inquiry(customer_id)
    has_existing = existing_inquiry is not None

    if has_existing:
        logger.info(f"Existing inquiry found: id={existing_inquiry.id}, status={existing_inquiry.status}")

    # Use the new database-powered Q&A function
    try:
        answer = await answer_product_question_from_db(
            question=last_message,
            customer_data=data
        )

        logger.info(f"Answer generated from database products")

        # If this looks like a new inquiry (customer asking about products first time),
        # create an inquiry record for tracking
        if not has_existing and _is_product_inquiry(last_message):
            logger.info("Creating new product inquiry record")

            inquiry = await create_product_inquiry(
                customer_id=customer_id,
                product_type="GENERAL",  # Will be updated based on actual interest
                vehicle_type=data.get('vehicle_alias') or data.get('vehicle_alias', 'kendaraan'),
                unit_qty=data.get('unit_qty', 1)
            )

            logger.info(f"Product inquiry created: id={inquiry.id}")

        logger.info(f"EXIT: node_ecommerce -> Answer provided")
        logger.info("=" * 50)

        return {
            "messages": [AIMessage(content=answer)],
            "route": "ECOMMERCE",
            "customer_id": customer_id
        }

    except Exception as e:
        logger.error(f"Error in node_ecommerce: {str(e)}", exc_info=True)

        # Fallback response
        fallback_message = f"""Maaf kak {customer_name}, terjadi kesalahan saat memproses pertanyaan kakak. 🙏

Mohon coba lagi atau hubungi tim CS kami ya kak! 😊"""

        return {
            "messages": [AIMessage(content=fallback_message)],
            "route": "ECOMMERCE",
            "customer_id": customer_id
        }


def _is_product_inquiry(message: str) -> bool:
    """
    Check if the message is a product inquiry (asking about products, prices, etc.)
    vs just a greeting or follow-up.
    """
    if not message:
        return False

    message_lower = message.lower()

    # Keywords that indicate product inquiry
    inquiry_keywords = [
        'harga', 'price', 'produk', 'product', 'gps', 'tracker',
        'pasang', 'install', 'beli', 'order', 'tanya', 'ask',
        'fitur', 'feature', 'spesifikasi', 'spec',
        'obu', 'mobil', 'motor', 'kendaraan', 'vehicle',
        'matikan mesin', 'sadap', 'lacak', 'track'
    ]

    return any(keyword in message_lower for keyword in inquiry_keywords)
