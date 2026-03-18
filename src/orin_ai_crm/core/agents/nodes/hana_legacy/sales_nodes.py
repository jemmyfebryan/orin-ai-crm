"""
Sales Nodes - Simplified B2B/High-Volume Sales Flow

This node handles customers who are:
- B2B customers (is_b2b == True)
- Large volume orders (unit_qty > 5)

Flow:
1. Greet customer and acknowledge B2B/high-volume context
2. Ask if they want a meeting with sales team
3. LLM classifies response as "wants meeting" or "doesn't want meeting"
4. If YES → Trigger human takeover (live agents handle meetings)
5. If NO → Return to orchestrator (routes to ecommerce_node for product recommendations)
"""

import os
from datetime import timedelta, timezone
from typing import Literal
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.models.schemas import AgentState

logger = get_logger(__name__)
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
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

CONTEX: Ini adalah pelanggan B2B atau high-volume (butuh banyak unit).
"""


# ============================================================================
# MEETING DESIRE CLASSIFICATION SCHEMA
# ============================================================================

class MeetingDesireClassification(BaseModel):
    """Classification of customer's desire for a meeting"""
    wants_meeting: bool = Field(
        description="True jika customer ingin meeting dengan tim sales (sepakat, mau, iya, ok, dll)"
    )
    confidence: float = Field(
        description="Confidence score 0.0 - 1.0 tentang keinginan meeting",
        ge=0.0,
        le=1.0
    )
    reasoning: str = Field(
        description="Alasan mengapa customer ingin/tidak ingin meeting"
    )


# ============================================================================
# MAIN SALES NODE
# ============================================================================

async def node_sales(state: AgentState):
    """
    Simplified Sales Node - For B2B/large volume customers.

    This node:
    1. Greets customer and acknowledges B2B/high-volume context
    2. Asks if they want a meeting with sales team
    3. Classifies response using LLM
    4. Routes accordingly:
       - If wants meeting → human_takeover (live agents handle meetings)
       - If no meeting → back to orchestrator → ecommerce_node

    Args:
        state: Current agent state (LangGraph standard)

    Returns:
        Updated state with:
        - human_takeover: bool (if customer wants meeting)
        - messages: AI response
        - route: "ORCHESTRATOR" (to continue flow)
    """
    logger.info("=" * 50)
    logger.info("ENTER: node_sales (Simplified)")

    messages = state.get('messages', [])
    data = state.get('customer_data', {})
    customer_id = state.get('customer_id')

    customer_name = data.get('name', 'Kak')
    unit_qty = data.get('unit_qty', 0)
    is_b2b = data.get('is_b2b', False)
    domicile = data.get('domicile', '')

    logger.info(f"Customer: {customer_name}, qty: {unit_qty}, b2b: {is_b2b}, domicile: {domicile}")

    # Check if this is first interaction (no previous messages from sales_node)
    # If first interaction, ask about meeting interest
    # If follow-up, classify their response

    # Get the latest human message
    latest_user_message = ""
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == "human":
            latest_user_message = msg.content
            break

    logger.info(f"Latest user message: {latest_user_message[:100] if latest_user_message else 'empty'}...")

    # Use LLM to classify if customer wants meeting
    classification = await _classify_meeting_desire(
        messages=messages,
        customer_name=customer_name,
        unit_qty=unit_qty,
        is_b2b=is_b2b,
        domicile=domicile
    )

    logger.info(f"Meeting desire classification: wants={classification.wants_meeting}, confidence={classification.confidence:.2f}")
    logger.info(f"Reasoning: {classification.reasoning}")

    # Route based on classification
    if classification.wants_meeting and classification.confidence >= 0.6:
        # Customer wants meeting → trigger human takeover
        logger.info("Customer WANTS meeting - triggering human takeover")

        takeover_message = f"""Baik kak {customer_name}! 👍

Tim sales kami akan segera membantu kakak untuk jadwal meeting penawaran khusus.

Mohon tunggu sebentar ya kak, tim kami akan menghubungi kakak segera! 🙏"""

        logger.info(f"EXIT: node_sales -> human_takeover")
        logger.info("=" * 50)

        return {
            "messages": [AIMessage(content=takeover_message)],
            "human_takeover": True,  # Trigger human takeover
            "customer_id": customer_id
        }
    else:
        # Customer doesn't want meeting → provide response and let orchestrator route to ecommerce
        logger.info("Customer does NOT want meeting - continuing to ecommerce")

        # Generate helpful response acknowledging their choice
        prompt = f"""{HANA_PERSONA}

Customer: {customer_name}
Context: B2B atau butuh {unit_qty}+ unit
Domisili: {domicile}
B2B: {is_b2b}

Customer sudah menyatakan tidak ingin meeting.

Tugas:
1. Acknowledge dengan sopan
2. Berikan informasi singkat bahwa kami akan bantu berikan info produk
3. Jangan tanya meeting lagi
4. Ramah dan membantu
5. Singkat saja (1-2 kalimat)

Contoh: "Baik kak {customer_name}, tidak masalah! Kakak bisa tanya-tanya dulu tentang produk GPS Tracker kami ya kak. 😊"
"""

        response = llm.invoke([SystemMessage(content=prompt)] + messages)

        logger.info(f"EXIT: node_sales -> orchestrator (will route to ecommerce)")
        logger.info("=" * 50)

        return {
            "messages": [AIMessage(content=response.content)],
            "route": "ORCHESTRATOR",  # Let orchestrator decide next agent (likely ecommerce)
            "customer_id": customer_id
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _classify_meeting_desire(
    messages: list,
    customer_name: str,
    unit_qty: int,
    is_b2b: bool,
    domicile: str
) -> MeetingDesireClassification:
    """
    Use LLM to classify if customer wants a meeting.

    This function analyzes the conversation history to determine if the customer
    has expressed interest in meeting with the sales team.

    Args:
        messages: Conversation history
        customer_name: Customer's name
        unit_qty: Number of units they want
        is_b2b: Whether this is a B2B customer
        domicile: Customer's domicile

    Returns:
        MeetingDesireClassification with wants_meeting bool and confidence score
    """
    from langchain_core.messages import HumanMessage

    # Get the latest human message for classification
    latest_user_message = ""
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == "human":
            latest_user_message = msg.content
            break

    # Build classification prompt
    classification_prompt = f"""You are a meeting desire classifier for ORIN GPS Tracker sales.

Customer Context:
- Name: {customer_name}
- B2B: {is_b2b}
- Unit Quantity: {unit_qty}
- Domicile: {domicile}

Latest User Message:
"{latest_user_message}"

Your task: Classify if the customer WANTS a meeting with sales team.

INDICATORS THAT CUSTOMER WANTS MEETING (wants_meeting = True):
- Explicit agreement: "iya", "ya", "boleh", "ok", "setuju", "silahkan", "mau"
- Positive interest: "boleh tanya", "coba", "contact", "hubungi"
- Asking about meeting: "kapan bisa", "jadwal meeting", "meeting kapan"
- Providing availability: "besok", "senin", "jam 2", "pagi", "sore"

INDICATORS THAT CUSTOMER DOES NOT WANT MEETING (wants_meeting = False):
- Explicit refusal: "tidak", "nggak", "ga", "gak mau", "tidak perlu"
- Wants product info only: "tanya produk", "harga", "spek", "info dulu"
- Not ready: "nanti dulu", "lagi pikir", "belum saatnya"
- Just browsing: "lihat-lihat", "cek dulu"

IMPORTANT:
- Consider context and conversation flow
- If customer is unsure or asking questions first, set wants_meeting = False
- If customer explicitly says YES or agrees to meeting, set wants_meeting = True
- Be confident in your classification (confidence should be 0.7+ for clear cases)
"""

    # Use structured output for classification
    structured_llm = llm.with_structured_output(MeetingDesireClassification)

    # Build messages for LLM
    messages_for_llm = [
        SystemMessage(content=classification_prompt),
        HumanMessage(content=latest_user_message or "Hello")
    ]

    # Invoke LLM and return classification
    classification = await structured_llm.ainvoke(messages_for_llm)

    logger.info(f"LLM classification result: wants_meeting={classification.wants_meeting}, confidence={classification.confidence:.2f}")

    return classification
