"""
Hana AI Agent - Agentic/Tool-Calling Architecture with 30+ Granular Tools

This refactored implementation replaces the intent classification node with an
agentic architecture that allows the LLM to handle multiple intents in a single
message by calling tools in parallel or sequentially.

Architecture:
1. agent_entry_handler: Ensures customer_id exists
2. agent_decision_node: LLM with 30+ granular tools bound using bind_tools()
3. tool_execution_node: LangGraph's ToolNode for executing requested tools
4. quality_check_node: Evaluates AI answer quality
5. final_message_node: Adds form if needed and prepares final response
6. human_takeover_node: Triggers human agent takeover

Key Benefits:
- LLM can call multiple tools simultaneously for multi-intent messages
- 30+ granular tools for maximum flexibility
- More flexible than rigid intent classification
- Better handles complex user requests
- Maintains conversation context and flow
"""

import os
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.tools.agent_tools import AGENT_TOOLS
from src.orin_ai_crm.core.agents.nodes.quality_check_nodes import (
    node_quality_check,
    quality_router,
    node_final_message,
    node_human_takeover
)

logger = get_logger(__name__)

# Initialize LLM with tool calling support
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"), temperature=0)

# Bind ALL 30+ tools to LLM for maximum agentic capability
llm_with_tools = llm.bind_tools(AGENT_TOOLS)

# Tool execution node using LangGraph's built-in ToolNode
tool_execution_node = ToolNode(AGENT_TOOLS)

HANA_AGENT_SYSTEM_PROMPT = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.

Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PRODUK GPS:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin)
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak)

KEMAMPUAN TOOL (30+ tools tersedia):
Kamu memiliki banyak tools yang dapat membantu customer. Tool-category terbagi menjadi:

1. CUSTOMER MANAGEMENT (3 tools):
   - get_or_create_customer: Get/create customer from database
   - get_customer_profile: Get customer profile data
   - update_customer_data: Update specific customer fields

2. PROFILING (7 tools):
   - extract_customer_info_from_message: Extract info from message using LLM
   - check_profiling_completeness: Check if profiling is complete
   - determine_next_profiling_field: Determine what to ask next
   - generate_profiling_question: Generate natural profiling question
   - search_vehicle_in_vps: Search vehicle in VPS database
   - create_lead_routing: Create lead routing when profiling complete
   - generate_greeting_message: Generate personalized greeting

3. SALES & MEETING (6 tools):
   - get_pending_meeting: Get existing meeting
   - extract_meeting_details: Extract meeting info from message
   - book_or_update_meeting_db: Book/update meeting in database
   - generate_meeting_negotiation_message: Generate negotiation message
   - generate_meeting_confirmation: Generate confirmation message
   - generate_existing_meeting_reminder: Generate reminder for existing meeting

4. PRODUCT & E-COMMERCE (8 tools):
   - get_all_active_products: Get all products from database
   - search_products: Search products by keyword/category/vehicle
   - get_product_details: Get detailed product info
   - answer_product_question: Answer product questions
   - get_ecommerce_links: Get e-commerce purchase links
   - create_product_inquiry: Create product inquiry record
   - get_pending_product_inquiry: Get existing inquiry
   - recommend_products_for_customer: Recommend products

5. SUPPORT & COMPLAINTS (3 tools):
   - classify_issue_type: Classify issue (complaint/support/general)
   - generate_empathetic_response: Generate empathetic response
   - set_human_takeover_flag: Trigger human takeover

PENTING - PENGGUNAAN TOOL:
- Kamu BISA dan BOLEH memanggil LEBIH DARI SATU tool secara bersamaan!
- Contoh multi-intent: "Saya Budi dari Surabaya, mau tanya GPS untuk motor"
  → Panggil: get_or_create_customer, extract_customer_info_from_message, search_products, answer_product_question

- Contoh multi-intent: "Meeting saya bisa diganti besok jam 2? Sekalian tanya harga GPS"
  → Panggil: get_pending_meeting, extract_meeting_details, book_or_update_meeting_db, answer_product_question

Alur Percakapan:
1. Mulai dengan get_or_create_customer untuk identify customer
2. Extract info dari pesan dengan extract_customer_info_from_message
3. Jika perlu, collect more profiling data dengan generate_profiling_question
4. Setelah profiling lengkap → determine route (SALES vs ECOMMERCE)
5. SALES: Tawarkan meeting, gunakan meeting tools
6. ECOMMERCE: Jawab pertanyaan produk, berikan rekomendasi

INGAT: Database adalah sumber kebenaran. JANGAN mengarang info."""


async def agent_entry_handler(state: AgentState) -> dict:
    """
    Entry point handler - ensures customer_id exists before entering agent decision.
    """
    from src.orin_ai_crm.core.agents.tools.agent_tools import get_or_create_customer

    logger.info("ENTER: agent_entry_handler")

    # If we don't have customer_id yet, get or create customer
    if not state.get('customer_id'):
        identifier = {
            'phone_number': state.get('phone_number'),
            'lid_number': state.get('lid_number')
        }
        contact_name = state.get('contact_name')

        customer = await get_or_create_customer(
            phone_number=identifier.get('phone_number'),
            lid_number=identifier.get('lid_number'),
            contact_name=contact_name
        )

        customer_id = customer['customer_id']

        logger.info(f"Customer resolved: id={customer_id}")

        # Build customer_data from customer dict
        customer_data = {
            'id': customer_id,
            'name': customer.get('name', ''),
            'domicile': customer.get('domicile', ''),
            'vehicle_id': customer.get('vehicle_id', -1),
            'vehicle_alias': customer.get('vehicle_alias', ''),
            'unit_qty': customer.get('unit_qty', 0),
            'is_b2b': customer.get('is_b2b', False),
            'is_onboarded': customer.get('is_onboarded', False),
        }

        # Update state with customer info
        state['customer_id'] = customer_id
        state['customer_data'] = customer_data

        # Check if form should be sent
        send_form = True if not customer.get('is_onboarded', False) else False
        state['send_form'] = send_form

        logger.info(f"State updated: customer_id={customer_id}, send_form={send_form}")

    logger.info("EXIT: agent_entry_handler")
    return state


async def agent_decision_node(state: AgentState) -> dict:
    """
    Agent Decision Node - The LLM decides which tools to call (if any) based on user input.

    This replaces the old intent classification node. Instead of classifying into a single
    intent, the LLM can call multiple tools (from 30+ available) to handle complex,
    multi-intent messages.

    The LLM will intelligently compose tools like:
    - get_or_create_customer + extract_customer_info_from_message + update_customer_data
    - get_pending_meeting + extract_meeting_details + book_or_update_meeting_db
    - search_products + answer_product_question + get_ecommerce_links
    - Any combination of the 30+ available tools!

    Args:
        state: Current agent state with messages, customer_data, etc.

    Returns:
        Updated state with AI response (which may include tool_calls)
    """
    logger.info("=" * 50)
    logger.info("ENTER: agent_decision_node")

    messages = state.get('messages', [])
    customer_data = state.get('customer_data', {})
    customer_id = state.get('customer_id')
    contact_name = state.get('contact_name')

    # Build context for the LLM
    customer_name = customer_data.get('name') or contact_name or 'Kak'
    context_info = f"""
Customer Profile:
- Nama: {customer_name}
- Domisili: {customer_data.get('domicile', 'Belum diketahui')}
- Kendaraan: {customer_data.get('vehicle_alias', 'Belum diketahui')}
- Jumlah Unit: {customer_data.get('unit_qty', 0)}
- B2B: {customer_data.get('is_b2b', False)}
- Customer ID: {customer_id or 'Belum ada'}
- Profiling Status: {'Complete' if all([customer_data.get('name'), customer_data.get('domicile')]) else 'Incomplete'}

Customer Identifier:
- Phone Number: {state.get('phone_number') or 'N/A'}
- LID Number: {state.get('lid_number') or 'N/A'}

AVAILABLE TOOLS (30+ tools organized by category):

1. CUSTOMER MANAGEMENT:
   - get_or_create_customer: Identify customer from phone/lid_number
   - get_customer_profile: Get complete customer data
   - update_customer_data: Update specific customer fields (name, domicile, vehicle, qty, b2b)

2. PROFILING:
   - extract_customer_info_from_message: Extract info from message (name, domicile, vehicle, qty)
   - check_profiling_completeness: Check if we have all required data
   - determine_next_profiling_field: Decide what to ask next
   - generate_profiling_question: Generate natural question for specific field
   - search_vehicle_in_vps: Search vehicle in VPS database
   - create_lead_routing: Create routing when profiling complete
   - generate_greeting_message: Generate personalized greeting

3. SALES & MEETING:
   - get_pending_meeting: Check existing meeting
   - extract_meeting_details: Extract meeting info (date, time, agreement)
   - book_or_update_meeting_db: Create/update meeting in DB
   - generate_meeting_negotiation_message: Generate negotiation message
   - generate_meeting_confirmation: Generate confirmation message
   - generate_existing_meeting_reminder: Remind about existing meeting

4. PRODUCT & E-COMMERCE:
   - get_all_active_products: Get all products from DB
   - search_products: Search by keyword, category, or vehicle type
   - get_product_details: Get detailed product info
   - answer_product_question: Answer product questions
   - get_ecommerce_links: Get purchase links (Tokopedia, Shopee)
   - create_product_inquiry: Create inquiry tracking
   - get_pending_product_inquiry: Check existing inquiry
   - recommend_products_for_customer: Recommend based on profile

5. SUPPORT & COMPLAINTS:
   - classify_issue_type: Classify issue type and severity
   - generate_empathetic_response: Generate empathetic response
   - set_human_takeover_flag: Trigger human agent takeover

IMPORTANT - TOOL COMPOSITION:
You can and SHOULD call MULTIPLE tools together for complex requests:

Examples:
- "Saya Budi dari Surabaya, mau tanya GPS motor"
  → get_or_create_customer (identify) + extract_customer_info_from_message (get data) +
     search_products (find motor GPS) + answer_product_question (provide info)

- "Meeting besok jam 2 bisa diganti? Sekalian tanya harga GPS"
  → get_pending_meeting (check existing) + extract_meeting_details (extract new time) +
     book_or_update_meeting_db (update meeting) + answer_product_question (answer price)

- "Saya Rina, butuh 10 unit untuk fleet perusahaan"
  → get_or_create_customer + extract_customer_info_from_message +
     update_customer_data (save data) + check_profiling_completeness +
     create_lead_routing (route to sales)

CONVERSATION HISTORY:
"""

    # Add recent conversation history
    recent_messages = messages[-8:] if len(messages) >= 8 else messages  # Include more messages for tool results
    for msg in recent_messages:
        from langchain_core.messages import HumanMessage, ToolMessage
        if isinstance(msg, HumanMessage):
            context_info += f"Customer: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                context_info += f"Hana: [Called {len(msg.tool_calls)} tool(s): {[tc['name'] for tc in msg.tool_calls]}]\n"
            else:
                context_info += f"Hana: {msg.content}\n"
        elif isinstance(msg, ToolMessage):
            # IMPORTANT: Include the actual tool result content!
            # Parse the tool result to show the LLM what was returned
            if hasattr(msg, 'content') and msg.content:
                try:
                    # Try to parse as JSON for cleaner display
                    import json
                    try:
                        result_dict = json.loads(msg.content)
                        if isinstance(result_dict, dict):
                            # Format dict nicely
                            context_info += f"[Tool Result ({msg.name}): {json.dumps(result_dict, ensure_ascii=False)[:200]}]\n"
                        else:
                            context_info += f"[Tool Result ({msg.name}): {msg.content[:200]}]\n"
                    except:
                        context_info += f"[Tool Result ({msg.name}): {msg.content[:200]}]\n"
                except:
                    context_info += f"[Tool Result ({msg.name}): {msg.content[:200] if msg.content else 'empty'}]\n"
            else:
                context_info += f"[Tool Result ({msg.name}): executed]\n"

    context_info += """

INSTRUKSI:
1. Analisis pesan customer terakhir
2. Tentukan tool(s) yang perlu dipanggil
3. Kamu BOLEH memanggil LEBIH DARI SATU tool (multi-tool composition)
4. Jika customer memberikan informasi → extract & save data
5. Jika customer bertanya produk → jawab dengan database info
6. Jika customer B2B/unit >= 5 → tawarkan meeting
7. Jika customer punya keluhan → classify & generate empathetic response

Response Format:
- Jika perlu panggil tool: Return ONLY tool calls (no text response first)
- Setelah tool results: Generate natural response based on results
- Jika tidak perlu tool: Berikan text response biasa
"""

    # Invoke LLM with all 30+ tools
    response = await llm_with_tools.ainvoke(
        [SystemMessage(content=context_info)] + messages
    )

    logger.info(f"LLM response has {len(response.tool_calls) if hasattr(response, 'tool_calls') else 0} tool calls")

    # Log tool calls if any
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tc in response.tool_calls:
            logger.info(f"  Tool call: {tc['name']}")

    logger.info("EXIT: agent_decision_node")
    logger.info("=" * 50)

    return {
        "messages": [response]
    }


def should_continue_to_tools(state: AgentState) -> Literal["tool_execution", "quality_check"]:
    """
    Conditional routing function: determines if we should execute tools or skip to quality check.

    Routes to:
    - "tool_execution" if the last AI message has tool_calls
    - "quality_check" if no tool_calls (direct response from LLM)
    """
    messages = state.get('messages', [])
    if not messages:
        return "quality_check"

    last_message = messages[-1]

    # Check if last message is AIMessage with tool_calls
    if isinstance(last_message, AIMessage):
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info("Route: agent_decision → tool_execution (tool calls detected)")
            return "tool_execution"

    logger.info("Route: agent_decision → quality_check (no tool calls)")
    return "quality_check"


def should_continue_after_tools(state: AgentState) -> Literal["agent_decision", "quality_check"]:
    """
    Conditional routing after tool execution: continue to agent or finalize.

    After tools execute, we ALWAYS route back to agent_decision so it can:
    1. See the tool results
    2. Generate a final response based on those results
    3. Or call more tools if needed

    This creates the ReAct loop: Thought → Action → Observation → Thought → ...

    The agent_decision node will then decide whether to call more tools or finalize.
    """
    logger.info("Route: tool_execution → agent_decision (synthesize results)")
    return "agent_decision"


# ============================================================================
# BUILD THE AGENTIC GRAPH
# ============================================================================

def build_hana_agent_graph():
    """
    Build and compile the Hana AI agent graph with 30+ granular tools.

    Graph Structure:
    1. Entry → agent_entry_handler → agent_decision_node
    2. agent_decision_node → tool_execution (if tool_calls) OR quality_check (if no tool_calls)
    3. tool_execution → agent_decision (ALWAYS - to synthesize results)
    4. agent_decision → quality_check (when done - no tool_calls)
    5. quality_check → final_message OR human_takeover
    6. final_message → END
    7. human_takeover → END

    The agent can now compose multiple tools together to handle complex,
    multi-intent messages in a single conversation turn!

    ReAct Flow:
    - Thought (agent_decision with tool_calls)
    - Action (tool_execution)
    - Observation (agent_decision sees tool results)
    - Thought (agent_decision synthesizes response without tool_calls)
    - → Proceeds to quality_check
    """
    logger.info("Building Hana Agent Graph with 30+ granular tools...")

    # Initialize the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent_entry", agent_entry_handler)
    workflow.add_node("agent_decision", agent_decision_node)
    workflow.add_node("tool_execution", tool_execution_node)
    workflow.add_node("quality_check", node_quality_check)
    workflow.add_node("final_message", node_final_message)
    workflow.add_node("human_takeover", node_human_takeover)

    # Set entry point
    workflow.set_entry_point("agent_entry")

    # Entry handler → agent decision
    workflow.add_edge("agent_entry", "agent_decision")

    # Agent decision → tools OR quality check (based on tool_calls)
    workflow.add_conditional_edges(
        "agent_decision",
        should_continue_to_tools,
        {
            "tool_execution": "tool_execution",
            "quality_check": "quality_check"
        }
    )

    # Tool execution → agent decision (ReAct loop) OR quality check (if done)
    workflow.add_conditional_edges(
        "tool_execution",
        should_continue_after_tools,
        {
            "agent_decision": "agent_decision",
            "quality_check": "quality_check"
        }
    )

    # Quality check → final message OR human takeover
    workflow.add_conditional_edges(
        "quality_check",
        quality_router,
        {
            "final_message": "final_message",
            "human_takeover": "human_takeover"
        }
    )

    # Final nodes → END
    workflow.add_edge("final_message", END)
    workflow.add_edge("human_takeover", END)

    # Compile the graph
    hana_agent = workflow.compile()

    logger.info(f"Hana Agent Graph compiled successfully with {len(AGENT_TOOLS)} tools!")
    return hana_agent


# Create the compiled agent
hana_agent = build_hana_agent_graph()
