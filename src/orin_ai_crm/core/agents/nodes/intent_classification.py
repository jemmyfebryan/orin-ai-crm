"""
Intent Classification Node

Classifies user messages into "greeting" or "other" to determine
whether to send follow-up messages after periods of inactivity.

For greetings, sends two follow-up messages:
- After 3 minutes: "Halo kak, ada yang bisa {agent_name} bantu? 😊"
- After 6 minutes: "Baik Kak, silahkan chat lagi bila masih butuh bantuan. Untuk panduan online ORIN, bisa cek https://orin.id/panduan ya"
"""

import asyncio
from typing import Literal
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import get_llm
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_agent_name

logger = get_logger(__name__)

# Use medium model for intent classification (fast and accurate)
intent_llm = get_llm("medium")


class IntentClassification(BaseModel):
    """Classification of user message intent"""
    intent: Literal["greeting", "other"] = Field(
        description="Classification of the user's intent: 'greeting' for simple greetings with no important information, 'other' for messages with actual content/information"
    )
    reasoning: str = Field(
        description="Brief explanation for why this message was classified this way"
    )


# In-memory storage for pending follow-up tasks
# Format: {customer_id: asyncio.Task}
pending_follow_up_tasks = {}


async def classify_user_intent(user_message: str) -> IntentClassification:
    """
    Classify user message as "greeting" or "other".

    Args:
        user_message: The user's message text

    Returns:
        IntentClassification with intent and reasoning
    """
    logger.info(f"classify_user_intent called - message: {user_message[:100]}...")

    # Import here to avoid circular dependency
    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    agent_name = get_agent_name()

    # Fetch intent classification prompt from database
    system_prompt_template = await get_prompt_from_db("intent_classification_prompt")
    if not system_prompt_template:
        logger.warning("intent_classification_prompt not found in DB, using default")
        system_prompt_template = """You are {agent_name}, an AI assistant from ORIN GPS Tracker.

TASK:
Classify the user's message intent into one of two categories:

1. "greeting" - Simple greeting, such as:
   - "Hi", "Hello", "Halo"
   - "Halo kak", "Hi kak"
   - "Saya pengguna orin"
   - "Minta tolong", "Help me", "Tolong"
   - "Halo test", "Testing"
   - "P", "Pagi", "Siang", "Sore", "Malam"

2. "other" - Message other than greeting

Return ONLY the classification as JSON with "intent" and "reasoning" fields."""

    # Format prompt with agent_name
    system_prompt = system_prompt_template.format(agent_name=agent_name)

    # Use structured output
    classifier = intent_llm.with_structured_output(IntentClassification)

    result = await classifier.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Classify this message: {user_message}")
    ])

    logger.info(f"Intent classification result: {result.intent} - {result.reasoning}")
    return result


async def send_first_follow_up_message(
    customer_id: int,
    phone_number: str,
    lid_number: str,
    conversation_id: str,
    agent_name: str
):
    """
    Send first follow-up message to customer after 3 minutes of inactivity.

    Message fetched from database: first_follow_up_message
    """
    logger.info(f"send_first_follow_up_message called - customer_id: {customer_id}")

    # Import here to avoid circular dependency
    from src.orin_ai_crm.core.agents.tools.db_tools import save_message_to_db
    from src.orin_ai_crm.server.services.freshchat_api import send_message_to_freshchat
    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    # Fetch first follow-up message from database
    follow_up_template = await get_prompt_from_db("first_follow_up_message")
    if not follow_up_template:
        logger.warning("first_follow_up_message not found in DB, using default")
        follow_up_template = "Halo kak, ada yang bisa {agent_name} bantu? 😊"

    # Format message with agent_name
    follow_up_text = follow_up_template.format(agent_name=agent_name)

    try:
        # Use the Freshchat conversation ID provided
        if not conversation_id:
            logger.error(f"No conversation_id provided for customer: {customer_id}")
            return

        # Send follow-up message via Freshchat
        await send_message_to_freshchat(
            conversation_id=conversation_id,
            message_content=follow_up_text
        )

        # Save to database for analytics
        await save_message_to_db(customer_id, "ai", follow_up_text, content_type="text")

        logger.info(f"First follow-up message sent to customer {customer_id}: {follow_up_text}")

    except Exception as e:
        logger.error(f"Failed to send first follow-up message to customer {customer_id}: {e}")


async def send_second_follow_up_message(
    customer_id: int,
    phone_number: str,
    lid_number: str,
    conversation_id: str,
    agent_name: str
):
    """
    Send second follow-up message to customer after 6 minutes of inactivity.

    Message fetched from database: second_follow_up_message
    """
    logger.info(f"send_second_follow_up_message called - customer_id: {customer_id}")

    # Import here to avoid circular dependency
    from src.orin_ai_crm.core.agents.tools.db_tools import save_message_to_db
    from src.orin_ai_crm.server.services.freshchat_api import send_message_to_freshchat
    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    # Fetch second follow-up message from database
    follow_up_text = await get_prompt_from_db("second_follow_up_message")
    if not follow_up_text:
        logger.warning("second_follow_up_message not found in DB, using default")
        follow_up_text = "Baik Kak, silahkan chat lagi bila masih butuh bantuan. Untuk panduan online ORIN, bisa cek https://orin.id/panduan ya"

    try:
        # Use the Freshchat conversation ID provided
        if not conversation_id:
            logger.error(f"No conversation_id provided for customer: {customer_id}")
            return

        # Send follow-up message via Freshchat
        await send_message_to_freshchat(
            conversation_id=conversation_id,
            message_content=follow_up_text
        )

        # Save to database for analytics
        await save_message_to_db(customer_id, "ai", follow_up_text, content_type="text")

        logger.info(f"Second follow-up message sent to customer {customer_id}: {follow_up_text}")

    except Exception as e:
        logger.error(f"Failed to send second follow-up message to customer {customer_id}: {e}")


async def schedule_follow_up_message(
    customer_id: int,
    phone_number: str,
    lid_number: str,
    conversation_id: str,
    delay_seconds: int = 180
):
    """
    Schedule follow-up messages to be sent after delays.

    Sends two follow-up messages:
    1. After delay_seconds (default: 180s / 3 minutes)
    2. After 2 * delay_seconds (default: 360s / 6 minutes total)

    Cancels any existing pending task for this customer before scheduling new one.

    Args:
        customer_id: Customer ID
        phone_number: Phone number for Freshchat
        lid_number: LID number for Freshchat
        conversation_id: Freshchat conversation ID (UUID)
        delay_seconds: Delay before first follow-up (default: 180 seconds)

    Returns:
        asyncio.Task: The scheduled task
    """
    global pending_follow_up_tasks

    # Cancel existing task if any
    await cancel_pending_follow_up(customer_id)

    agent_name = get_agent_name()

    # Create new background task
    task = asyncio.create_task(
        _follow_up_delay(
            customer_id=customer_id,
            phone_number=phone_number,
            lid_number=lid_number,
            conversation_id=conversation_id,
            agent_name=agent_name,
            delay_seconds=delay_seconds
        )
    )

    # Store task reference
    pending_follow_up_tasks[customer_id] = task

    logger.info(f"Scheduled follow-up message for customer {customer_id} in {delay_seconds} seconds")
    return task


async def _follow_up_delay(
    customer_id: int,
    phone_number: str,
    lid_number: str,
    conversation_id: str,
    agent_name: str,
    delay_seconds: int
):
    """
    Internal function that sends two follow-up messages with delays.

    Timeline:
    - 0s: Customer sends greeting
    - 180s (3 min): Send first follow-up
    - 360s (6 min): Send second follow-up

    This can be cancelled if customer sends another message.
    """
    try:
        # First delay: 3 minutes
        await asyncio.sleep(delay_seconds)

        # Check if task is still scheduled (not cancelled)
        if customer_id in pending_follow_up_tasks:
            # Send first follow-up message
            await send_first_follow_up_message(
                customer_id=customer_id,
                phone_number=phone_number,
                lid_number=lid_number,
                conversation_id=conversation_id,
                agent_name=agent_name
            )
            logger.info(f"First follow-up sent for customer {customer_id}, waiting 3 more minutes for second follow-up")

            # Second delay: another 3 minutes (total 6 minutes from greeting)
            await asyncio.sleep(delay_seconds)

            # Check again if task is still scheduled
            if customer_id in pending_follow_up_tasks:
                # Send second follow-up message
                await send_second_follow_up_message(
                    customer_id=customer_id,
                    phone_number=phone_number,
                    lid_number=lid_number,
                    conversation_id=conversation_id,
                    agent_name=agent_name
                )

                # Remove from pending tasks after second follow-up
                del pending_follow_up_tasks[customer_id]
                logger.info(f"Second follow-up sent and task removed for customer {customer_id}")
            else:
                logger.info(f"Task was cancelled before second follow-up for customer {customer_id}")
        else:
            logger.info(f"Task was cancelled before first follow-up for customer {customer_id}")

    except asyncio.CancelledError:
        logger.info(f"Follow-up task cancelled for customer {customer_id}")
        raise


async def cancel_pending_follow_up(customer_id: int):
    """
    Cancel any pending follow-up task for this customer.

    Args:
        customer_id: Customer ID

    Returns:
        bool: True if task was cancelled, False if no task was found
    """
    global pending_follow_up_tasks

    if customer_id in pending_follow_up_tasks:
        task = pending_follow_up_tasks[customer_id]
        if not task.done():
            task.cancel()
            logger.info(f"Cancelled pending follow-up task for customer {customer_id}")

        # Remove from pending tasks
        del pending_follow_up_tasks[customer_id]
        return True

    return False


async def node_intent_classification(state):
    """
    Intent Classification Node - First node in the workflow.

    Classifies user message as "greeting" or "other":
    - "greeting" → Schedule two follow-ups (3min and 6min), END workflow
    - "other" → Cancel any pending follow-ups, continue to agent_entry_handler

    Args:
        state: Current agent state (LangGraph standard)

    Returns:
        Updated state with routing decision
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import save_message_to_db

    logger.info("=" * 50)
    logger.info("ENTER: node_intent_classification")

    # Get customer info
    customer_id = state.get('customer_id')
    phone_number = state.get('phone_number')
    lid_number = state.get('lid_number')
    conversation_id = state.get('conversation_id')  # Freshchat conversation ID
    messages = state.get('messages', [])

    # Get user's last message
    user_message = ""
    if messages and len(messages) > 0:
        last_message = messages[-1]
        if isinstance(last_message, HumanMessage):
            user_message = last_message.content
        elif hasattr(last_message, 'content'):
            user_message = last_message.content

    if not user_message:
        logger.warning("No user message found - routing to agent_entry_handler")
        logger.info("EXIT: node_intent_classification -> agent_entry")
        logger.info("=" * 50)
        return {
            "route": "agent_entry"
        }

    logger.info(f"Classifying message: {user_message[:100]}...")

    # Classify intent
    try:
        classification = await classify_user_intent(user_message)
        logger.info(f"Intent: {classification.intent}")
        logger.info(f"Reasoning: {classification.reasoning}")
    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        # Default to "other" on error to continue normal flow
        classification = IntentClassification(intent="other", reasoning="Classification error, defaulting to other")

    # Handle based on classification
    if classification.intent == "greeting":
        logger.info("Message classified as 'greeting' - scheduling follow-up and ending workflow")

        # Save greeting message to database for analytics
        if customer_id:
            try:
                await save_message_to_db(customer_id, "user", user_message)
                logger.info(f"Greeting message saved to database for customer {customer_id}")
            except Exception as e:
                logger.error(f"Failed to save greeting message: {e}")

        # Schedule two follow-up messages (after 3 and 6 minutes)
        if customer_id:
            await schedule_follow_up_message(
                customer_id=customer_id,
                phone_number=phone_number or "",
                lid_number=lid_number or "",
                conversation_id=conversation_id or "",  # Pass Freshchat conversation ID
                delay_seconds=180
            )

        logger.info("EXIT: node_intent_classification -> END (greeting)")
        logger.info("=" * 50)

        # Return empty state to END workflow (no response sent)
        return {
            "route": "END",
            "classification": classification.model_dump()
        }

    else:  # "other"
        logger.info("Message classified as 'other' - cancelling any pending follow-up and continuing to agent")

        # Cancel any pending follow-up task
        if customer_id:
            cancelled = await cancel_pending_follow_up(customer_id)
            if cancelled:
                logger.info(f"Cancelled pending follow-up for customer {customer_id}")

        logger.info("EXIT: node_intent_classification -> agent_entry")
        logger.info("=" * 50)

        # Continue to normal agent flow
        return {
            "route": "agent_entry",
            "classification": classification.model_dump()
        }


def intent_router(state):
    """
    Router function for intent classification.

    Routes to:
    - END if greeting (follow-up will be sent by background task)
    - agent_entry_handler if other (continue normal flow)
    """
    route = state.get("route", "agent_entry")

    if route == "END":
        return "END"
    else:
        return "agent_entry"
