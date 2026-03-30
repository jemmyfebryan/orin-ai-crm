"""
Hana AI Agent - Orchestrator-Worker Architecture

This implementation uses the Orchestrator pattern (also known as Supervisor pattern)
for multi-agent collaboration. The orchestrator acts as a traffic controller that
decides which worker agent to call next based on customer context and conversation.

Architecture:
1. agent_entry_handler: Ensures customer_id exists
2. orchestrator_node: Traffic controller that decides which worker to call
3. profiling_node: Collects and updates customer data (name, domicile, vehicle, unit_qty, is_b2b)
4. sales_node: Handles B2B/large volume customers, qualifies for meeting → human takeover or ecommerce
5. ecommerce_node: Handles product questions, pricing, catalog, recommendations
6. support_node: Handles complaints, technical support, and issues
7. orchestrator_router: Routes from orchestrator to appropriate worker
8. quality_check_node: Evaluates AI answer quality
9. final_message_node: Adds form if needed and prepares final response
10. human_takeover_node: Triggers human agent takeover

Flow:
Entry → Orchestrator → Worker (profiling/sales/ecommerce/support) → Orchestrator → Worker → ...
                  ↓
             (loops until orchestrator says "final")
                  ↓
             final_message → quality_check → END/human_takeover

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
import asyncio
import json
import re
from typing import Dict, Literal
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.custom.hana_agent.custom_agent import create_custom_agent
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config, get_llm
from src.orin_ai_crm.core.agents.tools.agent_tools import (
    ORCHESTRATOR_TOOLS,
    PROFILING_AGENT_TOOLS,
    SALES_AGENT_TOOLS,
    ECOMMERCE_AGENT_TOOLS,
    SUPPORT_AGENT_TOOLS,
)
from src.orin_ai_crm.core.agents.tools.customer_agent_tools import (
    get_customer_profile,
)
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db, get_agent_name
from src.orin_ai_crm.core.agents.nodes.quality_check_nodes import (
    node_quality_check,
    quality_router,
    node_final_message,
    node_human_takeover
)

logger = get_logger(__name__)

# ============================================================================
# TIERED LLM CONFIGURATION
# ============================================================================
# Advanced: Best reasoning and tool calling (orchestrator, ecommerce, profiling)
# Medium: Balanced performance (sales, support)
# Basic: Fast and cost-effective (quality check, final message)
orchestrator_llm = get_llm("advanced")      # Complex routing decisions
ecommerce_llm = get_llm("advanced")         # Heavy tool calling, fixes hallucination
profiling_llm = get_llm("advanced")         # Structured data extraction
sales_llm = get_llm("medium")               # Simple qualification flow
support_llm = get_llm("medium")             # FAQ-style responses
final_message_llm = get_llm("basic")        # Template-based (user requested basic)
quality_check_llm = get_llm("basic")        # Simple validation

# Legacy single LLM (kept for backward compatibility in some tools)
llm = get_llm("medium")


# ============================================================================
# CUSTOM AGENT REACT PROMPTS
# ============================================================================
# These prompts control how agents decide which tools to call and when to stop

ECOMMERCE_REACT_PROMPT = """
You are an ecommerce assistant helping customers with product information.

CRITICAL - UNDERSTAND CONVERSATION CONTEXT:
You have access to message_history which contains the previous conversation.
ALWAYS check message_history FIRST before deciding which products to show.

Common Contextual Requests:
- "produknya" (the product) → refers to LAST product discussed in conversation
- "foto produknya" → images for the SPECIFIC product mentioned earlier
- "link tokopedianya" → e-commerce links for the SPECIFIC product mentioned

Examples of Contextual Requests:
- User discussed OBU V → asks "minta foto dan link produknya dong"
  → CALL get_ecommerce_links ONLY for OBU V (product_id 12, sort_order 2)
  → DO NOT call for all 9 products

- User discussed AI CAM → asks "ada linknya?"
  → CALL get_ecommerce_links ONLY for AI CAM
  → DO NOT call for all products

IMPORTANT TOOL CALLING STRATEGY:
1. CHECK message_history for which product was discussed
2. IF user is specific ("produknya", "that product", "the one you mentioned"):
   - Call tools ONLY for that specific product
3. IF user is general BUT no specific product was discussed:
   - Call get_all_active_products
   - Call get_ecommerce_links for top 3 products (sort_orders 1, 2, 3)
   - This is better than calling for all 9 products
4. IF user explicitly asks for all products ("semua", "all"):
   - You can call for multiple products

Tool Usage Rules:
- Links → call get_ecommerce_links for RELEVANT products (typically 1-3 products max)
- Images → call send_product_images with sort_orders (max 3 images)
- Details → call get_product_details for specific products
- Catalog → call send_catalog

When to Stop:
- Only stop after you've called tools for the RELEVANT products
- If user asks about "produknya" (singular), call tools for 1 product only
- If user asks generally without context, show top 3 products
"""


# ============================================================================
# ORCHESTRATOR DECISION SCHEMA
# ============================================================================

def extract_json_from_text(text: str) -> str:
    """
    Extract JSON object from text that may contain additional content.

    Args:
        text: Text that contains JSON, possibly with extra text before/after

    Returns:
        Extracted JSON string, or original text if no JSON found
    """
    # Try to find JSON object in the text
    # Look for opening brace
    start_idx = text.find("{")
    if start_idx == -1:
        return text

    # Count braces to find matching closing brace
    brace_count = 0
    in_string = False
    escape_next = False
    for i in range(start_idx, len(text)):
        char = text[i]

        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if not in_string:
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    # Found matching closing brace
                    return text[start_idx:i+1]

    # If no complete JSON found, return original
    return text


class OrchestratorDecision(BaseModel):
    """Orchestrator routing decision schema with forced output structure."""
    next_agent: Literal["profiling", "sales", "ecommerce", "support", "final"] = Field(
        description="Next agent to call: profiling, sales, ecommerce, support, or final"
    )
    reasoning: str = Field(
        description="Brief explanation of your decision"
    )
    plan: str = Field(
        description="What happens next"
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def apply_tool_state_updates(result: Dict) -> Dict:
    """
    Scan tool results for update_state and apply them to the agent result.

    Tools can return JSON with {"update_state": {...}} to modify the agent state.
    This function extracts those updates and applies them to the result.

    Args:
        result: The result dict from agent execution with "messages" key

    Returns:
        The updated result dict with state changes applied
    """
    import json
    from langchain_core.messages import ToolMessage

    new_messages = result.get("messages", [])
    state_updates = {}

    # Scan messages for tool results
    for msg in new_messages:
        # Only process ToolMessage types (results from tool execution)
        if isinstance(msg, ToolMessage):
            try:
                # Tool outputs are usually JSON strings
                data = json.loads(msg.content)
                data_update_state = data.get("update_state")
                if isinstance(data_update_state, dict):
                    state_updates.update(data_update_state)
                    logger.info(f"Tool: {msg.name} update states: {data_update_state}")
            except (json.JSONDecodeError, TypeError) as e:
                # Ignore non-JSON tool outputs
                pass

    # Apply state updates to result
    if state_updates:
        logger.info(f"Final tool state_updates: {state_updates}")
        for k, v in state_updates.items():
            result[k] = v

    return result


async def agent_entry_handler(state: AgentState) -> Dict:
    """
    Entry point handler - ensures customer_id exists and builds system prompt.
    Also initializes orchestrator tracking fields.
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_or_create_customer

    logger.info("ENTER: agent_entry_handler")

    # Debug: Check messages list at entry
    messages_at_entry = state.get('messages', [])
    # logger.info(f"state.get('messages') has {len(messages_at_entry)} messages at agent_entry_handler")
    for i, msg in enumerate(messages_at_entry):
        msg_type = type(msg).__name__
        content = msg.content[:50] if hasattr(msg, 'content') else 'N/A'
        logger.info(f"  messages[{i}]: [{msg_type}] {content}...")

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
    if 'human_takeover' not in state:
        state['human_takeover'] = False

    logger.info("EXIT: agent_entry_handler")
    logger.info(f"current state: {state}")

    # IMPORTANT: Don't return 'messages' to avoid triggering operator.add reducer
    # which would duplicate messages. Only return fields we've modified.
    result = {}
    if 'customer_id' in state:
        result['customer_id'] = state['customer_id']
    if 'customer_data' in state:
        result['customer_data'] = state['customer_data']
    if 'send_form' in state:
        result['send_form'] = state['send_form']
    if 'orchestrator_step' in state:
        result['orchestrator_step'] = state['orchestrator_step']
    if 'max_orchestrator_steps' in state:
        result['max_orchestrator_steps'] = state['max_orchestrator_steps']
    if 'agents_called' in state:
        result['agents_called'] = state['agents_called']
    if 'orchestrator_plan' in state:
        result['orchestrator_plan'] = state['orchestrator_plan']
    if 'orchestrator_decision' in state:
        result['orchestrator_decision'] = state['orchestrator_decision']
    if 'human_takeover' in state:
        result['human_takeover'] = state['human_takeover']

    return result


# ============================================================================
# ORCHESTRATOR NODE
# ============================================================================

async def orchestrator_node(state: AgentState) -> Dict:
    """
    Orchestrator node - decides which worker agent to call next.

    This is the traffic controller of the multi-agent system.
    Uses LLM with structured output to make routing decisions.
    """
    logger.info("ENTER: orchestrator_node")

    step = state.get("orchestrator_step", 0)
    max_steps = state.get("max_orchestrator_steps", 5)
    agents_called = state.get("agents_called", [])

    logger.info(f"Orchestrator step {step}/{max_steps}")
    logger.info(f"Agents called so far: {agents_called}")

    # Get customer context
    customer_data = state.get('customer_data', {})
    messages = state.get('messages', [])
    messages_history = state.get('messages_history', [])

    # Debug logging to understand message flow
    # logger.info(f"messages_history has {len(messages_history)} messages")
    # logger.info(f"messages has {len(messages)} messages")

    # Show all messages in 'messages' list
    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        content = msg.content[:50] if hasattr(msg, 'content') else 'N/A'
        # logger.info(f"  messages[{i}]: [{msg_type}] {content}...")

    if messages_history:
        last_history_content = messages_history[-1].content[:50] if hasattr(messages_history[-1], 'content') else 'N/A'
        # logger.info(f"Last history message: {last_history_content}...")
    if messages:
        last_msg_content = messages[-1].content[:50] if hasattr(messages[-1], 'content') else 'N/A'
        # logger.info(f"Last current message: {last_msg_content}...")

    # Combine messages_history + messages for full conversation context
    # This is CRITICAL for understanding responses like "boleh" (yes) to previous questions
    all_messages = list(messages_history) + list(messages)

    # Get orchestrator prompt from DB
    system_prompt = await get_prompt_from_db("hana_orchestrator_agent")
    if not system_prompt:
        logger.error("Failed to load orchestrator prompt from DB! Using fallback.")
        system_prompt = """You are a router. Decide next agent: profiling, sales, ecommerce, or final."""

    # Get agent name
    agent_name = get_agent_name()

    # Fill in context variables
    # Build a concise state summary instead of dumping entire state
    # Include LAST 5 MESSAGES from full conversation (history + current)
    state_summary = f"""
Total messages in conversation (history + current): {len(all_messages)}
Customer ID: {state.get('customer_id', 'N/A')}
Send Form: {state.get('send_form', False)}
Human Takeover: {state.get('human_takeover', False)}
Last 5 messages from full conversation:
"""
    # Add last 5 messages from combined history + current
    for msg in all_messages[-5:]:
        if hasattr(msg, 'type'):
            msg_type = msg.type
        elif isinstance(msg, dict):
            msg_type = msg.get('type', msg.get('role', 'unknown'))
        else:
            msg_type = 'unknown'

        if hasattr(msg, 'content'):
            content = msg.content[:150]
        elif isinstance(msg, dict):
            content = str(msg.get('content', ''))[:150]
        else:
            content = str(msg)[:150]

        state_summary += f"- [{msg_type}] {content}...\n"

    try:
        system_prompt = system_prompt.format(
            agent_name=agent_name,
            name=customer_data.get('name', ''),
            domicile=customer_data.get('domicile', ''),
            vehicle_alias=customer_data.get('vehicle_alias', ''),
            unit_qty=customer_data.get('unit_qty', 0),
            is_b2b=customer_data.get('is_b2b', False),
            is_complete=customer_data.get('is_onboarded', False),
            agents_called=agents_called,
            orchestrator_step=step,
            max_orchestrator_steps=max_steps,
            state=state_summary,  # Provide concise summary instead of full state
        )
    except KeyError as e:
        logger.error(f"Missing variable in orchestrator prompt: {e}")
        logger.error("Using prompt without formatting")
        # Continue with unformatted prompt

    # Use structured output directly (no create_agent needed)
    # Orchestrator doesn't need tools - just makes a routing decision
    # Use advanced model for better routing decisions
    structured_llm = orchestrator_llm.with_structured_output(OrchestratorDecision)

    # Build messages for the LLM
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

    # CRITICAL: Pass actual conversation messages to LLM for proper context
    # Include messages_history + current messages so LLM sees full conversation
    # This is essential for understanding responses like "boleh" (yes/okay)
    messages_for_llm = [SystemMessage(content=system_prompt)]

    # Add conversation history (last 5 messages for context)
    # IMPORTANT: Filter out messages with tool_calls AND ToolMessages to avoid OpenAI API errors
    # ToolMessages must be filtered because their parent tool_calls messages are also filtered
    # Orchestrator only needs to see conversation content, not tool execution details
    for msg in all_messages[-5:]:
        # Skip messages with tool_calls (they were already executed)
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            continue

        # Skip ToolMessages (responses to already-executed tool calls)
        if isinstance(msg, ToolMessage):
            continue

        if isinstance(msg, AIMessage):
            messages_for_llm.append(msg)
        elif isinstance(msg, HumanMessage):
            messages_for_llm.append(msg)
        # Handle dict format messages
        elif isinstance(msg, dict):
            # Skip if it has tool_calls
            if 'tool_calls' in msg and msg['tool_calls']:
                continue

            # Skip dict messages with role='tool'
            role = msg.get('type') or msg.get('role', 'human')
            if role == 'tool':
                continue

            content = msg.get('content', '')
            if role == 'human':
                messages_for_llm.append(HumanMessage(content=content))
            else:
                # For AI messages from dict, create AIMessage without tool_calls
                messages_for_llm.append(AIMessage(content=content))

    # Log context for debugging
    if len(all_messages) > 1:
        logger.info(f"Orchestrator receiving {len(messages_for_llm)} messages (after filtering tool_calls)")
        for i, msg in enumerate(messages_for_llm[-3:]):  # Show last 3
            msg_type = msg.type if hasattr(msg, 'type') else 'system'
            msg_content = msg.content[:80] if hasattr(msg, 'content') else ''
            logger.info(f"  Context msg {i+1}: [{msg_type}] {msg_content}...")

    # Invoke the LLM with structured output (with timeout)
    try:
        decision = await asyncio.wait_for(
            structured_llm.ainvoke(messages_for_llm),
            timeout=30.0  # 30 second timeout for orchestrator decision
        )
    except asyncio.TimeoutError:
        logger.error(f"Orchestrator LLM timeout after 30s at step {step}, forcing 'final' decision")
        # Create a fallback decision to go to final
        decision = OrchestratorDecision(
            next_agent="final",
            reasoning=f"Orchestrator timeout at step {step}/{max_steps}",
            plan="Proceeding to final message due to timeout"
        )
    except Exception as e:
        # Handle validation errors (e.g., invalid JSON from LLM)
        error_msg = str(e)
        if "json_invalid" in error_msg or "validation_error" in error_msg:
            logger.error(f"Orchestrator LLM returned invalid JSON, attempting manual extraction")

            # Try to get raw response and extract JSON manually
            try:
                # Get the raw LLM response without structured output
                raw_response = await asyncio.wait_for(
                    orchestrator_llm.ainvoke(messages_for_llm),
                    timeout=30.0
                )

                if hasattr(raw_response, 'content'):
                    content = raw_response.content
                    logger.info(f"Raw LLM response: {content[:200]}...")

                    # Extract JSON from the response
                    json_str = extract_json_from_text(content)
                    logger.info(f"Extracted JSON: {json_str[:200]}...")

                    # Parse the JSON
                    data = json.loads(json_str)
                    decision = OrchestratorDecision(**data)
                    logger.info("Successfully extracted and parsed JSON manually")
                else:
                    raise ValueError("Raw response has no content attribute")

            except Exception as manual_error:
                logger.error(f"Manual JSON extraction also failed: {manual_error}")

                # Final fallback: try to extract next_agent from error message
                next_agent = "final"
                if "ecommerce" in error_msg.lower():
                    next_agent = "ecommerce"
                elif "profiling" in error_msg.lower():
                    next_agent = "profiling"
                elif "sales" in error_msg.lower():
                    next_agent = "sales"
                elif "support" in error_msg.lower():
                    next_agent = "support"

                decision = OrchestratorDecision(
                    next_agent=next_agent,
                    reasoning=f"Orchestrator LLM parsing error, using fallback routing",
                    plan=f"Proceeding to {next_agent} due to LLM response parsing error"
                )
        else:
            # Re-raise unexpected errors
            raise

    # Extract decision from validated OrchestratorDecision object
    next_agent = decision.next_agent
    reasoning = decision.reasoning
    plan = decision.plan

    logger.info(f"Orchestrator decision: {next_agent}")
    logger.info(f"Reasoning: {reasoning}")
    logger.info(f"Plan: {plan}")

    # Update state with decision
    # Don't copy entire state to avoid triggering operator.add on messages
    update = {
        "orchestrator_decision": decision.model_dump(),
        "orchestrator_plan": plan
    }

    logger.info("EXIT: orchestrator_node")
    return update


async def orchestrator_router(state: AgentState) -> str:
    """
    Router that reads orchestrator decision and routes to appropriate worker.

    Enforces two safety limits:
    1. Max orchestrator steps (prevents infinite loops)
    2. Hard-cap per agent (each agent can only be called once per chat request)
    3. Human takeover flag (bypasses orchestrator and goes directly to human takeover)
    """
    logger.info("ENTER: orchestrator_router")

    # Check if human takeover is triggered (highest priority)
    if state.get("human_takeover", False):
        logger.warning("Human takeover flag detected - routing directly to human_takeover node")
        logger.info("EXIT: orchestrator_router -> human_takeover")
        return "human_takeover"

    # Check safety limit: max steps
    step = state.get("orchestrator_step", 0)
    max_steps = state.get("max_orchestrator_steps", 5)

    if step >= max_steps:
        logger.warning(f"Max orchestrator steps reached ({step}), forcing final")
        logger.info("EXIT: orchestrator_router -> final_message")
        return "final_message"

    # Get orchestrator decision
    decision = state.get("orchestrator_decision", {})
    next_agent = decision.get("next_agent", "final")

    logger.info(f"Routing decision: {next_agent}")

    # HARD CAP: Check if agent was already called in this chat request
    agents_called = state.get("agents_called", [])

    if next_agent in agents_called:
        logger.warning(f"Agent '{next_agent}' already called in this chat: {agents_called}")
        logger.warning(f"Forcing route to final_message (hard-cap enforced)")
        logger.info("EXIT: orchestrator_router -> final_message (hard-cap)")
        return "final_message"

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
    elif next_agent == "support":
        logger.info("EXIT: orchestrator_router -> support_node")
        return "support_node"
    else:  # "final" or unknown
        logger.info("EXIT: orchestrator_router -> final_message")
        return "final_message"


# ============================================================================
# WORKER NODES
# ============================================================================

async def profiling_node(state: AgentState) -> Dict:
    """
    Profiling node - collects and updates customer data.

    This is the PROFILING agent - handles customer onboarding,
    data collection, and profile updates.
    """
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

    # Get profiling agent prompt from database (reuse hana_customer_agent)
    system_prompt = await get_prompt_from_db("hana_customer_agent")
    if not system_prompt:
        logger.warning("Failed to load hana_customer_agent prompt from DB, using fallback")
        agent_name = get_agent_name()
        system_prompt = f"You are {agent_name}, Customer Service AI from ORIN GPS Tracker. Collect customer data."
    else:
        # Format agent name into the prompt
        agent_name = get_agent_name()
        try:
            system_prompt = system_prompt.format(agent_name=agent_name)
        except KeyError:
            # Prompt doesn't have {agent_name} placeholder, use as-is
            pass

    # Create profiling agent with profiling tools
    # Use advanced model for better data extraction
    agent = create_agent(
        model=profiling_llm,
        tools=PROFILING_AGENT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    # Invoke the agent
    result = await agent.ainvoke(state, recursion_limit=8)

    # Apply tool state updates (e.g., send_images from send_product_images tool)
    result = await apply_tool_state_updates(result)

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

    # IMPORTANT: Don't return entire result dict to avoid triggering operator.add reducer
    # on messages field. Only return explicitly modified fields.
    update = {}
    if 'customer_data' in result:
        update['customer_data'] = result['customer_data']
    if 'agents_called' in result:
        update['agents_called'] = result['agents_called']
    if 'orchestrator_step' in result:
        update['orchestrator_step'] = result['orchestrator_step']
    if 'send_images' in result:
        update['send_images'] = result['send_images']
    if 'send_pdfs' in result:
        update['send_pdfs'] = result['send_pdfs']
    if 'send_form' in result:
        update['send_form'] = result['send_form']
    if 'human_takeover' in result:
        update['human_takeover'] = result['human_takeover']
    if 'session_ending_detected' in result:
        update['session_ending_detected'] = result['session_ending_detected']

    # Note: messages field is NOT returned here because it has operator.add reducer
    # The agent already added messages to state via reducer, we don't trigger it again

    return update


async def sales_node(state: AgentState) -> Dict:
    """
    Sales node - handles B2B and large order sales flow.

    Simplified approach:
    1. Ask if customer wants meeting with sales team
    2. If YES → trigger human takeover (live agents handle meetings)
    3. If NO → continue to ecommerce for product recommendations
    """
    logger.info("ENTER: sales_node")

    # Get sales agent prompt from database
    system_prompt = await get_prompt_from_db("hana_sales_agent")
    if not system_prompt:
        logger.warning("Failed to load hana_sales_agent prompt from DB, using fallback")
        agent_name = get_agent_name()
        system_prompt = f"""You are {agent_name} from ORIN GPS Tracker.

You are handling B2B or high-volume customers (5+ units).

Your task:
1. Greet the customer warmly
2. Ask if they want a meeting with our sales team for special pricing
3. If they agree to meeting → use the trigger_human_takeover tool
4. If they don't want meeting → let them know you can provide product information

Important:
- Be friendly and helpful
- Don't pressure them
- If they want meeting, trigger human takeover immediately
- If they don't, acknowledge and let them know product info is available
"""
    else:
        # Format agent name into the prompt
        agent_name = get_agent_name()
        try:
            system_prompt = system_prompt.format(agent_name=agent_name)
        except KeyError:
            # Prompt doesn't have {agent_name} placeholder, use as-is
            pass

    # Create sales agent with meeting tools
    # Use medium model (simple qualification flow)
    agent = create_agent(
        model=sales_llm,
        tools=SALES_AGENT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    # Invoke the agent with current state
    result = await agent.ainvoke(state, recursion_limit=10)

    # Apply tool state updates (e.g., human_takeover flag)
    result = await apply_tool_state_updates(result)

    # Track that this agent was called
    agents_called = result.get("agents_called", [])
    agents_called.append("sales")
    result["agents_called"] = list(set(agents_called))  # Remove duplicates

    # Increment orchestrator step
    result["orchestrator_step"] = state.get("orchestrator_step", 0) + 1

    logger.info("EXIT: sales_node")

    # IMPORTANT: Don't return entire result dict to avoid triggering operator.add reducer
    update = {}
    if 'agents_called' in result:
        update['agents_called'] = result['agents_called']
    if 'orchestrator_step' in result:
        update['orchestrator_step'] = result['orchestrator_step']
    if 'send_images' in result:
        update['send_images'] = result['send_images']
    if 'send_pdfs' in result:
        update['send_pdfs'] = result['send_pdfs']
    if 'send_form' in result:
        update['send_form'] = result['send_form']
    if 'human_takeover' in result:
        update['human_takeover'] = result['human_takeover']
    if 'session_ending_detected' in result:
        update['session_ending_detected'] = result['session_ending_detected']
    if 'wants_meeting' in result:
        update['wants_meeting'] = result['wants_meeting']
    if 'existing_meeting_id' in result:
        update['existing_meeting_id'] = result['existing_meeting_id']

    return update


async def ecommerce_node(state: AgentState) -> Dict:
    """
    Ecommerce node - handles B2C and small order product inquiries.
    """
    logger.info("ENTER: ecommerce_node")

    # Get ecommerce agent prompt from database
    system_prompt = await get_prompt_from_db("hana_ecommerce_agent")
    if not system_prompt:
        logger.warning("Failed to load hana_ecommerce_agent prompt from DB, using fallback")
        agent_name = get_agent_name()
        system_prompt = f"You are {agent_name}, Customer Service AI from ORIN GPS Tracker."
    else:
        # Format agent name into the prompt
        agent_name = get_agent_name()
        try:
            system_prompt = system_prompt.format(agent_name=agent_name)
        except KeyError:
            # Prompt doesn't have {agent_name} placeholder, use as-is
            pass

    # Create ecommerce agent with product tools
    # Use custom agent with separate react prompt for better tool calling behavior
    agent = create_custom_agent(
        model=ecommerce_llm,
        tools=ECOMMERCE_AGENT_TOOLS,
        system_prompt=system_prompt,
        react_prompt=ECOMMERCE_REACT_PROMPT,
        state_schema=AgentState,
        debug=False,
    )

    # Invoke the agent with current state
    result = await agent.ainvoke(state, recursion_limit=10)

    # Apply tool state updates (e.g., send_images from send_product_images tool)
    result = await apply_tool_state_updates(result)

    # Track that this agent was called
    agents_called = result.get("agents_called", [])
    agents_called.append("ecommerce")
    result["agents_called"] = list(set(agents_called))  # Remove duplicates

    # Increment orchestrator step
    result["orchestrator_step"] = state.get("orchestrator_step", 0) + 1

    logger.info("EXIT: ecommerce_node")

    # IMPORTANT: Don't return entire result dict to avoid triggering operator.add reducer
    update = {}
    if 'agents_called' in result:
        update['agents_called'] = result['agents_called']
    if 'orchestrator_step' in result:
        update['orchestrator_step'] = result['orchestrator_step']
    if 'send_images' in result:
        update['send_images'] = result['send_images']
    if 'send_pdfs' in result:
        update['send_pdfs'] = result['send_pdfs']
    if 'ecommerce_links' in result:
        update['ecommerce_links'] = result['ecommerce_links']
    if 'human_takeover' in result:
        update['human_takeover'] = result['human_takeover']

    return update


async def support_node(state: AgentState) -> Dict:
    """
    Support node - handles complaints, technical support, and issues.
    """
    logger.info("ENTER: support_node")

    # Get support agent prompt from database
    system_prompt = await get_prompt_from_db("hana_support_agent")
    if not system_prompt:
        logger.warning("Failed to load hana_support_agent prompt from DB, using fallback")
        agent_name = get_agent_name()
        system_prompt = f"You are {agent_name}, Customer Service AI from ORIN GPS Tracker."
    else:
        # Format agent name into the prompt
        agent_name = get_agent_name()
        try:
            system_prompt = system_prompt.format(agent_name=agent_name)
        except KeyError:
            # Prompt doesn't have {agent_name} placeholder, use as-is
            pass

    # Create support agent with support tools
    # Use medium model (FAQ-style responses)
    agent = create_agent(
        model=support_llm,
        tools=SUPPORT_AGENT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    # Invoke the agent with current state
    result = await agent.ainvoke(state, recursion_limit=10)

    # Apply tool state updates
    result = await apply_tool_state_updates(result)

    # Track that this agent was called
    agents_called = result.get("agents_called", [])
    agents_called.append("support")
    result["agents_called"] = list(set(agents_called))  # Remove duplicates

    # Increment orchestrator step
    result["orchestrator_step"] = state.get("orchestrator_step", 0) + 1

    logger.info("EXIT: support_node")

    # IMPORTANT: Don't return entire result dict to avoid triggering operator.add reducer
    update = {}
    if 'agents_called' in result:
        update['agents_called'] = result['agents_called']
    if 'orchestrator_step' in result:
        update['orchestrator_step'] = result['orchestrator_step']
    if 'send_images' in result:
        update['send_images'] = result['send_images']
    if 'send_pdfs' in result:
        update['send_pdfs'] = result['send_pdfs']
    if 'human_takeover' in result:
        update['human_takeover'] = result['human_takeover']

    return update


# ============================================================================
# BUILD THE GRAPH
# ============================================================================

def build_hana_agent_graph():
    """
    Build AI agent graph with Orchestrator-Worker pattern.

    Graph Structure:
    1. Entry → orchestrator_node (decides first agent)
    2. orchestrator_node → orchestrator_router (routes to worker)
    3. Worker (profiling/sales/ecommerce/support) → orchestrator_node (back to orchestrator)
    4. Loop: orchestrator → worker → orchestrator → worker → ...
    5. When orchestrator says "final" → final_message (generates WhatsApp bubbles)
    6. final_message → quality_check (evaluates actual WhatsApp bubbles user will see)
    7. quality_check → END (send to user) OR human_takeover
    8. When human_takeover flag is set → human_takeover (bypasses quality_check)
    9. human_takeover → END

    The orchestrator:
    - Analyzes customer context and conversation intent
    - Decides which worker agent to call next
    - Can call multiple agents in sequence
    - Knows when conversation is complete
    - Checks for human_takeover flag to bypass quality_check

    Worker agents:
    - profiling_agent: Collects/updates customer data
    - sales_agent: Handles B2B/large volume, qualifies for meeting → human takeover or ecommerce
    - ecommerce_agent: Handles products, pricing, recommendations
    - support_agent: Handles complaints, technical support, issues
    """
    agent_name = get_agent_name()
    logger.info(f"Building {agent_name} Agent Graph with Orchestrator-Worker pattern...")

    # Initialize the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent_entry", agent_entry_handler)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("profiling_node", profiling_node)
    workflow.add_node("sales_node", sales_node)
    workflow.add_node("ecommerce_node", ecommerce_node)
    workflow.add_node("support_node", support_node)
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
            "support_node": "support_node",
            "final_message": "final_message",
            "quality_check": "quality_check",
            "human_takeover": "human_takeover"
        }
    )

    # ALL workers → back to orchestrator (the loop!)
    workflow.add_edge("profiling_node", "orchestrator")
    workflow.add_edge("sales_node", "orchestrator")
    workflow.add_edge("ecommerce_node", "orchestrator")
    workflow.add_edge("support_node", "orchestrator")

    # Final message → quality check (evaluates actual WhatsApp bubbles)
    workflow.add_edge("final_message", "quality_check")

    # Quality check → END OR human takeover
    workflow.add_conditional_edges(
        "quality_check",
        quality_router,
        {
            "end": END,
            "human_takeover": "human_takeover"
        }
    )

    # Human takeover → END
    workflow.add_edge("human_takeover", END)

    # Compile the graph
    hana_agent = workflow.compile()

    agent_name = get_agent_name()
    logger.info(f"{agent_name} Agent Graph compiled with Orchestrator-Worker pattern!")
    logger.info(f"Orchestrator tools: {len(ORCHESTRATOR_TOOLS)}")
    logger.info(f"Profiling agent tools: {len(PROFILING_AGENT_TOOLS)}")
    logger.info(f"Sales agent tools: {len(SALES_AGENT_TOOLS)}")
    logger.info(f"Ecommerce agent tools: {len(ECOMMERCE_AGENT_TOOLS)}")
    logger.info(f"Support agent tools: {len(SUPPORT_AGENT_TOOLS)}")
    logger.info("Using LangChain's create_agent for agent loop handling")
    return hana_agent


# Create the compiled agent
hana_agent = build_hana_agent_graph()
