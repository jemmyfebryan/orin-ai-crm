"""
Message batching service for Freshchat webhooks.

This service implements debouncing to prevent multiple rapid messages from
triggering separate AI processing workflows. Messages are batched until
AI processing completes, then processed together as a single request.

Features:
- Batches messages by conversation_id
- Max 5 messages OR 2000 characters per batch (whichever comes first)
- Cancels in-flight processing if new message arrives
- Individual messages saved to DB immediately
- Concatenated message used for AI processing only (NOT saved to DB)
- Comprehensive chat logging for debugging
"""
import asyncio
from collections import deque
from typing import Optional

from src.orin_ai_crm.core.logger import get_logger

logger = get_logger(__name__)

# Configuration
MAX_BUFFER_SIZE = 5  # Maximum number of messages per batch
MAX_CHAR_COUNT = 2000  # Maximum character count per batch

# Global state tracking
# Maps conversation_id -> asyncio.Task (the AI processing task)
pending_tasks: dict[str, asyncio.Task] = {}
# Maps conversation_id -> asyncio.Task (the timeout task)
pending_timeouts: dict[str, asyncio.Task] = {}
# Maps conversation_id -> deque of message strings (accumulated messages)
message_buffers: dict[str, deque[str]] = {}
# Maps conversation_id -> asyncio.Lock (for thread safety per conversation)
processing_locks: dict[str, asyncio.Lock] = {}


def _can_add_to_buffer(buffer: deque[str], new_message: str) -> bool:
    """
    Check if a new message can be added to the buffer.

    A message can be added if BOTH conditions are met:
    1. Buffer has less than MAX_BUFFER_SIZE messages
    2. Total character count (including new message) <= MAX_CHAR_COUNT

    Args:
        buffer: Current message buffer
        new_message: New message to add

    Returns:
        True if message can be added, False otherwise
    """
    # Check message count
    if len(buffer) >= MAX_BUFFER_SIZE:
        logger.info(f"Buffer full: {len(buffer)}/{MAX_BUFFER_SIZE} messages")
        return False

    # Check character count
    current_chars = sum(len(msg) for msg in buffer)
    total_chars = current_chars + len(new_message) + len("\n\n") * len(buffer)

    if total_chars > MAX_CHAR_COUNT:
        logger.info(
            f"Character limit reached: {total_chars}/{MAX_CHAR_COUNT} chars "
            f"(current: {current_chars}, new: {len(new_message)})"
        )
        return False

    return True


async def process_message_batch(
    user_id: str,
    conversation_id: str,
    accumulated_messages: list[str],
    timeout_task: Optional[asyncio.Task] = None
):
    """
    Process batched messages as a single AI request.

    This function is called after batching completes (when AI processing finishes).
    It concatenates all accumulated messages and sends them to the AI processor.

    The concatenated message is NOT saved to database (only individual messages
    were saved when webhooks arrived).

    Args:
        user_id: Freshchat user ID
        conversation_id: Freshchat conversation ID
        accumulated_messages: List of accumulated message strings
        timeout_task: Optional timeout task to pass to processor
    """
    from src.orin_ai_crm.server.routes.freshchat import process_freshchat_webhook_task

    # Concatenate messages with double newline separator
    concatenated = "\n\n".join(accumulated_messages)

    # Calculate batch stats
    batch_message_count = len(accumulated_messages)
    batch_total_chars = len(concatenated)

    logger.info(
        f"Processing batched messages for conversation {conversation_id}: "
        f"{batch_message_count} messages, {batch_total_chars} characters"
    )
    logger.info(f"Concatenated message preview: {concatenated[:200]}...")

    # Call the existing processor with skip_db_save=True and timeout task
    # (individual messages were already saved when webhooks arrived)
    await process_freshchat_webhook_task(
        user_id=user_id,
        message_content=concatenated,
        conversation_id=conversation_id,
        skip_db_save=True,  # Don't save concatenated message to DB
        timeout_task=timeout_task,  # Pass timeout task for cancellation
        batch_message_count=batch_message_count,  # Pass batch info for logging
        batch_total_chars=batch_total_chars,
    )

    logger.info(
        f"Batch processing completed for conversation {conversation_id}, "
        f"clearing buffer"
    )


async def _process_with_lock(
    user_id: str,
    conversation_id: str,
    messages: list[str],
    lock: asyncio.Lock,
    timeout_task: Optional[asyncio.Task] = None
):
    """
    Execute batch processing with a lock to prevent race conditions.

    Releases the conversation's resources (buffer, task, lock, timeout) after processing.

    Args:
        user_id: Freshchat user ID
        conversation_id: Freshchat conversation ID
        messages: List of messages to process
        lock: Asyncio lock for this conversation
        timeout_task: Optional timeout task to cancel after processing completes
    """
    processing_successful = False
    try:
        async with lock:
            await process_message_batch(user_id, conversation_id, messages, timeout_task)
            processing_successful = True
    except asyncio.CancelledError:
        # Task was cancelled - don't clean up anything, new task will overwrite references
        logger.info(f"Task cancelled for conversation {conversation_id} - preserving all state for new task")
        raise
    finally:
        # Only clean up if processing was successful (not cancelled)
        if processing_successful:
            # Clean up resources after processing completes
            message_buffers.pop(conversation_id, None)
            pending_tasks.pop(conversation_id, None)
            processing_locks.pop(conversation_id, None)

            # Cancel and clean up timeout task if it's still running
            if conversation_id in pending_timeouts:
                existing_timeout = pending_timeouts[conversation_id]
                if not existing_timeout.done():
                    existing_timeout.cancel()
                    logger.info(f"Cancelled timeout task for conversation {conversation_id}")
                pending_timeouts.pop(conversation_id, None)

            logger.info(f"Cleaned up resources for conversation {conversation_id}")


def queue_or_batch_webhook(
    user_id: str,
    message_content: str,
    conversation_id: str
) -> dict:
    """
    Queue a webhook message for batched processing.

    This function is called by the freshchat-webhook endpoint for every incoming message.

    Logic:
    1. Initialize buffer and lock for this conversation if needed
    2. Check if message can be added (size and char limits)
    3. Add message to buffer
    4. Cancel existing AI processing task if still running
    5. Start new AI processing task with accumulated messages

    Args:
        user_id: Freshchat user ID
        message_content: Message text content
        conversation_id: Freshchat conversation ID

    Returns:
        dict with status information:
        - added: bool - whether message was added to buffer
        - message_count: int - number of messages in buffer
        - char_count: int - total character count
        - ignored: bool - whether message was ignored due to limits
    """
    logger.info(
        f"queue_or_batch_webhook called: conversation_id={conversation_id}, "
        f"message={message_content[:50]}..."
    )

    # Initialize buffer and lock for this conversation if needed
    if conversation_id not in message_buffers:
        message_buffers[conversation_id] = deque(maxlen=MAX_BUFFER_SIZE)
        processing_locks[conversation_id] = asyncio.Lock()
        logger.info(f"Initialized new buffer for conversation {conversation_id}")

    buffer = message_buffers[conversation_id]
    lock = processing_locks[conversation_id]

    # Check if message can be added to buffer
    can_add = _can_add_to_buffer(buffer, message_content)

    if not can_add:
        # Message ignored due to limits (still saved to DB by caller)
        current_chars = sum(len(msg) for msg in buffer)
        logger.warning(
            f"Message ignored for conversation {conversation_id}: "
            f"buffer has {len(buffer)}/{MAX_BUFFER_SIZE} messages, "
            f"{current_chars}/{MAX_CHAR_COUNT} chars"
        )
        return {
            "added": False,
            "message_count": len(buffer),
            "char_count": current_chars,
            "ignored": True
        }

    # Add message to buffer
    buffer.append(message_content)
    new_chars = sum(len(msg) for msg in buffer) + len("\n\n") * (len(buffer) - 1)

    logger.info(
        f"Added message to buffer for conversation {conversation_id}: "
        f"{len(buffer)}/{MAX_BUFFER_SIZE} messages, "
        f"{new_chars}/{MAX_CHAR_COUNT} chars"
    )

    # Cancel existing AI processing task if still running
    if conversation_id in pending_tasks:
        existing_task = pending_tasks[conversation_id]
        if not existing_task.done():
            logger.info(
                f"Cancelling previous AI task for conversation {conversation_id}"
            )
            existing_task.cancel()

    # Cancel existing timeout task if still running
    if conversation_id in pending_timeouts:
        existing_timeout = pending_timeouts[conversation_id]
        if not existing_timeout.done():
            logger.info(
                f"Cancelling previous timeout task for conversation {conversation_id}"
            )
            existing_timeout.cancel()

    # Create new timeout task (10 seconds)
    async def send_timeout_after_delay():
        await asyncio.sleep(10)  # Wait 10 seconds
        from src.orin_ai_crm.server.routes.freshchat import send_timeout_message
        await send_timeout_message(conversation_id)

    timeout_task = asyncio.create_task(send_timeout_after_delay())
    pending_timeouts[conversation_id] = timeout_task
    logger.info(f"Started timeout task for conversation {conversation_id}")

    # Create new AI processing task with accumulated messages
    # (start immediately - no timer!)
    task = asyncio.create_task(
        _process_with_lock(user_id, conversation_id, list(buffer), lock, timeout_task)
    )
    pending_tasks[conversation_id] = task

    logger.info(
        f"Started new AI processing task for conversation {conversation_id}"
    )

    return {
        "added": True,
        "message_count": len(buffer),
        "char_count": new_chars,
        "ignored": False
    }


__all__ = [
    'MAX_BUFFER_SIZE',
    'MAX_CHAR_COUNT',
    'queue_or_batch_webhook',
    'pending_timeouts',
]
