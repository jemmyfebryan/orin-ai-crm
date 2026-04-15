"""
Orin Landing Agent Chat Processor

This module handles chat processing for the orin_landing_agent.
Key differences from hana_agent:
- Uses lid_number for customer identification (not phone_number)
- API-based (JSON request/response)
- Text-based only (no images/PDFs)
- human_takeover sends wa.me link (does NOT set database flag)
"""

from typing import Optional, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.tools.db_tools import (
    get_or_create_customer,
    get_chat_history,
    save_message_to_db,
)
from src.orin_ai_crm.core.agents.custom.orin_landing_agent import orin_landing_agent

logger = get_logger(__name__)


async def process_orin_landing_request(
    lid_number: str,
    message: str,
    contact_name: Optional[str] = None,
    skip_user_save: bool = False,
) -> Dict[str, Any]:
    """
    Process a chat request using orin_landing_agent.

    Args:
        lid_number: Customer's LID number for identification
        message: User's message
        contact_name: Optional contact name
        skip_user_save: If True, skip saving user message to DB (already saved)

    Returns:
        Dict with:
            - customer_id: Customer ID
            - lid_number: Customer's LID number
            - replies: List of WhatsApp bubble messages (final_messages)
            - messages_count: Number of messages exchanged
            - human_takeover: Whether human takeover was triggered
    """
    logger.info(f"Processing orin_landing request - lid: {lid_number}, message: {message[:50]}...")

    # Get or create customer by lid_number
    customer = await get_or_create_customer(
        phone_number=None,
        lid_number=lid_number,
        contact_name=contact_name
    )
    customer_id = customer['customer_id']

    logger.info(f"Customer resolved: customer_id={customer_id}, lid_number={lid_number}")

    # Save user message to DB
    if not skip_user_save:
        await save_message_to_db(customer_id, "user", message, content_type="text")

    # Get chat history for context
    messages_history = await get_chat_history(customer_id, limit=20)

    # Convert ChatSession to LangChain messages
    langchain_messages = []
    for msg in messages_history:
        if msg.message_role == "user":
            langchain_messages.append(HumanMessage(content=msg.content))
        elif msg.message_role == "ai":
            langchain_messages.append(AIMessage(content=msg.content))

    # Prepare state for orin_landing_agent
    state = {
        "lid_number": lid_number,
        "contact_name": contact_name,
        "customer_id": customer_id,
        "customer_data": {
            "id": customer_id,
            "name": customer.get('name', ''),
            "domicile": customer.get('domicile', ''),
            "vehicle_id": customer.get('vehicle_id', -1),
            "vehicle_alias": customer.get('vehicle_alias', ''),
            "unit_qty": customer.get('unit_qty', 0),
            "is_b2b": customer.get('is_b2b', False),
            "is_onboarded": customer.get('is_onboarded', False),
            "user_id": customer.get('user_id'),
        },
        "send_form": customer.get('send_form', False),
        "messages": [HumanMessage(content=message)],
        "messages_history": langchain_messages,
        "orchestrator_step": 0,
        "max_orchestrator_steps": 5,
        "agents_called": [],
        "orchestrator_instruction": "",
        "orchestrator_decision": {},
        "human_takeover": False,
    }

    # Invoke orin_landing_agent
    logger.info(f"Invoking orin_landing_agent for customer_id={customer_id}")

    try:
        result = await orin_landing_agent.ainvoke(state, recursion_limit=20)

        logger.info(f"orin_landing_agent completed for customer_id={customer_id}")

        # Extract final_messages (WhatsApp bubbles)
        final_messages = result.get("final_messages", [])

        if not final_messages:
            logger.warning(f"No final_messages returned for customer_id={customer_id}")
            final_messages = ["Maaf, terjadi kesalahan. Silakan coba lagi."]

        # Save AI replies to DB
        for reply in final_messages:
            await save_message_to_db(customer_id, "ai", reply, content_type="text")

        # Check if human takeover was triggered
        human_takeover = result.get("human_takeover", False)

        logger.info(f"orin_landing_agent result: {len(final_messages)} bubbles, human_takeover={human_takeover}")

        return {
            "customer_id": customer_id,
            "lid_number": lid_number,
            "replies": final_messages,
            "messages_count": len(final_messages),
            "human_takeover": human_takeover,
        }

    except Exception as e:
        logger.error(f"Error invoking orin_landing_agent: {str(e)}")
        import traceback
        traceback.print_exc()

        # Return error message
        error_message = "Maaf, terjadi kesalahan pada sistem AI. Silakan hubungi customer service."
        await save_message_to_db(customer_id, "ai", error_message, content_type="text")

        return {
            "customer_id": customer_id,
            "lid_number": lid_number,
            "replies": [error_message],
            "messages_count": 1,
            "human_takeover": False,
            "error": str(e),
        }
