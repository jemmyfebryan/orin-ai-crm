"""
Admin endpoints for customer management and product reset.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, or_

from fastapi import APIRouter, HTTPException

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from src.orin_ai_crm.core.agents.tools.product_agent_tools import reset_products_to_default
from src.orin_ai_crm.server.schemas.admin import ResetCustomerRequest, ResetCustomerResponse, ResetProductsResponse

# Setup WIB timezone (UTC+7)
WIB = timezone(timedelta(hours=7))

logger = get_logger(__name__)
router = APIRouter()


@router.post("/delete-customer", response_model=ResetCustomerResponse)
async def delete_customer_endpoint(req: ResetCustomerRequest):
    """
    Soft delete customer dengan menandai deleted_at timestamp.

    Ini TIDAK menghapus data dari database, hanya menandai customer sebagai "deleted".
    Semua data (chat_sessions, intent_classifications, dll) tetap preserved untuk ML training.

    Yang diubah:
    - Set deleted_at timestamp di tabel customers

    Data preserved untuk training:
    - intent_classifications (untuk intent classification training)
    - chat_sessions (untuk context analysis)
    - semua foreign key tables lainnya
    """
    try:
        identifier = {
            "phone_number": req.phone_number,
            "lid_number": req.lid_number
        }

        async with AsyncSessionLocal() as db:
            # DEBUG: Log what we're searching for
            logger.warning(f"DELETE CUSTOMER REQUEST - Searching for: {identifier}")

            # 1. Cari customer berdasarkan identifier
            # Build conditions properly to avoid NULL matching issues
            conditions = []
            if identifier.get('phone_number'):
                conditions.append(Customer.phone_number == identifier.get('phone_number'))
            if identifier.get('lid_number'):
                conditions.append(Customer.lid_number == identifier.get('lid_number'))

            if not conditions:
                return ResetCustomerResponse(
                    success=False,
                    message=f"Invalid identifier: {identifier}. Must provide phone_number or lid_number.",
                    deleted_tables={"customers_marked_deleted": 0},
                    customer_id=None
                )

            query = select(Customer).where(Customer.deleted_at.is_(None), or_(*conditions))
            result = await db.execute(query)
            customer = result.scalars().first()

            # DEBUG: Log what we found
            if customer:
                logger.warning(f"FOUND CUSTOMER - id={customer.id}, phone={customer.phone_number}, lid={customer.lid_number}, deleted_at={customer.deleted_at}")
            else:
                logger.warning(f"NO CUSTOMER FOUND for identifier: {identifier}")

            if not customer:
                return ResetCustomerResponse(
                    success=True,
                    message=f"Tidak ditemukan customer untuk identifier: {identifier}",
                    deleted_tables={"customers_marked_deleted": 0},
                    customer_id=None
                )

            # Check if already deleted
            if customer.deleted_at is not None:
                return ResetCustomerResponse(
                    success=True,
                    message=f"Customer sudah di-delete sebelumnya pada: {customer.deleted_at}",
                    deleted_tables={"customers_marked_deleted": 0},
                    customer_id=customer.id
                )

            # 2. Soft delete: Set deleted_at timestamp
            customer.deleted_at = datetime.now(WIB)
            await db.commit()
            await db.refresh(customer)

        return ResetCustomerResponse(
            success=True,
            message=f"Berhasil soft-delete customer untuk customer_id: {customer.id}. Data preserved untuk training.",
            deleted_tables={"customers_marked_deleted": 1},
            customer_id=customer.id
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return ResetCustomerResponse(
            success=False,
            message=f"Gagal soft-delete customer: {str(e)}",
            deleted_tables={"customers_marked_deleted": 0},
            customer_id=None
        )


@router.post("/reset-products", response_model=ResetProductsResponse)
async def reset_products_endpoint():
    """
    Reset products table to default values from JSON file.
    Hati-hati: Ini akan MENGHAPUS SEMUA produk dan menggantinya dengan default dari JSON!
    """
    try:
        result = await reset_products_to_default.ainvoke({})

        return ResetProductsResponse(
            success=True,
            message=f"Berhasil reset products: {result['created']} produk dibuat, {result['deleted']} produk dihapus",
            deleted=result.get("deleted", 0),
            created=result.get("created", 0),
            errors=result.get("errors", [])
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return ResetProductsResponse(
            success=False,
            message=f"Gagal reset products: {str(e)}",
            deleted=0,
            created=0,
            errors=[str(e)]
        )
