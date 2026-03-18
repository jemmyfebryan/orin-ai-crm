from typing import Optional, List
from datetime import datetime

from sqlalchemy import select

from src.orin_ai_crm.core.models.database import AsyncSessionLocal, ChatSession, ChatLog, Customer, WIB
from src.orin_ai_crm.core.logger import get_logger

logger = get_logger(__name__)

async def get_or_create_customer(
    phone_number: Optional[str] = None,
    lid_number: Optional[str] = None,
    contact_name: Optional[str] = None
) -> dict:
    """
    Get existing customer or create a new one from database.

    Use this tool when:
    - Starting a new conversation (need to identify the customer)
    - Customer provides their phone number or ID
    - You need customer_id for other operations

    Returns:
        dict with: customer_id, name, domicile, vehicle_id, vehicle_alias, unit_qty, is_b2b, is_onboarded

    Example:
        Input: phone_number="628123456789", contact_name="Budi"
        Output: {customer_id: 123, name: "Budi", domicile: "Jakarta", ...}
    """
    logger.info(f"TOOL: get_or_create_customer - phone: {phone_number}, lid: {lid_number}, contact: {contact_name}")

    async with AsyncSessionLocal() as db:
        # Search by phone_number first (priority)
        customer = None
        if phone_number:
            query = select(Customer).where(
                Customer.phone_number == phone_number,
                Customer.deleted_at.is_(None)  # Exclude soft-deleted customers
            )
            result = await db.execute(query)
            customer = result.scalars().first()

        # If not found, search by lid_number
        if not customer and lid_number:
            query = select(Customer).where(
                Customer.lid_number == lid_number,
                Customer.deleted_at.is_(None)  # Exclude soft-deleted customers
            )
            result = await db.execute(query)
            customer = result.scalars().first()

        if customer:
            # Update missing identifiers
            need_update = False
            if phone_number and not customer.phone_number:
                customer.phone_number = phone_number
                need_update = True
            if lid_number and not customer.lid_number:
                customer.lid_number = lid_number
                need_update = True
            if contact_name and contact_name != customer.contact_name:
                customer.contact_name = contact_name
                need_update = True

            if need_update:
                await db.commit()
                await db.refresh(customer)

            db.expunge(customer)
            logger.info(f"Customer FOUND: id={customer.id}")
        else:
            # Create new customer
            customer = Customer(
                phone_number=phone_number,
                lid_number=lid_number,
                contact_name=contact_name,
                name=contact_name,
                is_onboarded=False
            )
            db.add(customer)
            await db.commit()
            await db.refresh(customer)
            db.expunge(customer)
            logger.info(f"New customer CREATED: id={customer.id}")

    return {
        'customer_id': customer.id,
        'name': customer.name or '',
        'domicile': customer.domicile or '',
        'vehicle_id': customer.vehicle_id if customer.vehicle_id else -1,
        'vehicle_alias': customer.vehicle_alias or '',
        'unit_qty': customer.unit_qty if customer.unit_qty else 0,
        'is_b2b': customer.is_b2b if customer.is_b2b else False,
        'is_onboarded': customer.is_onboarded if customer.is_onboarded else False,
        'contact_name': customer.contact_name or '',
        'human_takeover': customer.human_takeover if customer.human_takeover else False
    }


async def get_chat_history(customer_id: int, limit: int = 20):
    """
    Mengambil riwayat chat paling baru dari database.

    Fetches the most recent 'limit' messages, sorted oldest->newest for LLM context.
    Example: If customer has 100 messages and limit=20, returns messages #81-100 sorted #81->#100.
    """
    logger.info(f"get_chat_history called - customer_id: {customer_id}, limit: {limit}")

    async with AsyncSessionLocal() as db:
        # First fetch most recent messages (DESC order)
        query = (
            select(ChatSession)
            .where(ChatSession.customer_id == customer_id)
            .order_by(ChatSession.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        rows = result.scalars().all()

        # Reverse to get oldest->newest order for proper LLM context
        rows = rows[::-1]

        logger.info(f"get_chat_history found {len(rows)} rows for customer_id: {customer_id}")
        for row in rows:
            logger.info(f"  - {row.message_role}: {row.content[:50]}...")

        # Detach semua objects dari session
        for row in rows:
            db.expunge(row)

        return rows
    


async def save_message_to_db(customer_id: Optional[int], role: str, content: str, content_type: str = "text") -> Optional[int]:
    """
    Simpan pesan ke database dengan customer_id.

    Args:
        customer_id: Customer ID
        role: Message role ('user', 'ai', 'system')
        content: Message content
        content_type: Content type ('text', 'image', 'pdf')

    Returns:
        int: The ID of the created message, or None if failed
    """
    logger.info(f"save_message_to_db called - customer_id: {customer_id}, role: {role}, content_type: {content_type}, content: {content[:100]}...")

    from src.orin_ai_crm.core.models.database import ChatSession

    try:
        async with AsyncSessionLocal() as db:
            new_msg = ChatSession(
                customer_id=customer_id,
                message_role=role,
                content=content,
                content_type=content_type
            )
            db.add(new_msg)
            await db.commit()
            await db.refresh(new_msg)
            logger.info(f"Message saved to DB - id: {new_msg.id}, customer_id: {new_msg.customer_id}, content_type: {new_msg.content_type}")
            return new_msg.id
    except Exception as e:
        logger.error(f"Error saving message to DB: {str(e)}")
        return None


async def get_account_type(customer_id: int) -> Optional[str]:
    """
    Get customer's account type from VPS database.

    Fetches the customer's phone number from the local database,
    then queries the VPS database to get the account type.

    Args:
        customer_id: The customer's ID

    Returns:
        Optional[str]: Account type ('free', 'basic', 'lite', 'promo', 'plus') or None if not found
    """
    from src.orin_ai_crm.core.agents.tools.vps_tools import get_account_type_from_vps

    logger.info(f"get_account_type called - customer_id: {customer_id}")

    async with AsyncSessionLocal() as db:
        # Fetch customer's phone number
        query = select(Customer.phone_number).where(
            Customer.id == customer_id,
            Customer.deleted_at.is_(None)
        )
        result = await db.execute(query)
        phone_number = result.scalar_one_or_none()

    if not phone_number:
        logger.warning(f"No phone_number found for customer_id: {customer_id}")
        return None

    logger.info(f"Found phone_number for customer {customer_id}: {phone_number}")

    # Query VPS database for account type
    account_type = await get_account_type_from_vps(phone_number)
    logger.info(f"Account type for customer {customer_id}: {account_type}")

    return account_type


async def get_device_type(customer_id: int) -> Optional[str]:
    """
    Get customer's device type from VPS database.

    Fetches the customer's phone number from the local database,
    then queries the VPS database to get the device type.

    Args:
        customer_id: The customer's ID

    Returns:
        Optional[str]: Device type (from VPS device_types.protocol or name) or None if not found
    """
    from src.orin_ai_crm.core.agents.tools.vps_tools import get_device_type_from_vps

    logger.info(f"get_device_type called - customer_id: {customer_id}")

    async with AsyncSessionLocal() as db:
        # Fetch customer's phone number
        query = select(Customer.phone_number).where(
            Customer.id == customer_id,
            Customer.deleted_at.is_(None)
        )
        result = await db.execute(query)
        phone_number = result.scalar_one_or_none()

    if not phone_number:
        logger.warning(f"No phone_number found for customer_id: {customer_id}")
        return None

    logger.info(f"Found phone_number for customer {customer_id}: {phone_number}")

    # Query VPS database for device type
    device_type = await get_device_type_from_vps(phone_number)
    logger.info(f"Device type for customer {customer_id}: {device_type}")

    return device_type


async def soft_delete_customer(phone_number: str) -> dict:
    """
    Soft delete a customer by setting their deleted_at timestamp.

    This is a testing feature that allows resetting a customer's chat history.
    The customer record is not actually deleted from the database, just marked
    as deleted. A new customer record will be created on the next message.

    Args:
        phone_number: The customer's phone number

    Returns:
        dict with:
            - success: bool - whether the soft delete was successful
            - customer_id: int - the ID of the deleted customer (if successful)
            - message: str - status message

    Example:
        Input: phone_number="628123456789"
        Output: {success: True, customer_id: 123, message: "Customer 123 deleted successfully. Chat reset complete."}
    """
    from datetime import datetime
    from src.orin_ai_crm.core.models.database import WIB

    logger.info(f"soft_delete_customer called - phone_number: {phone_number}")

    try:
        async with AsyncSessionLocal() as db:
            # Find customer by phone_number (only non-deleted ones)
            query = select(Customer).where(
                Customer.phone_number == phone_number,
                Customer.deleted_at.is_(None)
            )
            result = await db.execute(query)
            customer = result.scalars().first()

            if not customer:
                logger.info(f"Customer not found for phone: {phone_number}")
                return {
                    'success': True,
                    'message': f'No customer found for phone: {phone_number}',
                    'customer_id': None
                }

            # Check if already deleted
            if customer.deleted_at is not None:
                logger.info(f"Customer already deleted: {customer.id}")
                return {
                    'success': True,
                    'message': f'Customer already deleted at: {customer.deleted_at}',
                    'customer_id': customer.id
                }

            # Soft delete: Set deleted_at timestamp
            customer_id = customer.id
            customer.deleted_at = datetime.now(WIB)
            await db.commit()
            await db.refresh(customer)

            logger.info(f"Customer {customer_id} soft-deleted successfully")

            return {
                'success': True,
                'message': f'Customer {customer_id} deleted successfully. Chat reset complete.',
                'customer_id': customer_id
            }

    except Exception as e:
        logger.error(f"Error soft-deleting customer: {str(e)}")
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'customer_id': None
        }


async def create_chat_log(
    customer_id: Optional[int],
    conversation_id: str,
    user_id: str,
    phone_number: str,
    contact_name: Optional[str],
    batch_message_count: int = 1,
    batch_total_chars: int = 0,
) -> int:
    """
    Create a new chat log entry for background task tracking.

    Args:
        customer_id: Customer ID
        conversation_id: Freshchat conversation ID
        user_id: Freshchat user ID
        phone_number: Customer phone number
        contact_name: Customer contact name
        batch_message_count: Number of messages in batch
        batch_total_chars: Total character count of batch

    Returns:
        int: The ID of the created chat log
    """
    logger.info(
        f"create_chat_log - conversation_id: {conversation_id}, "
        f"customer_id: {customer_id}, batch_count: {batch_message_count}"
    )

    async with AsyncSessionLocal() as db:
        chat_log = ChatLog(
            customer_id=customer_id,
            conversation_id=conversation_id,
            user_id=user_id,
            phone_number=phone_number,
            contact_name=contact_name,
            batch_message_count=batch_message_count,
            batch_total_chars=batch_total_chars,
            started_at=datetime.now(WIB),
            status="in_progress"
        )
        db.add(chat_log)
        await db.commit()
        await db.refresh(chat_log)

        logger.info(f"Chat log created with ID: {chat_log.id}")
        return chat_log.id


async def update_chat_log(
    chat_log_id: int,
    status: str,
    user_message_ids: Optional[List[int]] = None,
    ai_reply_ids: Optional[List[int]] = None,
    timeout_triggered: bool = False,
    human_takeover_triggered: bool = False,
    ai_model: Optional[str] = None,
    ai_reply_count: int = 0,
    tool_calls: Optional[List[str]] = None,
    images_sent: int = 0,
    pdfs_sent: int = 0,
    agent_route: Optional[str] = None,
    agents_called: Optional[List[str]] = None,
    orchestrator_step: Optional[int] = None,
    max_orchestrator_steps: Optional[int] = None,
    orchestrator_plan: Optional[str] = None,
    orchestrator_decision: Optional[str] = None,
    error_stage: Optional[str] = None,
    error_message: Optional[str] = None,
    error_traceback: Optional[str] = None,
) -> dict:
    """
    Update a chat log entry with processing results.

    Args:
        chat_log_id: Chat log ID to update
        status: Final status (success, failed, cancelled, timeout)
        user_message_ids: List of chat_session IDs for user messages
        ai_reply_ids: List of chat_session IDs for AI replies
        timeout_triggered: Whether timeout message was sent
        human_takeover_triggered: Whether human takeover was triggered
        ai_model: AI model used
        ai_reply_count: Number of AI reply bubbles
        tool_calls: List of tool names used
        images_sent: Number of images sent
        pdfs_sent: Number of PDFs sent
        agent_route: Final agent route
        agents_called: List of agent names called
        orchestrator_step: Orchestrator step reached
        max_orchestrator_steps: Max orchestrator steps
        orchestrator_plan: Orchestrator plan
        orchestrator_decision: Orchestrator decision JSON
        error_stage: Stage where error occurred
        error_message: Error message
        error_traceback: Full error traceback

    Returns:
        dict with: success (bool), message (str), chat_log_id (int)
    """
    logger.info(f"update_chat_log - chat_log_id: {chat_log_id}, status: {status}")

    try:
        async with AsyncSessionLocal() as db:
            # Fetch the chat log
            query = select(ChatLog).where(ChatLog.id == chat_log_id)
            result = await db.execute(query)
            chat_log = result.scalars().first()

            if not chat_log:
                logger.error(f"Chat log not found: {chat_log_id}")
                return {
                    'success': False,
                    'message': f'Chat log not found: {chat_log_id}',
                    'chat_log_id': chat_log_id
                }

            # Update basic fields
            chat_log.status = status
            chat_log.completed_at = datetime.now(WIB)

            # Calculate duration
            if chat_log.started_at:
                duration = chat_log.completed_at - chat_log.started_at
                chat_log.processing_duration_ms = int(duration.total_seconds() * 1000)

            # Update references to chat_sessions
            if user_message_ids:
                chat_log.user_message_ids = ",".join(map(str, user_message_ids))
            if ai_reply_ids:
                chat_log.ai_reply_ids = ",".join(map(str, ai_reply_ids))

            # Update flags
            chat_log.timeout_triggered = timeout_triggered
            chat_log.human_takeover_triggered = human_takeover_triggered

            # Update AI processing results
            if ai_model:
                chat_log.ai_model = ai_model
            chat_log.ai_reply_count = ai_reply_count
            if tool_calls:
                import json
                chat_log.tool_calls = json.dumps(tool_calls)
            chat_log.images_sent = images_sent
            chat_log.pdfs_sent = pdfs_sent

            # Update orchestrator details
            if agent_route:
                chat_log.agent_route = agent_route
            if agents_called:
                import json
                chat_log.agents_called = json.dumps(agents_called)
            if orchestrator_step is not None:
                chat_log.orchestrator_step = orchestrator_step
            if max_orchestrator_steps is not None:
                chat_log.max_orchestrator_steps = max_orchestrator_steps
            if orchestrator_plan:
                chat_log.orchestrator_plan = orchestrator_plan
            if orchestrator_decision:
                chat_log.orchestrator_decision = orchestrator_decision

            # Update error information
            if error_stage:
                chat_log.error_stage = error_stage
            if error_message:
                chat_log.error_message = error_message
            if error_traceback:
                chat_log.error_traceback = error_traceback

            await db.commit()

            logger.info(f"Chat log {chat_log_id} updated successfully with status: {status}")
            return {
                'success': True,
                'message': f'Chat log updated successfully',
                'chat_log_id': chat_log_id
            }

    except Exception as e:
        logger.error(f"Error updating chat log {chat_log_id}: {str(e)}")
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'chat_log_id': chat_log_id
        }
