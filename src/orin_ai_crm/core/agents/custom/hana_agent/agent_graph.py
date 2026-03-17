"""
Hana AI Agent - Orchestrator-Worker Architecture

This implementation uses the Orchestrator pattern (also known as Supervisor pattern)
for multi-agent collaboration. The orchestrator acts as a traffic controller that
decides which worker agent to call next based on customer context and conversation.

Architecture:
1. agent_entry_handler: Ensures customer_id exists
2. orchestrator_node: Traffic controller that decides which worker to call
3. profiling_node: Collects and updates customer data (name, domicile, vehicle, unit_qty, is_b2b)
4. sales_node: Handles B2B inquiries, meeting scheduling, large orders (>5 units)
5. ecommerce_node: Handles product questions, pricing, catalog, small orders (≤5 units)
6. orchestrator_router: Routes from orchestrator to appropriate worker
7. quality_check_node: Evaluates AI answer quality
8. final_message_node: Adds form if needed and prepares final response
9. human_takeover_node: Triggers human agent takeover

Flow:
Entry → Orchestrator → Worker (profiling/sales/ecommerce) → Orchestrator → Worker → ...
                  ↓
             (loops until orchestrator says "final")
                  ↓
             quality_check → final_message/human_takeover

Key Benefits:
- True multi-agent collaboration with intelligent routing
- Orchestrator can call multiple agents in sequence
- Handles complex scenarios (e.g., B2B + product inquiry)
- Each worker agent has focused tools and personality
- Orchestrator makes decisions based on full conversation context
- Easy to add new worker agents (support, billing, technical)
- Uses LangChain's modern create_agent API
- LLM can call multiple tools simultaneously for multi-intent messages
- Maintains conversation context and flow
- recursion_limit in graph invocation prevents infinite loops

IMPORTANT ARCHITECTURAL CHANGE:
- get_customer_profile is NOT in the tools list
- It's called directly in profiling_node before the LLM runs
- This ensures: (1) Single execution, (2) Fresh data from DB, (3) No loops
"""

import os
import json
from typing import Dict

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.agents.tools.agent_tools import (
    ORCHESTRATOR_TOOLS,
    PROFILING_AGENT_TOOLS,
    SALES_AGENT_TOOLS,
    ECOMMERCE_AGENT_TOOLS,
)
from src.orin_ai_crm.core.agents.tools.customer_agent_tools import (
    get_customer_profile,
)
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


async def agent_entry_handler(state: AgentState) -> Dict:
    """
    Entry point handler - ensures customer_id exists and builds system prompt.
    Also initializes orchestrator tracking fields.
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

    # Initialize orchestrator tracking fields
    if 'orchestrator_step' not in state:
        state['orchestrator_step'] = 0
    if 'max_orchestrator_steps' not in state:
        state['max_orchestrator_steps'] = 5
    if 'agents_called' not in state:
        state['agents_called'] = []
    if 'orchestrator_plan' not in state:
        state['orchestrator_plan'] = ""
    if 'orchestrator_decision' not in state:
        state['orchestrator_decision'] = {}

    logger.info("EXIT: agent_entry_handler")
    logger.info(f"current state: {state}")
    return state


# ============================================================================
# ORCHESTRATOR NODE
# ============================================================================

async def orchestrator_node(state: AgentState) -> Dict:
    """
    Orchestrator node - decides which worker agent to call next.

    This is the traffic controller of the multi-agent system.
    Uses LLM with structured output to make routing decisions.
    """
    from langchain.agents import create_agent

    logger.info("ENTER: orchestrator_node")

    step = state.get("orchestrator_step", 0)
    max_steps = state.get("max_orchestrator_steps", 5)
    agents_called = state.get("agents_called", [])

    logger.info(f"Orchestrator step {step}/{max_steps}")
    logger.info(f"Agents called so far: {agents_called}")

    # Get customer context
    customer_data = state.get('customer_data', {})
    messages = state.get('messages', [])

    # Build conversation summary (last 5 messages for context)
    conversation_summary = "\n".join([
        f"{msg.type}: {msg.content[:100]}..."
        for msg in messages[-5:] if hasattr(msg, 'content')
    ])

    # Get latest user message
    latest_message = ""
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == "human":
            latest_message = msg.content
            break

    # Get orchestrator prompt from DB
    system_prompt = await get_prompt_from_db("hana_orchestrator_agent")
    if not system_prompt:
        logger.error("Failed to load orchestrator prompt from DB! Using fallback.")
        system_prompt = """You are a router. Decide next agent: profiling, sales, ecommerce, or final.
Return JSON: {"next_agent": "profiling|sales|ecommerce|final", "reasoning": "...", "plan": "..."}"""

    # Fill in context variables
    try:
        system_prompt = system_prompt.format(
            name=customer_data.get('name', ''),
            domicile=customer_data.get('domicile', ''),
            vehicle_alias=customer_data.get('vehicle_alias', ''),
            unit_qty=customer_data.get('unit_qty', 0),
            is_b2b=customer_data.get('is_b2b', False),
            is_complete=customer_data.get('is_onboarded', False),
            agents_called=agents_called,
            orchestrator_step=step,
            max_orchestrator_steps=max_steps,
            latest_message=latest_message,
            conversation_history=conversation_summary
        )
    except KeyError as e:
        logger.error(f"Missing variable in orchestrator prompt: {e}")
        logger.error("Using prompt without formatting")
        # Continue with unformatted prompt

    # Create orchestrator agent with structured output (JSON mode)
    llm_with_structured_output = llm.bind(
        response_format={"type": "json_object"}
    )

    agent = create_agent(
        model=llm_with_structured_output,
        tools=ORCHESTRATOR_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    # Invoke orchestrator
    result = await agent.ainvoke(state, recursion_limit=3)

    # Extract routing decision from last message
    last_message = result.get("messages", [])[-1]

    try:
        # Parse JSON decision
        decision = json.loads(last_message.content)

        next_agent = decision.get("next_agent", "final")
        reasoning = decision.get("reasoning", "")
        plan = decision.get("plan", "")

        logger.info(f"Orchestrator decision: {next_agent}")
        logger.info(f"Reasoning: {reasoning}")
        logger.info(f"Plan: {plan}")

        # Update state with decision
        result["orchestrator_decision"] = decision
        result["orchestrator_plan"] = plan

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse orchestrator decision: {e}")
        logger.error(f"Raw content: {last_message.content}")
        # Default to final if parsing fails
        result["orchestrator_decision"] = {"next_agent": "final", "reasoning": "Parse error", "plan": "End conversation"}

    logger.info("EXIT: orchestrator_node")
    return result


async def orchestrator_router(state: AgentState) -> str:
    """
    Router that reads orchestrator decision and routes to appropriate worker.

    Enforces two safety limits:
    1. Max orchestrator steps (prevents infinite loops)
    2. Hard-cap per agent (each agent can only be called once per chat request)
    """
    logger.info("ENTER: orchestrator_router")

    # Check safety limit: max steps
    step = state.get("orchestrator_step", 0)
    max_steps = state.get("max_orchestrator_steps", 5)

    if step >= max_steps:
        logger.warning(f"Max orchestrator steps reached ({step}), forcing final")
        logger.info("EXIT: orchestrator_router -> quality_check")
        return "quality_check"

    # Get orchestrator decision
    decision = state.get("orchestrator_decision", {})
    next_agent = decision.get("next_agent", "final")

    logger.info(f"Routing decision: {next_agent}")

    # HARD CAP: Check if agent was already called in this chat request
    agents_called = state.get("agents_called", [])

    if next_agent in agents_called:
        logger.warning(f"Agent '{next_agent}' already called in this chat: {agents_called}")
        logger.warning(f"Forcing route to quality_check (hard-cap enforced)")
        logger.info("EXIT: orchestrator_router -> quality_check (hard-cap)")
        return "quality_check"

    # Map to node names
    if next_agent == "profiling":
        logger.info("EXIT: orchestrator_router -> profiling_node")
        return "profiling_node"
    elif next_agent == "sales":
        logger.info("EXIT: orchestrator_router -> sales_node")
        return "sales_node"
    elif next_agent == "ecommerce":
        logger.info("EXIT: orchestrator_router -> ecommerce_node")
        return "ecommerce_node"
    else:  # "final" or unknown
        logger.info("EXIT: orchestrator_router -> quality_check")
        return "quality_check"


# ============================================================================
# WORKER NODES
# ============================================================================

async def profiling_node(state: AgentState) -> Dict:
    """
    Profiling node - collects and updates customer data.

    This is the PROFILING agent - handles customer onboarding,
    data collection, and profile updates.
    """
    from langchain.agents import create_agent

    logger.info("ENTER: profiling_node")

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

    # Get profiling agent prompt from database (reuse hana_base_agent)
    system_prompt = await get_prompt_from_db("hana_base_agent")
    if not system_prompt:
        logger.warning("Failed to load hana_base_agent prompt from DB, using fallback")
        system_prompt = "You are Hana, Customer Service AI from ORIN GPS Tracker. Collect customer data."

    # Create profiling agent with profiling tools
    agent = create_agent(
        model=llm,
        tools=PROFILING_AGENT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    # Invoke the agent
    result = await agent.ainvoke(state, recursion_limit=8)

    # Load fresh customer data after profiling
    if customer_id:
        try:
            profile_result = await get_customer_profile.ainvoke({'state': result})
            logger.info(f"Customer profile refreshed: {profile_result}")

            if 'customer_data' in result:
                result['customer_data'].update(profile_result)
            else:
                result['customer_data'] = profile_result

        except Exception as e:
            logger.error(f"Failed to refresh customer profile: {e}")

    # Track that this agent was called
    agents_called = result.get("agents_called", [])
    agents_called.append("profiling")
    result["agents_called"] = list(set(agents_called))  # Remove duplicates

    # Increment orchestrator step
    result["orchestrator_step"] = state.get("orchestrator_step", 0) + 1

    logger.info("EXIT: profiling_node")
    return result


async def sales_node(state: AgentState) -> Dict:
    """
    Sales node - handles B2B and large order sales flow with meetings.
    """
    from langchain.agents import create_agent

    logger.info("ENTER: sales_node")

    # Get sales agent prompt from database
    system_prompt = await get_prompt_from_db("hana_sales_agent")
    if not system_prompt:
        logger.warning("Failed to load hana_sales_agent prompt from DB, using fallback")
        system_prompt = "You are Hana, Customer Service AI from ORIN GPS Tracker."

    # Create sales agent with sales tools
    agent = create_agent(
        model=llm,
        tools=SALES_AGENT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    # Invoke the agent with current state
    result = await agent.ainvoke(state, recursion_limit=10)

    # Track that this agent was called
    agents_called = result.get("agents_called", [])
    agents_called.append("sales")
    result["agents_called"] = list(set(agents_called))  # Remove duplicates

    # Increment orchestrator step
    result["orchestrator_step"] = state.get("orchestrator_step", 0) + 1

    logger.info("EXIT: sales_node")
    return result


async def ecommerce_node(state: AgentState) -> Dict:
    """
    Ecommerce node - handles B2C and small order product inquiries.
    """
    from langchain.agents import create_agent

    logger.info("ENTER: ecommerce_node")

    # Get ecommerce agent prompt from database
    system_prompt = await get_prompt_from_db("hana_ecommerce_agent")
    if not system_prompt:
        logger.warning("Failed to load hana_ecommerce_agent prompt from DB, using fallback")
        system_prompt = "You are Hana, Customer Service AI from ORIN GPS Tracker."

    # Create ecommerce agent with product tools
    agent = create_agent(
        model=llm,
        tools=ECOMMERCE_AGENT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    # Invoke the agent with current state
    result = await agent.ainvoke(state, recursion_limit=10)

    # Track that this agent was called
    agents_called = result.get("agents_called", [])
    agents_called.append("ecommerce")
    result["agents_called"] = list(set(agents_called))  # Remove duplicates

    # Increment orchestrator step
    result["orchestrator_step"] = state.get("orchestrator_step", 0) + 1

    logger.info("EXIT: ecommerce_node")
    return result


# ============================================================================
# BUILD THE GRAPH
# ============================================================================

def build_hana_agent_graph():
    """
    Build Hana AI agent graph with Orchestrator-Worker pattern.

    Graph Structure:
    1. Entry → orchestrator_node (decides first agent)
    2. orchestrator_node → orchestrator_router (routes to worker)
    3. Worker (profiling/sales/ecommerce) → orchestrator_node (back to orchestrator)
    4. Loop: orchestrator → worker → orchestrator → worker → ...
    5. When orchestrator says "final" → quality_check
    6. quality_check → final_message OR human_takeover
    7. final_message → END
    8. human_takeover → END

    The orchestrator:
    - Analyzes customer context and conversation intent
    - Decides which worker agent to call next
    - Can call multiple agents in sequence
    - Knows when conversation is complete

    Worker agents:
    - profiling_agent: Collects/updates customer data
    - sales_agent: Handles B2B, meetings, large orders
    - ecommerce_agent: Handles products, pricing, small orders
    """
    logger.info("Building Hana Agent Graph with Orchestrator-Worker pattern...")

    # Initialize the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent_entry", agent_entry_handler)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("profiling_node", profiling_node)
    workflow.add_node("sales_node", sales_node)
    workflow.add_node("ecommerce_node", ecommerce_node)
    workflow.add_node("quality_check", node_quality_check)
    workflow.add_node("final_message", node_final_message)
    workflow.add_node("human_takeover", node_human_takeover)

    # Set entry point
    workflow.set_entry_point("agent_entry")

    # Entry handler → Orchestrator (traffic controller)
    workflow.add_edge("agent_entry", "orchestrator")

    # Orchestrator → orchestrator_router (decides which worker)
    workflow.add_conditional_edges(
        "orchestrator",
        orchestrator_router,
        {
            "profiling_node": "profiling_node",
            "sales_node": "sales_node",
            "ecommerce_node": "ecommerce_node",
            "quality_check": "quality_check"
        }
    )

    # ALL workers → back to orchestrator (the loop!)
    workflow.add_edge("profiling_node", "orchestrator")
    workflow.add_edge("sales_node", "orchestrator")
    workflow.add_edge("ecommerce_node", "orchestrator")

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

    logger.info("Hana Agent Graph compiled with Orchestrator-Worker pattern!")
    logger.info(f"Orchestrator tools: {len(ORCHESTRATOR_TOOLS)}")
    logger.info(f"Profiling agent tools: {len(PROFILING_AGENT_TOOLS)}")
    logger.info(f"Sales agent tools: {len(SALES_AGENT_TOOLS)}")
    logger.info(f"Ecommerce agent tools: {len(ECOMMERCE_AGENT_TOOLS)}")
    logger.info("Using LangChain's create_agent for agent loop handling")
    return hana_agent


# Create the compiled agent
hana_agent = build_hana_agent_graph()
