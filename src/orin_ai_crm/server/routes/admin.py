"""
Admin endpoints for customer management, product reset, and prompt management.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, or_

from fastapi import APIRouter, HTTPException

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer, Prompt
from src.orin_ai_crm.core.agents.tools.product_agent_tools import reset_products_to_default
from src.orin_ai_crm.core.agents.tools.prompt_tools import reset_prompts_to_default, update_prompt_in_db
from src.orin_ai_crm.server.schemas.admin import (
    ResetCustomerRequest, ResetCustomerResponse, ResetProductsResponse,
    PromptItem, GetPromptsResponse, UpdatePromptRequest, UpdatePromptResponse, ResetPromptsResponse
)

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


# ============================================================================
# PROMPT MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/prompts", response_model=GetPromptsResponse)
async def get_prompts_endpoint():
    """
    Get all prompts from database.

    Returns all active prompts with their details.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Prompt).where(Prompt.is_active == True)
            )
            prompts = result.scalars().all()

            prompt_items = [
                PromptItem(
                    prompt_key=p.prompt_key,
                    prompt_name=p.prompt_name,
                    prompt_text=p.prompt_text,
                    description=p.description,
                    prompt_type=p.prompt_type,
                    is_active=p.is_active
                )
                for p in prompts
            ]

            return GetPromptsResponse(
                success=True,
                prompts=prompt_items,
                count=len(prompt_items)
            )

    except Exception as e:
        logger.error(f"Error in get_prompts_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return GetPromptsResponse(
            success=False,
            prompts=[],
            count=0
        )


@router.put("/prompts/{prompt_key}", response_model=UpdatePromptResponse)
async def update_prompt_endpoint(prompt_key: str, req: UpdatePromptRequest):
    """
    Update a specific prompt in database.

    Args:
        prompt_key: The prompt key to update (e.g., "hana_base_agent")
        req: Request body with new prompt_text

    Returns:
        UpdatePromptResponse with success status
    """
    try:
        logger.info(f"UPDATE PROMPT REQUEST - prompt_key: {prompt_key}")

        result = await update_prompt_in_db(prompt_key, req.prompt_text)

        if result['success']:
            return UpdatePromptResponse(
                success=True,
                message=result['message'],
                prompt_key=prompt_key
            )
        else:
            raise HTTPException(status_code=404, detail=result['message'])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_prompt_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return UpdatePromptResponse(
            success=False,
            message=f"Error: {str(e)}",
            prompt_key=prompt_key
        )


@router.post("/prompts/reset", response_model=ResetPromptsResponse)
async def reset_prompts_endpoint():
    """
    Reset prompts table to default values from JSON file.

    Hati-hati: Ini akan MENGHAPUS SEMUA prompts dan menggantinya dengan default dari JSON!
    """
    try:
        result = await reset_prompts_to_default()

        return ResetPromptsResponse(
            success=True,
            message=f"Berhasil reset prompts: {result['created']} prompt dibuat, {result['deleted']} prompt dihapus",
            deleted=result.get("deleted", 0),
            created=result.get("created", 0),
            errors=result.get("errors", [])
        )

    except Exception as e:
        logger.error(f"Error in reset_prompts_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return ResetPromptsResponse(
            success=False,
            message=f"Gagal reset prompts: {str(e)}",
            deleted=0,
            created=0,
            errors=[str(e)]
        )
