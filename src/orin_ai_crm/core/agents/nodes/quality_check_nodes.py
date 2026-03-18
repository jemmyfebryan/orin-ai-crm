"""
Quality Check Node - Evaluates AI answers and triggers human takeover if needed
"""

import os
from datetime import timedelta, timezone
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from src.orin_ai_crm.core.models.schemas import AgentState
from sqlalchemy import update, select

logger = get_logger(__name__)
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))

# HANA_PERSONA is now loaded from database (hana_persona prompt key)
# Hardcoded fallback in case DB is not available
HANA_PERSONA_FALLBACK = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PERCAKAPAN:
- Jawab dengan personalized berdasarkan nama customer jika tersedia
- Singkat tapi ramah dan membantu"""


async def get_hana_persona() -> str:
    """Load Hana persona from database, with fallback to hardcoded value."""
    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    persona = await get_prompt_from_db("hana_persona")
    if not persona:
        logger.warning("hana_persona not found in DB, using fallback")
        return HANA_PERSONA_FALLBACK
    return persona


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
    session_ending: bool = Field(
        default=False,
        description="True jika user menunjukkan kepuasan/tanda-tanda ingin mengakhiri percakapan (ucapan terima kasih, puas, dll)"
    )


class FinalMessagesResponse(BaseModel):
    """Multi-bubble final messages for user"""
    messages: list[str] = Field(
        description="List of message strings to be sent as separate chat bubbles. Each should be a complete, standalone message."
    )
    reasoning: str = Field(
        description="Alasan mengapa response dibagi menjadi beberapa bubble"
    )


async def evaluate_answer_quality(
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
    logger.info(f"evaluate_answer_quality called - user_msg: {user_message[:200]}..., ai_answer: {ai_answer[:50]}...")

    # Load persona from DB
    hana_persona = await get_hana_persona()

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

    system_prompt = f"""{hana_persona}

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

**PENTING - SESSION ENDING DETECTION:**
Cek apakah user menunjukkan tanda-tanda ingin mengakhiri percakapan dengan ekspresi kepuasan:
- User mengucapkan terima kasih: "terima kasih", "makasih", "thanks", "thank you", "trims"
- User menunjukkan kepuasan: "sangat membantu", "membantu banget", "puas", "sudah jelas", "paham", "mengerti"
- User menunjukkan penutupan: "baik terima kasih kak", "oke makasih", "sudah kak", "udah lah"
- User menggabungkan terima kasih dengan kata lain: "terima kasih atas infonya", "makasih ya", "thanks kak"

Jika user menunjukkan tanda-tanda session ending:
- Set session_ending = True
- Ini adalah behavior BAIK (user puas dengan pelayanan)
- Tetap set is_satisfactory = True (ini bukan masalah, ini adalah sukses!)
CONTOH USER MESSAGE YANG MENUNJUKKAN SESSION ENDING:
- "Baik terima kasih kak"
- "Sangat membantu, thanks"
- "Oke kak terima kasih"
- "Makasih ya Hana"
- "Sudah jelas, terima kasih"
- "Puas sama pelayanannya, thanks"

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

    # Load persona from DB
    hana_persona = await get_hana_persona()

    customer_context = customer_name if customer_name else "Kak"

    system_prompt = f"""{hana_persona}

TASK:
Generate pesan handover yang natural dan ramah untuk menjelaskan bahwa live agent yang akan mengambil alih percakapan.

CUSTOMER: {customer_context}

CONTEXT:
AI tidak bisa menjawab pertanyaan ini dengan memuaskan. Sekarang live agent dari ORIN GPS Tracker akan mengambil alih untuk membantu.

RULES:
- Pesan harus sopan dan ramah
- Jelaskan bahwa live agent akan segera membantu
- Berikan harapan kapan live agent akan membalas (misal: "segera", "dalam waktu singkat")
- Gunakan emoji secara wajar
- Personalized dengan nama customer
- Jangan terlalu formal, natural seperti chat WhatsApp
- Jangan buat customer merasa buruk karena pertanyaannya tidak terjawab
Generate response HANYA dengan pesan yang akan dikirim ke customer."""

    response = llm.invoke([SystemMessage(content=system_prompt)])

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
    It evaluates the answer quality using LLM and routes accordingly:
    - If answer is satisfactory → route to final_message
    - If answer is NOT satisfactory → route to human_takeover

    The LLM evaluator is smart enough to understand:
    - Conversational context (profiling questions vs answers)
    - Form flow (acknowledgment vs full answer)
    - Session ending (user satisfaction detection)

    Args:
        state: Current agent state (LangGraph standard)

    Returns:
        Updated state with routing decision and session_ending_detected flag
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_chat_history

    logger.info("=" * 50)
    logger.info("ENTER: node_quality_check")

    messages = state.get('messages', [])
    customer_id = state.get('customer_id')
    customer_data = state.get('customer_data', {})

    # Basic validation: must have messages
    if not messages:
        logger.warning("No messages in state - passing through to final_message")
        logger.info(f"EXIT: node_quality_check -> final_message (no messages)")
        logger.info("=" * 50)
        return {
            "step": "final_message",
            "route": "FINAL_MESSAGE"
        }

    # Extract AI's last message (the answer to evaluate)
    last_message = messages[-1]
    ai_answer = last_message.content if hasattr(last_message, 'content') else ""

    # Extract user's last message (before the AI's response)
    user_message = ""
    for msg in reversed(messages[:-1]):  # Look at messages before the last one
        if hasattr(msg, 'type') and msg.type == 'human':
            user_message = msg.content
            break
        elif hasattr(msg, 'content'):
            # Fallback: use the second-to-last message
            user_message = msg.content
            break

    # Get customer name for context
    customer_name = customer_data.get('name') or state.get('contact_name')

    logger.info(f"Quality check - customer_id: {customer_id}, user_msg: {user_message[:50] if user_message else 'N/A'}...")

    # Validate we have both user message and AI answer
    if not user_message or not ai_answer:
        logger.info("Missing user_message or ai_answer - passing through without evaluation")
        logger.info(f"EXIT: node_quality_check -> final_message (incomplete data)")
        logger.info("=" * 50)
        return {
            "step": "final_message",
            "route": "FINAL_MESSAGE"
        }

    # Fetch REAL WhatsApp conversation history from database for context
    conversation_history = []
    if customer_id:
        try:
            chat_history = await get_chat_history(customer_id, limit=8)  # Last 8 messages
            logger.info(f"Fetched {len(chat_history)} real messages from database for customer {customer_id}")
            conversation_history = chat_history
        except Exception as e:
            logger.error(f"Error fetching chat history from DB: {e}")
            # Fallback to empty history if DB fetch fails
            conversation_history = []

    # Run LLM evaluation with REAL conversation context
    evaluation = await evaluate_answer_quality(
        user_message=user_message,
        ai_answer=ai_answer,
        customer_name=customer_name,
        conversation_history=conversation_history  # Pass real WhatsApp history, not internal workflow
    )

    logger.info(f"Quality evaluation result: satisfactory={evaluation.is_satisfactory}, confidence={evaluation.confidence_score:.2f}, session_ending={evaluation.session_ending}")

    # Route based on evaluation result
    if evaluation.is_satisfactory and evaluation.confidence_score >= 0.35:
        # Answer is good - proceed to final message
        logger.info(f"Answer is SATISFACTORY (score: {evaluation.confidence_score:.2f}) - proceeding with original answer")
        logger.info(f"EXIT: node_quality_check -> final_message")
        logger.info("=" * 50)

        return {
            "step": "final_message",
            "route": "FINAL_MESSAGE",
            "session_ending_detected": evaluation.session_ending
        }
    else:
        # Answer is not satisfactory - trigger human takeover
        logger.info(f"Answer is NOT satisfactory (score: {evaluation.confidence_score:.2f}) - triggering human takeover")
        logger.info(f"Reasoning: {evaluation.reasoning}")
        logger.info(f"EXIT: node_quality_check -> human_takeover")
        logger.info("=" * 50)

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
    """
    Final Message Node - Synthesizes the conversation into user-friendly multi-bubble response.

    This node:
    - Fetches WhatsApp conversation history from database for context
    - Summarizes what happened from user's perspective
    - Generates multiple chat bubbles when appropriate
    - Handles form integration when send_form=True
    - Uses LLM to ensure dynamic, contextual responses

    Args:
        state: Current agent state (LangGraph standard)

    Returns:
        Updated state with final_messages (list of strings for multi-bubble chat)
    """
    from langchain_core.messages import ToolMessage, HumanMessage
    from src.orin_ai_crm.core.agents.tools.db_tools import get_chat_history

    logger.info("=" * 50)
    logger.info("ENTER: node_final_message")

    customer_data = state.get("customer_data", {})
    customer_id = customer_data.get("id")
    customer_name = customer_data.get("name") or state.get("contact_name", "Kak")
    send_form = state.get("send_form", False)

    logger.info(f"Customer Data: {customer_data}")
    logger.info(f"send_form: {send_form}")
    logger.info(f"customer_id: {customer_id}")

    # Build conversation context from TWO sources:
    # 1. Database history (real WhatsApp messages) - for conversation flow context
    # 2. State messages (current execution) - for tool results and what just happened

    # PART 1: Get WhatsApp conversation history from database
    db_conversation_summary = ""
    if customer_id:
        try:
            chat_history = await get_chat_history(customer_id, limit=8)  # Last 8 messages
            logger.info(f"Fetched {len(chat_history)} messages from database for customer {customer_id}")

            # Build summary from database (pure WhatsApp messages)
            for msg in chat_history:
                role = msg.message_role  # 'user' or 'ai'
                content = msg.content
                role_display = "User" if role == "user" else "AI"
                db_conversation_summary += f"{role_display}: {content}\n\n"

            logger.info(f"Built DB conversation summary: {len(chat_history)} messages")
        except Exception as e:
            logger.error(f"Error fetching chat history from DB: {e}")
            db_conversation_summary = "(Error loading conversation history)"

    # PART 2: Get current workflow execution from state
    # Filter to show what happened in THIS interaction (tool calls + latest messages)
    current_execution_summary = ""
    messages = state.get("messages", [])

    for msg in messages:
        if isinstance(msg, HumanMessage):
            current_execution_summary += f"User: {msg.content}\n\n"
        elif isinstance(msg, AIMessage):
            # Include AIMessage content (actual responses)
            if msg.content and msg.content.strip():
                current_execution_summary += f"AI: {msg.content}\n\n"
            # Include tool calls for transparency
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_name = tool_call.get('name', 'unknown_tool')
                    current_execution_summary += f"[AI called tool: {tool_name}]\n"

    logger.info(f"Built current execution summary: {len(messages)} recent messages")

    # PART 3: Combine both summaries
    # Start with DB history for context, then add current execution
    conversation_summary = f"""=== WHATSAPP CONVERSATION HISTORY ===
{db_conversation_summary}

=== AI AGENT WORKFLOW INTERNAL CONVERSATION ===
{current_execution_summary}
"""

    # Build form instructions if needed
    form_instructions = ""
    if send_form:
        # Check which fields are missing
        missing_fields = []
        if not customer_data.get("name"):
            missing_fields.append("- Nama")
        if not customer_data.get("domicile"):
            missing_fields.append("- Domisili/kota")
        if not customer_data.get("vehicle_alias"):
            missing_fields.append("- Jenis kendaraan (mobil, motor, truk, dll)")
        if not customer_data.get("unit_qty") or customer_data.get("unit_qty") == 0:
            missing_fields.append("- Jumlah unit")
        if not customer_data.get("is_b2b"):
            missing_fields.append("- Kebutuhan (pribadi, perusahaan, operasional, dll)")

        if missing_fields:
            form_instructions = f"""

TAMBAHKAN FORM DATA UNTUK PESAN KEPADA USER (1 Form untuk 1 Bubble Chat):
Supaya Hana bisa kasih penawaran yang lebih pas, tolong lengkapi data berikut:
{chr(10).join(missing_fields)}

Contoh format yang bisa digunakan:
"Nama: Budi
Domisili: Jakarta
Jenis kendaraan: Mobil
Jumlah unit: 2
Kebutuhan: Pribadi"
"""

    # Load persona from DB
    hana_persona = await get_hana_persona()

    # Build system prompt for LLM
    system_prompt = f"""{hana_persona}

TASK:
Kamu adalah Final Message Generator untuk Hana AI dari ORIN GPS Tracker.
Tugasmu adalah menyusun percakapan menjadi response yang user-friendly dalam bentuk beberapa chat bubble.

CUSTOMER PROFILE:
- Nama: {customer_name}
- Domisili: {customer_data.get('domicile', 'Belum diketahui')}
- Kendaraan: {customer_data.get('vehicle_alias', 'Belum diketahui')}
- Jumlah Unit: {customer_data.get('unit_qty', 0)}
- B2B: {customer_data.get('is_b2b', False)}
{form_instructions}

IMAGES_SENT: {bool(state.get("send_images"))}
PDFS_SENT: {bool(state.get("send_pdfs"))}

CONVERSATION HISTORY:
{conversation_summary if conversation_summary else "(No conversation history)"}

CONTEXT:
- Percakapan ini mungkin melibatkan berbagai tool calls (database operations, product searches, dll)
- JANGAN sebutkan operasi backend seperti "database", "tool", "API", "system", dll
- Fokus pada apa yang user dapatkan/tahu
- Gunakan bahasa yang natural dan ramah

RULES FOR MULTI-BUBBLE RESPONSE:
1. Split response into multiple bubbles when:
   - Greeting + separate answer
   - Answer + follow-up question
   - Long information that's better broken down
   - Acknowledgment + action/next step
2. Each bubble should be complete and meaningful on its own
3. Use emoji naturally in appropriate bubbles
4. Be conversational and friendly
5. DON'T mention technical/backend operations
6. Personalized with customer name when appropriate
7. If this is your first message with customer (empty conversation history), introduce yourself
8. No need to include any image&pdf url/name in the text (see IMAGES_SENT & PDFS_SENT)
9. Do not make up any information if it's not stated in the conversation history"""

    # Use LLM with structured output to generate multi-bubble response
    final_messages_llm = llm.with_structured_output(FinalMessagesResponse)
    result = final_messages_llm.invoke([SystemMessage(content=system_prompt)])

    logger.info(f"Generated {len(result.messages)} message bubbles")
    logger.info(f"Reasoning: {result.reasoning}")

    # Check if session ending is detected (user expressed satisfaction)
    session_ending_detected = state.get("session_ending_detected", False)
    logger.info(f"Session ending detected: {session_ending_detected}")

    final_messages = result.messages

    # If session ending detected, append review request message
    if session_ending_detected:
        logger.info("Appending review request message to final messages")
        review_message = """Bila Kakak puas dengan pelayanan kami di VASTEL / ORIN, kami harap Kakak berkenan meluangkan 30 detik saja untuk memberi kami bintang 5 di salah satu platform ini:

Google Reviews
https://g.page/r/CaKeWLJ0K6l4EB0/review

Google Play Store
https://play.google.com/store/apps/details?id=com.orin&hl=id&gl=US

Apple App Store
https://apps.apple.com/id/app/orin-gps-tracking/id1450590467

Terimakasih ya Kak.
#SobatVASTEL
follow https://instagram.com/vastel.co.id"""

        final_messages.append(review_message)
        logger.info(f"Total messages after appending review: {len(final_messages)}")

    # Set is_onboarded = True if send_form was triggered
    if send_form and customer_id:
        try:
            async with AsyncSessionLocal() as db:
                stmt = update(Customer).where(Customer.id == customer_id).values(is_onboarded=True)
                await db.execute(stmt)
                await db.commit()
                logger.info(f"Is Onboarded SET to TRUE for customer_id: {customer_id}")
        except Exception as e:
            logger.error(f"Failed to set is_onboarded: {str(e)}")

    # Return state with final_messages
    # Note: We're not returning messages because the final bubbles should be fetched from final_messages field
    logger.info("EXIT: node_final_message")
    logger.info("=" * 50)

    return {
        "final_messages": final_messages
    }

async def node_human_takeover(state: AgentState):
    customer_id = state.get('customer_id')
    customer_data = state.get('customer_data', {})

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

    # Return state with the handover message and final_messages
    return {
        "messages": [AIMessage(content=handover_message)],
        "final_messages": [handover_message]  # Set final_messages for consistent response format
    }
