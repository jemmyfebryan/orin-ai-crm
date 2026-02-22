"""
Customer Tools - Customer CRUD operations
"""

from typing import Optional
from sqlalchemy import select
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from src.orin_ai_crm.core.models.schemas import CustomerProfile
from src.orin_ai_crm.core.logger import get_logger

logger = get_logger(__name__)


async def get_or_create_customer(
    identifier: dict,
    contact_name: Optional[str] = None
) -> Customer:
    """
    Ambil customer berdasarkan phone_number ATAU lid_number.
    Priority: phone_number dulu, lalu lid_number.

    PENTING: Setiap phone_number/lid_number yang BERBEDA akan create customer BARU.
    """
    logger.info(f"get_or_create_customer called - identifier: {identifier}, contact_name: {contact_name}")

    async with AsyncSessionLocal() as db:
        # Cari berdasarkan prioritas: phone_number dulu, lalu lid_number
        customer = None

        # 1. Cari by phone_number dulu (prioritas utama)
        if identifier.get('phone_number'):
            query = select(Customer).where(
                Customer.phone_number == identifier.get('phone_number')
            )
            result = await db.execute(query)
            customer = result.scalars().first()
            logger.info(f"Search by phone_number '{identifier.get('phone_number')}': {'FOUND' if customer else 'NOT FOUND'}")

        # 2. Jika tidak ketemu by phone, cari by lid_number
        if not customer and identifier.get('lid_number'):
            query = select(Customer).where(
                Customer.lid_number == identifier.get('lid_number')
            )
            result = await db.execute(query)
            customer = result.scalars().first()
            logger.info(f"Search by lid_number '{identifier.get('lid_number')}': {'FOUND' if customer else 'NOT FOUND'}")

        if customer:
            logger.info(f"Customer FOUND - id: {customer.id}, phone: {customer.phone_number}, lid: {customer.lid_number}")

            # Update identifier yang kosong (link phone & lid)
            need_update = False
            if identifier.get('phone_number') and not customer.phone_number:
                customer.phone_number = identifier.get('phone_number')
                need_update = True
                logger.info(f"Updating customer.phone_number to: {identifier.get('phone_number')}")
            if identifier.get('lid_number') and not customer.lid_number:
                customer.lid_number = identifier.get('lid_number')
                need_update = True
                logger.info(f"Updating customer.lid_number to: {identifier.get('lid_number')}")
            # Update contact_name dari payload (latest)
            if contact_name and contact_name != customer.contact_name:
                customer.contact_name = contact_name
                need_update = True
                logger.info(f"Updating customer.contact_name to: {contact_name}")

            if need_update:
                await db.commit()
                await db.refresh(customer)

            # Detach dari session agar tidak terus terikat
            db.expunge(customer)
            return customer

        # Create new customer (tidak ketemu sama sekali)
        logger.info(f"Customer NOT FOUND - Creating NEW customer")
        customer = Customer(
            phone_number=identifier.get('phone_number'),
            lid_number=identifier.get('lid_number'),
            contact_name=contact_name
        )
        db.add(customer)
        await db.commit()
        await db.refresh(customer)

        logger.info(f"New customer CREATED - id: {customer.id}")

        # Detach dari session
        db.expunge(customer)
        return customer


async def update_customer_profile(
    customer_id: int,
    profile: CustomerProfile
) -> bool:
    """
    Update customer data dari extracted profile.
    Return True jika ada data yang berubah.
    """
    logger.info(f"update_customer_profile called - customer_id: {customer_id}, profile: {profile.model_dump()}")

    async with AsyncSessionLocal() as db:
        # Ambil customer fresh dari session baru
        query = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(query)
        customer = result.scalars().first()

        if not customer:
            logger.warning(f"Customer NOT FOUND for id: {customer_id}")
            return False

        need_update = False
        updates = []

        # Update field yang kosong atau berubah
        if profile.name and profile.name != customer.name:
            customer.name = profile.name
            need_update = True
            updates.append(f"name={profile.name}")

        if profile.domicile and profile.domicile != customer.domicile:
            customer.domicile = profile.domicile
            need_update = True
            updates.append(f"domicile={profile.domicile}")

        if profile.vehicle_type and profile.vehicle_type != customer.vehicle_type:
            customer.vehicle_type = profile.vehicle_type
            need_update = True
            updates.append(f"vehicle_type={profile.vehicle_type}")

        if profile.unit_qty and profile.unit_qty != customer.unit_qty:
            customer.unit_qty = profile.unit_qty
            need_update = True
            updates.append(f"unit_qty={profile.unit_qty}")

        if profile.is_b2b != customer.is_b2b:
            customer.is_b2b = profile.is_b2b
            need_update = True
            updates.append(f"is_b2b={profile.is_b2b}")

        if need_update:
            logger.info(f"Updating customer {customer_id}: {', '.join(updates)}")
            await db.commit()
            await db.refresh(customer)
            return True

        logger.info(f"No updates needed for customer {customer_id}")
        return False


async def get_chat_history(customer_id: int, limit: int = 20):
    """Mengambil riwayat chat dari database"""
    from src.orin_ai_crm.core.models.database import ChatSession

    async with AsyncSessionLocal() as db:
        query = (
            select(ChatSession)
            .where(ChatSession.customer_id == customer_id)
            .order_by(ChatSession.created_at.asc())
            .limit(limit)
        )
        result = await db.execute(query)
        rows = result.scalars().all()

        # Detach semua objects dari session
        for row in rows:
            db.expunge(row)

        return rows


async def save_message_to_db(customer_id: Optional[int], role: str, content: str):
    """Simpan pesan ke database dengan customer_id"""
    from src.orin_ai_crm.core.models.database import ChatSession

    async with AsyncSessionLocal() as db:
        new_msg = ChatSession(
            customer_id=customer_id,
            message_role=role,
            content=content
        )
        db.add(new_msg)
        await db.commit()
