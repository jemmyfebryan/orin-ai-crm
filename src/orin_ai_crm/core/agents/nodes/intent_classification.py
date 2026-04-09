"""
Intent Classification Node

Classifies user messages into "greeting" or "other" to determine
whether to send a follow-up message after 10 seconds of inactivity.
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

    agent_name = get_agent_name()

    system_prompt = f"""You are {agent_name}, an AI assistant from ORIN GPS Tracker.

TASK:
Classify the user's message intent into one of two categories:

1. "greeting" - Simple greeting with NO important information, such as:
   - "Hi", "Hello", "Halo"
   - "Halo kak", "Hi kak"
   - "Saya pengguna orin", "I'm an orin user"
   - "Minta tolong", "Help me", "Tolong"
   - "Halo test", "Testing"
   - "P", "Pagi", "Siang", "Sore", "Malam"
   - Any greeting WITHOUT specific questions, requests, or information needs

2. "other" - Messages with actual content/information, such as:
   - Product inquiries: "Info produk OBU V", "Berapa harga GPS", "Saya mau pasang GPS"
   - Technical issues: "GPS saya tidak aktif", "Tidak bisa tracking"
   - Specific questions: "Apakah ada fitur X", "Bagaimana cara setting"
   - Complaints, requests for support, detailed conversations
   - Any message that shows a clear intent or needs a response

RULES:
- Be LENIENT with "greeting" classification - if unsure, classify as "greeting"
- If message contains ANY specific question, product mention, or clear intent, classify as "other"
- Single words or very short phrases without context → "greeting"
- Messages asking for help but WITHOUT details → "greeting"

Return ONLY the classification as JSON with "intent" and "reasoning" fields."""

    # Use structured output
    classifier = intent_llm.with_structured_output(IntentClassification)

    result = await classifier.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Classify this message: {user_message}")
    ])

    logger.info(f"Intent classification result: {result.intent} - {result.reasoning}")
    return result


async def send_follow_up_message(
    customer_id: int,
    phone_number: str,
    lid_number: str,
    agent_name: str
):
    """
    Send a follow-up message to customer after 10 seconds of inactivity.

    This function is called by the background task scheduled after greeting.
    """
    logger.info(f"send_follow_up_message called - customer_id: {customer_id}")

    # Import here to avoid circular dependency
    from src.orin_ai_crm.core.agents.tools.db_tools import save_message_to_db
    from src.orin_ai_crm.server.services.freshchat_api import send_message_to_freshchat

    # Generate follow-up message
    follow_up_text = f"Halo kak, ada yang bisa {agent_name} bantu? 😊"

    try:
        # Get conversation ID from phone/lid number
        # We need to get the Freshchat conversation ID
        from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            stmt = select(Customer).where(Customer.id == customer_id)
            result = await db.execute(stmt)
            customer = result.scalars().first()

            if not customer:
                logger.error(f"Customer not found: {customer_id}")
                return

            # Get or create conversation ID
            conversation_id = phone_number or lid_number

            if not conversation_id:
                logger.error(f"No conversation ID for customer: {customer_id}")
                return

        # Send follow-up message via Freshchat
        await send_message_to_freshchat(
            conversation_id=conversation_id,
            message_content=follow_up_text
        )

        # Save to database for analytics
        await save_message_to_db(customer_id, "ai", follow_up_text, content_type="text")

        logger.info(f"Follow-up message sent to customer {customer_id}: {follow_up_text}")

    except Exception as e:
        logger.error(f"Failed to send follow-up message to customer {customer_id}: {e}")


async def schedule_follow_up_message(
    customer_id: int,
    phone_number: str,
    lid_number: str,
    delay_seconds: int = 10
):
    """
    Schedule a follow-up message to be sent after delay_seconds.

    Cancels any existing pending task for this customer before scheduling new one.

    Args:
        customer_id: Customer ID
        phone_number: Phone number for Freshchat
        lid_number: LID number for Freshchat
        delay_seconds: Delay before sending follow-up (default: 10 seconds)

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
    agent_name: str,
    delay_seconds: int
):
    """
    Internal function that waits for delay_seconds then sends follow-up.

    This can be cancelled if customer sends another message.
    """
    try:
        await asyncio.sleep(delay_seconds)

        # Check if task is still scheduled (not cancelled)
        if customer_id in pending_follow_up_tasks:
            # Send follow-up message
            await send_follow_up_message(
                customer_id=customer_id,
                phone_number=phone_number,
                lid_number=lid_number,
                agent_name=agent_name
            )

            # Remove from pending tasks
            del pending_follow_up_tasks[customer_id]
            logger.info(f"Follow-up sent and task removed for customer {customer_id}")

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
    - "greeting" → Schedule follow-up after 10s, END workflow
    - "other" → Cancel any pending follow-up, continue to agent_entry_handler

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

        # Schedule follow-up message after 10 seconds
        if customer_id:
            await schedule_follow_up_message(
                customer_id=customer_id,
                phone_number=phone_number or "",
                lid_number=lid_number or "",
                delay_seconds=10
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
