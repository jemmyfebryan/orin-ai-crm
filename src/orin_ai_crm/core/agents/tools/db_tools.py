from typing import Optional
import random

from sqlalchemy import select

from src.orin_ai_crm.core.models.database import AsyncSessionLocal, ChatSession, Customer
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
    


async def save_message_to_db(customer_id: Optional[int], role: str, content: str, content_type: str = "text"):
    """Simpan pesan ke database dengan customer_id"""
    logger.info(f"save_message_to_db called - customer_id: {customer_id}, role: {role}, content_type: {content_type}, content: {content[:100]}...")

    from src.orin_ai_crm.core.models.database import ChatSession

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


async def get_account_type(customer_id: int) -> str:
    """
    Get customer's account type.

    For testing purposes, returns 'free' or 'plus' with 50% random chance.
    In production, this would query the actual account type from the database.

    Args:
        customer_id: The customer's ID

    Returns:
        str: Account type - 'free', 'lite', 'promo', 'pro', or 'plus'
    """
    logger.info(f"get_account_type called - customer_id: {customer_id}")

    # TODO: In production, query actual account_type from database
    # For now, return random 'free' or 'plus' for testing
    account_type = random.choice(['free', 'plus'])
    logger.info(f"Account type for customer {customer_id}: {account_type}")

    return account_type


async def get_device_type(state) -> str:
    """
    Get device type based on device name.

    For testing purposes, returns random device types.
    In production, this would query the actual device type from the database.

    Args:
        device_name: The device name/identifier

    Returns:
        str: Device type - 'GT06N', 'TR06', 'T700', 'T2', 'T30', 'Wetrack', 'moplus', 'TR02', 'postpaid', or other
    """
    logger.info(f"get_device_type called")

    # TODO: In production, query actual device_type from database based on device_name
    # For testing, return random device types
    device_types = ['GT06N', 'postpaid', 'OBU'] # 'TR06', 'T700', 'T2', 'T30', 'Wetrack', 'moplus', 'TR02',
    device_type = random.choice(device_types)
    logger.info(f"Device type result: {device_type}")

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
