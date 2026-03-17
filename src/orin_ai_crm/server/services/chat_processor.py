"""
Shared chat processing logic for both /chat-agent and /freshchat-agent endpoints.
"""
from typing import Optional, Dict, Any

from langchain_core.messages import HumanMessage, AIMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.tools.db_tools import (
    get_or_create_customer,
    get_chat_history,
    save_message_to_db,
)
from src.orin_ai_crm.core.agents.custom.hana_agent import hana_agent

logger = get_logger(__name__)


async def process_chat_request(
    phone_number: Optional[str],
    lid_number: Optional[str],
    message: str,
    contact_name: Optional[str],
    is_new_chat: bool,
) -> Dict[str, Any]:
    """
    Process a chat request using the agentic AI workflow.

    This is the core business logic shared by both /chat-agent and /freshchat-agent endpoints.

    Args:
        phone_number: User's phone number
        lid_number: User's LID number (alternative identifier)
        message: User's message text
        contact_name: User's contact name
        is_new_chat: Whether this is a new conversation

    Returns:
        Dict containing:
            - customer_id: int
            - phone_number: str
            - lid_number: str
            - replies: List[str] (AI response bubbles)
            - tool_calls: List[str] (tools used)
            - messages_count: int
    """
    # 1. Get or create customer
    customer = await get_or_create_customer(
        phone_number=phone_number,
        lid_number=lid_number,
        contact_name=contact_name
    )
    customer_id = customer['customer_id']
    logger.info(f"customer_id resolved: {customer_id}")

    # 2. Fetch chat history if not new chat
    history = []
    logger.info(f"Fetching chat history for customer_id: {customer_id}")
    history_rows = await get_chat_history(customer_id, limit=10)
    for row in history_rows:
        if row.message_role == "user":
            history.append(HumanMessage(content=row.content))
        else:
            history.append(AIMessage(content=row.content))

    # 3. Load customer data
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

    logger.info(f"Customer data: {customer_data}")

    # 4. Determine if we should send the form
    is_onboarded = customer.get('is_onboarded', False)
    send_form = not is_onboarded if is_onboarded is not None else is_new_chat
    logger.info(f"send_form determined as: {send_form} (is_onboarded={is_onboarded}, is_new_chat={is_new_chat})")

    # 5. Save user message to database
    await save_message_to_db(customer_id, "user", message)

    # 6. Prepare state for agent
    current_messages = history + [HumanMessage(content=message)]

    initial_state = {
        "messages": current_messages,
        "phone_number": phone_number,
        "lid_number": lid_number,
        "contact_name": contact_name,
        "customer_id": customer_id,
        "customer_data": customer_data,
        "send_form": send_form,
        "route": "DEFAULT",
        # Orchestrator tracking fields
        "orchestrator_step": 0,
        "max_orchestrator_steps": 5,
        "agents_called": [],
        "orchestrator_plan": "",
        "orchestrator_decision": {},
    }

    # 7. Run Agentic AI Workflow
    # Lower recursion limit to prevent infinite tool calling loops
    # Each tool call = 1 step. 10 steps = plenty for normal flow
    final_state = await hana_agent.ainvoke(initial_state, recursion_limit=10)

    logger.info(f"FINAL STATE (Agent): messages_count={len(final_state['messages'])}")

    # 8. Extract AI replies
    messages = final_state["messages"]
    final_messages = final_state.get("final_messages", [])
    tool_calls_used = []

    # Find all tool calls made during the conversation
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc['name'] not in tool_calls_used:
                    tool_calls_used.append(tc['name'])

    # Get the final messages (multi-bubble response)
    ai_replies = []
    if final_messages:
        ai_replies = final_messages
        logger.info(f"Using final_messages from node_final_message: {len(ai_replies)} bubbles")
    else:
        # Fallback: find last AIMessage with content
        logger.warning("No final_messages found, using fallback to extract from messages")
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and hasattr(msg, 'content') and msg.content:
                # Skip tool result messages
                if not hasattr(msg, 'name') or msg.name != 'ToolMessage':
                    ai_replies = [msg.content]
                    break

    # If still no content, this is an error
    if not ai_replies:
        logger.error("No AI reply found in final state!")
        ai_replies = ["Maaf, terjadi kesalahan sistem. Silakan coba lagi."]

    # 9. Save AI replies to database
    ai_reply_for_db = "\n\n".join(ai_replies)
    await save_message_to_db(customer_id, "ai", ai_reply_for_db)

    logger.info(f"Tool calls used: {tool_calls_used}")
    logger.info(f"AI replies ({len(ai_replies)} bubbles):")
    for i, reply in enumerate(ai_replies):
        logger.info(f"  Bubble {i+1}: {reply[:100]}...")

    return {
        "customer_id": customer_id,
        "phone_number": phone_number,
        "lid_number": lid_number,
        "replies": ai_replies,
        "tool_calls": tool_calls_used if tool_calls_used else None,
        "messages_count": len(messages),
        "send_images": final_state.get("send_images", [])
    }
