"""
Product Tools - Product extraction, inquiry, and link generation
"""

import os
from typing import Optional
from datetime import timedelta, timezone
from sqlalchemy import select
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from src.orin_ai_crm.core.models.database import AsyncSessionLocal, ProductInquiry
from src.orin_ai_crm.core.logger import get_logger

logger = get_logger(__name__)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))


class ProductInfo(BaseModel):
    """Extract product information dari chat"""
    product_type: Optional[str] = Field(
        default=None,
        description="Tipe produk: TANAM atau INSTAN"
    )
    vehicle_type: Optional[str] = Field(
        default=None,
        description="Jenis kendaraan"
    )
    unit_qty: Optional[int] = Field(
        default=0,
        description="Jumlah unit"
    )


async def get_pending_inquiry(customer_id: int) -> Optional[ProductInquiry]:
    """Get pending product inquiry untuk customer"""
    async with AsyncSessionLocal() as db:
        query = select(ProductInquiry).where(
            (ProductInquiry.customer_id == customer_id) &
            (ProductInquiry.status == "pending")
        ).order_by(ProductInquiry.created_at.desc())

        result = await db.execute(query)
        inquiry = result.scalars().first()

        if inquiry:
            db.expunge(inquiry)
            return inquiry
        return None


async def create_product_inquiry(
    customer_id: int,
    product_type: str,
    vehicle_type: str,
    unit_qty: int
) -> ProductInquiry:
    """Create new product inquiry"""
    logger.info(f"Creating product inquiry - customer_id: {customer_id}, type: {product_type}")

    async with AsyncSessionLocal() as db:
        inquiry = ProductInquiry(
            customer_id=customer_id,
            product_type=product_type,
            vehicle_type=vehicle_type,
            unit_qty=unit_qty,
            status="pending"
        )
        db.add(inquiry)
        await db.commit()
        await db.refresh(inquiry)
        db.expunge(inquiry)

        logger.info(f"Product inquiry CREATED - id: {inquiry.id}")
        return inquiry


async def update_product_inquiry(
    inquiry_id: int,
    product_type: Optional[str] = None,
    ecommerce_link: Optional[str] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None
) -> bool:
    """Update existing product inquiry"""
    logger.info(f"Updating product inquiry - id: {inquiry_id}")

    async with AsyncSessionLocal() as db:
        query = select(ProductInquiry).where(ProductInquiry.id == inquiry_id)
        result = await db.execute(query)
        inquiry = result.scalars().first()

        if not inquiry:
            logger.warning(f"Product inquiry NOT FOUND for id: {inquiry_id}")
            return False

        if product_type:
            inquiry.product_type = product_type
        if ecommerce_link:
            inquiry.ecommerce_link = ecommerce_link
        if status:
            inquiry.status = status
        if notes:
            inquiry.notes = notes

        await db.commit()
        logger.info(f"Product inquiry {inquiry_id} UPDATED successfully")
        return True


def extract_product_type(messages: list, customer_data: dict) -> ProductInfo:
    """
    Extract product type (TANAM/INSTAN) dari conversation.
    """
    logger.info(f"extract_product_type called - customer_data: {customer_data}")

    system_prompt = f"""Extract product preference dari conversation.

Data customer:
- Vehicle: {customer_data.get('vehicle_type')}
- Unit Qty: {customer_data.get('unit_qty')}

Tipe produk:
1. TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin) - Lebih mahal tapi lebih lengkap
2. INSTAN: OBU D, T1, T (Colok OBD sendiri, hanya lacak) - Lebih murah, DIY installation

Extract:
- product_type: "TANAM" atau "INSTAN" (jika user tidak sebut, return null)
- vehicle_type: jenis kendaraan dari customer data atau conversation
- unit_qty: jumlah unit"""

    extractor_llm = llm.with_structured_output(ProductInfo)
    result = extractor_llm.invoke([SystemMessage(content=system_prompt)] + messages)

    logger.info(f"extract_product_type result: {result.model_dump()}")
    return result


def generate_ecommerce_link(product_type: str, vehicle_type: str, unit_qty: int) -> str:
    """
    Generate appropriate e-commerce link based on product type.
    Untuk production, ini bisa diupdate dengan link sebenarnya.
    """
    logger.info(f"Generating e-commerce link - type: {product_type}, vehicle: {vehicle_type}, qty: {unit_qty}")

    # Placeholder links - update dengan link Tokopedia/Shopee yang sebenarnya
    if product_type == "TANAM":
        return "🛒 Tokopedia: https://tokopedia.com/orin/gps-tanam\n🛒 Shopee: https://shopee.co.id/orin/gps-tanam"
    elif product_type == "INSTAN":
        return "🛒 Tokopedia: https://tokopedia.com/orin/gps-instan\n🛒 Shopee: https://shopee.co.id/orin/gps-instan"
    else:
        return "🛒 Tokopedia: https://tokopedia.com/orin\n🛒 Shopee: https://shopee.co.id/orin"
