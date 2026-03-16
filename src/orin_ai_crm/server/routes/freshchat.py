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
from src.orin_ai_crm.server.services.freshchat_api import send_message_to_freshchat, get_freshchat_user_details
from src.orin_ai_crm.server.services.chat_processor import process_chat_request

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
    timeout_task: Optional[asyncio.Task] = None
):
    """
    Background task to process chat and send replies to Freshchat.

    This function runs asynchronously after the API request is accepted.

    Args:
        timeout_task: Optional asyncio task that sends timeout message.
                     Will be cancelled before sending final messages to prevent collision.
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

        # 3. Send each reply bubble as a separate message to Freshchat
        ai_replies = result["replies"]
        logger.info(f"Sending {len(ai_replies)} message bubbles to Freshchat...")
        for i, reply in enumerate(ai_replies):
            logger.info(f"Sending bubble {i+1}/{len(ai_replies)}: {reply[:50]}...")
            success = await send_message_to_freshchat(conversation_id, reply)
            if not success:
                logger.error(f"Failed to send bubble {i+1} to Freshchat")
            else:
                logger.info(f"Successfully sent bubble {i+1} to Freshchat")

        logger.info(f"Freshchat agent task completed for conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Error in Freshchat agent background task: {str(e)}")
        import traceback
        traceback.print_exc()


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
    """
    timeout_message = "Mohon tunggu sebentar ya, Hana akan segera membalas..."
    logger.info(f"Sending timeout message to conversation {conversation_id}")
    await send_message_to_freshchat(conversation_id, timeout_message)


async def process_freshchat_webhook_task(
    user_id: str,
    message_content: str,
    conversation_id: str
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
    """
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
        if phone_number not in settings.allowed_numbers:
            logger.info(f"Phone number not in allowlist: {phone_number}. ALLOWED_NUMBERS={settings.allowed_numbers}. Leaving for human agents.")
            return

        logger.info(f"Allowlist check passed for phone_number: {phone_number}")

        # 2.5. Start timeout timer (10 seconds)
        # If processing takes longer, send "please wait" message
        async def send_timeout_after_delay():
            await asyncio.sleep(10)  # Wait 10 seconds
            await send_timeout_message(conversation_id)

        timeout_task = asyncio.create_task(send_timeout_after_delay())

        # 2.6. TESTING: Check for "reset_chat" command (only for allowed numbers)
        if message_content.strip().lower() == "reset_chat":
            logger.info(f"Reset chat command detected for phone: {phone_number}")

            # Import the delete function
            from src.orin_ai_crm.server.routes.admin import soft_delete_customer_by_phone

            # Delete the customer
            result = await soft_delete_customer_by_phone(phone_number)

            # Send confirmation message back to user
            if result['success']:
                confirmation_msg = f"✅ Chat reset successful! Customer ID: {result['customer_id']}. Starting fresh chat."
            else:
                confirmation_msg = f"❌ Failed to reset chat: {result['message']}"

            # Send message to Freshchat
            await send_message_to_freshchat(conversation_id, confirmation_msg)

            logger.info(f"Reset chat completed for {phone_number}: {result['message']}")
            return  # Stop processing, don't continue to AI

        # 3. Integrate with existing AI processing logic
        # Pass timeout_task so it can be cancelled before sending final messages
        await process_freshchat_agent_task(
            phone_number=phone_number,
            lid_number=None,  # Webhook only provides phone_number
            message=message_content,
            contact_name=contact_name,
            is_new_chat=True,  # Always new chat at first, the second tries will use DB as source of truth
            conversation_id=conversation_id,
            user_id=user_id,
            timeout_task=timeout_task  # Pass timeout task to cancel before sending messages
        )

        logger.info(f"Webhook processing completed for conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Error in webhook background task: {str(e)}")
        import traceback
        traceback.print_exc()


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
        actor = payload.get("actor", {})
        actor_type = actor.get("actor_type", "")

        if actor_type != "user":
            # Still return 200 OK to Freshchat (don't retry)
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

        # 8. Queue Background Task (all heavy processing happens here)
        background_tasks.add_task(
            process_freshchat_webhook_task,
            user_id=user_id,
            message_content=message_content,
            conversation_id=conversation_id
        )

        # 9. Instant Response (CRITICAL - must be within 3 seconds)
        return FreshchatWebhookResponse(status="success")

    except Exception as e:
        logger.error(f"Error in freshchat-webhook endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        # STILL return 200 OK to prevent Freshchat from retrying
        return FreshchatWebhookResponse(status="success")
