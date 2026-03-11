"""
Hana AI Agent - Agentic/Tool-Calling Architecture with 30+ Granular Tools

This implementation uses LangChain's create_agent to handle
the agent loop (Thought → Action → Observation) automatically.

Architecture:
1. agent_entry_handler: Ensures customer_id exists
2. react_agent: LangChain's create_agent with 27 tools
3. quality_check_node: Evaluates AI answer quality
4. final_message_node: Adds form if needed and prepares final response
5. human_takeover_node: Triggers human agent takeover

Key Benefits:
- Uses LangChain's modern create_agent API
- LLM can call multiple tools simultaneously for multi-intent messages
- 27 granular tools for maximum flexibility
- More flexible than rigid intent classification
- Better handles complex user requests
- Maintains conversation context and flow
"""

import os
import json
from typing import List, Dict

from langgraph.graph import StateGraph, END
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI

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


#    - search_vehicle_in_vps: Search vehicle in VPS database
#    - create_lead_routing: Create lead routing when profiling complete
# System prompt for the agent

# 3. SALES & MEETING (6 tools):
#    - get_pending_meeting: Get existing meeting
#    - extract_meeting_details: Extract meeting info from message
#    - book_or_update_meeting_db: Book/update meeting in database
#    - generate_meeting_negotiation_message: Generate negotiation message
#    - generate_meeting_confirmation: Generate confirmation message
#    - generate_existing_meeting_reminder: Generate reminder for existing meeting

# 4. PRODUCT & E-COMMERCE (8 tools):
#    - get_all_active_products: Get all products from database
#    - search_products: Search products by keyword/category/vehicle
#    - get_product_details: Get detailed product info
#    - answer_product_question: Answer product questions
#    - get_ecommerce_links: Get e-commerce purchase links
#    - create_product_inquiry: Create product inquiry record
#    - get_pending_product_inquiry: Get existing inquiry
#    - recommend_products_for_customer: Recommend products

# 5. SUPPORT & COMPLAINTS (3 tools):
#    - classify_issue_type: Classify issue (complaint/support/general)
#    - generate_empathetic_response: Generate empathetic response
#    - set_human_takeover_flag: Trigger human takeover

HANA_AGENT_SYSTEM_PROMPT = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.

Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

ATURAN PRODUK GPS:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin)
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak)

KEMAMPUAN TOOL (6 tools tersedia):
Kamu memiliki banyak tools yang dapat membantu customer. Tool-category terbagi menjadi:

1. CUSTOMER MANAGEMENT (2 tools):
   - get_customer_profile: Get customer profile data
   - update_customer_data: Update specific customer fields

2. PROFILING (4 tools):
   - extract_customer_info_from_message: Extract info from message using LLM
   - check_profiling_completeness: Check if profiling is complete
   - determine_next_profiling_field: Determine what to ask next

Alur Percakapan:
1. Mulai dengan get_customer_profile untuk identify customer
2. Pakai tool check_profiling_completeness untuk mengecek apakah profil user sudah lengkap atau belum

INGAT: Database adalah sumber kebenaran. JANGAN mengarang info.
"""


# 3. Setelah profiling lengkap → determine route (SALES vs ECOMMERCE)
# 4. SALES: Tawarkan meeting, gunakan meeting tools
# 5. ECOMMERCE: Jawab pertanyaan produk, berikan rekomendasi



def build_system_prompt(state: AgentState) -> str:
    """
    Build system prompt with customer profile context.
    This is passed to the agent as system_prompt.
    """
    customer_data = state.get('customer_data', {})
    customer_id = state.get('customer_id')
    contact_name = state.get('contact_name')

    customer_name = customer_data.get('name') or contact_name or 'Kak'

    context_info = f"""Customer Profile:
- Nama: {customer_name}
- Domisili: {customer_data.get('domicile', 'Belum diketahui')}
- Kendaraan: {customer_data.get('vehicle_alias', 'Belum diketahui')}
- Jumlah Unit: {customer_data.get('unit_qty', 0)}
- B2B: {customer_data.get('is_b2b', False)}
- Customer ID: {customer_id or 'Belum ada'}

Customer Identifier:
- Phone Number: {state.get('phone_number') or 'N/A'}
- LID Number: {state.get('lid_number') or 'N/A'}

{HANA_AGENT_SYSTEM_PROMPT}
"""

    return context_info


async def agent_entry_handler(state: AgentState) -> Dict:
    """
    Entry point handler - ensures customer_id exists and builds system prompt.
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_or_create_customer

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

        # Build customer_data from customer Dict
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

    # Build system prompt with customer context
    customer_data = state.get('customer_data', {})
    customer_id = state.get('customer_id')
    contact_name = state.get('contact_name')
    customer_name = customer_data.get('name') or contact_name or 'Kak'

#     system_prompt = f"""Customer Profile:
# - Nama: {customer_name}
# - Domisili: {customer_data.get('domicile', 'Belum diketahui')}
# - Kendaraan: {customer_data.get('vehicle_alias', 'Belum diketahui')}
# - Jumlah Unit: {customer_data.get('unit_qty', 0)}
# - B2B: {customer_data.get('is_b2b', False)}
# - Customer ID: {customer_id or 'Belum ada'}

# Customer Identifier:
# - Phone Number: {state.get('phone_number') or 'N/A'}
# - LID Number: {state.get('lid_number') or 'N/A'}

# {HANA_AGENT_SYSTEM_PROMPT}
# """

    # Store system prompt in state for the agent to use
    # state['system_prompt'] = system_prompt

    logger.info("EXIT: agent_entry_handler")
    logger.info(f"current state: {state}")
    return state


# ============================================================================
# BUILD THE AGENTIC GRAPH USING LANGCHAIN'S CREATE_AGENT
# ============================================================================

async def agent_node(state: AgentState) -> Dict:
    """
    Agent node that creates and executes agent with dynamic system prompt.
    """
    from langchain.agents import create_agent

    # Get system prompt from state (built by agent_entry_handler)
    system_prompt = HANA_AGENT_SYSTEM_PROMPT

    logger.info("ENTER: agent_node")

    # Create agent with dynamic system prompt and our AgentState schema
    agent = create_agent(
        model=llm,
        tools=AGENT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState  # Pass our custom AgentState
    )

    # Invoke the agent with current state
    result = await agent.ainvoke(state)
    
    # Detecting Route changes from tools
    new_messages: List = result.get("messages", [])
    
    state_updates = {}

    # Scan messages for tool results
    for msg in new_messages:
        # Only process ToolMessage types (results from tool execution)
        if isinstance(msg, ToolMessage):
            try:
                # Tool outputs are usually JSON strings
                data: Dict = json.loads(msg.content)
                data_update_state = data.get("update_state")
                if isinstance(data_update_state, dict):
                    state_updates.update(data_update_state)
                    logger.info(f"Tool: {msg.name} update states: {data_update_state}")
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse tool output: {e}, msg.content: {msg.content}")

    if state_updates:
        logger.info(f"Final tool state_updates: {state_updates}")

    logger.info("EXIT: agent_node")

    return result


def build_hana_agent_graph():
    """
    Build and compile the Hana AI agent graph using LangChain's create_agent.

    Graph Structure:
    1. Entry → agent_entry_handler → agent_node
    2. agent_node → (handles tool calling and execution automatically)
    3. agent_node → quality_check (when agent is done)
    4. quality_check → final_message OR human_takeover
    5. final_message → END
    6. human_takeover → END

    The create_agent handles:
    - Agent decision making (which tools to call)
    - Tool execution
    - Routing back to agent after tools
    - Agent loop (Thought → Action → Observation → Thought)

    We provide:
    - The LLM model
    - The tools
    - Dynamic system prompt with customer context
    """
    logger.info("Building Hana Agent Graph with LangChain's create_agent...")

    # Initialize the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent_entry", agent_entry_handler)
    workflow.add_node("agent", agent_node)
    workflow.add_node("quality_check", node_quality_check)
    workflow.add_node("final_message", node_final_message)
    workflow.add_node("human_takeover", node_human_takeover)

    # Set entry point
    workflow.set_entry_point("agent_entry")

    # Entry handler → Agent
    workflow.add_edge("agent_entry", "agent")

    # Agent → quality check (when agent is done with all tool calls)
    workflow.add_edge("agent", "quality_check")

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
    logger.info("Using LangChain's create_agent for agent loop handling")
    return hana_agent


# Create the compiled agent
hana_agent = build_hana_agent_graph()
