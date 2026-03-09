"""
Quality Check Node - Evaluates AI answers and triggers human takeover if needed
"""

import os
from datetime import timedelta, timezone
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from src.orin_ai_crm.core.models.schemas import AgentState
from sqlalchemy import update, select

logger = get_logger(__name__)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))

HANA_PERSONA = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAL: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak).

ATURAN PERCAKAPAN:
- Jawab dengan personalized berdasarkan nama customer jika tersedia
- Gunakan konteks percakapan sebelumnya untuk memberikan response yang relevan
- Jangan ulang informasi yang sudah diketahui dari percakapan sebelumnya
- Singkat tapi ramah dan membantu"""


class AnswerQualityEvaluation(BaseModel):
    """Evaluation of AI answer quality"""
    is_satisfactory: bool = Field(
        description="True jika jawaban AI memuaskan dan menjawab pertanyaan user dengan benar"
    )
    confidence_score: float = Field(
        description="Confidence score 0.0 - 1.0 tentang seberapa baik jawaban tersebut",
        ge=0.0,
        le=1.0
    )
    reasoning: str = Field(
        description="Alasan mengapa jawaban tersebut memuaskan atau tidak"
    )
    missing_info: list[str] = Field(
        default=[],
        description="List informasi yang hilang atau kurang dari jawaban (jika ada)"
    )


def evaluate_answer_quality(
    user_message: str,
    ai_answer: str,
    customer_name: Optional[str] = None,
    conversation_history: Optional[list] = None
) -> AnswerQualityEvaluation:
    """
    Evaluates whether the AI answer satisfactorily addresses the user's question.

    Args:
        user_message: The user's original question/message
        ai_answer: The AI's proposed answer
        customer_name: Optional customer name for context
        conversation_history: Optional list of recent messages for context (last 5 bubbles)

    Returns:
        AnswerQualityEvaluation with score and reasoning
    """
    logger.info(f"evaluate_answer_quality called - user_msg: {user_message[:50]}..., ai_answer: {ai_answer[:50]}...")

    customer_context = f"Customer: {customer_name}" if customer_name else "Customer: Kak"

    # Build conversation context from history
    conversation_context = ""
    if conversation_history and len(conversation_history) > 0:
        conversation_context = "\n\nCONVERSATION HISTORY (last 5 messages for context):\n"
        for msg in conversation_history[-5:]:
            if hasattr(msg, 'type'):
                role = "User" if msg.type == 'human' else "AI"
            elif hasattr(msg, '__class__') and 'Human' in msg.__class__.__name__:
                role = "User"
            else:
                role = "AI"
            content = msg.content if hasattr(msg, 'content') else str(msg)
            conversation_context += f"{role}: {content}\n"

    system_prompt = f"""{HANA_PERSONA}

TASK:
Kamu adalah Quality Evaluator untuk jawaban AI dari ORIN GPS Tracker.
Tugasmu adalah mengevaluasi apakah jawaban AI memuaskan dan menjawab pertanyaan user dengan benar.

{customer_context}
{conversation_context}

CURRENT USER QUESTION:
{user_message}

AI ANSWER TO EVALUATE:
{ai_answer}

EVALUATION CRITERIA:
1. **Relevance**: Apakah jawaban relevan dengan pertanyaan?
2. **Completeness**: Apakah jawaban lengkap atau ada informasi penting yang hilang?
3. **Accuracy**: Apakah jawaban akurat dan dapat dipercaya?
4. **Helpfulness**: Apakah jawaban membantu user atau hanya menunda?
5. **Context Awareness**: Gunakan conversation history untuk memahami konteks. Jawaban mungkin terlihat tidak relevan jika di luar konteks, tapi sebenarnya tepat jika melihat history.

RULES:
- Isi is_satisfactory dengan True jika jawaban baik (confidence >= 0.6)
- Isi is_satisfactory dengan False jika jawaban buruk (confidence < 0.6)
- Confidence score 0.0 - 1.0:
  * 0.8 - 1.0: Jawaban sangat baik dan lengkap
  * 0.6 - 0.7: Jawaban cukup baik, tapi bisa lebih baik
  * 0.4 - 0.5: Jawaban kurang memuaskan, ada informasi penting yang hilang
  * 0.0 - 0.3: Jawaban buruk, tidak menjawab pertanyaan, atau salah
- Berikan reasoning yang jelas
- List missing_info jika ada informasi penting yang hilang

**PENTING - FORM FLOW DETECTION:**
Cek conversation history untuk mendeteksi form flow:
- Jika AI sebelumnya meminta data (ada kata "mohon isi", "tolong isi", "domisili", "kebutuhan", "jumlah unit")
- Dan user menjawab dengan jawaban SINGKAT (nama kota, angka, kata kunci seperti "jakarta", "surabaya", "1", "5", "pribadi", "perusahaan")
- Maka user SEDANG MENGISI FORM!

Dalam kasus form flow:
- Jawaban AI hanya perlu: Acknowledge data diterima + optional next step
- Tidak perlu jawaban panjang/detail karena ini hanya acknowledgment
- CONTOH JAWABAN YANG SANGAT BAIK untuk form flow:
  * "Data sudah diterima, terima kasih 😊"
  * "Siap kak, noted ya!"
  * "Oke kak, domisili: Jakarta. Ada yang bisa dibantu?"
- JANGAN anggap jawaban ini buruk hanya karena singkat!

CONTOH JAWABAN BURUK (is_satisfactory=False, confidence<0.6):
- Jawaban yang mengatakan "saya tidak bisa membantu" tanpa alternatif
- Jawaban yang tidak relevan dengan pertanyaan
- Jawaban yang meminta user untuk mengulang pertanyaan tanpa alasan yang jelas
- Jawaban yang terpotong/tidak lengkap (kecuali karena batasan teknis)

CONTOH JAWABAN BAIK (is_satisfactory=True, confidence>=0.6):
- Jawaban yang langsung menjawab pertanyaan dengan informasi yang jelas
- Jawaban yang memberikan solusi atau alternatif jika tidak bisa membantu langsung
- Jawaban yang relevan, lengkap, dan membantu
- Jawaban yang menjelaskan dengan baik dan ramah
- **Form acknowledgment**: User isi form data, AI acknowledge dengan sopan → ini SANGAT BAIK, confidence 0.8-1.0"""

    evaluator_llm = llm.with_structured_output(AnswerQualityEvaluation)
    result = evaluator_llm.invoke([SystemMessage(content=system_prompt)])

    return result


async def generate_human_takeover_message(
    customer_name: Optional[str] = None
) -> str:
    """
    Generate a natural message explaining that a human agent will take over.

    Args:
        user_message: The user's original question
        customer_name: Optional customer name for personalization

    Returns:
        Generated handover message
    """
    logger.info(f"generate_human_takeover_message called - customer: {customer_name}")

    customer_context = customer_name if customer_name else "Kak"

    system_prompt = f"""{HANA_PERSONA}

TASK:
Generate pesan handover yang natural dan ramah untuk menjelaskan bahwa agent manusia yang akan mengambil alih percakapan.

CUSTOMER: {customer_context}

CONTEXT:
AI tidak bisa menjawab pertanyaan ini dengan memuaskan. Sekarang CS manusia dari ORIN GPS Tracker akan mengambil alih untuk membantu.

RULES:
- Pesan harus sopan dan ramah
- Jelaskan bahwa CS manusia akan segera membantu
- Berikan harapan kapan CS akan membalas (misal: "segera", "dalam waktu singkat")
- Gunakan emoji secara wajar
- Personalized dengan nama customer
- Jangan terlalu formal, natural seperti chat WhatsApp
- Jangan buat customer merasa buruk karena pertanyaannya tidak terjawab

CONTOH:
- "Mohon maaf {customer_context}, Hana belum bisa membantu menjawab pertanyaan ini dengan baik. CS Orin akan segera membantu menjawab pertanyaan {customer_context} ya 🙏"
- "Maaf {customer_context}, pertanyaannya perlu dibantu lebih lanjut oleh tim CS Orin. Mereka akan segera membalas ya 😊"

Generate response HANYA dengan pesan yang akan dikirim ke customer."""

    response = llm.invoke([SystemMessage(content=system_prompt)])

    return response.content

async def add_send_form_message(
    last_message: str
):
    system_prompt = f"""{HANA_PERSONA}

Task:
Ubah pesan yang ingin dikirim AI ke user dengan menambahkan form untuk user isi

Pesan AI:
{last_message}

Fields yang diperlukan:
- name: Nama (skip jika sudah ada)
- domicile: Domisili/kota (untuk pengiriman & penawaran yang tepat)
- purpose: Kebutuhan kendaraan (pribadi, perusahaan, operasional kantor, fleet, delivery, dll)
- vehicle_type: Jenis kendaraan (mobil, motor, truk, dll)
- unit_qty: Jumlah unit (untuk penawaran yang tepat)

CATATAN PENTING:
- Jangan tanya field yang sudah terisi di customer_data
- Jelaskan bahwa data ini diperlukan untuk penawaran
- Gunakan bahasa ramah tapi tegas
- Kebutuhan adalah tujuan penggunaan (pribadi/kantor/operasional)
- Di akhir, jelaskan bahwa form harus diisi untuk lanjut

Contoh:
"Supaya Hana bisa kasih penawaran yang lebih pas, mohon isi data singkat berikut:
Nama : ...
Domisili : ...
Kebutuhan (pribadi, kantor, lainnya): ...
Jenis Kendaraan (mobil, motor, lainnya): ...
Jumlah unit : ..."""
    response = llm.invoke([SystemMessage(content=system_prompt)])
    
    logger.info(f"Generated send_form_message: {response.content[:100]}...")
    
    return response.content

async def set_human_takeover_flag(customer_id: int):
    """
    Set human_takeover flag to True for a customer.

    Args:
        customer_id: The customer's ID
    """
    logger.info(f"set_human_takeover_flag called - customer_id: {customer_id}")

    try:
        async with AsyncSessionLocal() as db:
            # Update human_takeover flag
            stmt = update(Customer).where(Customer.id == customer_id).values(human_takeover=True)
            await db.execute(stmt)
            await db.commit()

            logger.info(f"Human takeover flag SET for customer_id: {customer_id}")
    except Exception as e:
        logger.error(f"Failed to set human_takeover flag: {str(e)}")


async def node_quality_check(state: AgentState):
    """
    Quality Check Node - Evaluates AI answer and triggers human takeover if needed.

    This node is the FINAL GATEKEEPER before END. All responses pass through this node.
    It evaluates the answer quality and:
    - For certain steps (profiling, greeting, etc.): Just passes through without evaluation
    - For other steps: Evaluates quality and either passes through or triggers human takeover

    Args:
        state: Current agent state (LangGraph standard)

    Returns:
        Updated state with final answer (either original or handover message)
    """
    logger.info("=" * 50)
    logger.info("ENTER: node_quality_check")

    messages = state.get('messages', [])
    customer_id = state.get('customer_id')
    customer_data = state.get('customer_data', {})
    step = state.get('step', '')

    # Get the AI's last message (the answer to evaluate)
    if not messages:
        logger.warning("No messages in state - returning empty state")
        return {
            "step": "final_message",
            "route": "FINAL_MESSAGE"
        }

    last_message = messages[-1]
    ai_answer = last_message.content if hasattr(last_message, 'content') else ""

    # Steps that should skip quality evaluation (just pass through)
    # Skip profiling questions since they're part of normal conversational flow
    SKIP_QUALITY_CHECK_STEPS = {
        "profiling",  # Profiling questions are conversational and don't need quality check
        "greeting",  # Simple greetings from existing customers
        "human_takeover",  # Already a handover message
        "handle_reschedule",  # Specific flow, pass through
        "no_meeting_found",  # Specific flow, pass through
        "need_identifier",  # Specific flow, pass through
        "order_guidance",  # Specific flow, pass through
        "vehicle_id",  # Part of profiling flow, asking about vehicle
        "vehicle_clarification",  # Part of profiling flow, asking for vehicle model clarification
    }
    # Note: Profiling questions should always pass through quality check
    # They're natural conversational questions, not answers to user queries

    # Skip quality evaluation for certain steps - just pass through
    if step in SKIP_QUALITY_CHECK_STEPS:
        logger.info(f"Step '{step}' is in skip list - passing through without quality check")
        logger.info(f"EXIT: node_quality_check -> pass through")
        logger.info("=" * 50)

        # Return state as-is (pass through the original answer)
        return {
            "step": "final_message",
            "route": "FINAL_MESSAGE"
        }

    # Get user's last message for quality evaluation
    # Find the last human message (before the AI's response)
    user_message = ""
    for msg in reversed(messages[:-1]):  # Look at messages before the last one
        if hasattr(msg, 'type') and msg.type == 'human':
            user_message = msg.content
            break
        elif hasattr(msg, 'content'):
            # Fallback: use the second-to-last message
            user_message = msg.content
            break

    # Get customer name
    customer_name = customer_data.get('name') or state.get('contact_name')

    logger.info(f"Quality check - customer_id: {customer_id}, step: {step}, user_msg: {user_message[:50] if user_message else 'N/A'}...")

    # Only evaluate if we have both user message and AI answer
    if not user_message or not ai_answer:
        logger.info("Missing user_message or ai_answer - passing through without evaluation")
        logger.info(f"EXIT: node_quality_check -> pass through")
        logger.info("=" * 50)
        return {
            "step": "final_message",
            "route": "FINAL_MESSAGE"
        }

    # Evaluate answer quality with conversation history (last 5 messages)
    evaluation = evaluate_answer_quality(
        user_message=user_message,
        ai_answer=ai_answer,
        customer_name=customer_name,
        conversation_history=messages  # Pass full message history for context
    )

    # Check if answer is satisfactory
    if evaluation.is_satisfactory and evaluation.confidence_score >= 0.5:
        logger.info(f"Answer is SATISFACTORY (score: {evaluation.confidence_score}) - proceeding with original answer")
        logger.info(f"EXIT: node_quality_check -> use original answer")
        logger.info("=" * 50)

        # Return state as-is (keep the original answer)
        return {
            "step": "final_message",
            "route": "FINAL_MESSAGE"
        }
    else:
        # Answer is not satisfactory - trigger human takeover
        logger.info(f"Answer is NOT satisfactory (score: {evaluation.confidence_score}) - triggering human takeover")
        logger.info(f"Reasoning: {evaluation.reasoning}")
        
        # Trigger human takeover
        return {
            "step": "human_takeover",
            "route": "HUMAN_TAKEOVER"
        }
        
def quality_router(state: AgentState) -> str:
    route = state.get("route")
    if route == "FINAL_MESSAGE":
        return "final_message"
    if route == "HUMAN_TAKEOVER":
        return "human_takeover"
    # Fallback to human
    logger.info(f"Quality Router error with route: {route}")
    return "human_takeover"

async def node_final_message(state: AgentState):
    # Soon will be used to convert final message to multiple bubble of chat
    # Now will be modify the message to include the form to fill if send_form = True
    logger.info("=" * 50)
    logger.info("ENTER: node_final_message")
    
    customer_data = state.get("customer_data", {})
    logger.info(f"Customer Data: {customer_data}")
    customer_id = customer_data.get("id")
    messages = state.get("messages")
    send_form = state.get("send_form")
    last_message = messages[-1]
    
    logger.info(f"send_form: {send_form}")
    
    if send_form:
        send_form_message = await add_send_form_message(
            last_message=last_message
        )
        
        # Set is_onboarded = True
        try:
            async with AsyncSessionLocal() as db:
                # Update human_takeover flag
                stmt = update(Customer).where(Customer.id == customer_id).values(is_onboarded=True)
                await db.execute(stmt)
                await db.commit()

                logger.info(f"Is Onboarded SET to TRUE for customer_id: {customer_id}")
        except Exception as e:
            logger.error(f"Failed to set is_onboarded: {str(e)}")
            
        return {
            "messages": [AIMessage(content=send_form_message)]
        }
    
    return {}

async def node_human_takeover(state: AgentState):
    messages = state.get('messages', [])
    customer_id = state.get('customer_id')
    customer_data = state.get('customer_data', {})
    step = state.get('step', '')
    
    customer_name = customer_data.get('name') or state.get('contact_name')
    
    # Set human_takeover flag in database
    if customer_id:
        await set_human_takeover_flag(customer_id)

    # Generate handover message
    handover_message = await generate_human_takeover_message(
        customer_name=customer_name
    )

    logger.info(f"Generated handover message: {handover_message[:100]}...")
    logger.info(f"EXIT: node_quality_check -> human takeover")
    logger.info("=" * 50)

    # Return state with the handover message
    return {
        "messages": [AIMessage(content=handover_message)]
    }
