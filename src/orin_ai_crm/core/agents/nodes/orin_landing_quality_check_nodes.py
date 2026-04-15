"""
Quality Check Nodes for Orin Landing Agent - Evaluates AI answers and triggers human takeover if needed

This is a separate module from hana_agent's quality_check_nodes to avoid affecting production.
The key difference is in node_human_takeover behavior:
- hana_agent: Sets human_takeover=True in database, notifies live agent
- orin_landing_agent: Sends wa.me/6281329293939 link, does NOT set database flag
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import get_llm
from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db, get_agent_name

logger = get_logger(__name__)


def filter_final_messages(final_messages: list[str], customer_name: str = "") -> list[str]:
    """
    Apply rule-based filtering to final messages.

    This function performs post-processing on the AI-generated messages
    to fix common formatting issues without re-prompting the LLM.

    Current filters:
    - Replace exclamation mark after customer name with comma: "{name}!" → "{name},"
    - Remove image URLs (since images are sent separately via API)

    Args:
        final_messages: List of message strings from node_final_message
        customer_name: Customer name to use for filtering (optional)

    Returns:
        Filtered list of message strings
    """
    import re

    if not final_messages:
        return final_messages

    filtered_messages = []

    # Pattern to match image URLs (http/https URLs ending with image extensions or containing 'image', 'photo', 'product', etc.)
    image_url_pattern = re.compile(
        r'https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp|bmp|svg)(?:\?[^\s]*)?',
        re.IGNORECASE
    )

    for message in final_messages:
        filtered_message = message

        # Filter: Replace exclamation mark after customer name with comma
        if customer_name:
            filtered_message = filtered_message.replace(f"{customer_name}!", f"{customer_name},")
            filtered_message = filtered_message.replace(f"kak {customer_name}!", f"kak {customer_name},")
            filtered_message = filtered_message.replace(f"Kak {customer_name}!", f"Kak {customer_name},")
            filtered_message = filtered_message.replace(f"Kakak {customer_name}!", f"Kakak {customer_name},")

        # Filter: Remove image URLs (since images are sent separately via API)
        lines = filtered_message.split('\n')
        filtered_lines = []
        for line in lines:
            if image_url_pattern.match(line.strip()):
                logger.info(f"filter_final_messages: Removed image URL: {line.strip()}")
                continue
            cleaned_line = image_url_pattern.sub('', line)
            cleaned_line = ' '.join(cleaned_line.split())
            if cleaned_line.strip():
                filtered_lines.append(cleaned_line)

        filtered_message = '\n'.join(filtered_lines)

        if filtered_message.strip():
            filtered_messages.append(filtered_message)

    if filtered_messages != final_messages:
        logger.info(f"filter_final_messages: Applied {len(final_messages)} filters")

    return filtered_messages


# ============================================================================
# TIERED LLM CONFIGURATION FOR QUALITY CHECK NODES
# ============================================================================
quality_llm = get_llm("medium")
final_message_llm = get_llm("medium")
human_takeover_llm = get_llm("medium")

WIB = timezone(timedelta(hours=7))

# AGENT_PERSONA is now loaded from database (orin_landing_persona prompt key)
AGENT_PERSONA_FALLBACK = """Kamu adalah {agent_name}, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PERCAKAPAN:
- Jawab dengan personalized berdasarkan nama customer jika tersedia
- Singkat tapi ramah dan membantu"""


async def get_agent_persona() -> str:
    """Load agent persona from database, with fallback to hardcoded value."""
    persona = await get_prompt_from_db("orin_landing_persona")
    if not persona:
        logger.warning("orin_landing_persona not found in DB, using fallback")
        agent_name = get_agent_name()
        return AGENT_PERSONA_FALLBACK.format(agent_name=agent_name)

    # Format agent name into the persona
    agent_name = get_agent_name()
    try:
        return persona.format(agent_name=agent_name)
    except KeyError:
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


class FinalMessagesResponse(BaseModel):
    """Multi-bubble final messages for user with session ending detection"""
    messages: list[str] = Field(
        description="List of message strings to be sent as separate chat bubbles. Each should be a complete, standalone message."
    )
    reasoning: str = Field(
        description="Alasan mengapa response dibagi menjadi beberapa bubble"
    )
    is_session_ending: bool = Field(
        description="True jika user menunjukkan tanda-tanda ingin mengakhiri percakapan dengan ekspresi kepuasan"
    )
    session_ending_reasoning: str = Field(
        default="",
        description="Alasan mengapa ini dikategorikan sebagai session ending (isi hanya jika is_session_ending=True)"
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
        conversation_history: Optional list of recent messages for context

    Returns:
        AnswerQualityEvaluation with score and reasoning
    """
    logger.info(f"evaluate_answer_quality called - user_msg: {user_message[:200]}..., ai_answer: {ai_answer[:50]}...")

    agent_persona = await get_agent_persona()
    customer_context = f"Customer: {customer_name}" if customer_name else "Customer: Kak"

    conversation_context = ""
    if conversation_history and len(conversation_history) > 0:
        whatsapp_only_history = [
            msg for msg in conversation_history
            if hasattr(msg, 'message_role') and msg.message_role in ['user', 'ai']
        ]

        if whatsapp_only_history:
            conversation_context = "\n\nCONVERSATION HISTORY (WhatsApp messages only - last 5 for context):\n"
            for msg in whatsapp_only_history[-5:]:
                if hasattr(msg, 'message_role'):
                    role = "User" if msg.message_role == 'user' else "AI"
                    content = msg.content if hasattr(msg, 'content') else str(msg)
                    conversation_context += f"{role}: {content}\n"

    system_prompt = f"""{agent_persona}

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
2. **Completeness**: Apakah jawaban cukup lengkap?
3. **Accuracy**: Apakah jawaban secara umum akurat?
4. **Helpfulness**: Apakah jawaban membantu user?
5. **Context Awareness**: Gunakan conversation history untuk memahami konteks.

RULES:
- BIAS LEBIH LENIENT: Kalau ragu, anggap jawaban itu memuaskan (is_satisfactory=True)
- Isi is_satisfactory dengan True jika jawaban cukup membantu (confidence >= 0.4)
- Isi is_satisfactory dengan False HANYA jika jawaban jelas-jelas buruk (confidence < 0.4)
- Confidence score 0.0 - 1.0:
  * 0.7 - 1.0: Jawaban sangat baik dan lengkap
  * 0.5 - 0.6: Jawaban baik dan membantu
  * 0.4 - 0.5: Jawaban cukup, bisa diterima
  * 0.2 - 0.3: Jawaban kurang
  * 0.0 - 0.1: Jawaban buruk
- Berikan reasoning yang jelas
- List missing_info HANYA jika ada informasi KRUSIAL yang hilang

CONTOH JAWABAN BURUK (is_satisfactory=False, confidence<0.4):
- Jawaban yang mengatakan "saya tidak bisa membantu" tanpa alternatif
- Jawaban yang tidak relevan dengan pertanyaan
- Jawaban yang terpotong/tidak lengkap

CONTOH JAWABAN BAIK (is_satisfactory=True, confidence>=0.6):
- Jawaban yang langsung menjawab pertanyaan dengan informasi jelas
- Jawaban yang memberikan solusi atau alternatif
- Jawaban yang relevan, lengkap, dan membantu"""

    evaluator_llm = quality_llm.with_structured_output(AnswerQualityEvaluation)
    result = evaluator_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content="Evaluate the above answer.")
    ])

    return result


async def generate_human_takeover_message(
    customer_name: Optional[str] = None
) -> str:
    """
    Generate a message with WhatsApp link for live agent.

    For orin_landing_agent, this does NOT set database flag or notify live agent.
    Instead, it provides the customer with a direct WhatsApp link to contact live support.

    Args:
        customer_name: Optional customer name for personalization

    Returns:
        Generated handover message with wa.me link
    """
    logger.info(f"generate_human_takeover_message called (orin_landing) - customer: {customer_name}")

    agent_persona = await get_agent_persona()
    customer_context = customer_name if customer_name else "Kak"

    system_prompt = f"""{agent_persona}

TASK:
Generate pesan handover yang natural dan ramah untuk menjelaskan bahwa customer bisa menghubungi live agent via WhatsApp.

CUSTOMER: {customer_context}

CONTEXT:
AI tidak bisa menjawab pertanyaan ini dengan memuaskan. Customer bisa menghubungi live agent langsung via WhatsApp.

RULES:
- Pesan harus sopan dan ramah
- Berikan link WhatsApp: https://wa.me/6281329293939
- Jelaskan bahwa customer bisa klik link tersebut untuk chat dengan live agent
- Gunakan emoji secara wajar
- Personalized dengan nama customer
- Jangan terlalu formal, natural seperti chat WhatsApp
- Jangan buat customer merasa buruk karena pertanyaannya tidak terjawab
Generate response HANYA dengan pesan yang akan dikirim ke customer."""

    response = human_takeover_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content="Generate the human takeover response.")
    ])

    content = response.content

    # Convert to string if it's a list (Gemini 4.x format)
    if isinstance(content, list):
        content_str = ""
        for block in content:
            if isinstance(block, dict):
                if 'text' in block:
                    content_str += block['text']
            elif hasattr(block, 'text'):
                content_str += block.text
            elif isinstance(block, str):
                content_str += block
            elif hasattr(block, 'content'):
                content_str += str(block.content)
        content = content_str

    return content


async def node_quality_check(state: AgentState):
    """
    Quality Check Node - Evaluates final WhatsApp messages and triggers human takeover if needed.

    This is for orin_landing_agent - uses same logic as hana_agent but routes to different human_takeover node.

    Args:
        state: Current agent state (LangGraph standard)

    Returns:
        Updated state with routing decision ("END" or "human_takeover")
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_chat_history

    logger.info("=" * 50)
    logger.info("ENTER: node_quality_check (orin_landing)")

    messages = state.get('messages', [])
    final_messages = state.get('final_messages', [])
    customer_id = state.get('customer_id')
    customer_data = state.get('customer_data', {})

    # PRIORITY: Check if we have final_messages (actual WhatsApp bubbles to evaluate)
    if final_messages and len(final_messages) > 0:
        logger.info(f"Evaluating {len(final_messages)} final WhatsApp bubbles")
        ai_answer = "\n\n".join(final_messages)
    elif messages and len(messages) > 0:
        logger.info("No final_messages found, evaluating raw AI answer (fallback)")
        last_message = messages[-1]
        ai_answer = last_message.content if hasattr(last_message, 'content') else ""
    else:
        logger.warning("No messages or final_messages in state - passing through to END")
        logger.info(f"EXIT: node_quality_check -> END (no messages)")
        logger.info("=" * 50)
        return {"route": "END"}

    # Extract user's last message
    user_message = ""
    for msg in reversed(messages[:-1] if len(messages) > 1 else []):
        if hasattr(msg, 'type') and msg.type == 'human':
            user_message = msg.content
            break
        elif hasattr(msg, 'content'):
            user_message = msg.content
            break

    customer_name = customer_data.get('name') or state.get('contact_name')

    logger.info(f"Quality check - customer_id: {customer_id}, user_msg: {user_message[:50] if user_message else 'N/A'}...")

    if not ai_answer:
        logger.info("Missing ai_answer - passing through without evaluation")
        logger.info(f"EXIT: node_quality_check -> END (incomplete data)")
        logger.info("=" * 50)
        return {"route": "END"}

    # Fetch REAL WhatsApp conversation history from database for context
    conversation_history = []
    if customer_id:
        try:
            chat_history = await get_chat_history(customer_id, limit=8)
            logger.info(f"Fetched {len(chat_history)} real messages from database for customer {customer_id}")
            conversation_history = chat_history
        except Exception as e:
            logger.error(f"Error fetching chat history from DB: {e}")
            conversation_history = []

    # Run LLM evaluation
    evaluation = await evaluate_answer_quality(
        user_message=user_message,
        ai_answer=ai_answer,
        customer_name=customer_name,
        conversation_history=conversation_history
    )

    logger.info(f"Quality evaluation result: satisfactory={evaluation.is_satisfactory}, confidence={evaluation.confidence_score:.2f}")

    if evaluation.is_satisfactory:
        logger.info(f"Answer is SATISFACTORY (score: {evaluation.confidence_score:.2f}) - sending to user")
        logger.info(f"EXIT: node_quality_check -> END")
        logger.info("=" * 50)
        return {"route": "END"}
    else:
        logger.info(f"Answer is NOT satisfactory (score: {evaluation.confidence_score:.2f}) - triggering human takeover")
        logger.info(f"Reasoning: {evaluation.reasoning}")
        logger.info(f"EXIT: node_quality_check -> human_takeover")
        logger.info("=" * 50)
        return {"route": "HUMAN_TAKEOVER"}


def quality_router(state: AgentState) -> str:
    """Route based on quality check result."""
    route = state.get("route")
    if route == "END":
        return "end"
    if route == "HUMAN_TAKEOVER":
        return "human_takeover"
    logger.info(f"Quality Router: {route}")
    return "end"


async def node_final_message(state: AgentState):
    """
    Final Message Node - Synthesizes the conversation into user-friendly multi-bubble response.

    This is for orin_landing_agent - similar to hana_agent's node_final_message.

    Args:
        state: Current agent state (LangGraph standard)

    Returns:
        Updated state with final_messages (list of strings for multi-bubble chat)
    """
    from langchain_core.messages import HumanMessage
    from src.orin_ai_crm.core.agents.tools.db_tools import get_chat_history

    logger.info("=" * 50)
    logger.info("ENTER: node_final_message (orin_landing)")

    customer_data = state.get("customer_data", {})
    customer_id = customer_data.get("id")
    customer_name = customer_data.get("name") or state.get("contact_name", "Kak")
    send_form = state.get("send_form", False)

    logger.info(f"Customer Data: {customer_data}")
    logger.info(f"send_form: {send_form}")
    logger.info(f"customer_id: {customer_id}")

    messages_history = state.get("messages_history")
    if messages_history:
        messages_history = messages_history[-5:]
    else:
        messages_history = []
    workflow_messages = state.get("messages")

    conversation_summary = f"""=== WHATSAPP CONVERSATION HISTORY ===
{messages_history}

=== AI AGENT WORKFLOW INTERNAL MESSAGES RESULT ===
{workflow_messages}
"""

    agent_persona = await get_agent_persona()
    agent_name = get_agent_name()

    now_wib = datetime.now(WIB)

    hari_indo = {
        "Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu",
        "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu",
        "Sunday": "Minggu"
    }

    bulan_indo = {
        "January": "Januari", "February": "Februari", "March": "Maret",
        "April": "April", "May": "Mei", "June": "Juni",
        "July": "Juli", "August": "Agustus", "September": "September",
        "October": "Oktober", "November": "November", "December": "Desember"
    }

    day_en = now_wib.strftime("%A")
    month_en = now_wib.strftime("%B")
    day_indo = hari_indo.get(day_en, day_en)
    month_indo = bulan_indo.get(month_en, month_en)
    today = f"{day_indo}, {now_wib.day} {month_indo} {now_wib.year}"
    datetime_now = now_wib.strftime("%H:%M")

    system_prompt = f"""{agent_persona}

ENVIRONMENT CONTEXT:
Hari, Tanggal: {today}, {datetime_now}

TASK:
Kamu adalah {agent_name} ORIN GPS Tracker.
Tugasmu adalah menyusun percakapan menjadi response yang user-friendly dalam bentuk beberapa chat bubble.

AGENT ABILITIES:
- Meng-update data customer
- Bertanya mengenai meeting (untuk b2b)
- Mengalihkan sesi chat ke Live Agent (via WhatsApp link)
- Pertanyaan detail mengenai spesifikasi dan rekomendasi produk
- Link e-commerce adalah source of truth untuk harga produk, stok produk, maupun promo
- Agent belum memiliki ability untuk penawaran pemasangan maupun biaya pemasangan

CUSTOMER PROFILE:
- Nama: {customer_name}
- Domisili: {customer_data.get('domicile', 'Belum diketahui')}
- Kendaraan: {customer_data.get('vehicle_alias', 'Belum diketahui')}
- Jumlah Unit: {customer_data.get('unit_qty', 0)}
- B2B: {customer_data.get('is_b2b', False)}

FORM_SENT: {bool(send_form)} {"(No need to send customer profile-related question)" if send_form else ""}

CONVERSATION HISTORY:
{conversation_summary if conversation_summary else "(No conversation history)"}

CONTEXT:
- Percakapan ini mungkin melibatkan berbagai tool calls (database operations, product searches, dll)
- JANGAN sebutkan operasi backend seperti "database", "tool", "API", "system", dll
- Fokus pada apa yang user dapatkan/tahu
- Gunakan bahasa yang natural dan ramah

WHATSAPP MARKDOWN FORMATTING:
- *bold* → gunakan *asterisk* untuk tebal
- _italic_ → gunakan _underscore_ untuk miring
- JANGAN gunakan # untuk heading
- JANGAN gunakan > untuk blockquote
- Untuk list, gunakan format: "1. Item pertama" atau "• Item pertama"

RULES FOR MULTI-BUBBLE RESPONSE:
1. Bagi menjadi beberapa-bubble untuk sapaan, jawaban, pertanyaan follow-up
2. Pakai emoji yang natural
3. Friendly dan conversational
4. Jangan menyebut operasi backend
5. Jika ini pesan pertama, perkenalkan dirimu
6. Jangan mengarang informasi
7. Gunakan style bold untuk nama agent `*{agent_name}*`

SESSION ENDING DETECTION:
Cek CONVERSATION HISTORY, khususnya user message terakhir.
SESSION ENDING INDICATORS: set is_session_ending = True JIKA user mengucapkan kepuasan, terima kasih, "sangat membantu", "siap mengerti"

RULES:
1. Set is_session_ending = True HANYA jika user message terakhir jelas menunjukkan session ending
2. Set is_session_ending = False JIKA user masih bertanya atau tidak ada tanda puas
3. Jika True, isi session_ending_reasoning dengan alasan yang jelas"""

    final_messages_llm_structured = final_message_llm.with_structured_output(FinalMessagesResponse)

    result: FinalMessagesResponse = final_messages_llm_structured.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content="Generate the response based on the above instructions.")
    ])

    logger.info(f"Generated {len(result.messages)} message bubbles")
    logger.info(f"Reasoning: {result.reasoning}")
    logger.info(f"Session ending detection: is_session_ending={result.is_session_ending}")

    final_messages = result.messages

    # Append form message if send_form = True
    if send_form:
        logger.info("send_form=True - appending form message to final messages")
        form_message = f"""Supaya {agent_name} bisa kasih penawaran yang lebih pas, tolong lengkapi data berikut:

Nama: ...
Domisili: ...
Jenis kendaraan: ...
Jumlah unit: ...
Kebutuhan: ...

Terima kasih kak 😊"""
        final_messages.append(form_message)

    # If session ending detected, append review request message
    if result.is_session_ending:
        logger.info("Session ending detected - appending review request message")
        review_message = """Bila Kakak puas dengan pelayanan kami di VASTEL / ORIN, kami harap Kakak berkenan meluangkan 30 detik saja untuk memberi kami bintang 5 di salah satu platform ini:

*Google Reviews*
https://g.page/r/CaKeWLJ0K6l4EB0/review

*Google Play Store*
https://play.google.com/store/apps/details?id=com.orin&hl=id&gl=US

*Apple App Store*
https://apps.apple.com/id/app/orin-gps-tracking/id1450590467

Terimakasih ya Kak.
#SobatVASTEL
follow https://instagram.com/vastel.co.id"""
        final_messages.append(review_message)

    logger.info("EXIT: node_final_message (orin_landing)")
    logger.info("=" * 50)

    return {"final_messages": final_messages}


async def node_human_takeover(state: AgentState):
    """
    Human Takeover Node for orin_landing_agent.

    KEY DIFFERENCE from hana_agent:
    - Does NOT set human_takeover flag in database
    - Does NOT notify live agent
    - Instead, sends message with wa.me/6281329293939 link for customer to contact live support directly

    Args:
        state: Current agent state (LangGraph standard)

    Returns:
        Updated state with human takeover message
    """
    customer_id = state.get('customer_id')
    customer_data = state.get('customer_data', {})
    customer_name = customer_data.get('name') or state.get('contact_name')

    # NOTE: We do NOT set human_takeover flag in database for orin_landing_agent
    # This is different from hana_agent behavior
    logger.info("node_human_takeover (orin_landing): NOT setting database flag, sending wa.me link instead")

    # Generate handover message with wa.me link
    handover_message = await generate_human_takeover_message(
        customer_name=customer_name
    )

    logger.info(f"Generated handover message: {handover_message[:100]}...")
    logger.info(f"EXIT: node_human_takeover (orin_landing)")
    logger.info("=" * 50)

    return {
        "messages": [AIMessage(content=handover_message)],
        "final_messages": [handover_message]
    }
