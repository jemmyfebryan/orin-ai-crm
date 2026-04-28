"""
Freshchat integration endpoints - agent and webhook.
"""
from typing import Optional
import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.server.schemas.freshchat import (
    FreshchatAgentRequest,
    FreshchatAgentResponse,
    FreshchatWebhookResponse,
)
from src.orin_ai_crm.server.security.auth import verify_bearer_token
from src.orin_ai_crm.server.security.webhook import is_ip_allowed, verify_freshchat_signature
from src.orin_ai_crm.server.config.settings import settings
from src.orin_ai_crm.server.services.freshchat_api import send_message_to_freshchat, send_image_to_freshchat, send_pdf_to_freshchat, get_freshchat_user_details, notify_live_agent_takeover
from src.orin_ai_crm.server.services.chat_processor import process_chat_request
from src.orin_ai_crm.server.services.message_batcher import queue_or_batch_webhook, MAX_BUFFER_SIZE, MAX_CHAR_COUNT, pending_timeouts
from src.orin_ai_crm.core.agents.tools.db_tools import save_message_to_db, soft_delete_customer
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_agent_name
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from sqlalchemy import select, update
from src.orin_ai_crm.core.utils.db_retry import execute_with_retry

logger = get_logger(__name__)
router = APIRouter()


async def process_freshchat_agent_task(
    phone_number: Optional[str],
    lid_number: Optional[str],
    message: str,
    contact_name: Optional[str],
    is_new_chat: bool,
    conversation_id: str,
    user_id: str,
    timeout_task: Optional[asyncio.Task] = None,
    skip_user_save: bool = False,
    chat_log_id: Optional[int] = None,
):
    """
    Background task to process chat and send replies to Freshchat.

    This function runs asynchronously after the API request is accepted.

    Args:
        timeout_task: Optional asyncio task that sends timeout message.
                     Will be cancelled before sending final messages to prevent collision.
        skip_user_save: If True, skip saving user message to DB (used for batched messages).
        chat_log_id: Optional chat log ID for tracking.

    Returns:
        dict with processing results for chat log update:
            - ai_reply_ids: List of AI reply chat_session IDs
            - ai_reply_count: Number of AI reply bubbles
            - tool_calls: List of tool names used
            - images_sent: Number of images sent
            - pdfs_sent: Number of PDFs sent
            - human_takeover_triggered: Whether human takeover was triggered
            - agent_route: Final agent route
            - agents_called: List of agents called
            - orchestrator_step: Orchestrator step reached
            - max_orchestrator_steps: Max orchestrator steps
            - orchestrator_plan: Orchestrator plan
            - orchestrator_decision: Orchestrator decision JSON
    """
    try:
        logger.info(f"Processing Freshchat agent task for conversation {conversation_id}")

        # 1. Process the chat request using shared logic (HEAVY WAITING HERE)
        result = await process_chat_request(
            phone_number=phone_number,
            lid_number=lid_number,
            message=message,
            contact_name=contact_name,
            is_new_chat=is_new_chat,
            skip_user_save=skip_user_save,
            conversation_id=conversation_id,  # Pass Freshchat conversation ID
        )

        # 2. CANCEL TIMEOUT TASK before sending final messages
        # This prevents collision between "please wait" and final response bubbles
        if timeout_task and not timeout_task.done():
            timeout_task.cancel()
            try:
                await timeout_task
            except asyncio.CancelledError:
                logger.info("Timeout task cancelled before sending final messages")
                pass  # Expected if task was cancelled

        # 3. Send PDFs FIRST (before images and text messages)
        send_pdfs = result.get("send_pdfs", [])
        if send_pdfs:
            logger.info(f"Sending {len(send_pdfs)} PDFs to Freshchat...")
            for i, pdf_url in enumerate(send_pdfs):
                logger.info(f"Sending PDF {i+1}/{len(send_pdfs)}: {pdf_url}")
                success = await send_pdf_to_freshchat(conversation_id, pdf_url)
                if not success:
                    logger.error(f"Failed to send PDF {i+1} to Freshchat")
                else:
                    logger.info(f"Successfully sent PDF {i+1} to Freshchat")

        # 4. Send images SECOND (before text messages)
        send_images = result.get("send_images", [])
        if send_images:
            logger.info(f"Sending {len(send_images)} images to Freshchat...")
            for i, img_url in enumerate(send_images):
                logger.info(f"Sending image {i+1}/{len(send_images)}: {img_url}")
                success = await send_image_to_freshchat(conversation_id, img_url)
                if not success:
                    logger.error(f"Failed to send image {i+1} to Freshchat")
                else:
                    logger.info(f"Successfully sent image {i+1} to Freshchat")

        # 5. Send each reply bubble as a separate message to Freshchat
        ai_replies = result["replies"]
        logger.info(f"Sending {len(ai_replies)} message bubbles to Freshchat...")

        # Track AI reply IDs for chat log
        ai_reply_ids = []
        for i, reply in enumerate(ai_replies):
            logger.info(f"Sending bubble {i+1}/{len(ai_replies)}: {reply[:50]}...")
            success = await send_message_to_freshchat(conversation_id, reply)
            if not success:
                logger.error(f"Failed to send bubble {i+1} to Freshchat")
            else:
                logger.info(f"Successfully sent bubble {i+1} to Freshchat")

        # 6. Get AI reply IDs from chat_sessions table (for chat log)
        if chat_log_id and ai_replies:
            from sqlalchemy import select, desc
            from src.orin_ai_crm.core.models.database import ChatSession

            # Get customer_id from result
            customer_id = result.get("customer_id")
            if customer_id:
                async with AsyncSessionLocal() as db:
                    # Query the most recent N AI messages for this customer
                    # N = number of ai_replies
                    query = (
                        select(ChatSession.id)
                        .where(
                            ChatSession.customer_id == customer_id,
                            ChatSession.message_role == "ai"
                        )
                        .order_by(desc(ChatSession.created_at))
                        .limit(len(ai_replies))
                    )
                    # Use retry logic for database query
                    db_result = await execute_with_retry(db.execute, query, max_retries=3)
                    rows = db_result.scalars().all()
                    # Reverse to get oldest->newest order
                    ai_reply_ids = list(reversed(rows))

                logger.info(f"Found {len(ai_reply_ids)} AI reply IDs for chat log")

        logger.info(f"Freshchat agent task completed for conversation {conversation_id}")

        # 7. Return result data for chat log update
        return {
            "ai_reply_ids": ai_reply_ids,
            "ai_reply_count": len(ai_replies),
            "tool_calls": result.get("tool_calls", []),
            "images_sent": len(send_images),
            "pdfs_sent": len(send_pdfs),
            "human_takeover_triggered": False,  # Will be updated if human takeover occurs
            "agent_route": result.get("agent_route"),
            "agents_called": result.get("agents_called", []),
            "orchestrator_step": result.get("orchestrator_step"),
            "max_orchestrator_steps": result.get("max_orchestrator_steps"),
            "orchestrator_plan": result.get("orchestrator_plan"),
            "orchestrator_decision": result.get("orchestrator_decision"),
        }

    except asyncio.CancelledError:
        logger.info(f"Freshchat agent task cancelled for conversation {conversation_id} - stopping immediately")
        # Cancel timeout task if it exists
        if timeout_task and not timeout_task.done():
            timeout_task.cancel()
        # Re-raise to ensure task is properly cancelled
        raise

    except Exception as e:
        logger.error(f"Error in Freshchat agent background task: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return error result for chat log update
        return {
            "ai_reply_ids": [],
            "ai_reply_count": 0,
            "tool_calls": [],
            "images_sent": 0,
            "pdfs_sent": 0,
            "human_takeover_triggered": False,
            "agent_route": None,
            "agents_called": [],
            "orchestrator_step": None,
            "max_orchestrator_steps": None,
            "orchestrator_plan": None,
            "orchestrator_decision": None,
        }


@router.post("/freshchat-agent", response_model=FreshchatAgentResponse)
async def freshchat_agent_endpoint(
    req: FreshchatAgentRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    token: str = Depends(verify_bearer_token)
):
    """
    Freshchat integration endpoint with async/sync mode support.

    This endpoint:
    - Accepts chat requests from Freshchat webhook
    - Validates Bearer token for security
    - Can process asynchronously (background) or synchronously (wait)
    - Sends AI replies back to Freshchat via API

    Expected payload fields:
    - phone_number OR lid_number (required for internal DB)
    - message: User's message text
    - contact_name: Optional contact name
    - is_new_chat: Whether this is a new conversation
    - conversation_id: Freshchat conversation ID (required)
    - user_id: Freshchat user ID (required)
    - async_mode: True=background (immediate response), False=wait for completion

    Authentication:
    - Header: Authorization: Bearer <FRESHCHAT_AGENT_BEARER_TOKEN>

    Response modes:
    - async_mode=True: Returns {"status": "accepted"} immediately
    - async_mode=False: Waits for processing, returns {"status": "completed"}
    """
    try:
        logger.info(f"Get a request: {req}")
        conversation_link = req.conversation_id  # temporary use link
        conversation_id = conversation_link.split("/")[-1]

        if req.async_mode:
            # Asynchronous mode: process in background, return immediately
            background_tasks.add_task(
                process_freshchat_agent_task,
                phone_number=req.phone_number,
                lid_number=req.lid_number,
                message=req.message,
                contact_name=req.contact_name,
                is_new_chat=req.is_new_chat,
                conversation_id=conversation_id,
                user_id=req.user_id
            )

            logger.info(f"Background task queued for conversation {conversation_id}")

            return FreshchatAgentResponse(
                status="accepted",
                message="Chat request accepted and is being processed asynchronously"
            )
        else:
            # Synchronous mode: wait for processing to complete
            logger.info(f"Processing chat synchronously for conversation {conversation_id}")

            await process_freshchat_agent_task(
                phone_number=req.phone_number,
                lid_number=req.lid_number,
                message=req.message,
                contact_name=req.contact_name,
                is_new_chat=req.is_new_chat,
                conversation_id=conversation_id,
                user_id=req.user_id
            )

            logger.info(f"Synchronous processing completed for conversation {conversation_id}")

            return FreshchatAgentResponse(
                status="completed",
                message="Chat request processed successfully"
            )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in freshchat-agent endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat request error: {str(e)}")


async def send_timeout_message(conversation_id: str):
    """
    Send a timeout message to customer if processing takes too long.
    This function is called after 10 seconds if processing hasn't completed.

    NOTE: Temporarily disabled - client doesn't want this message anymore.
    """
    # agent_name = get_agent_name()
    # timeout_message = f"Mohon tunggu sebentar ya, {agent_name} akan segera membalas..."
    logger.info(f"Timeout message would be sent to conversation {conversation_id} (currently disabled)")
    # TEMPORARILY DISABLED: Client doesn't want this message
    # await send_message_to_freshchat(conversation_id, timeout_message)


async def process_freshchat_webhook_task(
    user_id: str,
    message_content: str,
    conversation_id: str,
    skip_db_save: bool = False,
    timeout_task: Optional[asyncio.Task] = None,
    batch_message_count: int = 1,
    batch_total_chars: int = 0,
):
    """
    Background task to process Freshchat webhook payload.

    This function runs asynchronously after the webhook returns 200 OK.
    All heavy processing happens here to avoid the 3-second timeout.

    If processing takes more than 10 seconds, sends a "please wait" message.

    Args:
        user_id: Freshchat user ID
        message_content: Message text content
        conversation_id: Freshchat conversation ID
        skip_db_save: If True, skip saving message to DB (used for batched messages)
        timeout_task: Optional timeout task (created by message_batcher)
        batch_message_count: Number of messages in this batch
        batch_total_chars: Total character count of this batch
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import (
        get_or_create_customer,
        create_chat_log,
        update_chat_log,
    )
    from src.orin_ai_crm.core.agents.config import llm_config

    chat_log_id = None
    timeout_triggered = False

    try:
        logger.info(f"Processing webhook task: conversation={conversation_id}, user_id={user_id}")

        # 1. Fetch User Details from Freshchat API (to get phone number)
        user_details = await get_freshchat_user_details(user_id)

        if not user_details:
            logger.warning(f"Failed to fetch user details for user_id={user_id}. Leaving for human agents.")
            return

        phone_number = user_details.get("phone", "")
        contact_name = user_details.get("first_name", "")

        if not phone_number:
            logger.warning(f"User has no phone number: user_id={user_id}. Leaving for human agents.")
            return

        logger.info(f"User details fetched: phone={phone_number}, name={contact_name}")

        # 2. Allowlist / Beta Testing Filter (by phone number)
        # If allowed_numbers is empty, allow all numbers (no filter)
        if settings.allowed_numbers and phone_number not in settings.allowed_numbers:
            logger.info(f"Phone number not in allowlist: {phone_number}. ALLOWED_NUMBERS={settings.allowed_numbers}. Leaving for human agents.")
            return

        logger.info(f"Allowlist check passed for phone_number: {phone_number}")

        # 3. Get or Create Customer (for chat log creation)
        customer_data = await get_or_create_customer(
            phone_number=phone_number,
            lid_number=None,
            contact_name=contact_name
        )
        customer_id = customer_data.get('customer_id')

        # 4. Get recent user message IDs from DB (for chat log)
        # We need to query the most recent N messages to get their IDs
        user_message_ids = []
        if not skip_db_save and batch_message_count > 0:
            from sqlalchemy import select, desc
            from src.orin_ai_crm.core.models.database import ChatSession

            async with AsyncSessionLocal() as db:
                # Query the most recent N user messages for this customer
                query = (
                    select(ChatSession.id)
                    .where(
                        ChatSession.customer_id == customer_id,
                        ChatSession.message_role == "user"
                    )
                    .order_by(desc(ChatSession.created_at))
                    .limit(batch_message_count)
                )
                # Use retry logic for database query
                result = await execute_with_retry(db.execute, query, max_retries=3)
                rows = result.scalars().all()
                # Reverse to get oldest->newest order
                user_message_ids = list(reversed(rows))

            logger.info(f"Found {len(user_message_ids)} user message IDs for chat log")

        # 5. Create Chat Log
        chat_log_id = await create_chat_log(
            customer_id=customer_id,
            conversation_id=conversation_id,
            user_id=user_id,
            phone_number=phone_number,
            contact_name=contact_name,
            batch_message_count=batch_message_count,
            batch_total_chars=batch_total_chars,
        )
        logger.info(f"Chat log created with ID: {chat_log_id}")

        # 6. Check if timeout was triggered (timeout task is still running after 10s)
        if timeout_task and not timeout_task.done() and timeout_task in pending_timeouts.values():
            # Check if 10 seconds have passed since task creation
            # We can't easily check this, so we'll mark it as potentially triggered
            # and let the update_chat_log set it properly if needed
            pass

        # 7. Integrate with existing AI processing logic
        # Pass timeout_task so it can be cancelled before sending final messages
        result = await process_freshchat_agent_task(
            phone_number=phone_number,
            lid_number=None,  # Webhook only provides phone_number
            message=message_content,
            contact_name=contact_name,
            is_new_chat=True,  # Always new chat at first, the second tries will use DB as source of truth
            conversation_id=conversation_id,
            user_id=user_id,
            timeout_task=timeout_task,  # Pass timeout task to cancel before sending messages
            skip_user_save=skip_db_save,  # Skip DB save if this is a batched message
            chat_log_id=chat_log_id,  # Pass chat_log_id for tracking
        )

        # 8. Update Chat Log with success
        # Get AI reply IDs from result
        ai_reply_ids = result.get("ai_reply_ids", [])

        # Check if timeout was triggered (timeout task completed)
        timeout_triggered = (
            timeout_task is not None and
            timeout_task.done() and
            not timeout_task.cancelled()
        )

        await update_chat_log(
            chat_log_id=chat_log_id,
            status="success",
            user_message_ids=user_message_ids,
            ai_reply_ids=ai_reply_ids,
            timeout_triggered=timeout_triggered,
            human_takeover_triggered=result.get("human_takeover_triggered", False),
            ai_model=llm_config.DEFAULT_MODEL,
            ai_reply_count=result.get("ai_reply_count", 0),
            tool_calls=result.get("tool_calls", []),
            images_sent=result.get("images_sent", 0),
            pdfs_sent=result.get("pdfs_sent", 0),
            agent_route=result.get("agent_route"),
            agents_called=result.get("agents_called", []),
            orchestrator_step=result.get("orchestrator_step"),
            max_orchestrator_steps=result.get("max_orchestrator_steps"),
            orchestrator_plan=result.get("orchestrator_plan"),
            orchestrator_decision=result.get("orchestrator_decision"),
        )

        logger.info(f"Webhook processing completed for conversation {conversation_id}, chat_log_id: {chat_log_id}")

    except asyncio.CancelledError:
        logger.info(f"Webhook task cancelled for conversation {conversation_id} - stopping immediately")

        # Update chat log with cancelled status
        if chat_log_id:
            try:
                await update_chat_log(
                    chat_log_id=chat_log_id,
                    status="cancelled",
                    timeout_triggered=timeout_triggered,
                )
            except Exception as e:
                logger.error(f"Failed to update chat log on cancellation: {str(e)}")

        # Re-raise to ensure task is properly cancelled
        raise

    except Exception as e:
        logger.error(f"Error in webhook background task: {str(e)}")
        import traceback
        error_traceback = traceback.format_exc()

        # Update chat log with error status
        if chat_log_id:
            try:
                await update_chat_log(
                    chat_log_id=chat_log_id,
                    status="failed",
                    error_stage="ai_processing",
                    error_message=str(e),
                    error_traceback=error_traceback,
                    timeout_triggered=timeout_triggered,
                )
            except Exception as log_error:
                logger.error(f"Failed to update chat log on error: {str(log_error)}")


@router.post("/freshchat-webhook", response_model=FreshchatWebhookResponse)
async def freshchat_webhook_endpoint(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Production-ready Freshchat webhook endpoint.

    This endpoint:
    - Accepts webhooks from Freshchat platform
    - Verifies RSA signature authentication
    - ONLY responds to WhatsApp messages (ignores Instagram, web, etc.)
    - Implements anti-loop mechanism (only processes user messages)
    - Responds instantly with 200 OK (within 3-second timeout)
    - Processes all heavy lifting in background tasks (API calls, allowlist checks, AI)

    Authentication:
    - Header: X-Freshchat-Signature: <Base64-encoded signature>
    - Algorithm: RSA-SHA256
    - Public key from: FRESHCHAT_WEBHOOK_TOKEN env variable

    Channel Filter (CRITICAL):
    - Only processes messages from configured FRESHCHAT_ALLOWED_CHANNEL_IDS
    - Each channel (WhatsApp, Instagram, etc.) has a unique freshchat_channel_id
    - Find your channel ID: Freshchat Admin > Channels > WhatsApp > Settings
    - This AI CRM only responds to configured channels (e.g., WhatsApp only)

    Anti-Loop Mechanism:
    - Only processes messages where actor.actor_type == "user"
    - Safely aborts if actor_type is "agent" or "system"

    Background Processing:
    - All heavy lifting happens in background task (FAST response)
    - Fetches user details from Freshchat API
    - Checks phone number against ALLOWED_NUMBERS
    - Processes AI response
    """
    try:
        # 1. Get Raw Body for Signature Verification
        body = await request.body()

        # 2. IP Allowlist Check (additional security layer)
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP", "")
            or request.client.host if request.client else "unknown"
        )

        ip_is_allowed = is_ip_allowed(client_ip, settings.freshchat_webhook_allowed_ips)

        # 3. Authentication Check (RSA Signature Verification)
        signature_header = request.headers.get("X-Freshchat-Signature", "").strip()

        if not signature_header:
            if not ip_is_allowed:
                logger.warning("Webhook authentication failed: missing X-Freshchat-Signature header")
                raise HTTPException(status_code=401, detail="Unauthorized")

        # Verify the signature
        signature_valid = verify_freshchat_signature(body, signature_header) if signature_header else False

        # Allow webhook if EITHER signature is valid OR IP is in allowlist
        if not signature_valid and not ip_is_allowed:
            logger.warning("Webhook authentication failed: invalid signature and IP not in allowlist")
            raise HTTPException(status_code=401, detail="Unauthorized")

        # 3. Parse JSON Payload
        payload = await request.json()

        # 4. Anti-Loop Mechanism (CRITICAL)
        # Detect live agent messages and set human_takeover flag
        actor = payload.get("actor", {})
        actor_type = actor.get("actor_type", "")

        if actor_type == "agent":
            # Live agent detected - set human_takeover flag if not already set
            logger.info("Live agent message detected - checking human_takeover flag...")

            # Extract conversation details
            data = payload.get("data", {})
            message = data.get("message", {})
            conversation_id = message.get("conversation_id", "")
            user_id = message.get("user_id", "")

            # Extract message content to verify it's a real agent message
            message_parts = message.get("message_parts", [])
            has_content = bool(message_parts and len(message_parts) > 0)

            if conversation_id and user_id and has_content:
                try:
                    # Fetch user details to get phone number
                    user_details = await get_freshchat_user_details(user_id)

                    if user_details:
                        phone_number = user_details.get("phone", "")

                        if phone_number:
                            # Get customer record
                            async with AsyncSessionLocal() as db:
                                customer_stmt = select(Customer).where(
                                    (Customer.phone_number == phone_number) |
                                    (Customer.lid_number == phone_number)
                                )
                                customer_result = await db.execute(customer_stmt)
                                customer = customer_result.scalars().first()

                                if customer:
                                    # Only set takeover flag if not already set
                                    if not customer.human_takeover:
                                        logger.info(f"Setting human_takeover=True for customer_id={customer.id} (live agent joined conversation)")

                                        # Update human_takeover flag
                                        update_stmt = update(Customer).where(
                                            Customer.id == customer.id
                                        ).values(human_takeover=True)

                                        await execute_with_retry(db.execute, update_stmt, max_retries=3)
                                        await db.commit()

                                        logger.info(f"✅ Live agent takeover activated for customer_id={customer.id}, phone={phone_number}")

                                        # Notify live agents about the takeover
                                        customer_name = customer.name or customer.contact_name or ""
                                        await notify_live_agent_takeover(
                                            customer_name=customer_name,
                                            customer_phone=phone_number
                                        )

                                        logger.info(f"📢 Live agent notified about takeover for customer_id={customer.id}")
                                    else:
                                        logger.info(f"Human takeover already active for customer_id={customer.id} - no action needed")

                except Exception as e:
                    logger.error(f"Error processing live agent message: {str(e)}")
                    import traceback
                    traceback.print_exc()

            # Return success - don't process agent messages through AI
            return FreshchatWebhookResponse(status="success")

        elif actor_type != "user":
            # System or other actor types - ignore
            return FreshchatWebhookResponse(status="success")

        # 5. Action Filter (only process message_create)
        action = payload.get("action", "")
        if action != "message_create":
            return FreshchatWebhookResponse(status="success")

        # 6. Safe Payload Extraction
        data = payload.get("data", {})
        message = data.get("message", {})

        # Extract required fields with safe defaults
        conversation_id = message.get("conversation_id", "")

        # CRITICAL: Channel Filter - ONLY respond to allowed channels
        freshchat_channel_id = message.get("freshchat_channel_id", "")

        # Check if this channel ID is allowed
        if settings.freshchat_allowed_channel_ids and freshchat_channel_id not in settings.freshchat_allowed_channel_ids:
            return FreshchatWebhookResponse(status="success")

        if not freshchat_channel_id:
            logger.warning(f"freshchat_channel_id is empty! This might be a test or system message. Allowing for now.")

        # Extract message content from message_parts array
        message_parts = message.get("message_parts", [])
        message_content = ""
        if message_parts and len(message_parts) > 0:
            message_content = message_parts[0].get("text", {}).get("content", "")

        # Extract user_id from Freshchat
        user_id = message.get("user_id", "")

        # 7. Validation Checks
        if not conversation_id or not message_content:
            logger.warning(f"Incomplete webhook payload: conversation_id={conversation_id}, has_message={bool(message_content)}")
            return FreshchatWebhookResponse(status="success")

        # 8. Fetch User Details (for DB save and allowlist check)
        user_details = await get_freshchat_user_details(user_id)

        if not user_details:
            logger.warning(f"Failed to fetch user details for user_id={user_id}. Leaving for human agents.")
            return FreshchatWebhookResponse(status="success")

        phone_number = user_details.get("phone", "")
        contact_name = user_details.get("first_name", "")

        if not phone_number:
            logger.warning(f"User has no phone number: user_id={user_id}. Leaving for human agents.")
            return FreshchatWebhookResponse(status="success")

        logger.info(f"User details fetched: phone={phone_number}, name={contact_name}")

        # 9. Allowlist / Beta Testing Filter (by phone number)
        # If allowed_numbers is empty, allow all numbers (no filter)
        if settings.allowed_numbers and phone_number not in settings.allowed_numbers:
            logger.info(f"Phone number not in allowlist: {phone_number}. ALLOWED_NUMBERS={settings.allowed_numbers}. Leaving for human agents.")
            return FreshchatWebhookResponse(status="success")

        logger.info(f"Allowlist check passed for phone_number: {phone_number}")

        # 10. Testing Feature: reset_chat command
        # If user sends "reset_chat", soft delete the customer immediately
        # This is a testing feature to reset chat history
        if message_content.strip() == "reset_chat":
            logger.info(f"reset_chat command detected for phone_number: {phone_number}")

            # Soft delete the customer in background
            async def reset_chat_task():
                result = await soft_delete_customer(phone_number)
                if result.get('success'):
                    logger.info(f"Customer soft deleted successfully: {result.get('customer_id')}")
                    # Send confirmation message to Freshchat
                    await send_message_to_freshchat(
                        conversation_id=conversation_id,
                        message_content=f"✅ {result.get('message')}"
                    )
                else:
                    logger.error(f"Failed to soft delete customer: {result.get('message')}")
                    await send_message_to_freshchat(
                        conversation_id=conversation_id,
                        message_content=f"❌ {result.get('message')}"
                    )

            # Queue background task for soft delete
            background_tasks.add_task(reset_chat_task)

            # Return immediately without saving to DB or batching
            return FreshchatWebhookResponse(status="success")

        # 11. Get or Create Customer (for DB save)
        from src.orin_ai_crm.core.agents.tools.db_tools import get_or_create_customer

        customer_data = await get_or_create_customer(
            phone_number=phone_number,
            lid_number=None,
            contact_name=contact_name
        )
        customer_id = customer_data.get('customer_id')
        human_takeover = customer_data.get('human_takeover', False)

        # 12. Check human_takeover flag - if True, skip AI processing
        if human_takeover:
            logger.info(f"Human takeover is active for customer_id={customer_id}. Skipping AI processing and leaving for human agents.")
            # Still save message to DB for record keeping
            await save_message_to_db(customer_id, "user", message_content, content_type="text")
            logger.info(f"Message saved to DB (human takeover mode): customer_id={customer_id}, message={message_content[:50]}...")
            # Return immediately without AI processing
            return FreshchatWebhookResponse(status="success")

        # 13. Save individual message to DB immediately (before batching)
        await save_message_to_db(customer_id, "user", message_content, content_type="text")
        logger.info(f"Individual message saved to DB: customer_id={customer_id}, message={message_content[:50]}...")

        # 13. Queue or Batch webhook (message batching logic)
        # This will either add to buffer and restart AI processing, or ignore if buffer is full
        batch_result = queue_or_batch_webhook(
            user_id=user_id,
            message_content=message_content,
            conversation_id=conversation_id
        )

        if batch_result.get("ignored"):
            logger.warning(
                f"Message ignored due to buffer limits: "
                f"{batch_result['message_count']}/{MAX_BUFFER_SIZE} messages, "
                f"{batch_result['char_count']}/{MAX_CHAR_COUNT} chars"
            )

        # 14. Instant Response (CRITICAL - must be within 3 seconds)
        return FreshchatWebhookResponse(status="success")

    except Exception as e:
        logger.error(f"Error in freshchat-webhook endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        # STILL return 200 OK to prevent Freshchat from retrying
        return FreshchatWebhookResponse(status="success")
