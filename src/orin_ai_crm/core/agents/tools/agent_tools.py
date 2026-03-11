"""
Agentic Tools for Hana AI - Granular Tool-Calling Architecture

This file imports and organizes tools that the LLM can compose together
to handle complex customer interactions. Each tool does ONE thing well.

IMPORTANT: The LLM CAN and SHOULD call MULTIPLE tools in parallel to handle
multi-intent messages. This is the power of the agentic approach!

Tool Categories:
1. CUSTOMER MANAGEMENT (2 tools)
2. PROFILING (7 tools)
3. SALES & MEETING (7 tools)
4. PRODUCT & E-COMMERCE (8 tools)
5. SUPPORT & COMPLAINTS (3 tools)
6. GREETING & CONVERSATION (2 tools)

Total: 30+ granular tools
"""

# Import all tool categories from their respective modules
from src.orin_ai_crm.core.agents.tools.customer_agent_tools import (
    CUSTOMER_MANAGEMENT_TOOLS,
)
from src.orin_ai_crm.core.agents.tools.profiling_agent_tools import (
    PROFILING_TOOLS,
)
from src.orin_ai_crm.core.agents.tools.meeting_agent_tools import (
    SALES_MEETING_TOOLS,
)
from src.orin_ai_crm.core.agents.tools.support_agent_tools import (
    SUPPORT_TOOLS,
)

# Import product-related tools that use @tool decorator
# These are defined here because they rely on product_tools functions
import os
from typing import Optional
from datetime import timedelta, timezone
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from sqlalchemy import select

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Product, ProductInquiry
import json

logger = get_logger(__name__)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))

HANA_PERSONA = """Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif.
Jangan terlalu kaku, gunakan bahasa natural seperti chat WhatsApp asli.

ATURAN PRODUK GPS MOBIL:
- Tipe TANAM: OBU F & OBU V (Tersembunyi, dipasang teknisi, lacak + matikan mesin).
- Tipe INSTAN: OBU D, T1, T (Bisa pasang sendiri tinggal colok OBD, hanya lacak)."""

# Import product tools function with alias to avoid naming conflict with our tool
from src.orin_ai_crm.core.agents.tools.product_tools import (
    get_all_active_products as get_all_active_products_from_db,
    format_products_for_llm
)


# ============================================================================
# CATEGORY 4: PRODUCT & E-COMMERCE TOOLS (8 tools)
# ============================================================================

@tool
async def get_all_active_products() -> dict:
    """
    Get all active products from database.

    Use this tool when:
    - Need product information for recommendations
    - Customer asks about available products
    - Building product context for LLM

    Returns:
        dict with: products (list of product dicts), count (int)
    """
    logger.info(f"TOOL: get_all_active_products")

    async with AsyncSessionLocal() as db:
        query = select(Product).where(
            Product.is_active == True
        ).order_by(Product.sort_order.asc(), Product.name.asc())

        result = await db.execute(query)
        products = result.scalars().all()

        product_list = []
        for p in products:
            product_list.append({
                'id': p.id,
                'name': p.name,
                'sku': p.sku,
                'category': p.category,
                'subcategory': p.subcategory,
                'vehicle_type': p.vehicle_type,
                'description': p.description,
                'price': p.price,
                'ecommerce_links': json.loads(p.ecommerce_links) if p.ecommerce_links else {},
                'features': json.loads(p.features) if p.features else {},
                'installation_type': p.installation_type,
                'can_shutdown_engine': p.can_shutdown_engine,
            })

        logger.info(f"Retrieved {len(product_list)} active products")

        return {
            'products': product_list,
            'count': len(product_list)
        }


@tool
async def search_products(
    keyword: str,
    category: Optional[str] = None,
    vehicle_type: Optional[str] = None
) -> dict:
    """
    Search products by keyword, category, or vehicle type.

    Use this tool when:
    - Customer asks about specific products
    - Need to filter products by criteria
    - Customer mentions specific vehicle type

    Args:
        keyword: Search term (product name, SKU, or feature)
        category: Optional filter by category (TANAM, INSTAN, KAMERA, AKSESORIS)
        vehicle_type: Optional filter by vehicle type (mobil, motor, alat berat)

    Returns:
        dict with: products (list), count (int), search_criteria (dict)
    """
    logger.info(f"TOOL: search_products - keyword: {keyword}, category: {category}, vehicle: {vehicle_type}")

    async with AsyncSessionLocal() as db:
        query = select(Product).where(Product.is_active == True)

        # Apply filters
        if category:
            query = query.where(Product.category == category)
        if vehicle_type:
            query = query.where(Product.vehicle_type == vehicle_type)
        if keyword:
            query = query.where(
                (Product.name.ilike(f"%{keyword}%")) |
                (Product.description.ilike(f"%{keyword}%")) |
                (Product.sku.ilike(f"%{keyword}%"))
            )

        query = query.order_by(Product.sort_order.asc())
        result = await db.execute(query)
        products = result.scalars().all()

        product_list = []
        for p in products:
            product_list.append({
                'id': p.id,
                'name': p.name,
                'sku': p.sku,
                'category': p.category,
                'description': p.description,
                'price': p.price,
                'features': json.loads(p.features) if p.features else {},
            })

        return {
            'products': product_list,
            'count': len(product_list),
            'search_criteria': {
                'keyword': keyword,
                'category': category,
                'vehicle_type': vehicle_type
            }
        }


@tool
async def get_product_details(product_id: int) -> dict:
    """
    Get detailed information about a specific product.

    Use this tool when:
    - Customer asks about specific product details
    - Need full product information including specs, features, links

    Returns:
        dict with complete product information
    """
    logger.info(f"TOOL: get_product_details - product_id: {product_id}")

    async with AsyncSessionLocal() as db:
        query = select(Product).where(Product.id == product_id)
        result = await db.execute(query)
        product = result.scalars().first()

        if not product:
            return {
                'found': False,
                'product': None
            }

        return {
            'found': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'category': product.category,
                'subcategory': product.subcategory,
                'vehicle_type': product.vehicle_type,
                'description': product.description,
                'price': product.price,
                'installation_type': product.installation_type,
                'can_shutdown_engine': product.can_shutdown_engine,
                'is_realtime_tracking': product.is_realtime_tracking,
                'features': json.loads(product.features) if product.features else {},
                'specifications': json.loads(product.specifications) if product.specifications else {},
                'ecommerce_links': json.loads(product.ecommerce_links) if product.ecommerce_links else {},
                'images': json.loads(product.images) if product.images else [],
                'compatibility': json.loads(product.compatibility) if product.compatibility else {},
            }
        }


@tool
async def answer_product_question(
    question: str,
    customer_profile: dict
) -> dict:
    """
    Answer product questions using LLM with database product context.

    Use this tool when:
    - Customer asks about products (features, prices, differences)
    - Customer wants recommendations
    - Customer asks how to buy

    Args:
        question: The customer's question
        customer_profile: Customer profile for personalization

    Returns:
        dict with: answer (str) - AI-generated answer
    """
    logger.info(f"TOOL: answer_product_question")

    # Get all products for context
    products_result = await get_all_products()
    products_context = format_products_for_llm(products_result['products'])

    customer_name = customer_profile.get('name') or 'Kak'
    customer_info = f"""
Customer Profile:
- Nama: {customer_name}
- Kendaraan: {customer_profile.get('vehicle_alias', '-')}
- Jumlah Unit: {customer_profile.get('unit_qty', 0)}
- B2B: {customer_profile.get('is_b2b', False)}
"""

    prompt = f"""{HANA_PERSONA}

{products_context}

{customer_info}
Pertanyaan Customer: {question}

TASK:
Jawab pertanyaan customer dengan sopan dan ramah.
Berikan informasi produk yang akurat dari database.
Jika tanya harga, sebutkan harganya.
Jika tanya cara beli, berikan link e-commerce yang tersedia.
JANGAN mengarang info yang tidak ada di database.
Gunakan emoji yang sesuai (🚗, 🏍️, ✅, dll).

Response HANYA dengan jawaban yang akan dikirim ke customer."""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'answer': response.content
    }


@tool
async def get_ecommerce_links(product_id: int) -> dict:
    """
    Get e-commerce purchase links for a product.

    Use this tool when:
    - Customer wants to buy a product
    - Customer asks for purchase links
    - Need to provide Tokopedia/Shopee links

    Returns:
        dict with: product_name (str), links (dict with platform: url)
    """
    logger.info(f"TOOL: get_ecommerce_links - product_id: {product_id}")

    async with AsyncSessionLocal() as db:
        query = select(Product).where(Product.id == product_id)
        result = await db.execute(query)
        product = result.scalars().first()

        if not product:
            return {
                'found': False,
                'product_name': '',
                'links': {}
            }

        links = json.loads(product.ecommerce_links) if product.ecommerce_links else {}

        return {
            'found': True,
            'product_name': product.name,
            'links': links
        }


@tool
async def create_product_inquiry(
    customer_id: int,
    product_type: str,
    vehicle_type: str,
    unit_qty: int
) -> dict:
    """
    Create a product inquiry record for tracking.

    Use this tool when:
    - Customer asks about products for the first time
    - Need to track product interest

    Returns:
        dict with: success (bool), inquiry_id (int)
    """
    logger.info(f"TOOL: create_product_inquiry - customer: {customer_id}")

    async with AsyncSessionLocal() as db:
        # Check for existing pending inquiry
        query = select(ProductInquiry).where(
            (ProductInquiry.customer_id == customer_id) &
            (ProductInquiry.status == "pending")
        )
        result = await db.execute(query)
        existing = result.scalars().first()

        if existing:
            return {
                'success': True,
                'inquiry_id': existing.id,
                'message': 'Inquiry already exists'
            }

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

        logger.info(f"Product inquiry CREATED: {inquiry.id}")

        return {
            'success': True,
            'inquiry_id': inquiry.id,
            'message': 'Inquiry created'
        }


@tool
async def get_pending_product_inquiry(customer_id: int) -> dict:
    """
    Get pending product inquiry for customer.

    Use this tool when:
    - Customer has ongoing product inquiry
    - Need to check inquiry status

    Returns:
        dict with: found (bool), inquiry (dict or None)
    """
    logger.info(f"TOOL: get_pending_product_inquiry - customer: {customer_id}")

    async with AsyncSessionLocal() as db:
        query = select(ProductInquiry).where(
            (ProductInquiry.customer_id == customer_id) &
            (ProductInquiry.status == "pending")
        )
        result = await db.execute(query)
        inquiry = result.scalars().first()

        if inquiry:
            return {
                'found': True,
                'inquiry': {
                    'id': inquiry.id,
                    'product_type': inquiry.product_type,
                    'vehicle_type': inquiry.vehicle_type,
                    'unit_qty': inquiry.unit_qty,
                    'status': inquiry.status
                }
            }
        else:
            return {
                'found': False,
                'inquiry': None
            }


@tool
async def recommend_products_for_customer(
    customer_profile: dict,
    preferences: Optional[str] = None
) -> dict:
    """
    Recommend products based on customer profile using LLM.

    Use this tool when:
    - Customer wants product recommendations
    - Profiling is complete, suggesting products
    - Customer asks "what's best for me?"

    Args:
        customer_profile: Customer profile with vehicle, qty, etc.
        preferences: Optional customer preferences/budget

    Returns:
        dict with: recommended_products (list), explanation (str)
    """
    logger.info(f"TOOL: recommend_products_for_customer")

    # Get relevant products based on vehicle type
    vehicle_alias = customer_profile.get('vehicle_alias', '')
    vehicle_type = 'motor' if 'motor' in vehicle_alias.lower() else 'mobil'

    products_result = await search_products(
        keyword='',
        vehicle_type=vehicle_type
    )

    products = products_result['products']

    if not products:
        # Fallback to all products
        all_products = await get_all_active_products()
        products = all_products['products']

    products_context = format_products_for_llm(products)

    customer_name = customer_profile.get('name') or 'Kak'
    unit_qty = customer_profile.get('unit_qty', 1)

    prompt = f"""{HANA_PERSONA}

{products_context}

CUSTOMER NEEDS:
- Nama: {customer_name}
- Kendaraan: {vehicle_alias}
- Jumlah Unit: {unit_qty}
- Preferensi: {preferences or '-'}

TASK:
Rekomendasikan 1-3 produk terbaik dari daftar di atas.
Jelaskan alasan rekomendasi.
Berikan link e-commerce untuk pembelian.
Ramah dan natural.

Response HANYA dengan rekomendasi yang akan dikirim ke customer."""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'recommended_products': [p['name'] for p in products[:3]],
        'explanation': response.content
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_all_products():
    """Helper to get all active products - uses product_tools function"""
    result = await get_all_active_products_from_db()
    return result


# ============================================================================
# PRODUCT & E-COMMERCE TOOLS LIST
# ============================================================================

PRODUCT_ECOMMERCE_TOOLS = [
    get_all_active_products,
    search_products,
    get_product_details,
    answer_product_question,
    get_ecommerce_links,
    create_product_inquiry,
    get_pending_product_inquiry,
    recommend_products_for_customer,
]


# ============================================================================
# TOOL LIST FOR AGENT
# ============================================================================

# All tools combined - customize which tools to include here
AGENT_TOOLS = (
    CUSTOMER_MANAGEMENT_TOOLS
    + PROFILING_TOOLS
    # SALES_MEETING_TOOLS +
    # PRODUCT_ECOMMERCE_TOOLS +
    # SUPPORT_TOOLS
)

__all__ = [
    'AGENT_TOOLS',
    'CUSTOMER_MANAGEMENT_TOOLS',
    'PROFILING_TOOLS',
    'SALES_MEETING_TOOLS',
    'PRODUCT_ECOMMERCE_TOOLS',
    'SUPPORT_TOOLS',
]
