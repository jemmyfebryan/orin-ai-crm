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


async def soft_delete_customer_by_phone(phone_number: str) -> dict:
    """
    Soft delete a customer by phone number.

    This is a reusable function that can be called from multiple places.
    Sets deleted_at timestamp instead of actually deleting the record.

    Args:
        phone_number: Customer's phone number

    Returns:
        dict with: success (bool), message (str), customer_id (int or None)
    """
    try:
        async with AsyncSessionLocal() as db:
            # Find customer by phone_number
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
            customer.deleted_at = datetime.now(WIB)
            await db.commit()
            await db.refresh(customer)

            logger.info(f"Customer {customer.id} soft-deleted successfully")

            return {
                'success': True,
                'message': f'Customer {customer.id} deleted successfully. Chat reset complete.',
                'customer_id': customer.id
            }

    except Exception as e:
        logger.error(f"Error soft-deleting customer: {str(e)}")
        return {
            'success': False,
            'message': f'Failed to delete customer: {str(e)}',
            'customer_id': None
        }


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

        logger.warning(f"DELETE CUSTOMER REQUEST - Searching for: {identifier}")

        # For now, only support phone_number
        # TODO: Add lid_number support if needed
        if not req.phone_number:
            return ResetCustomerResponse(
                success=False,
                message=f"Must provide phone_number. lid_number not yet supported.",
                deleted_tables={"customers_marked_deleted": 0},
                customer_id=None
            )

        # Use the reusable function
        result = await soft_delete_customer_by_phone(req.phone_number)

        return ResetCustomerResponse(
            success=result['success'],
            message=result['message'],
            deleted_tables={"customers_marked_deleted": 1 if result['customer_id'] else 0},
            customer_id=result['customer_id']
        )

    except Exception as e:
        logger.error(f"Error in delete_customer_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return ResetCustomerResponse(
            success=False,
            message=f"Error: {str(e)}",
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
