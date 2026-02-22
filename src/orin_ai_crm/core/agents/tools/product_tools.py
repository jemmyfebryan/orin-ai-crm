"""
Product Tools - Product query, recommendation, and e-commerce inquiry management
"""

import os
import json
from typing import Optional, List
from datetime import timedelta, timezone
from datetime import datetime
from sqlalchemy import select
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field

from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Product, ProductInquiry
from src.orin_ai_crm.core.logger import get_logger

logger = get_logger(__name__)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))


async def get_all_active_products() -> List[dict]:
    """Get all active products dari database"""
    async with AsyncSessionLocal() as db:
        query = select(Product).where(
            Product.is_active == True
        ).order_by(Product.sort_order.asc(), Product.name.asc())

        result = await db.execute(query)
        products = result.scalars().all()

        # Convert to list of dicts
        product_list = []
        for p in products:
            product_dict = {
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "category": p.category,
                "subcategory": p.subcategory,
                "vehicle_type": p.vehicle_type,
                "description": p.description,
                "features": json.loads(p.features) if p.features else {},
                "price": p.price,
                "installation_type": p.installation_type,
                "can_shutdown_engine": p.can_shutdown_engine,
                "is_realtime_tracking": p.is_realtime_tracking,
                "ecommerce_links": json.loads(p.ecommerce_links) if p.ecommerce_links else {},
                "images": json.loads(p.images) if p.images else [],
                "specifications": json.loads(p.specifications) if p.specifications else {},
                "compatibility": json.loads(p.compatibility) if p.compatibility else {}
            }
            product_list.append(product_dict)

        logger.info(f"Retrieved {len(product_list)} active products")
        return product_list


async def get_products_by_category(category: str) -> List[dict]:
    """Get products by category (TANAM/INSTAN)"""
    async with AsyncSessionLocal() as db:
        query = select(Product).where(
            (Product.category == category) &
            (Product.is_active == True)
        ).order_by(Product.sort_order.asc())

        result = await db.execute(query)
        products = result.scalars().all()

        product_list = []
        for p in products:
            product_list.append({
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "category": p.category,
                "subcategory": p.subcategory,
                "description": p.description,
                "price": p.price,
                "ecommerce_links": json.loads(p.ecommerce_links) if p.ecommerce_links else {}
            })

        logger.info(f"Retrieved {len(product_list)} products for category: {category}")
        return product_list


async def get_products_by_vehicle_type(vehicle_type: str) -> List[dict]:
    """Get products by vehicle type (mobil, motor, alat berat, dll)"""
    async with AsyncSessionLocal() as db:
        query = select(Product).where(
            (Product.vehicle_type == vehicle_type) &
            (Product.is_active == True)
        ).order_by(Product.sort_order.asc())

        result = await db.execute(query)
        products = result.scalars().all()

        product_list = []
        for p in products:
            product_list.append({
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "category": p.category,
                "vehicle_type": p.vehicle_type,
                "description": p.description,
                "features": json.loads(p.features) if p.features else {}
            })

        logger.info(f"Retrieved {len(product_list)} products for vehicle: {vehicle_type}")
        return product_list


async def search_products(keyword: str) -> List[dict]:
    """Search products by keyword in name, description, or SKU"""
    async with AsyncSessionLocal() as db:
        # Case-insensitive search
        query = select(Product).where(
            (Product.name.ilike(f"%{keyword}%")) |
            (Product.description.ilike(f"%{keyword}%")) |
            (Product.sku.ilike(f"%{keyword}%"))
        ).where(Product.is_active == True)

        result = await db.execute(query)
        products = result.scalars().all()

        product_list = []
        for p in products:
            product_list.append({
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "category": p.category,
                "subcategory": p.subcategory,
                "description": p.description,
                "price": p.price
            })

        logger.info(f"Search for '{keyword}' found {len(product_list)} products")
        return product_list


def format_products_for_llm(products: List[dict]) -> str:
    """
    Format product data menjadi string yang bisa dibaca oleh LLM.
    Output ini akan diberikan ke LLM sebagai context untuk menjawab pertanyaan customer.
    """
    if not products:
        return "Maaf, tidak ada produk yang ditemukan."

    formatted = "PRODUK TERSEDIA:\n\n"

    for idx, p in enumerate(products, 1):
        formatted += f"{idx}. {p['name']} ({p['sku']})\n"
        formatted += f"   Kategori: {p['category']}"
        if p.get('subcategory'):
            formatted += f" - {p['subcategory']}"
        formatted += f"\n   Harga: Rp {p['price']:,}" if p.get('price') else ""
        formatted += f"\n   Deskripsi: {p.get('description', '-')}\n"

        # Add features if available
        if p.get('features'):
            features = p['features']
            if features.get('fitur_utama'):
                formatted += f"   Fitur Utama: {features['fitur_utama']}\n"

        # Add ecommerce links if available
        if p.get('ecommerce_links'):
            links = p['ecommerce_links']
            if links:
                formatted += "   Link Beli:\n"
                for platform, url in links.items():
                    formatted += f"   • {platform.title()}: {url}\n"

        formatted += "\n"

    return formatted


async def answer_product_question(
    question: str,
    customer_vehicle: Optional[str] = None,
    customer_qty: Optional[int] = None
) -> str:
    """
    Jawab pertanyaan produk menggunakan LLM dengan context dari database produk.
    """
    logger.info(f"answer_product_question called - question: {question[:50]}..., vehicle: {customer_vehicle}, qty: {customer_qty}")

    # Get all active products as context
    all_products = await get_all_active_products()
    products_context = format_products_for_llm(all_products)

    # Build prompt untuk LLM
    system_prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Tugasmu adalah menjawab pertanyaan customer tentang produk GPS berdasarkan database produk.

{products_context}

Customer Vehicle: {customer_vehicle or '-'}
Jumlah Unit: {customer_qty or '-'}

Pertanyaan Customer: {question}

Tugas:
1. Jawab pertanyaan customer dengan sopan dan ramah
2. Berikan rekomendasi produk yang sesuai dengan kebutuhan mereka
3. Jika customer tanya tentang fitur, jelaskan dengan jelas
4. Jika customer tanya tentang harga, sebutkan harganya
5. Jika customer tanya tentang cara beli, berikan link e-commerce yang tersedia
6. Gunakan emoji yang sesuai (🚗, 🏍️, ✅, dll)
7. JANGAN mengarang info yang tidak ada di database

Jawaban harus natural seperti CS asli, bukan seperti robot."""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=question)
    ])

    logger.info(f"LLM response generated: {response.content[:100]}...")
    return response.content


async def recommend_products(
    vehicle_type: str,
    unit_qty: int,
    preferences: Optional[str] = None
) -> tuple[List[dict], str]:
    """
    Recommend products berdasarkan kebutuhan customer.
    Return (products, explanation)
    """
    logger.info(f"recommend_products called - vehicle: {vehicle_type}, qty: {unit_qty}, preferences: {preferences}")

    # Get relevant products
    relevant_products = await get_products_by_vehicle_type(vehicle_type)

    if not relevant_products:
        # Fallback to category-based if vehicle_type not found
        logger.info(f"No products found for vehicle_type: {vehicle_type}, trying category")
        relevant_products = await get_all_active_products()

    # Use LLM to recommend and explain
    products_context = format_products_for_llm(relevant_products)

    prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.

{products_context}

Kebutuhan Customer:
- Jenis Kendaraan: {vehicle_type}
- Jumlah Unit: {unit_qty}
- Preferensi Tambahan: {preferences or '-'}

Tugas:
1. Rekomendasikan produk yang paling sesuai dari list di atas
2. Jelaskan alasan rekomendasi tersebut
3. Berikan link e-commerce untuk pembelian

Return format:
- Berikan list nomor urut produk yang direkomendasikan [1, 3, 5]
- Berikan penjelasan singkat dan natural"""

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=f"Rekomendasikan produk untuk {vehicle_type}, {unit_qty} unit")
    ])

    logger.info(f"Recommendation generated: {response.content[:100]}...")

    return relevant_products, response.content


# ============================================================================
# E-COMMERCE INQUIRY MANAGEMENT
# ============================================================================

class ProductInfo(BaseModel):
    """Product information extracted from conversation"""
    product_type: Optional[str] = Field(default="", description="Tipe produk: TANAM atau INSTAN")
    vehicle_type: Optional[str] = Field(default="", description="Jenis kendaraan")
    unit_qty: Optional[int] = Field(default=0, description="Jumlah unit")


async def get_pending_inquiry(customer_id: int) -> Optional[ProductInquiry]:
    """Get pending product inquiry untuk customer"""
    async with AsyncSessionLocal() as db:
        query = select(ProductInquiry).where(
            (ProductInquiry.customer_id == customer_id) &
            (ProductInquiry.status == "pending")
        )
        result = await db.execute(query)
        inquiry = result.scalars().first()

        if inquiry:
            db.expunge(inquiry)

        return inquiry


async def create_product_inquiry(
    customer_id: int,
    product_type: str,
    vehicle_type: str,
    unit_qty: int
) -> ProductInquiry:
    """Buat product inquiry baru"""
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

        logger.info(f"Product inquiry CREATED for customer {customer_id}: {product_type}, {vehicle_type}, {unit_qty} unit")
        return inquiry


async def update_product_inquiry(
    inquiry_id: int,
    product_type: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    unit_qty: Optional[int] = None,
    recommended_product: Optional[str] = None,
    ecommerce_link: Optional[str] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None
) -> bool:
    """Update product inquiry"""
    async with AsyncSessionLocal() as db:
        query = select(ProductInquiry).where(ProductInquiry.id == inquiry_id)
        result = await db.execute(query)
        inquiry = result.scalars().first()

        if not inquiry:
            logger.warning(f"Product inquiry {inquiry_id} not found for update")
            return False

        if product_type is not None:
            inquiry.product_type = product_type
        if vehicle_type is not None:
            inquiry.vehicle_type = vehicle_type
        if unit_qty is not None:
            inquiry.unit_qty = unit_qty
        if recommended_product is not None:
            inquiry.recommended_product = recommended_product
        if ecommerce_link is not None:
            inquiry.ecommerce_link = ecommerce_link
        if status is not None:
            inquiry.status = status
        if notes is not None:
            inquiry.notes = notes

        inquiry.updated_at = datetime.now(WIB)
        await db.commit()

        logger.info(f"Product inquiry {inquiry_id} UPDATED: status={status}, link={'provided' if ecommerce_link else 'none'}")
        return True


def extract_product_type(messages: list, customer_data: dict) -> ProductInfo:
    """
    Extract product preference dari conversation using LLM.
    Structured output akan menentukan TANAM vs INSTAN.
    """
    logger.info(f"extract_product_type called - customer_data: {customer_data}, message_count: {len(messages)}")

    system_prompt = f"""Extract informasi produk yang customer inginkan.

Customer Data:
- Vehicle Type: {customer_data.get('vehicle_type', '-')}
- Unit Qty: {customer_data.get('unit_qty', 0)}
- B2B: {customer_data.get('is_b2b', False)}

Tentukan:
1. product_type: "TANAM" (pasang teknisi, bisa matikan mesin) atau "INSTAN" (colok sendiri, hanya lacak)
2. vehicle_type: Jenis kendaraan dari customer data atau conversation
3. unit_qty: Jumlah unit dari customer data atau conversation

Rules:
- Jika customer sebut "pasang teknisi", "matikan mesin", "tersembunyi" → TANAM
- Jika customer sebut "colok sendiri", "tinggal colok OBD", "praktis" → INSTAN
- Jika tidak jelas, default ke TANAM (karena lebih lengkap)
- Jangan mengarang info jika tidak disebutkan"""

    extractor_llm = llm.with_structured_output(ProductInfo)
    result = extractor_llm.invoke([SystemMessage(content=system_prompt)] + messages)

    logger.info(f"extract_product_type result: {result.model_dump()}")
    return result


def generate_ecommerce_link(product_type: str, vehicle_type: str, unit_qty: int) -> str:
    """
    Generate e-commerce link berdasarkan product type.
    Dalam real implementasi, ini bisa query database untuk dapat link spesifik.
    """
    logger.info(f"generate_ecommerce_link called - product_type: {product_type}, vehicle: {vehicle_type}, qty: {unit_qty}")

    # Placeholder - ganti dengan link asli
    if product_type == "TANAM":
        link = """Untuk pembelian GPS tipe TANAM (OBU F & OBU V - Dipasang teknisi, bisa matikan mesin), kakak bisa:

🛒 Tokopedia: https://tokopedia.com/orin/gps-tanam
🛒 Shopee: https://shopee.co.id/orin/gps-tanam

Produk ini butuh instalasi teknisi. Tim kami akan bantu pasang ya kak! 🔧"""
    elif product_type == "INSTAN":
        link = """Untuk pembelian GPS tipe INSTAN (OBU D, T1, T - Tinggal colok OBD), kakak bisa:

🛒 Tokopedia: https://tokopedia.com/orin/gps-instan
🛒 Shopee: https://shopee.co.id/orin/gps-instan

Produk ini tinggal colok ke port OBD kendaraan. Praktis! 🔌"""
    else:
        link = f"""Untuk pembelian GPS produk {product_type}, kakak bisa langsung ke:

🛒 Tokopedia: https://tokopedia.com/orin
🛒 Shopee: https://shopee.co.id/orin

Pilih produk yang sesuai dengan kebutuhan {vehicle_type} kakak ya! 🚗"""

    logger.info(f"E-commerce link generated for product_type: {product_type}")
    return link

