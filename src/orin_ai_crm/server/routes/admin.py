"""
Admin endpoints for customer management, product reset, and prompt management.
"""
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, or_, desc, func

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer, Prompt, Product, ChatSession
from src.orin_ai_crm.core.agents.tools.product_agent_tools import reset_products_to_default
from src.orin_ai_crm.core.agents.tools.prompt_tools import reset_prompts_to_default, update_prompt_in_db
from src.orin_ai_crm.core.utils.db_retry import retry_db_operation, execute_with_retry
from src.orin_ai_crm.server.schemas.admin import (
    ResetCustomerRequest, ResetCustomerResponse, ResetProductsResponse,
    PromptItem, GetPromptsResponse, UpdatePromptRequest, UpdatePromptResponse, ResetPromptsResponse,
    ProductItem, GetProductsResponse, UpdateProductRequest, UpdateProductResponse,
    ContactItem, GetContactsResponse, ChatMessageItem, GetChatHistoryResponse,
    ToggleHumanTakeoverResponse
)

# Setup WIB timezone (UTC+7)
WIB = timezone(timedelta(hours=7))

logger = get_logger(__name__)
router = APIRouter(prefix="/admin")


@retry_db_operation(max_retries=3)
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

    DEPRECATED: Use /admin/products/reset instead
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
# PRODUCT MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/products", response_model=GetProductsResponse)
async def get_products_endpoint():
    """
    Get all products from database.

    Returns all products with their details.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Product).where(Product.is_active == True).order_by(Product.sort_order.asc(), Product.name.asc())
            )
            products = result.scalars().all()

            product_items = [
                ProductItem(
                    id=p.id,
                    name=p.name,
                    sku=p.sku,
                    category=p.category,
                    subcategory=p.subcategory,
                    vehicle_type=p.vehicle_type,
                    description=p.description,
                    features=json.loads(p.features) if p.features else {},
                    price=p.price,
                    installation_type=p.installation_type,
                    can_shutdown_engine=p.can_shutdown_engine,
                    is_realtime_tracking=p.is_realtime_tracking,
                    ecommerce_links=json.loads(p.ecommerce_links) if p.ecommerce_links else {},
                    images=json.loads(p.images) if p.images else [],
                    specifications=json.loads(p.specifications) if p.specifications else {},
                    compatibility=json.loads(p.compatibility) if p.compatibility else {},
                    is_active=p.is_active,
                    sort_order=p.sort_order
                )
                for p in products
            ]

            return GetProductsResponse(
                success=True,
                products=product_items,
                count=len(product_items)
            )

    except Exception as e:
        logger.error(f"Error in get_products_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return GetProductsResponse(
            success=False,
            products=[],
            count=0
        )


@router.put("/products/{product_id}", response_model=UpdateProductResponse)
async def update_product_endpoint(product_id: int, req: UpdateProductRequest):
    """
    Update a specific product in database.

    Args:
        product_id: The product ID to update
        req: Request body with fields to update

    Returns:
        UpdateProductResponse with success status
    """
    try:
        logger.info(f"UPDATE PRODUCT REQUEST - product_id: {product_id}")

        async with AsyncSessionLocal() as db:
            # Find existing product
            result = await db.execute(
                select(Product).where(Product.id == product_id)
            )
            product = result.scalars().first()

            if not product:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

            # Update fields that are provided
            if req.name is not None:
                product.name = req.name
            if req.sku is not None:
                product.sku = req.sku
            if req.category is not None:
                product.category = req.category
            if req.subcategory is not None:
                product.subcategory = req.subcategory
            if req.vehicle_type is not None:
                product.vehicle_type = req.vehicle_type
            if req.description is not None:
                product.description = req.description
            if req.features is not None:
                product.features = json.dumps(req.features)
            if req.price is not None:
                product.price = req.price
            if req.installation_type is not None:
                product.installation_type = req.installation_type
            if req.can_shutdown_engine is not None:
                product.can_shutdown_engine = req.can_shutdown_engine
            if req.is_realtime_tracking is not None:
                product.is_realtime_tracking = req.is_realtime_tracking
            if req.ecommerce_links is not None:
                product.ecommerce_links = json.dumps(req.ecommerce_links)
            if req.images is not None:
                product.images = json.dumps(req.images)
            if req.specifications is not None:
                product.specifications = json.dumps(req.specifications)
            if req.compatibility is not None:
                product.compatibility = json.dumps(req.compatibility)
            if req.is_active is not None:
                product.is_active = req.is_active
            if req.sort_order is not None:
                product.sort_order = req.sort_order

            await db.commit()
            await db.refresh(product)

            logger.info(f"Product updated: {product_id}")

            return UpdateProductResponse(
                success=True,
                message=f"Product {product_id} updated successfully",
                product_id=product_id
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_product_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return UpdateProductResponse(
            success=False,
            message=f"Error: {str(e)}",
            product_id=product_id
        )


@router.post("/products/reset", response_model=ResetProductsResponse)
async def reset_products_endpoint_v2():
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
        logger.error(f"Error in reset_products_endpoint_v2: {str(e)}")
        import traceback
        traceback.print_exc()
        return ResetProductsResponse(
            success=False,
            message=f"Gagal reset products: {str(e)}",
            deleted=0,
            created=0,
            errors=[str(e)]
        )


@router.get("/products/download")
async def download_products_endpoint():
    """
    Download all products from database as a Python file.

    This generates a Python file with DEFAULT_PRODUCTS list that can be used
    to update the hardcoded default_products.py file.

    Returns:
        Python file with DEFAULT_PRODUCTS list
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Product).where(Product.is_active == True).order_by(Product.sort_order.asc(), Product.name.asc())
            )
            products = result.scalars().all()

            # Generate Python file content
            lines = [
                '"""',
                'Default Products for ORIN GPS Tracker',
                '',
                'This file contains the default product catalog.',
                'These products are loaded into the database on first startup or when reset.',
                '',
                'Auto-generated from database on: ' + datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S %Z'),
                '"""',
                '',
                'DEFAULT_PRODUCTS = ['
            ]

            for p in products:
                lines.append('    {')
                lines.append(f'        "name": "{p.name}",')
                lines.append(f'        "sku": "{p.sku}",')
                lines.append(f'        "category": "{p.category}",')
                lines.append(f'        "subcategory": "{p.subcategory}",')
                lines.append(f'        "vehicle_type": "{p.vehicle_type}",')
                lines.append(f'        "description": """{p.description}""",')
                lines.append(f'        "features": {json.dumps(json.loads(p.features) if p.features else {}, indent=8, ensure_ascii=False)},')
                lines.append(f'        "price": "{p.price}",')
                lines.append(f'        "installation_type": "{p.installation_type}",')
                lines.append(f'        "can_shutdown_engine": {str(p.can_shutdown_engine).lower()},')
                lines.append(f'        "is_realtime_tracking": {str(p.is_realtime_tracking).lower()},')
                lines.append(f'        "ecommerce_links": {json.dumps(json.loads(p.ecommerce_links) if p.ecommerce_links else {}, indent=8, ensure_ascii=False)},')
                lines.append(f'        "images": {json.dumps(json.loads(p.images) if p.images else [], indent=8, ensure_ascii=False)},')
                lines.append(f'        "specifications": {json.dumps(json.loads(p.specifications) if p.specifications else {}, indent=8, ensure_ascii=False)},')
                lines.append(f'        "compatibility": {json.dumps(json.loads(p.compatibility) if p.compatibility else {}, indent=8, ensure_ascii=False)},')
                lines.append(f'        "is_active": {str(p.is_active).lower()},')
                lines.append(f'        "sort_order": {p.sort_order}')
                lines.append('    },')

            lines.append(']')

            python_content = '\n'.join(lines)

            return Response(
                content=python_content,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=default_products.py"
                }
            )

    except Exception as e:
        logger.error(f"Error in download_products_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response(
            content=f"Error: {str(e)}",
            status_code=500
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


@router.get("/prompts/download")
async def download_prompts_endpoint():
    """
    Download all prompts from database as a Python file.

    This generates a Python file with DEFAULT_PROMPTS list that can be used
    to update the hardcoded default_prompts.py file.

    Returns:
        Python file with DEFAULT_PROMPTS list
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Prompt).where(Prompt.is_active == True)
            )
            prompts = result.scalars().all()

            # Generate Python file content
            lines = [
                '"""',
                'Default Prompts for Hana AI Agent',
                '',
                'This file contains the default system prompts for all Hana agents.',
                'These prompts are loaded into the database on first startup or when reset.',
                '',
                'Auto-generated from database on: ' + datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S %Z'),
                '"""',
                '',
                'DEFAULT_PROMPTS = ['
            ]

            for p in prompts:
                # Escape triple quotes in prompt_text
                prompt_text_escaped = p.prompt_text.replace('"""', '\\"\\"\\"')

                lines.append('    {')
                lines.append(f'        "prompt_key": "{p.prompt_key}",')
                lines.append(f'        "prompt_name": "{p.prompt_name}",')
                lines.append(f'        "prompt_text": """{prompt_text_escaped}""",')
                lines.append(f'        "description": "{p.description}",')
                lines.append(f'        "prompt_type": "{p.prompt_type}",')
                lines.append(f'        "is_active": {str(p.is_active).lower()}')
                lines.append('    },')

            lines.append(']')

            python_content = '\n'.join(lines)

            return Response(
                content=python_content,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=default_prompts.py"
                }
            )

    except Exception as e:
        logger.error(f"Error in download_prompts_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response(
            content=f"Error: {str(e)}",
            status_code=500
        )


# ============================================================================
# CHAT HISTORY ENDPOINTS
# ============================================================================

@router.get("/contacts", response_model=GetContactsResponse)
async def get_contacts_endpoint():
    """
    Get all customers with their chat information.

    Returns all customers where deleted_at IS NULL, sorted by last_message_time DESC.
    Includes vehicle information (combining vehicle_id and vehicle_alias) and
    the timestamp of their most recent message.
    """
    try:
        logger.info("Fetching contacts list...")

        async with AsyncSessionLocal() as db:
            # Subquery to get the last message time for each customer
            last_message_subquery = (
                select(
                    ChatSession.customer_id,
                    func.max(ChatSession.created_at).label('last_msg_time')
                )
                .group_by(ChatSession.customer_id)
                .subquery()
            )

            # Main query: customers with their last message time
            query = (
                select(
                    Customer.id,
                    Customer.phone_number,
                    Customer.name,
                    Customer.domicile,
                    Customer.vehicle_id,
                    Customer.vehicle_alias,
                    Customer.unit_qty,
                    Customer.human_takeover,
                    Customer.created_at,
                    last_message_subquery.c.last_msg_time
                )
                .outerjoin(last_message_subquery, Customer.id == last_message_subquery.c.customer_id)
                .where(Customer.deleted_at.is_(None))
                .order_by(desc(last_message_subquery.c.last_msg_time))
            )

            result = await db.execute(query)
            rows = result.all()

            contacts = []
            for row in rows:
                # Combine vehicle_id and vehicle_alias into a single vehicle field
                vehicle = None
                if row.vehicle_alias:
                    vehicle = row.vehicle_alias
                elif row.vehicle_id and row.vehicle_id != -1:
                    vehicle = f"Vehicle ID: {row.vehicle_id}"

                contacts.append(ContactItem(
                    id=row.id,
                    phone_number=row.phone_number,
                    name=row.name,
                    domicile=row.domicile,
                    vehicle=vehicle,
                    unit_qty=row.unit_qty,
                    human_takeover=row.human_takeover if row.human_takeover is not None else False,
                    created_at=row.created_at.isoformat() if row.created_at else None,
                    last_message_time=row.last_msg_time.isoformat() if row.last_msg_time else None
                ))

            logger.info(f"Found {len(contacts)} contacts")

            return GetContactsResponse(
                success=True,
                contacts=contacts,
                count=len(contacts)
            )

    except Exception as e:
        logger.error(f"Error in get_contacts_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return GetContactsResponse(
            success=False,
            contacts=[],
            count=0
        )


@router.get("/contacts/{customer_id}/chat-history", response_model=GetChatHistoryResponse)
async def get_chat_history_endpoint(customer_id: int):
    """
    Get all chat messages for a specific customer.

    Returns all messages for the given customer_id, sorted by timestamp ASC.
    Maps 'ai' role to 'assistant' for frontend consistency.
    """
    try:
        logger.info(f"Fetching chat history for customer_id: {customer_id}")

        async with AsyncSessionLocal() as db:
            # First check if customer exists
            customer_query = select(Customer).where(
                Customer.id == customer_id,
                Customer.deleted_at.is_(None)
            )
            customer_result = await db.execute(customer_query)
            customer = customer_result.scalars().first()

            if not customer:
                raise HTTPException(
                    status_code=404,
                    detail=f"Customer with id {customer_id} not found or has been deleted"
                )

            # Get all chat sessions for this customer
            query = (
                select(ChatSession)
                .where(ChatSession.customer_id == customer_id)
                .order_by(ChatSession.created_at.asc())
            )

            result = await db.execute(query)
            chat_sessions = result.scalars().all()

            # Convert to response format
            messages = []
            for session in chat_sessions:
                # Map 'ai' role to 'assistant' for frontend
                role = session.message_role
                if role == 'ai':
                    role = 'assistant'

                messages.append(ChatMessageItem(
                    role=role,
                    content=session.content,
                    timestamp=session.created_at.isoformat() if session.created_at else None
                ))

            logger.info(f"Found {len(messages)} messages for customer_id: {customer_id}")

            return GetChatHistoryResponse(
                success=True,
                customer_id=customer_id,
                messages=messages,
                count=len(messages)
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_chat_history_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return GetChatHistoryResponse(
            success=False,
            customer_id=customer_id,
            messages=[],
            count=0
        )


@router.put("/contacts/{customer_id}/human-takeover", response_model=ToggleHumanTakeoverResponse)
async def toggle_human_takeover_endpoint(customer_id: int):
    """
    Toggle human takeover status for a specific customer.

    When human_takeover is enabled, the AI system will route messages directly
    to human agents instead of processing them with AI agents.

    Args:
        customer_id: The customer ID to toggle human takeover for

    Returns:
        ToggleHumanTakeoverResponse with the new human_takeover state
    """
    try:
        logger.info(f"Toggling human_takeover for customer_id: {customer_id}")

        async with AsyncSessionLocal() as db:
            # Check if customer exists
            customer_query = select(Customer).where(
                Customer.id == customer_id,
                Customer.deleted_at.is_(None)
            )
            customer_result = await db.execute(customer_query)
            customer = customer_result.scalars().first()

            if not customer:
                raise HTTPException(
                    status_code=404,
                    detail=f"Customer with id {customer_id} not found or has been deleted"
                )

            # Toggle human_takeover status
            new_status = not customer.human_takeover
            customer.human_takeover = new_status
            customer.updated_at = datetime.now(WIB)

            await db.commit()
            await db.refresh(customer)

            status_text = "enabled" if new_status else "disabled"
            logger.info(f"Human takeover {status_text} for customer_id: {customer_id}")

            return ToggleHumanTakeoverResponse(
                success=True,
                message=f"Human takeover {status_text} for customer {customer_id}",
                customer_id=customer_id,
                human_takeover=new_status
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in toggle_human_takeover_endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return ToggleHumanTakeoverResponse(
            success=False,
            message=f"Error: {str(e)}",
            customer_id=customer_id,
            human_takeover=False
        )
