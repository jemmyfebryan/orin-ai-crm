from typing import Optional

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
        'contact_name': customer.contact_name or ''
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
    


async def save_message_to_db(customer_id: Optional[int], role: str, content: str):
    """Simpan pesan ke database dengan customer_id"""
    logger.info(f"save_message_to_db called - customer_id: {customer_id}, role: {role}, content: {content[:100]}...")

    from src.orin_ai_crm.core.models.database import ChatSession

    async with AsyncSessionLocal() as db:
        new_msg = ChatSession(
            customer_id=customer_id,
            message_role=role,
            content=content
        )
        db.add(new_msg)
        await db.commit()
        await db.refresh(new_msg)
        logger.info(f"Message saved to DB - id: {new_msg.id}, customer_id: {new_msg.customer_id}")
