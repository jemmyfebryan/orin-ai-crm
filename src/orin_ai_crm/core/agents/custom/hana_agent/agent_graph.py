"""
Hana AI Agent - Agentic/Tool-Calling Architecture with 30+ Granular Tools

This implementation uses LangChain's create_agent to handle
the agent loop (Thought → Action → Observation) automatically.

Architecture:
1. agent_entry_handler: Ensures customer_id exists
2. agent_node: Main profiling agent with profiling and customer tools
   - IMPORTANT: get_customer_profile is called DIRECTLY here (not as a tool)
   - This prevents infinite loops and guarantees customer data is loaded
3. route_profiling_router: Decides next route based on profiling completeness
4. sales_node: Sales agent with meeting tools (for B2B or >5 units)
5. ecommerce_node: Ecommerce agent with product tools (for B2C or <=5 units)
6. quality_check_node: Evaluates AI answer quality
7. final_message_node: Adds form if needed and prepares final response
8. human_takeover_node: Triggers human agent takeover

Key Benefits:
- Uses LangChain's modern create_agent API
- LLM can call multiple tools simultaneously for multi-intent messages
- 30+ granular tools for maximum flexibility
- Specialized agents for sales vs ecommerce flows
- More flexible than rigid intent classification
- Better handles complex user requests
- Maintains conversation context and flow
- recursion_limit in graph invocation prevents infinite loops

IMPORTANT ARCHITECTURAL CHANGE:
- get_customer_profile is NOT in the tools list
- It's called directly in agent_node before the LLM runs
- This ensures: (1) Single execution, (2) Fresh data from DB, (3) No loops
"""

import os
import json
from typing import List, Dict

from langgraph.graph import StateGraph, END
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.agents.tools.agent_tools import AGENT_TOOLS
from src.orin_ai_crm.core.agents.tools.profiling_agent_tools import (
    check_profiling_completeness,
)
from src.orin_ai_crm.core.agents.tools.customer_agent_tools import (
    get_customer_profile,
)
from src.orin_ai_crm.core.agents.tools.meeting_agent_tools import SALES_MEETING_TOOLS
from src.orin_ai_crm.core.agents.tools.product_agent_tools import PRODUCT_ECOMMERCE_TOOLS
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db
from src.orin_ai_crm.core.agents.nodes.quality_check_nodes import (
    node_quality_check,
    quality_router,
    node_final_message,
    node_human_takeover
)

logger = get_logger(__name__)

# Initialize LLM with tool calling support
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"), temperature=0)


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

# 6. COMPANY INFORMATION (1 tool):
#    - get_company_profile: Get company profile, address, contact info

# System prompts are now loaded from database via get_prompt_from_db()
# The default prompts are stored in default_prompts.json
# Available prompt keys:
#   - hana_base_agent: Main profiling agent
#   - hana_sales_agent: Sales agent for B2B/large orders
#   - hana_ecommerce_agent: Ecommerce agent for B2C/small orders


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

    logger.info("EXIT: agent_entry_handler")
    logger.info(f"current state: {state}")
    return state


# ============================================================================
# BUILD THE AGENTIC GRAPH USING LANGCHAIN'S CREATE_AGENT
# ============================================================================

async def agent_node(state: AgentState) -> Dict:
    """
    Agent node that creates and executes agent with dynamic system prompt.
    This is the PROFILING agent - handles customer profiling.
    """
    from langchain.agents import create_agent

    logger.info("ENTER: agent_node")

    # === CRITICAL: Load customer profile FIRST (before LLM) ===
    customer_id = state.get('customer_id')
    if customer_id:
        try:
            profile_result = await get_customer_profile.ainvoke({'state': state})
            logger.info(f"Customer profile loaded: {profile_result}")

            # Update state with fresh customer data from database
            if 'customer_data' in state:
                state['customer_data'].update(profile_result)
            else:
                state['customer_data'] = profile_result

            logger.info(f"State updated with customer data: {state['customer_data']}")
        except Exception as e:
            logger.error(f"Failed to load customer profile: {e}")

    # Get system prompt from database (fresh on each invoke)
    system_prompt = await get_prompt_from_db("hana_base_agent")
    if not system_prompt:
        logger.warning("Failed to load hana_base_agent prompt from DB, using fallback")
        system_prompt = "You are Hana, Customer Service AI from ORIN GPS Tracker."

    # Create agent with dynamic system prompt and our AgentState schema
    agent = create_agent(
        model=llm,
        tools=AGENT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,  # Pass our custom AgentState
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
        for k, v in state_updates.items():
            result[k] = v

    logger.info("EXIT: agent_node")

    return result


async def sales_node(state: AgentState) -> Dict:
    """
    Sales node - handles B2B and large order sales flow with meetings.
    """
    from langchain.agents import create_agent

    logger.info("ENTER: sales_node")

    # Get sales agent prompt from database (fresh on each invoke)
    system_prompt = await get_prompt_from_db("hana_sales_agent")
    if not system_prompt:
        logger.warning("Failed to load hana_sales_agent prompt from DB, using fallback")
        system_prompt = "You are Hana, Customer Service AI from ORIN GPS Tracker."

    # Create sales agent with sales tools
    agent = create_agent(
        model=llm,
        tools=SALES_MEETING_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    # Invoke the agent with current state
    result = await agent.ainvoke(state)

    logger.info("EXIT: sales_node")

    return result


async def ecommerce_node(state: AgentState) -> Dict:
    """
    Ecommerce node - handles B2C and small order product inquiries.
    """
    from langchain.agents import create_agent

    logger.info("ENTER: ecommerce_node")

    # Get ecommerce agent prompt from database (fresh on each invoke)
    system_prompt = await get_prompt_from_db("hana_ecommerce_agent")
    if not system_prompt:
        logger.warning("Failed to load hana_ecommerce_agent prompt from DB, using fallback")
        system_prompt = "You are Hana, Customer Service AI from ORIN GPS Tracker."

    # Create ecommerce agent with product tools
    agent = create_agent(
        model=llm,
        tools=PRODUCT_ECOMMERCE_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    # Invoke the agent with current state
    result = await agent.ainvoke(state)

    logger.info("EXIT: ecommerce_node")

    return result


async def route_profiling_router(state: AgentState) -> str:
    """
    Router function that decides the next route after profiling agent.
    Uses check_profiling_completeness to determine if profiling is complete.
    If complete, uses get_customer_profile to get unit_qty and is_b2b.
    Routes:
    - If unit_qty > 5 OR is_b2b == True: ecommerce_node (for B2B/large orders)
    - Else: sales_node (for B2C/small orders)
    - If profiling not complete: node_final_message
    """
    logger.info("ENTER: route_profiling_router")
    
    if state.get("route") != "DEFAULT":
        logger.info(f"Route is not default: {state.get("route")}, leads to custom node")
        if state.get("route") == "ECOMMERCE":
            return "ecommerce_node"
        elif state.get("route") == "SALES":
            return "sales_node"
        else:
            pass

    customer_data = state.get('customer_data', {})
    customer_id = state.get('customer_id')

    logger.info(f"customer_data: {customer_data}")
    logger.info(f"customer_id: {customer_id}")

    # Get customer profile data
    name = customer_data.get('name', '')
    domicile = customer_data.get('domicile', '')
    vehicle_alias = customer_data.get('vehicle_alias', '')
    unit_qty = customer_data.get('unit_qty', 0)
    is_b2b = customer_data.get('is_b2b', False)

    # Check profiling completeness
    profiling_result = await check_profiling_completeness.ainvoke({
        'name': name,
        'domicile': domicile,
        'vehicle_alias': vehicle_alias,
        'unit_qty': unit_qty,
        'is_b2b': is_b2b
    })

    logger.info(f"check_profiling_completeness result: {profiling_result}")

    is_complete = profiling_result.get('is_complete', False)

    if not is_complete:
        logger.info("Profiling is NOT complete - routing to final_message")
        logger.info("EXIT: route_profiling_router -> final_message")
        return "final_message"

    # Profiling is complete - get fresh customer profile from database
    if customer_id:
        profile_result = await get_customer_profile.ainvoke({'state': state})
        logger.info(f"get_customer_profile result: {profile_result}")

        # Get unit_qty and is_b2b from database
        unit_qty = profile_result.get('unit_qty', 0)
        is_b2b = profile_result.get('is_b2b', False)

        logger.info(f"unit_qty: {unit_qty}, is_b2b: {is_b2b}")

        # Route based on unit_qty and is_b2b
        if unit_qty > 5 or is_b2b:
            logger.info("Routing to sales_node (B2C or <=5 units)")
            logger.info("EXIT: route_profiling_router -> sales_node")
            return "sales_node"
        else:
            logger.info("Routing to ecommerce_node (B2B or >5 units)")
            logger.info("EXIT: route_profiling_router -> ecommerce_node")
            return "ecommerce_node"

    # Fallback - should not reach here
    logger.warning("Could not determine route - defaulting to final_message")
    logger.info("EXIT: route_profiling_router -> final_message (fallback)")
    return "final_message"


def build_hana_agent_graph():
    """
    Build and compile the Hana AI agent graph using LangChain's create_agent.

    Graph Structure:
    1. Entry → agent_entry_handler → agent_node (profiling agent)
    2. agent_node → route_profiling_router (decides next route)
    3. route_profiling_router → sales_node OR ecommerce_node OR final_message
    4. sales_node → quality_check
    5. ecommerce_node → quality_check
    6. final_message → END
    7. quality_check → final_message OR human_takeover
    8. human_takeover → END

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
    workflow.add_node("sales_node", sales_node)
    workflow.add_node("ecommerce_node", ecommerce_node)
    workflow.add_node("quality_check", node_quality_check)
    workflow.add_node("final_message", node_final_message)
    workflow.add_node("human_takeover", node_human_takeover)

    # Set entry point
    workflow.set_entry_point("agent_entry")

    # Entry handler → Agent (profiling)
    workflow.add_edge("agent_entry", "agent")

    # Agent → route_profiling_router (decides next route after profiling)
    workflow.add_conditional_edges(
        "agent",
        route_profiling_router,
        {
            "sales_node": "sales_node",
            "ecommerce_node": "ecommerce_node",
            "final_message": "final_message"
        }
    )

    # Sales node → quality check
    workflow.add_edge("sales_node", "quality_check")

    # Ecommerce node → quality check
    workflow.add_edge("ecommerce_node", "quality_check")

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

    logger.info(f"Hana Agent Graph compiled successfully with {len(AGENT_TOOLS)} profiling tools!")
    logger.info(f"Sales agent has {len(SALES_MEETING_TOOLS)} tools")
    logger.info(f"Ecommerce agent has {len(PRODUCT_ECOMMERCE_TOOLS)} tools")
    logger.info("Using LangChain's create_agent for agent loop handling")
    return hana_agent


# Create the compiled agent
hana_agent = build_hana_agent_graph()
