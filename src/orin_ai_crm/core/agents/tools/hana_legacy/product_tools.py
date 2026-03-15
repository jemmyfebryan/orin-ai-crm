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
from langchain_core.messages import SystemMessage, HumanMessage

from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Product, ProductInquiry
from src.orin_ai_crm.core.models.schemas import ProductInfo
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config

logger = get_logger(__name__)
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
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
        # Price is now a String, not Integer
        if p.get('price'):
            formatted += f"\n   Harga: {p['price']}"
        formatted += f"\n   Deskripsi: {p.get('description', '-')}\n"

        # Add features if available
        if p.get('features'):
            features = p['features']
            if isinstance(features, dict):
                # Handle list format for features
                if features.get('fitur_utama'):
                    fitur = features['fitur_utama']
                    if isinstance(fitur, list):
                        formatted += f"   Fitur Utama: {', '.join(fitur)}\n"
                    else:
                        formatted += f"   Fitur Utama: {fitur}\n"
                # Add other feature fields
                for key, value in features.items():
                    if key != 'fitur_utama':
                        formatted += f"   {key.replace('_', ' ').title()}: {value}\n"

        # Add specifications if available
        if p.get('specifications'):
            specs = p['specifications']
            if isinstance(specs, dict):
                formatted += "   Spesifikasi:\n"
                for key, value in specs.items():
                    if isinstance(value, list):
                        formatted += f"   • {key.replace('_', ' ').title()}: {', '.join(value)}\n"
                    else:
                        formatted += f"   • {key.replace('_', ' ').title()}: {value}\n"

        # Add ecommerce links if available
        if p.get('ecommerce_links'):
            links = p['ecommerce_links']
            if isinstance(links, dict) and links:
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

Customer Vehicle: {customer_vehicle or '-'} (This is user's description, e.g., "CRF", "Avanza", "motor")
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
- Vehicle: {customer_data.get('vehicle_alias', '-')}
- Unit Qty: {customer_data.get('unit_qty', 0)}
- B2B: {customer_data.get('is_b2b', False)}

Tentukan:
1. product_type: "TANAM" (pasang teknisi, bisa matikan mesin) atau "INSTAN" (colok sendiri, hanya lacak)
2. vehicle_id: ID kendaraan (gunakan -1 jika tidak diketahui)
3. vehicle_alias: Nama kendaraan dari customer data atau conversation
4. vehicle_alias: Teks asli dari user tentang kendaraan
5. unit_qty: Jumlah unit dari customer data atau conversation

Rules:
- Jika customer sebut "pasang teknisi", "matikan mesin", "tersembunyi" → TANAM
- Jika customer sebut "colok sendiri", "tinggal colok OBD", "praktis" → INSTAN
- Jika tidak jelas, default ke TANAM (karena lebih lengkap)
- Jangan mengarang info jika tidak disebutkan"""

    extractor_llm = llm.with_structured_output(ProductInfo)
    result = extractor_llm.invoke([SystemMessage(content=system_prompt)] + messages)

    logger.info(f"extract_product_type result: {result.model_dump()}")
    return result


# def generate_ecommerce_link(product_type: str, vehicle_type: str, unit_qty: int) -> str:
#     """
#     Generate e-commerce link berdasarkan product type.
#     Dalam real implementasi, ini bisa query database untuk dapat link spesifik.
#     """
#     logger.info(f"generate_ecommerce_link called - product_type: {product_type}, vehicle: {vehicle_type}, qty: {unit_qty}")

#     # Placeholder - ganti dengan link asli
#     if product_type == "TANAM":
#         link = """Untuk pembelian GPS tipe TANAM (OBU F & OBU V - Dipasang teknisi, bisa matikan mesin), kakak bisa:

# 🛒 Tokopedia: https://tokopedia.com/orin/gps-tanam
# 🛒 Shopee: https://shopee.co.id/orin/gps-tanam

# Produk ini butuh instalasi teknisi. Tim kami akan bantu pasang ya kak! 🔧"""
#     elif product_type == "INSTAN":
#         link = """Untuk pembelian GPS tipe INSTAN (OBU D, T1, T - Tinggal colok OBD), kakak bisa:

# 🛒 Tokopedia: https://tokopedia.com/orin/gps-instan
# 🛒 Shopee: https://shopee.co.id/orin/gps-instan

# Produk ini tinggal colok ke port OBD kendaraan. Praktis! 🔌"""
#     else:
#         link = f"""Untuk pembelian GPS produk {product_type}, kakak bisa langsung ke:

# 🛒 Tokopedia: https://tokopedia.com/orin
# 🛒 Shopee: https://shopee.co.id/orin

# Pilih produk yang sesuai dengan kebutuhan {vehicle_type} kakak ya! 🚗"""

#     logger.info(f"E-commerce link generated for product_type: {product_type}")
#     return link


# ============================================================================
# E-COMMERCE PRODUCT MANAGEMENT (with JSON default values)
# ============================================================================


def get_default_products_json_path() -> str:
    """Get path to default_products.json file"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "..", "custom", "hana_agent", "default_products.json")


def load_default_products_from_json() -> list:
    """
    Load default products from JSON file in hana_agent folder.
    Returns list of product dicts matching Product schema.
    """
    json_path = get_default_products_json_path()

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            default_products = json.load(f)
        logger.info(f"Loaded {len(default_products)} default products from {json_path}")
        return default_products if isinstance(default_products, list) else []
    except FileNotFoundError:
        logger.error(f"Default products JSON file not found: {json_path}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding default products JSON: {e}")
        return []


async def get_ecommerce_product(product_identifier: str) -> Optional[dict]:
    """
    Get a product from the products table by name or SKU.

    Args:
        product_identifier: Product name or SKU to search for

    Returns:
        Product dict if found, None otherwise
    """
    logger.info(f"get_ecommerce_product called - identifier: {product_identifier}")

    async with AsyncSessionLocal() as db:
        # Search by name or SKU (case-insensitive)
        query = select(Product).where(
            (Product.name.ilike(f"%{product_identifier}%")) |
            (Product.sku.ilike(f"%{product_identifier}%"))
        ).where(Product.is_active == True)

        result = await db.execute(query)
        product = result.scalars().first()

        if not product:
            logger.warning(f"Product not found: {product_identifier}")
            return None

        # Convert to dict
        product_dict = {
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "category": product.category,
            "subcategory": product.subcategory,
            "vehicle_type": product.vehicle_type,
            "description": product.description,
            "features": json.loads(product.features) if product.features else {},
            "price": product.price,
            "installation_type": product.installation_type,
            "can_shutdown_engine": product.can_shutdown_engine,
            "is_realtime_tracking": product.is_realtime_tracking,
            "ecommerce_links": json.loads(product.ecommerce_links) if product.ecommerce_links else {},
            "images": json.loads(product.images) if product.images else [],
            "specifications": json.loads(product.specifications) if product.specifications else {},
            "compatibility": json.loads(product.compatibility) if product.compatibility else {},
            "is_active": product.is_active,
            "sort_order": product.sort_order
        }

        logger.info(f"Product found: {product.name} ({product.sku})")
        return product_dict


async def reset_products_to_default() -> dict:
    """
    Reset all products in database to default values from JSON file.
    This will DELETE all existing products and INSERT new ones from JSON.

    Returns:
        Dict with summary: {deleted: int, created: int, errors: list}
    """
    logger.info("reset_products_to_default called - Starting reset process")

    # Load default products from JSON
    default_products = load_default_products_from_json()

    if not default_products:
        logger.error("No default products found in JSON file")
        return {"deleted": 0, "created": 0, "errors": ["JSON file not found or empty"]}

    summary = {"deleted": 0, "created": 0, "errors": []}

    async with AsyncSessionLocal() as db:
        try:
            # 1. Delete all existing products
            from sqlalchemy import delete
            delete_stmt = delete(Product)
            result = await db.execute(delete_stmt)
            summary["deleted"] = result.rowcount
            logger.info(f"Deleted {summary['deleted']} existing products")

            # 2. Insert new products from JSON
            for product_data in default_products:
                try:
                    # Convert dict fields to JSON strings where needed
                    features_json = json.dumps(product_data.get("features", {})) if product_data.get("features") else None
                    ecommerce_links_json = json.dumps(product_data.get("ecommerce_links", {})) if product_data.get("ecommerce_links") else None
                    images_json = json.dumps(product_data.get("images", [])) if product_data.get("images") else None
                    specifications_json = json.dumps(product_data.get("specifications", {})) if product_data.get("specifications") else None
                    compatibility_json = json.dumps(product_data.get("compatibility", {})) if product_data.get("compatibility") else None

                    # Create new product
                    new_product = Product(
                        name=product_data.get("name"),
                        sku=product_data.get("sku"),
                        category=product_data.get("category"),
                        subcategory=product_data.get("subcategory"),
                        vehicle_type=product_data.get("vehicle_type"),
                        description=product_data.get("description"),
                        features=features_json,
                        price=product_data.get("price"),
                        installation_type=product_data.get("installation_type", "pasang_technisi"),
                        can_shutdown_engine=product_data.get("can_shutdown_engine", False),
                        is_realtime_tracking=product_data.get("is_realtime_tracking", True),
                        ecommerce_links=ecommerce_links_json,
                        images=images_json,
                        specifications=specifications_json,
                        compatibility=compatibility_json,
                        is_active=product_data.get("is_active", True),
                        sort_order=product_data.get("sort_order", 0)
                    )
                    db.add(new_product)
                    summary["created"] += 1
                    logger.info(f"Created product: {product_data.get('name')} ({product_data.get('sku')})")

                except Exception as e:
                    error_msg = f"Error creating product '{product_data.get('name', 'unknown')}': {str(e)}"
                    logger.error(error_msg)
                    summary["errors"].append(error_msg)

            # Commit all changes
            await db.commit()
            logger.info(f"Products reset completed: {summary}")

        except Exception as e:
            await db.rollback()
            error_msg = f"Error during product reset: {str(e)}"
            logger.error(error_msg)
            summary["errors"].append(error_msg)

    return summary


async def initialize_default_products_if_empty() -> bool:
    """
    Initialize default products from JSON if the products table is empty.
    This is called during application startup.

    Returns:
        True if products were initialized, False if table already had data
    """
    logger.info("initialize_default_products_if_empty called - Checking products table")

    async with AsyncSessionLocal() as db:
        # Check if table is empty
        query = select(Product)
        result = await db.execute(query)
        existing_count = len(result.scalars().all())

        if existing_count > 0:
            logger.info(f"Products table already has {existing_count} products, skipping initialization")
            return False

        logger.info("Products table is empty, initializing from JSON")
        summary = await reset_products_to_default()
        logger.info(f"Products initialization completed: {summary}")
        return summary["created"] > 0


# ============================================================================
# PRODUCT RECOMMENDATION & QUESTION ANSWERING (with Database)
# ============================================================================


async def recommend_products_from_db(
    category: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    budget: Optional[str] = None,
    features_needed: Optional[list] = None
) -> tuple[List[dict], str]:
    """
    Recommend products based on customer needs using database products.
    Returns (products, explanation).

    Args:
        category: TANAM, INSTAN, KAMERA, AKSESORIS
        vehicle_type: mobil, motor, alat berat, truck
        budget: Price constraint (e.g., "25rb/bulan", "<500rb")
        features_needed: List of required features (e.g., ["matikan mesin", "sadap suara"])
    """
    logger.info(f"recommend_products_from_db called - category: {category}, vehicle: {vehicle_type}, budget: {budget}, features: {features_needed}")

    async with AsyncSessionLocal() as db:
        # Build query based on filters
        query = select(Product).where(Product.is_active == True)

        if category:
            query = query.where(Product.category == category)

        result = await db.execute(query.order_by(Product.sort_order.asc()))
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
                "specifications": json.loads(p.specifications) if p.specifications else {},
            }
            product_list.append(product_dict)

        # Use LLM to filter and recommend based on needs
        if not product_list:
            return [], "Maaf, tidak ada produk yang ditemukan."

        products_context = format_products_for_llm(product_list)

        prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.

{products_context}

Kebutuhan Customer:
- Category: {category or '-'}
- Jenis Kendaraan: {vehicle_type or '-'}
- Budget: {budget or '-'}
- Fitur yang dibutuhkan: {features_needed or '-'}

Tugas:
1. Analisis produk-produk di atas yang cocok dengan kebutuhan customer
2. Berikan rekomendasi 1-3 produk terbaik dengan alasan
3. Jelaskan fitur utama dan link e-commerce untuk pembelian
4. Buat respons natural seperti CS asli, gunakan emoji yang sesuai

Jawaban harus langsung bisa dikirim ke customer."""

        response = llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=f"Rekomendasikan produk untuk {vehicle_type or 'kendaraan'}")
        ])

        logger.info(f"Recommendation generated: {response.content[:100]}...")
        return product_list, response.content


async def answer_product_question_from_db(
    question: str,
    customer_data: Optional[dict] = None
) -> str:
    """
    Answer product questions using LLM with context from database products.

    Args:
        question: Customer's question
        customer_data: Customer profile data (vehicle, qty, etc.)

    Returns:
        AI-generated answer
    """
    logger.info(f"answer_product_question_from_db called - question: {question[:50]}...")

    # Get all active products as context
    all_products = await get_all_active_products()

    if not all_products:
        return "Maaf, saat ini data produk sedang tidak dapat diakses. Silakan coba lagi nanti atau hubungi CS kami."

    products_context = format_products_for_llm(all_products)

    # Build customer context
    customer_info = ""
    if customer_data:
        customer_info = f"""
Customer Profile:
- Nama: {customer_data.get('name', 'Kak')}
- Kendaraan: {customer_data.get('vehicle_alias', '-')}
- Jumlah Unit: {customer_data.get('unit_qty', 0)}
- B2B: {customer_data.get('is_b2b', False)}
"""

    system_prompt = f"""Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker.
Sikapmu: Ramah, menggunakan emoji (seperti :), 🙏), sopan, dan solutif. Jangan terlalu kaku.

{products_context}

{customer_info}
Pertanyaan Customer: {question}

Tugas:
1. Jawab pertanyaan customer dengan sopan dan ramah
2. Berikan informasi produk yang akurat berdasarkan database di atas
3. Jika customer tanya tentang fitur, jelaskan dengan jelas
4. Jika customer tanya tentang harga, sebutkan harganya dengan format yang sesuai
5. Jika customer tanya tentang cara beli, berikan link e-commerce yang tersedia
6. Jika customer butuh rekomendasi, tanyakan kebutuhan mereka (jenis kendaraan, budget, fitur yang diinginkan)
7. JANGAN mengarang info yang tidak ada di database
8. Gunakan emoji yang sesuai (🚗, 🏍️, ✅, dll)

Jawaban harus natural seperti CS asli, bukan seperti robot."""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=question)
    ])

    logger.info(f"Product answer generated: {response.content[:100]}...")
    return response.content

