"""
Intent Classification Node - Classify user intent at the start of conversation
"""

import os
import json
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.schemas import AgentState, IntentClassification
from src.orin_ai_crm.core.models.database import AsyncSessionLocal
from src.orin_ai_crm.core.models.database import IntentClassification as IntentClassificationModel

logger = get_logger(__name__)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))

HANA_PERSONA = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak).

ATURAN PERCAKAPAN:
- Jawab dengan personalized berdasarkan nama customer jika tersedia
- Gunakan konteks percakapan sebelumnya untuk memberikan response yang relevan
- Jangan ulang informasi yang sudah diketahui dari percakapan sebelumnya
- Jika user memberikan info baru, acknowledgments dengan sopan
- Singkat tapi ramah dan membantu"""

# 1. **greeting**: Salam, perkenalan, ucapan terima kasih
#    Contoh: "Halo", "Selamat pagi", "Terima kasih"

# 2. **profiling**: Memberikan atau mengupdate data diri
#    Contoh: "Saya Budi", "Domisili saya Jakarta", "Saya butuh 10 unit"

# 3. **product_inquiry**: Tanya tentang produk (fitur, harga, spesifikasi, dll)
#    Contoh: "Produk apa saja?", "Berapa harganya?", "Apa bedanya TANAM vs INSTAN?"

# 4. **meeting_request**: Meminta atau setuju booking meeting
#    Contoh: "Boleh booking meeting", "Meeting besok jam 2", "Saya mau konsultasi"

# 5. **complaint**: Keluhan atau komplain
#    Contoh: "Produk error", "Tidak bisa tracking", "Tim sales tidak datang"

# 6. **support**: Butuh bantuan teknis atau support
#    Contoh: "Cara installnya bagaimana?", "Aplikasi error", "Bagaimana cara pakai?"

# 7. **reschedule**: Minta ganti jadwal meeting
#    Contoh: "Ganti jadwal meeting", "Reschedule besok", "Tidak bisa datang"

# 8. **order**: Ingin order atau beli produk
#    Contoh: "Saya mau beli", "Order sekarang", "Cara pembayaran?"

# 9. **general_question**: Pertanyaan umum lainnya
#    Contoh: "Lokasi office dimana?", "Berapa lama garansi?"

def classify_user_intent(messages: list, customer_data: dict) -> IntentClassification:
    """
    Classify user intent dari conversation history.
    Ini membantu AI memutuskan alur percakapan apa yang harus diambil.
    """
    logger.info(f"classify_user_intent called - message_count: {len(messages)}, customer_data: {customer_data}")

    # Get last few messages for context
    recent_messages = messages[-5:] if len(messages) >= 5 else messages
    conversation = "\n".join([f"{msg.type}: {msg.content}" for msg in recent_messages])

    system_prompt = f"""Kamu adalah Intent Classifier untuk Hana AI Agent dari ORIN GPS Tracker.
Tugasmu adalah mengklasifikasikan intent user dari percakapan.

CONVERSATION:
{conversation}

CUSTOMER DATA:
- Name: {customer_data.get('name', '-')}
- Domicile: {customer_data.get('domicile', '-')}
- Vehicle: {customer_data.get('vehicle_alias', '-')}
- Unit Qty: {customer_data.get('unit_qty', 0)}

INTENT TYPES:
**greeting**: Salam, perkenalan, ucapan terima kasih
Contoh: "Halo", "Selamat pagi", "Terima kasih"

**profiling**: Memberikan atau mengupdate data diri
Contoh: "Saya Budi", "Domisili saya Jakarta", "Saya butuh 10 unit"

**product_inquiry**: Tanya tentang produk (fitur, harga, spesifikasi, dll)
Contoh: "Produk apa saja?", "Berapa harganya?", "Apa bedanya TANAM vs INSTAN?"

**complaint**: Keluhan atau komplain
Contoh: "Produk error", "Tidak bisa tracking", "Tim sales tidak datang"

**support**: Butuh bantuan teknis atau support
Contoh: "Cara installnya bagaimana?", "Aplikasi error", "Bagaimana cara pakai?"

**general_question**: Pertanyaan umum lainnya
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


async def classify_intent_level_with_llm(messages: list, customer_data: dict) -> dict:
    """
    Classify intent LEVEL using LLM (HIGH vs LOW).
    No rule-based matching!

    Returns: {
        "level": "HIGH" or "LOW",
        "reasoning": "explanation"
    }
    """
    logger.info("classify_intent_level_with_llm called")

    # Get last user message
    last_message = ""
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == 'human':
            last_message = msg.content
            break
        elif hasattr(msg, 'content'):
            last_message = msg.content
            break

    prompt = f"""Analyze this customer message and determine intent LEVEL.

Message: "{last_message}"

Customer Context: {json.dumps(customer_data, indent=2)}

Classify INTENT LEVEL:
- HIGH_INTENT: Customer is ready to transact, asking pricing, wants to buy, has urgency, specific product question, needs quick answer
  - Keywords: harga, price, beli, order, mau pasang, butuh, segera, promo, diskon, siap
  - Context: Asking specific product questions, ready to make decision

- LOW_INTENT: Customer is browsing, just asking questions, unclear intent, early stage, "tanya-tanya", wants information only
  - Keywords: tanya, info, cara kerja, pengen tahu, bisa jelasin, apa itu
  - Context: Early research, comparing options, not ready to buy

Consider:
- Message content and tone
- Urgency indicators
- Specific vs general questions
- Transaction readiness

Return JSON:
{{"level": "HIGH" or "LOW", "reasoning": "explanation"}}"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    try:
        result = json.loads(response.content.strip())
        level = result.get("level", "LOW")
        reasoning = result.get("reasoning", "")
        logger.info(f"Intent level: {level}, reasoning: {reasoning}")
        return result
    except Exception as e:
        logger.error(f"Failed to parse intent level: {e}, defaulting to LOW")
        return {"level": "LOW", "reasoning": "Parse error, default to LOW"}


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

    # Use provided messages if available, otherwise keep existing messages from state
    # IMPORTANT: Never clear messages - always preserve conversation history
    final_messages = messages if messages is not None else state.get('messages', [])
    last_user_msg = final_messages[-1].content if final_messages else ""

    # Build base state
    result_state = {
        "messages": final_messages,
        "step": step,
        "route": route,
        "customer_data": customer_data,
        "classified_intent": intent_result.intent,
        "intent_confidence": intent_result.confidence,
        "next_route": state.get("next_route"),  # Preserve next route if exists
        "send_form": state.get("send_form"),
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


async def generate_llm_response(
    messages: list,
    customer_data: dict,
    response_task: str,
    context_info: dict = None
) -> str:
    """
    Generate personalized LLM response based on conversation context.

    Args:
        messages: Conversation history
        customer_data: Known customer information
        response_task: What the response should accomplish
        context_info: Additional context for the specific task

    Returns:
        Generated response string
    """
    customer_name = customer_data.get('name') or customer_data.get('contact_name') or 'Kak'

    # Build context prompt
    context_prompt = f"""{HANA_PERSONA}

CONVERSATION HISTORY:
{format_conversation_history(messages[-5:])}

CUSTOMER INFO:
- Nama: {customer_data.get('name', 'Belum diketahui')}
- Domisili: {customer_data.get('domicile', 'Belum diketahui')}
- Kendaraan: {customer_data.get('vehicle_alias', 'Belum diketahui')}
- Jumlah unit: {customer_data.get('unit_qty', 0)}
"""

    if context_info:
        context_prompt += f"\nADDITIONAL CONTEXT:\n{context_info}\n"

    context_prompt += f"""
YOUR TASK:
{response_task}

Generate response yang:
1. Personalized dengan nama customer: {customer_name}
2. Menggunakan konteks percakapan di atas
3. Tidak mengulang informasi yang sudah diketahui
4. Singkat, ramah, dan natural (seperti chat WhatsApp asli)
5. Menggunakan emoji secara wajar

Response only dengan pesan yang akan dikirim ke customer."""

    response = llm.invoke([SystemMessage(content=context_prompt)] + messages)
    return response.content


def format_conversation_history(messages: list) -> str:
    """Format conversation history for prompt"""
    if not messages:
        return "No conversation history"

    formatted = []
    for msg in messages:
        role = "User" if msg.type == "human" else "Hana"
        content = msg.content[:200]  # Limit to 200 chars per message
        formatted.append(f"{role}: {content}")

    return "\n".join(formatted)


async def node_intent_classification(state: AgentState):
    """
    Intent Classification Node - Langkah pertama dalam workflow.
    TEMPORARY: All customers go through form (mandatory data collection).
    Interactive profiling is DISABLED.
    """
    logger.info("=" * 50)
    logger.info("ENTER: node_intent_classification")

    messages = state['messages']
    customer_data = state.get('customer_data', {})

    # Cek apakah user baru atau tidak
    is_onboarded = customer_data.get("is_onboarded")
    is_customer_data_filled = customer_data.get("is_filled")
    
    # Jika user baru, maka ikutkan send form
    send_form = True if (not is_onboarded) else False
    state["send_form"] = send_form
    logger.info(f"Set send_form to: {send_form}")
    
    # Classify intent
    intent_result = classify_user_intent(messages, customer_data)

    # Tentukan next action berdasarkan intent
    intent = intent_result.intent
    confidence = intent_result.confidence

    if confidence < 0.4:
        logger.info(f"Low confidence ({confidence}), routing to human takeover")
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            route="HUMAN_TAKEOVER",
            step="human_takeover",
        )


    if intent == "greeting":
        logger.info(f"Intent: GREETING")
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            route="GREETING",
            step="greeting",
        )

    elif intent == "profiling":
        logger.info("Intent: PROFILING")
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            route="PROFILING",
            step="profiling",
        )

    elif intent == "product_inquiry":
        logger.info(f"Intent: PRODUCT_INQUIRY")
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            route="PRODUCT_INQUIRY",
            step="show_form",
        )

    # elif intent == "meeting_request":
    #     logger.info("Intent: MEETING_REQUEST → Check if profiling complete")
    #     # Logic similar to product_inquiry
    #     has_all_profile = all([
    #         customer_data.get('name'),
    #         customer_data.get('domicile'),
    #         customer_data.get('vehicle_alias'),  # Has provided vehicle info
    #         customer_data.get('unit_qty', 0) > 0
    #     ])

    #     if has_all_profile:
    #         logger.info("Intent: MEETING_REQUEST (profiling complete) → Route to sales")
    #         # Pass to sales node with meeting intent
    #         return await _build_state_and_save(
    #             state=state,
    #             intent_result=intent_result,
    #             route="SALES",
    #             step="profiling_complete",
    #             wants_meeting=True
    #         )
    #     else:
    #         logger.info("Intent: MEETING_REQUEST (profiling incomplete) → Continue profiling")
    #         response = await generate_llm_response(
    #             messages=messages,
    #             customer_data=customer_data,
    #             response_task="User ingin booking meeting tapi profiling belum lengkap. Response dengan antusias bahwa Hana akan bantu aturkan meeting, tapi kenalan dulu ya (tanya data yang belum diketahui: nama/domisili/kendaraan/qty)."
    #         )
    #         return await _build_state_and_save(
    #             state=state,
    #             intent_result=intent_result,
    #             messages=[AIMessage(content=response)],
    #             route="UNASSIGNED",
    #             step="profiling"
    #         )

    # elif intent == "reschedule":
    #     logger.info("Intent: RESCHEDULE → Check for existing meeting")
    #     from src.orin_ai_crm.core.agents.tools.meeting_tools import get_pending_meeting

    #     customer_id = state.get('customer_id')

    #     if customer_id:
    #         existing_meeting = await get_pending_meeting(customer_id)

    #         if existing_meeting:
    #             logger.info(f"Existing meeting found: {existing_meeting.id} → Handle reschedule")
    #             # Pass to sales node with reschedule flag
    #             return await _build_state_and_save(
    #                 state=state,
    #                 intent_result=intent_result,
    #                 route="SALES",
    #                 step="handle_reschedule",
    #                 customer_id=customer_id,
    #                 existing_meeting_id=existing_meeting.id
    #             )
    #         else:
    #             logger.info("No existing meeting → Ask if they want to book new meeting")
    #             response = await generate_llm_response(
    #                 messages=messages,
    #                 customer_data=customer_data,
    #                 response_task="User ingin reschedule meeting tapi belum ada meeting yang di-book sebelumnya. Response dengan ramah, jelaskan bahwa belum ada jadwal meeting, dan tanya apakah mau booking meeting baru."
    #             )
    #             return await _build_state_and_save(
    #                 state=state,
    #                 intent_result=intent_result,
    #                 messages=[AIMessage(content=response)],
    #                 route="UNASSIGNED",
    #                 step="no_meeting_found",
    #                 customer_id=customer_id
    #             )
    #     else:
    #         logger.info("No customer_id → Ask for identification first")
    #         response = await generate_llm_response(
    #             messages=messages,
    #             customer_data=customer_data,
    #             response_task="User ingin reschedule meeting tapi tidak ada customer_id. Response minta user share nomor WhatsApp atau ID supaya Hana bisa cek jadwal meeting."
    #         )
    #         return await _build_state_and_save(
    #             state=state,
    #             intent_result=intent_result,
    #             messages=[AIMessage(content=response)],
    #             route="UNASSIGNED",
    #             step="need_identifier"
    #         )

    elif intent == "complaint":
        logger.info("Intent: COMPLAINT → Route to support")
        response = await generate_llm_response(
            messages=messages,
            customer_data=customer_data,
            response_task="User mengajukan keluhan/komplain. Response dengan empati, minta maaf atas ketidaknyamanan, dan tanya detail masalahnya agar tim support bisa membantu."
        )
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            messages=[AIMessage(content=response)],
            route="SUPPORT",
            step="complaint"
        )

    # elif intent == "support":
    #     logger.info("Intent: SUPPORT → Provide technical support")
    #     from src.orin_ai_crm.core.agents.tools.product_tools import answer_product_question

    #     last_user_msg = messages[-1].content if messages else ""

    #     # Answer support question
    #     answer = await answer_product_question(
    #         question=last_user_msg,
    #         customer_vehicle=customer_data.get('vehicle_alias') or customer_data.get('vehicle_alias'),
    #         customer_qty=customer_data.get('unit_qty')
    #     )

    #     return await _build_state_and_save(
    #         state=state,
    #         intent_result=intent_result,
    #         messages=[AIMessage(content=answer)],
    #         route="SUPPORT",
    #         step="support"
    #     )

#     elif intent == "order":
#         logger.info("Intent: ORDER → Guide to purchase")
#         response = await generate_llm_response(
#             messages=messages,
#             customer_data=customer_data,
#             response_task="""User ingin order/beli produk. Bantu proses pembelian dengan:
# 1. Tanya tipe produk yang diinginkan (TANAM vs INSTAN)
# 2. Jelaskan singkat bedanya:
#    - TANAM: dipasang teknisi, bisa matikan mesin
#    - INSTAN: colok sendiri ke OBD
# 3. Sediakan link e-commerce:
#    - Tokopedia: https://tokopedia.com/orin
#    - Shopee: https://shopee.co.id/orin
# 4. Tawarkan konsultasi dulu dengan tim sales jika perlu"""
#         )
#         return await _build_state_and_save(
#             state=state,
#             intent_result=intent_result,
#             messages=[AIMessage(content=response)],
#             route="ECOMMERCE",
#             step="order_guidance"
#         )

    else:  # general_question
        logger.info("Intent: GENERAL → Answer general question")
        response = await generate_llm_response(
            messages=messages,
            customer_data=customer_data,
            response_task="User mengirim pertanyaan umum. Response dengan ramah, terima kasih sudah menghubungi ORIN GPS Tracker, dan tanya apa yang bisa Hana bantu."
        )
        logger.info(f"EXIT: node_intent_classification -> intent: {intent}, confidence: {confidence}")
        logger.info("=" * 50)
        return await _build_state_and_save(
            state=state,
            intent_result=intent_result,
            messages=[AIMessage(content=response)],
            route="UNASSIGNED",
            step="general"
        )
