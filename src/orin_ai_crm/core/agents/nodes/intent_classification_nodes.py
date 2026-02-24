"""
Intent Classification Node - Classify user intent at the start of conversation
"""

import os
from typing import Literal
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.models.database import AsyncSessionLocal
from src.orin_ai_crm.core.models.database import IntentClassification as IntentClassificationModel

logger = get_logger(__name__)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))


class IntentClassification(BaseModel):
    """User Intent Classification"""
    intent: Literal["greeting", "profiling", "product_inquiry", "meeting_request", "complaint", "support", "reschedule", "order", "general_question"] = Field(
        description="Intent utama user"
    )
    confidence: float = Field(
        description="Confidence score 0-1",
        ge=0.0,
        le=1.0
    )
    reasoning: str = Field(
        description="Alasan klasifikasi intent"
    )
    product_keywords: list[str] = Field(
        default=[],
        description="Keywords terkait produk yang disebutkan"
    )


def classify_user_intent(messages: list, customer_data: dict) -> IntentClassification:
    """
    Classify user intent dari conversation history.
    Ini membantu AI memutuskan alur percakapan apa yang harus diambil.
    """
    logger.info(f"classify_user_intent called - message_count: {len(messages)}, customer_data: {customer_data}")

    # Get last few messages for context
    recent_messages = messages[-5:] if len(messages) >= 5 else messages
    conversation = "\n".join([f"{msg.type}: {msg.content}" for msg in recent_messages])

    # Check profiling status
    has_name = bool(customer_data.get('name'))
    has_domicile = bool(customer_data.get('domicile'))
    has_vehicle = bool(customer_data.get('vehicle_type'))
    has_qty = customer_data.get('unit_qty', 0) > 0
    profiling_complete = all([has_name, has_domicile, has_vehicle, has_qty])

    system_prompt = f"""Kamu adalah Intent Classifier untuk Hana AI Agent dari ORIN GPS Tracker.
Tugasmu adalah mengklasifikasikan intent user dari percakapan.

CONVERSATION:
{conversation}

CUSTOMER DATA:
- Name: {customer_data.get('name', '-')}
- Domicile: {customer_data.get('domicile', '-')}
- Vehicle: {customer_data.get('vehicle_type', '-')}
- Unit Qty: {customer_data.get('unit_qty', 0)}
- Profiling Complete: {profiling_complete}

INTENT TYPES:
1. **greeting**: Salam, perkenalan, ucapan terima kasih
   Contoh: "Halo", "Selamat pagi", "Terima kasih"

2. **profiling**: Memberikan atau mengupdate data diri
   Contoh: "Saya Budi", "Domisili saya Jakarta", "Saya butuh 10 unit"

3. **product_inquiry**: Tanya tentang produk (fitur, harga, spesifikasi, dll)
   Contoh: "Produk apa saja?", "Berapa harganya?", "Apa bedanya TANAM vs INSTAN?"

4. **meeting_request**: Meminta atau setuju booking meeting
   Contoh: "Boleh booking meeting", "Meeting besok jam 2", "Saya mau konsultasi"

5. **complaint**: Keluhan atau komplain
   Contoh: "Produk error", "Tidak bisa tracking", "Tim sales tidak datang"

6. **support**: Butuh bantuan teknis atau support
   Contoh: "Cara installnya bagaimana?", "Aplikasi error", "Bagaimana cara pakai?"

7. **reschedule**: Minta ganti jadwal meeting
   Contoh: "Ganti jadwal meeting", "Reschedule besok", "Tidak bisa datang"

8. **order**: Ingin order atau beli produk
   Contoh: "Saya mau beli", "Order sekarang", "Cara pembayaran?"

9. **general_question**: Pertanyaan umum lainnya
   Contoh: "Lokasi office dimana?", "Berapa lama garansi?"

RULES:
- Jika profiling belum complete, prioritaskan **profiling** intent
- Jika user tanya produk setelah profiling complete, gunakan **product_inquiry**
- Jika user sepakat meeting (tanggal+jam), gunakan **meeting_request**
- Jika user minta ganti jadwal, gunakan **reschedule**
- Confidence 0.8-1.0 untuk intent yang jelas
- Confidence 0.5-0.7 untuk intent yang kurang jelas
- Berikan reasoning yang singkat dan jelas

Return format:
- intent: salah satu intent type di atas
- confidence: 0.0 - 1.0
- reasoning: penjelasan singkat
- product_keywords: list kata kunci terkait produk (jika ada)"""

    classifier_llm = llm.with_structured_output(IntentClassification)
    result = classifier_llm.invoke([SystemMessage(content=system_prompt)])

    logger.info(f"Intent classified: {result.intent} (confidence: {result.confidence})")
    logger.info(f"Reasoning: {result.reasoning}")
    logger.info(f"Product keywords: {result.product_keywords}")

    return result


async def save_intent_classification(
    customer_id: int,
    intent_result: IntentClassification,
    route: str,
    step: str,
    message_context: str
):
    """
    Save intent classification ke database untuk dataset training.
    Table ini dinamis dan dapat mengakomodasi intent type baru di masa depan.
    """
    try:
        async with AsyncSessionLocal() as db:
            classification = IntentClassificationModel(
                customer_id=customer_id,
                intent=intent_result.intent,
                confidence=intent_result.confidence,
                reasoning=intent_result.reasoning,
                product_keywords=intent_result.product_keywords,
                route=route,
                step=step,
                message_context=message_context[:1000] if message_context else None  # Limit to 1000 chars
            )
            db.add(classification)
            await db.commit()
            logger.info(f"Intent classification SAVED - id: {classification.id}, customer_id: {customer_id}, intent: {intent_result.intent}, route: {route}, step: {step}")
    except Exception as e:
        logger.error(f"Failed to save intent classification: {str(e)}")


async def _build_state_and_save(
    state: AgentState,
    intent_result: IntentClassification,
    messages: list = None,
    route: str = "UNASSIGNED",
    step: str = "profiling",
    **kwargs
):
    """
    Helper function untuk build state dict dan save intent classification ke database.
    Ini memastikan setiap intent classification tersimpan dengan route dan step yang benar.
    """
    customer_id = state.get('customer_id')
    customer_data = state.get('customer_data', {})
    last_user_msg = (messages or state['messages'])[-1].content if (messages or state['messages']) else ""

    # Build base state
    result_state = {
        "messages": messages or [],
        "step": step,
        "route": route,
        "customer_data": customer_data,
        "classified_intent": intent_result.intent,
        "intent_confidence": intent_result.confidence,
        **kwargs
    }

    # Save intent classification to database for dataset training
    if customer_id:
        await save_intent_classification(
            customer_id=customer_id,
            intent_result=intent_result,
            route=route,
            step=step,
            message_context=last_user_msg
        )

    return result_state


async def node_intent_classification(state: AgentState):
    """
    Intent Classification Node - Langkah pertama dalam workflow.
    Classify user intent dan return decision untuk next step.
    Setiap intent classification akan disimpan ke table intent_classifications untuk dataset.
    """
    logger.info("=" * 50)
    logger.info("ENTER: node_intent_classification")

    messages = state['messages']
    customer_data = state.get('customer_data', {})

    # Classify intent
    intent_result = classify_user_intent(messages, customer_data)

    # Tentukan next action berdasarkan intent
    intent = intent_result.intent
    confidence = intent_result.confidence

    # Low confidence → lanjut ke default flow (profiling)
    if confidence < 0.6:
        logger.info(f"Low confidence ({confidence}), continuing to default flow")
        logger.info(f"EXIT: node_intent_classification -> default flow")
        logger.info("=" * 50)
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            route="UNASSIGNED",
            step="profiling"
        )

    # High confidence → route based on intent
    if intent == "greeting":
        logger.info("Intent: GREETING → Send greeting message")
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            messages=[AIMessage(content="Halo kak! 👋 Saya Hana dari ORIN GPS Tracker. Ada yang bisa Hana bantu hari ini?")],
            route="UNASSIGNED",
            step="greeting"
        )

    elif intent == "profiling":
        logger.info("Intent: PROFILING → Continue profiling")
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            route="UNASSIGNED",
            step="profiling"
        )

    elif intent == "product_inquiry":
        # Check if profiling complete
        has_all_profile = all([
            customer_data.get('name'),
            customer_data.get('domicile'),
            customer_data.get('vehicle_type'),
            customer_data.get('unit_qty', 0) > 0
        ])

        if has_all_profile:
            logger.info("Intent: PRODUCT_INQUIRY (profiling complete) → Route to product Q&A")
            from src.orin_ai_crm.core.agents.tools.product_tools import answer_product_question

            # Get last user message
            last_user_msg = messages[-1].content if messages else ""

            # Answer product question using product database
            answer = await answer_product_question(
                question=last_user_msg,
                customer_vehicle=customer_data.get('vehicle_type'),
                customer_qty=customer_data.get('unit_qty')
            )

            return await _build_state_and_save(
                state=state,
                intent_result=intent_result,
                messages=[AIMessage(content=answer)],
                route="PRODUCT_INFO",
                step="product_qa"
            )
        else:
            logger.info("Intent: PRODUCT_INQUIRY (profiling incomplete) → Continue profiling first")
            return await _build_state_and_save(
                state=state,
                intent_result=intent_result,
                messages=[AIMessage(content="Tentang produk kami ada banyak ya kak! 🚗 Tapi boleh kenalan dulu dengan Hana? Kakak nama dari mana ya?")],
                route="UNASSIGNED",
                step="profiling"
            )

    elif intent == "meeting_request":
        logger.info("Intent: MEETING_REQUEST → Check if profiling complete")
        # Logic similar to product_inquiry
        has_all_profile = all([
            customer_data.get('name'),
            customer_data.get('domicile'),
            customer_data.get('vehicle_type'),
            customer_data.get('unit_qty', 0) > 0
        ])

        if has_all_profile:
            logger.info("Intent: MEETING_REQUEST (profiling complete) → Route to sales")
            # Pass to sales node with meeting intent
            return await _build_state_and_save(
                state=state,
                intent_result=intent_result,
                route="SALES",
                step="profiling_complete",
                wants_meeting=True
            )
        else:
            logger.info("Intent: MEETING_REQUEST (profiling incomplete) → Continue profiling")
            return await _build_state_and_save(
                state=state,
                intent_result=intent_result,
                messages=[AIMessage(content="Siap kak, Hana bantu aturkan meetingnya! 📅 Tapi boleh kenalan dulu ya? Nama kakak siapa dan domisili di mana?")],
                route="UNASSIGNED",
                step="profiling"
            )

    elif intent == "reschedule":
        logger.info("Intent: RESCHEDULE → Check for existing meeting")
        from src.orin_ai_crm.core.agents.tools.meeting_tools import get_pending_meeting

        customer_id = state.get('customer_id')

        if customer_id:
            existing_meeting = await get_pending_meeting(customer_id)

            if existing_meeting:
                logger.info(f"Existing meeting found: {existing_meeting.id} → Handle reschedule")
                # Pass to sales node with reschedule flag
                return await _build_state_and_save(
                    state=state,
                    intent_result=intent_result,
                    route="SALES",
                    step="handle_reschedule",
                    customer_id=customer_id,
                    existing_meeting_id=existing_meeting.id
                )
            else:
                logger.info("No existing meeting → Ask if they want to book new meeting")
                return await _build_state_and_save(
                    state=state,
                    intent_result=intent_result,
                    messages=[AIMessage(content="Kakak ingin reschedule meeting ya? Hmm, sepertinya Hana belum ada jadwal meeting untuk kakak sebelumnya. Kakak mau booking meeting baru? 📅")],
                    route="UNASSIGNED",
                    step="no_meeting_found",
                    customer_id=customer_id
                )
        else:
            logger.info("No customer_id → Ask for identification first")
            return await _build_state_and_save(
                state=state,
                intent_result=intent_result,
                messages=[AIMessage(content="Mohon share nomor WhatsApp atau ID kakak ya supaya Hana bisa cek jadwal meeting yang sudah ada 😊")],
                route="UNASSIGNED",
                step="need_identifier"
            )

    elif intent == "complaint":
        logger.info("Intent: COMPLAINT → Route to support")
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            messages=[AIMessage(content="Mohon maaf atas ketidaknyamanan kakak 🙏\n\nBisa ceritakan lebih detail masalahnya apa? Tim support kami akan segera membantu menyelesaikannya.")],
            route="SUPPORT",
            step="complaint"
        )

    elif intent == "support":
        logger.info("Intent: SUPPORT → Provide technical support")
        from src.orin_ai_crm.core.agents.tools.product_tools import answer_product_question

        last_user_msg = messages[-1].content if messages else ""

        # Answer support question
        answer = await answer_product_question(
            question=last_user_msg,
            customer_vehicle=customer_data.get('vehicle_type'),
            customer_qty=customer_data.get('unit_qty')
        )

        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            messages=[AIMessage(content=answer)],
            route="SUPPORT",
            step="support"
        )

    elif intent == "order":
        logger.info("Intent: ORDER → Guide to purchase")
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            messages=[AIMessage(content="Siap kak! Hana bantu proses pembeliannya 😊\n\nKakak mau beli produk yang tipe apa?\n\n• Tipe TANAM (pasang teknisi, bisa matikan mesin)\n• Tipe INSTAN (colok sendiri, tinggal colok OBD)\n\nUntuk pembelian, kakak bisa langsung ke:\n🛒 Tokopedia: https://tokopedia.com/orin\n🛒 Shopee: https://shopee.co.id/orin\n\nAtau kakak bisa konsultasi dulu dengan tim kami untuk memastikan produk yang tepat. Mau booking meeting? 📅")],
            route="ECOMMERCE",
            step="order_guidance"
        )

    else:  # general_question
        logger.info("Intent: GENERAL → Answer general question")
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            messages=[AIMessage(content="Terima kasih sudah menghubungi ORIN GPS Tracker! 😊\n\nUntuk pertanyaan tentang produk, fitur, atau pemesanan, kakak bisa tanya langsung ke Hana ya. Ada yang bisa Hana bantu?")],
            route="UNASSIGNED",
            step="general"
        )

    logger.info(f"EXIT: node_intent_classification -> intent: {intent}, confidence: {confidence}")
    logger.info("=" * 50)
