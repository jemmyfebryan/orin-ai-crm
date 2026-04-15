"""
Orin Landing AI Agent - Orchestrator-Worker Architecture (API-based, text-only)

This implementation uses the Orchestrator pattern for multi-agent collaboration.
Key differences from hana_agent:
- NO intent classification (direct to orchestrator)
- Text-based only (no images/PDFs in ecommerce_agent)
- Limited tools in support_agent
- human_takeover sends wa.me link (does NOT set database flag)
- Uses lid_number for customer identification
- API-based (JSON request/response), not webhook-based

Architecture:
1. agent_entry_handler: Ensures customer_id exists (uses lid_number)
2. orchestrator_node: Traffic controller that decides which worker to call
3. profiling_node: Collects and updates customer data (same as hana)
4. sales_node: Handles B2B/large volume customers, qualifies for meeting → human takeover or ecommerce
5. ecommerce_node: Handles product questions, pricing, catalog (text-only, no images/PDFs)
6. support_node: Handles support with limited tools (human_takeover, forgot_password, get_company_profile)
7. orchestrator_router: Routes from orchestrator to appropriate worker
8. quality_check_node: Evaluates AI answer quality
9. final_message_node: Adds form if needed and prepares final response
10. human_takeover_node: Sends wa.me link (does NOT set database flag)

Flow:
Entry → Orchestrator → Worker (profiling/sales/ecommerce/support) → Orchestrator → Worker → ...
                  ↓
             (loops until orchestrator says "final")
                  ↓
             final_message → quality_check → END/human_takeover
"""

import asyncio
import json
from typing import Dict, Literal
from pydantic import BaseModel, Field, field_validator, ValidationError

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langchain.agents import create_agent

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.custom.hana_agent.custom_agent import create_custom_agent
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import get_llm
from src.orin_ai_crm.core.agents.tools.agent_tools import (
    ORCHESTRATOR_TOOLS,
    PROFILING_AGENT_TOOLS,
    SALES_AGENT_TOOLS,
    ORIN_LANDING_ECOMMERCE_TOOLS,
    ORIN_LANDING_SUPPORT_TOOLS,
)
from src.orin_ai_crm.core.agents.tools.customer_agent_tools import (
    get_customer_profile,
)
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db, get_agent_name
from src.orin_ai_crm.core.agents.nodes.orin_landing_quality_check_nodes import (
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
orchestrator_llm = get_llm("advanced")
ecommerce_llm = get_llm("advanced")
profiling_llm = get_llm("advanced")
sales_llm = get_llm("medium")
support_llm = get_llm("medium")
final_message_llm = get_llm("medium")
quality_check_llm = get_llm("medium")

llm = get_llm("medium")


# ============================================================================
# CUSTOM AGENT REACT PROMPTS
# ============================================================================

ECOMMERCE_REACT_PROMPT = """
You are an ecommerce assistant helping customers with product information.

CRITICAL - UNDERSTAND CONVERSATION CONTEXT:
You have access to message_history which contains the previous conversation.
ALWAYS check message_history FIRST before deciding which products to show.

Common Contextual Requests:
- "produknya" (the product) → refers to LAST product discussed in conversation
- "link produknya" → e-commerce links for the SPECIFIC product mentioned

IMPORTANT TOOL CALLING STRATEGY:
1. CHECK message_history for which product was discussed
2. IF user is specific ("produknya", "that product"):
   - Call tools ONLY for that specific product
3. IF user is general BUT no specific product was discussed:
   - Call get_all_active_products
   - Call get_ecommerce_links for top 3 products

Tool Usage Rules:
- Links → call get_ecommerce_links for RELEVANT products (typically 1-3 products max)
- Details → call get_product_details for specific products

When to Stop:
- Only stop after you've called tools for the RELEVANT products
- If user asks about "produknya" (singular), call tools for 1 product only
"""


# ============================================================================
# ORCHESTRATOR DECISION SCHEMA
# ============================================================================

def extract_json_from_text(text: str) -> str:
    """Extract JSON object from text that may contain additional content."""
    start_idx = text.find("{")
    if start_idx == -1:
        return text

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
                    return text[start_idx:i+1]

    return text


class OrchestratorDecision(BaseModel):
    """Orchestrator routing decision schema with forced output structure."""
    next_agent: Literal["profiling", "sales", "ecommerce", "support", "final"] = Field(
        description=(
            "Agent yang akan dipanggil berikutnya: profiling, sales, ecommerce, support, or final. "
            "Use ONLY these exact values without any suffixes or prefixes."
        )
    )
    reasoning: str = Field(
        description="Penjelasan mengenai decision yang dibuat"
    )
    instruction: str = Field(
        description="Instruksi kepada next agent dalam point of view orang pertama. Bicara seperti apa yang ingin kamu bilang ke next_agent agar next_agent mendapatkan konteks dari pertanyaan customer."
    )

    @field_validator('next_agent', mode='before')
    @classmethod
    def normalize_next_agent(cls, v: str) -> str:
        """Normalize the next_agent value to handle LLM variations."""
        if not isinstance(v, str):
            raise ValueError(f"next_agent must be a string, got {type(v)}")

        normalized = v.lower().strip()

        suffixes_to_remove = ["_agent", "_node", "_workflow", " agent", " node"]
        for suffix in suffixes_to_remove:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()

        mapping = {
            "profile": "profiling",
            "sale": "sales",
            "e-commerce": "ecommerce",
            "ecommerce": "ecommerce",
            "support": "support",
            "finalize": "final",
            "end": "final",
            "done": "final",
        }

        if normalized in mapping:
            normalized = mapping[normalized]

        allowed_values = ["profiling", "sales", "ecommerce", "support", "final"]
        if normalized not in allowed_values:
            raise ValueError(
                f"next_agent must be one of {allowed_values}, got '{v}' (normalized to '{normalized}')"
            )

        return normalized


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def apply_tool_state_updates(result: Dict) -> Dict:
    """
    Scan tool results for update_state and apply them to the agent result.
    """
    import json
    from langchain_core.messages import ToolMessage

    new_messages = result.get("messages", [])
    state_updates = {}

    for msg in new_messages:
        if isinstance(msg, ToolMessage):
            try:
                data = json.loads(msg.content)
                data_update_state = data.get("update_state")
                if isinstance(data_update_state, dict):
                    state_updates.update(data_update_state)
                    logger.info(f"Tool: {msg.name} update states: {data_update_state}")
            except (json.JSONDecodeError, TypeError):
                pass

    if state_updates:
        logger.info(f"Final tool state_updates: {state_updates}")
        for k, v in state_updates.items():
            result[k] = v

    return result


async def agent_entry_handler(state: AgentState) -> Dict:
    """
    Entry point handler - ensures customer_id exists and builds system prompt.
    Uses lid_number for customer identification (API-based, no phone_number).

    For orin_landing_agent, we use lid_number instead of phone_number.
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import get_or_create_customer

    logger.info("ENTER: agent_entry_handler (orin_landing)")

    messages_at_entry = state.get('messages', [])
    for i, msg in enumerate(messages_at_entry):
        msg_type = type(msg).__name__
        content = msg.content[:50] if hasattr(msg, 'content') else 'N/A'
        logger.info(f"  messages[{i}]: [{msg_type}] {content}...")

    # If we don't have customer_id yet, get or create customer by lid_number
    if not state.get('customer_id'):
        lid_number = state.get('lid_number')
        contact_name = state.get('contact_name')

        if not lid_number:
            logger.error("No lid_number provided for orin_landing_agent")
            raise ValueError("lid_number is required for orin_landing_agent")

        customer = await get_or_create_customer(
            lid_number=lid_number,
            contact_name=contact_name
        )

        customer_id = customer['customer_id']
        logger.info(f"Customer resolved: id={customer_id}")

        customer_data = {
            'id': customer_id,
            'name': customer.get('name', ''),
            'domicile': customer.get('domicile', ''),
            'vehicle_id': customer.get('vehicle_id', -1),
            'vehicle_alias': customer.get('vehicle_alias', ''),
            'unit_qty': customer.get('unit_qty', 0),
            'is_b2b': customer.get('is_b2b', False),
            'is_onboarded': customer.get('is_onboarded', False),
            'user_id': customer.get('user_id'),
        }

        state['customer_id'] = customer_id
        state['customer_data'] = customer_data
        state['send_form'] = customer.get('send_form', False)
        logger.info(f"State updated: customer_id={customer_id}, send_form={state['send_form']}")

    # Initialize orchestrator tracking fields
    if 'orchestrator_step' not in state:
        state['orchestrator_step'] = 0
    if 'max_orchestrator_steps' not in state:
        state['max_orchestrator_steps'] = 5
    if 'agents_called' not in state:
        state['agents_called'] = []
    if 'orchestrator_instruction' not in state:
        state['orchestrator_instruction'] = ""
    if 'orchestrator_decision' not in state:
        state['orchestrator_decision'] = {}
    if 'human_takeover' not in state:
        state['human_takeover'] = False

    logger.info("EXIT: agent_entry_handler (orin_landing)")

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
    if 'orchestrator_instruction' in state:
        result['orchestrator_instruction'] = state['orchestrator_instruction']
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
    """
    logger.info("ENTER: orchestrator_node (orin_landing)")

    step = state.get("orchestrator_step", 0)
    max_steps = state.get("max_orchestrator_steps", 5)
    agents_called = state.get("agents_called", [])

    logger.info(f"Orchestrator step {step}/{max_steps}")
    logger.info(f"Agents called so far: {agents_called}")

    customer_data = state.get('customer_data', {})
    messages = state.get('messages', [])
    messages_history = state.get('messages_history', [])

    all_messages = list(messages_history) + list(messages)

    # Get orchestrator prompt from DB (orin_landing_orchestrator_agent)
    system_prompt = await get_prompt_from_db("orin_landing_orchestrator_agent")
    if not system_prompt:
        logger.error("Failed to load orin_landing_orchestrator_agent prompt from DB! Using fallback.")
        system_prompt = """You are a router. Decide next agent: profiling, sales, ecommerce, support, or final."""

    agent_name = get_agent_name()

    # Build state summary
    state_summary = f"""
Total messages in conversation (history + current): {len(all_messages)}
Customer ID: {state.get('customer_id', 'N/A')}
Send Form: {state.get('send_form', False)}
Human Takeover: {state.get('human_takeover', False)}
Last 5 messages from full conversation:
"""
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
            state=state_summary,
        )
    except KeyError as e:
        logger.error(f"Missing variable in orchestrator prompt: {e}")

    structured_llm = orchestrator_llm.with_structured_output(OrchestratorDecision)

    from langchain_core.messages import SystemMessage, AIMessage, ToolMessage

    messages_for_llm = [SystemMessage(content=system_prompt)]

    for msg in all_messages[-5:]:
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            continue
        if isinstance(msg, ToolMessage):
            continue
        if isinstance(msg, AIMessage):
            messages_for_llm.append(msg)
        elif isinstance(msg, HumanMessage):
            messages_for_llm.append(msg)
        elif isinstance(msg, dict):
            if 'tool_calls' in msg and msg['tool_calls']:
                continue
            role = msg.get('type') or msg.get('role', 'human')
            if role == 'tool':
                continue
            content = msg.get('content', '')
            if role == 'human':
                messages_for_llm.append(HumanMessage(content=content))
            else:
                messages_for_llm.append(AIMessage(content=content))

    try:
        decision = await asyncio.wait_for(
            structured_llm.ainvoke(messages_for_llm),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        logger.error(f"Orchestrator LLM timeout after 30s at step {step}, forcing 'final' decision")
        decision = OrchestratorDecision(
            next_agent="final",
            reasoning=f"Orchestrator timeout at step {step}/{max_steps}",
            instruction="Proceed to final message due to timeout"
        )
    except ValidationError as e:
        logger.error(f"Orchestrator LLM returned invalid value: {e}")
        try:
            raw_response = await asyncio.wait_for(
                orchestrator_llm.ainvoke(messages_for_llm),
                timeout=30.0
            )
            if hasattr(raw_response, 'content'):
                content = raw_response.content
                json_str = extract_json_from_text(content)
                data = json.loads(json_str)
                decision = OrchestratorDecision(**data)
                logger.info(f"Successfully normalized and validated: {decision.next_agent}")
            else:
                raise ValueError("Raw response has no content attribute")
        except Exception as manual_error:
            logger.error(f"Manual normalization also failed: {manual_error}")
            next_agent = "final"
            decision = OrchestratorDecision(
                next_agent=next_agent,
                reasoning="LLM returned invalid value, normalized to fallback",
                instruction=f"Proceed to {next_agent} after validation error recovery"
            )
    except Exception as e:
        error_msg = str(e)
        if "json_invalid" in error_msg or "validation_error" in error_msg:
            try:
                raw_response = await asyncio.wait_for(
                    orchestrator_llm.ainvoke(messages_for_llm),
                    timeout=30.0
                )
                if hasattr(raw_response, 'content'):
                    content = raw_response.content
                    json_str = extract_json_from_text(content)
                    data = json.loads(json_str)
                    decision = OrchestratorDecision(**data)
                    logger.info("Successfully extracted and parsed JSON manually")
                else:
                    raise ValueError("Raw response has no content attribute")
            except Exception as manual_error:
                logger.error(f"Manual JSON extraction also failed: {manual_error}")
                next_agent = "final"
                decision = OrchestratorDecision(
                    next_agent=next_agent,
                    reasoning="Orchestrator LLM parsing error, using fallback routing",
                    instruction=f"Proceed to {next_agent} due to LLM response parsing error"
                )
        else:
            raise

    next_agent = decision.next_agent
    reasoning = decision.reasoning
    instruction = decision.instruction

    logger.info(f"Orchestrator decision: {next_agent}")
    logger.info(f"Reasoning: {reasoning}")
    logger.info(f"Instruction: {instruction}")

    update = {
        "orchestrator_decision": decision.model_dump(),
        "orchestrator_instruction": instruction
    }

    logger.info("EXIT: orchestrator_node (orin_landing)")
    return update


async def orchestrator_router(state: AgentState) -> str:
    """
    Router that reads orchestrator decision and routes to appropriate worker.
    """
    logger.info("ENTER: orchestrator_router (orin_landing)")

    if state.get("human_takeover", False):
        logger.warning("Human takeover flag detected - routing directly to human_takeover node")
        logger.info("EXIT: orchestrator_router -> human_takeover")
        return "human_takeover"

    step = state.get("orchestrator_step", 0)
    max_steps = state.get("max_orchestrator_steps", 5)

    if step >= max_steps:
        logger.warning(f"Max orchestrator steps reached ({step}), forcing final")
        logger.info("EXIT: orchestrator_router -> final_message")
        return "final_message"

    decision = state.get("orchestrator_decision", {})
    next_agent = decision.get("next_agent", "final")

    logger.info(f"Routing decision: {next_agent}")

    agents_called = state.get("agents_called", [])

    if next_agent in agents_called:
        logger.warning(f"Agent '{next_agent}' already called in this chat: {agents_called}")
        logger.warning(f"Forcing route to final_message (hard-cap enforced)")
        logger.info("EXIT: orchestrator_router -> final_message (hard-cap)")
        return "final_message"

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
    else:
        logger.info("EXIT: orchestrator_router -> final_message")
        return "final_message"


# ============================================================================
# WORKER NODES
# ============================================================================

async def profiling_node(state: AgentState) -> Dict:
    """Profiling node - collects and updates customer data."""
    logger.info("ENTER: profiling_node (orin_landing)")

    orchestrator_decision = state.get('orchestrator_decision', {})
    instruction = orchestrator_decision.get('instruction', 'Continue the conversation naturally.')

    logger.info(f"Orchestrator instruction: {instruction[:100]}...")

    fresh_state = dict(state)
    from langchain_core.messages import HumanMessage
    fresh_state['messages'] = [HumanMessage(content=instruction)]

    logger.info(f"Fresh state created for profiling agent with 1 message (instruction)")

    customer_id = fresh_state.get('customer_id')
    if customer_id:
        try:
            profile_result = await get_customer_profile.ainvoke({'state': fresh_state})
            logger.info(f"Customer profile loaded: {profile_result}")

            if 'customer_data' in fresh_state:
                fresh_state['customer_data'].update(profile_result)
            else:
                fresh_state['customer_data'] = profile_result

            logger.info(f"Fresh state updated with customer data: {fresh_state['customer_data']}")
        except Exception as e:
            logger.error(f"Failed to load customer profile: {e}")

    # Get profiling agent prompt from database (orin_landing_customer_agent)
    system_prompt = await get_prompt_from_db("orin_landing_customer_agent")
    if not system_prompt:
        logger.warning("Failed to load orin_landing_customer_agent prompt from DB, using fallback")
        agent_name = get_agent_name()
        system_prompt = f"You are {agent_name}, Customer Service AI from ORIN GPS Tracker. Collect customer data."
    else:
        agent_name = get_agent_name()
        try:
            system_prompt = system_prompt.format(agent_name=agent_name)
        except KeyError:
            pass

    agent = create_agent(
        model=profiling_llm,
        tools=PROFILING_AGENT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    logger.info("Invoking profiling agent with fresh state...")
    result = await agent.ainvoke(fresh_state, recursion_limit=8)

    result = await apply_tool_state_updates(result)

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

    agents_called = result.get("agents_called", [])
    agents_called.append("profiling")
    result["agents_called"] = list(set(agents_called))
    result["orchestrator_step"] = state.get("orchestrator_step", 0) + 1

    logger.info("EXIT: profiling_node (orin_landing)")

    update = {'messages': result.get('messages', [])}
    if 'customer_data' in result:
        update['customer_data'] = result['customer_data']
    if 'agents_called' in result:
        update['agents_called'] = result['agents_called']
    if 'orchestrator_step' in result:
        update['orchestrator_step'] = result['orchestrator_step']
    if 'send_form' in result:
        update['send_form'] = result['send_form']
    if 'human_takeover' in result:
        update['human_takeover'] = result['human_takeover']
    if 'session_ending_detected' in result:
        update['session_ending_detected'] = result['session_ending_detected']

    return update


async def sales_node(state: AgentState) -> Dict:
    """Sales node - handles B2B and large order sales flow."""
    logger.info("ENTER: sales_node (orin_landing)")

    orchestrator_decision = state.get('orchestrator_decision', {})
    instruction = orchestrator_decision.get('instruction', 'Continue the conversation naturally.')

    logger.info(f"Orchestrator instruction: {instruction[:100]}...")

    fresh_state = dict(state)
    from langchain_core.messages import HumanMessage
    fresh_state['messages'] = [HumanMessage(content=instruction)]

    logger.info(f"Fresh state created for sales agent with 1 message (instruction)")

    # Get sales agent prompt from database (orin_landing_sales_agent)
    system_prompt = await get_prompt_from_db("orin_landing_sales_agent")
    if not system_prompt:
        logger.warning("Failed to load orin_landing_sales_agent prompt from DB, using fallback")
        agent_name = get_agent_name()
        system_prompt = f"""You are {agent_name}, sales agent from ORIN GPS Tracker."""
    else:
        agent_name = get_agent_name()
        try:
            system_prompt = system_prompt.format(agent_name=agent_name)
        except KeyError:
            pass

    agent = create_agent(
        model=sales_llm,
        tools=SALES_AGENT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    logger.info("Invoking sales agent with fresh state...")
    result = await agent.ainvoke(fresh_state, recursion_limit=10)

    result = await apply_tool_state_updates(result)

    agents_called = result.get("agents_called", [])
    agents_called.append("sales")
    result["agents_called"] = list(set(agents_called))
    result["orchestrator_step"] = state.get("orchestrator_step", 0) + 1

    logger.info("EXIT: sales_node (orin_landing)")

    update = {'messages': result.get('messages', [])}
    if 'agents_called' in result:
        update['agents_called'] = result['agents_called']
    if 'orchestrator_step' in result:
        update['orchestrator_step'] = result['orchestrator_step']
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
    Ecommerce node - handles B2C and small order product inquiries (text-only, no images/PDFs).
    """
    logger.info("ENTER: ecommerce_node (orin_landing)")

    orchestrator_decision = state.get('orchestrator_decision', {})
    instruction = orchestrator_decision.get('instruction', 'Continue the conversation naturally.')

    logger.info(f"Orchestrator instruction: {instruction[:100]}...")

    fresh_state = dict(state)
    from langchain_core.messages import HumanMessage
    fresh_state['messages'] = [HumanMessage(content=instruction)]
    fresh_state['messages_history'] = []

    logger.info(f"Instruction: {instruction[:100]}...")

    # Get ecommerce agent prompt from database (orin_landing_ecommerce_agent)
    system_prompt = await get_prompt_from_db("orin_landing_ecommerce_agent")
    if not system_prompt:
        logger.warning("Failed to load orin_landing_ecommerce_agent prompt from DB, using fallback")
        agent_name = get_agent_name()
        system_prompt = f"You are {agent_name}, Ecommerce agent from ORIN GPS Tracker."
    else:
        agent_name = get_agent_name()
        try:
            system_prompt = system_prompt.format(agent_name=agent_name)
        except KeyError:
            pass

    # Use custom agent with text-only ecommerce tools
    agent = create_custom_agent(
        model=ecommerce_llm,
        tools=ORIN_LANDING_ECOMMERCE_TOOLS,
        system_prompt=system_prompt,
        react_prompt=ECOMMERCE_REACT_PROMPT,
        state_schema=AgentState,
        debug=False,
    )

    logger.info("Invoking ecommerce agent with fresh state...")
    result = await agent.ainvoke(fresh_state, recursion_limit=10)

    result = await apply_tool_state_updates(result)

    agents_called = result.get("agents_called", [])
    agents_called.append("ecommerce")
    result["agents_called"] = list(set(agents_called))
    result["orchestrator_step"] = state.get("orchestrator_step", 0) + 1

    logger.info("EXIT: ecommerce_node (orin_landing)")

    update = {'messages': result.get('messages', [])}
    if 'agents_called' in result:
        update['agents_called'] = result['agents_called']
    if 'orchestrator_step' in result:
        update['orchestrator_step'] = result['orchestrator_step']
    if 'ecommerce_links' in result:
        update['ecommerce_links'] = result['ecommerce_links']
    if 'human_takeover' in result:
        update['human_takeover'] = result['human_takeover']

    return update


async def support_node(state: AgentState) -> Dict:
    """
    Support node - handles support with limited tools (human_takeover, forgot_password, get_company_profile).
    """
    logger.info("ENTER: support_node (orin_landing)")

    orchestrator_decision = state.get('orchestrator_decision', {})
    instruction = orchestrator_decision.get('instruction', 'Continue the conversation naturally.')

    logger.info(f"Orchestrator instruction: {instruction[:100]}...")

    fresh_state = dict(state)
    from langchain_core.messages import HumanMessage
    fresh_state['messages'] = [HumanMessage(content=instruction)]

    logger.info(f"Fresh state created for support agent with 1 message (instruction)")

    # Get support agent prompt from database (orin_landing_support_agent)
    system_prompt = await get_prompt_from_db("orin_landing_support_agent")
    if not system_prompt:
        logger.warning("Failed to load orin_landing_support_agent prompt from DB, using fallback")
        agent_name = get_agent_name()
        system_prompt = f"You are {agent_name}, Customer Service AI from ORIN GPS Tracker."
    else:
        agent_name = get_agent_name()
        try:
            system_prompt = system_prompt.format(agent_name=agent_name)
        except KeyError:
            pass

    agent = create_agent(
        model=support_llm,
        tools=ORIN_LANDING_SUPPORT_TOOLS,
        system_prompt=system_prompt,
        state_schema=AgentState,
    )

    logger.info("Invoking support agent with fresh state...")
    result = await agent.ainvoke(fresh_state, recursion_limit=10)

    result = await apply_tool_state_updates(result)

    agents_called = result.get("agents_called", [])
    agents_called.append("support")
    result["agents_called"] = list(set(agents_called))
    result["orchestrator_step"] = state.get("orchestrator_step", 0) + 1

    logger.info("EXIT: support_node (orin_landing)")

    update = {'messages': result.get('messages', [])}
    if 'agents_called' in result:
        update['agents_called'] = result['agents_called']
    if 'orchestrator_step' in result:
        update['orchestrator_step'] = result['orchestrator_step']
    if 'human_takeover' in result:
        update['human_takeover'] = result['human_takeover']

    return update


# ============================================================================
# BUILD THE GRAPH
# ============================================================================

def build_orin_landing_agent_graph():
    """
    Build AI agent graph with Orchestrator-Worker pattern for orin_landing_agent.

    Graph Structure (NO intent classification):
    1. agent_entry_handler → ensures customer_id exists (uses lid_number)
    2. orchestrator_node → decides first agent to call
    3. orchestrator_node → orchestrator_router (routes to worker)
    4. Worker (profiling/sales/ecommerce/support) → orchestrator_node (back to orchestrator)
    5. Loop: orchestrator → worker → orchestrator → worker → ...
    6. When orchestrator says "final" → final_message (generates WhatsApp bubbles)
    7. final_message → quality_check (evaluates actual WhatsApp bubbles)
    8. quality_check → END (send to user) OR human_takeover (sends wa.me link)
    9. When human_takeover flag is set → human_takeover (sends wa.me link, NO database flag)
    10. human_takeover → END

    Key differences from hana_agent:
    - NO intent_classification node
    - ecommerce_node uses text-only tools (no images/PDFs)
    - support_node uses limited tools
    - human_takeover sends wa.me link (does NOT set database flag)
    """
    agent_name = get_agent_name()
    logger.info(f"Building {agent_name} Orin Landing Agent Graph with Orchestrator-Worker pattern...")

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

    # Set entry point to agent_entry (NO intent classification)
    workflow.set_entry_point("agent_entry")

    # Entry handler → Orchestrator
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
            "human_takeover": "human_takeover"
        }
    )

    # ALL workers → back to orchestrator (the loop!)
    workflow.add_edge("profiling_node", "orchestrator")
    workflow.add_edge("sales_node", "orchestrator")
    workflow.add_edge("ecommerce_node", "orchestrator")
    workflow.add_edge("support_node", "orchestrator")

    # Final message → quality check
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
    orin_landing_agent = workflow.compile()

    agent_name = get_agent_name()
    logger.info(f"{agent_name} Orin Landing Agent Graph compiled!")
    logger.info(f"Orchestrator tools: {len(ORCHESTRATOR_TOOLS)}")
    logger.info(f"Profiling agent tools: {len(PROFILING_AGENT_TOOLS)}")
    logger.info(f"Sales agent tools: {len(SALES_AGENT_TOOLS)}")
    logger.info(f"Ecommerce agent tools (text-only): {len(ORIN_LANDING_ECOMMERCE_TOOLS)}")
    logger.info(f"Support agent tools (limited): {len(ORIN_LANDING_SUPPORT_TOOLS)}")

    return orin_landing_agent


# Create the compiled agent
orin_landing_agent = build_orin_landing_agent_graph()
