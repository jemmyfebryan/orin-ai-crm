"""
Customer Management Agent Tools

LangChain StructuredTool objects for customer management operations.
These tools are used by the LangGraph agent for customer-related operations.
"""

from typing import Optional, Annotated
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from sqlalchemy import select

logger = get_logger(__name__)


@tool
async def get_customer_profile(
    state: Annotated[dict, InjectedState],
) -> dict:
    """
    Get complete customer profile from database.

    Use this tool when:
    - You need to check what customer data we already have
    - Starting a conversation to see existing profile
    - Checking if profiling is complete

    Args:
        customer_id: From state.customer_id

    Returns:
        dict with all customer profile fields
    """
    customer_id = state.get("customer_id", None)
    if not customer_id:
        return "Failed to fetch customer id from state"
    logger.info(f"TOOL: get_customer_profile - customer_id: {customer_id}")

    async with AsyncSessionLocal() as db:
        query = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(query)
        customer = result.scalars().first()

        if not customer:
            logger.warning(f"Customer NOT FOUND: {customer_id}")
            return {'error': f'Customer {customer_id} not found'}

        db.expunge(customer)

        # Get vehicle_alias from VPS DB if vehicle_id > 0 and no vehicle_alias
        vehicle_alias = customer.vehicle_alias or ''
        if not vehicle_alias and customer.vehicle_id and customer.vehicle_id > 0:
            from src.orin_ai_crm.core.agents.tools.vps_tools import get_vehicle_by_id
            vehicle_data = await get_vehicle_by_id(customer.vehicle_id)
            if vehicle_data:
                vehicle_alias = vehicle_data.get('name', '')

        return {
            'customer_id': customer.id,
            'name': customer.name or '',
            'domicile': customer.domicile or '',
            'vehicle_id': customer.vehicle_id if customer.vehicle_id else -1,
            'vehicle_alias': vehicle_alias,
            'unit_qty': customer.unit_qty if customer.unit_qty else 0,
            'is_b2b': customer.is_b2b if customer.is_b2b else False,
            'is_onboarded': customer.is_onboarded if customer.is_onboarded else False,
            'contact_name': customer.contact_name or ''
        }


@tool
async def update_customer_data(
    customer_id: int,
    name: Optional[str] = None,
    domicile: Optional[str] = None,
    vehicle_alias: Optional[str] = None,
    unit_qty: Optional[int] = None,
    is_b2b: Optional[bool] = None
) -> dict:
    """
    Update specific fields in customer profile.

    Use this tool when:
    - Customer provides new or updated information
    - After extracting customer info from messages
    - Need to update profile in database

    Only provided fields will be updated. Others remain unchanged.

    Args:
        customer_id: The customer ID (provided in system prompt - use that exact value!)
        name: Nama customer
        domicile: Domisili customer
        vehicle_alias: Jenis/Tipe kendaraan customer
        unit_qty: Jumlah unit yang ingin dipesan
        is_b2b: Apakah customer berasal dari business/company

    Returns:
        dict with: success (bool), message, updated_fields
    """
    try:
        logger.info(f"TOOL: update_customer_data - customer_id: {customer_id}")
        logger.info(f"TOOL: update_customer_data - params: name={name}, domicile={domicile}, vehicle_alias={vehicle_alias}, unit_qty={unit_qty}, is_b2b={is_b2b}")

        async with AsyncSessionLocal() as db:
            query = select(Customer).where(Customer.id == customer_id)
            result = await db.execute(query)
            customer = result.scalars().first()

            if not customer:
                logger.warning(f"TOOL: update_customer_data - Customer {customer_id} not found")
                return {'success': False, 'message': f'Customer {customer_id} not found', 'updated_fields': []}

            updated_fields = []

            if name and name != customer.name:
                customer.name = name
                updated_fields.append('name')

            if domicile and domicile != customer.domicile:
                customer.domicile = domicile
                updated_fields.append('domicile')

            if vehicle_alias and vehicle_alias != customer.vehicle_alias:
                customer.vehicle_alias = vehicle_alias
                updated_fields.append('vehicle_alias')

            # if vehicle_id is not None and vehicle_id != customer.vehicle_id:
            #     customer.vehicle_id = vehicle_id
            #     updated_fields.append('vehicle_id')

            if unit_qty and unit_qty != customer.unit_qty:
                customer.unit_qty = unit_qty
                updated_fields.append('unit_qty')

            if is_b2b is not None and is_b2b != customer.is_b2b:
                customer.is_b2b = is_b2b
                updated_fields.append('is_b2b')

            if updated_fields:
                await db.commit()
                await db.refresh(customer)
                logger.info(f"TOOL: update_customer_data - Customer {customer_id} updated: {', '.join(updated_fields)}")
                return {
                    'success': True,
                    'message': f'Updated: {", ".join(updated_fields)}',
                    'updated_fields': updated_fields
                }
            else:
                logger.info(f"TOOL: update_customer_data - No changes needed for customer {customer_id}")
                return {
                    'success': True,
                    'message': 'No changes needed',
                    'updated_fields': []
                }
    except Exception as e:
        logger.error(f"TOOL: update_customer_data - ERROR: {str(e)}")
        return {
            'success': False,
            'message': f'Error updating customer: {str(e)}',
            'updated_fields': []
        }


# List of customer management tools for easy import
# NOTE: get_customer_profile is NOT included here because it's called directly
# in agent_node before the LLM agent runs. This prevents infinite loops.
CUSTOMER_MANAGEMENT_TOOLS = [
    update_customer_data,
]

__all__ = ['CUSTOMER_MANAGEMENT_TOOLS', 'get_customer_profile', 'update_customer_data']
