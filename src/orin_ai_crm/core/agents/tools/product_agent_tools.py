"""
Product & E-Commerce Agent Tools

All functions are @tool decorated for LangGraph agent use.
For non-agent contexts, call these tools using .ainvoke() or .invoke()
"""

import os
import importlib.util
from typing import Optional, List, Annotated
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy import select, delete, text
from langgraph.prebuilt import InjectedState

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Product, ProductInquiry
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db
import json

logger = get_logger(__name__)
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))


# ============================================================================
# INTERNAL HELPER FUNCTIONS (Not @tool decorated, used internally by tools)
# ============================================================================

def validate_select_only_query(query: str) -> tuple[bool, str]:
    """
    Validate that the query is SELECT only (no destructive operations).
    Returns (is_valid, error_message)
    """
    query_upper = query.upper().strip()

    # Must start with SELECT
    if not query_upper.startswith('SELECT'):
        return False, "Query must start with SELECT"

    # Dangerous keywords that indicate destructive operations
    dangerous_keywords = [
        'DROP', 'DELETE', 'TRUNCATE', 'INSERT', 'UPDATE',
        'ALTER', 'CREATE', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE'
    ]

    for keyword in dangerous_keywords:
        if keyword in query_upper:
            return False, f"Destructive operation '{keyword}' is not allowed"

    # Check for comment injection attempts
    if '--' in query or '/*' in query or '*/' in query:
        return False, "SQL comments are not allowed"

    # Check for multiple statements
    if ';' in query and not query.rstrip().endswith(';'):
        return False, "Multiple statements are not allowed"

    return True, ""


def format_products_for_llm(products: List[dict]) -> str:
    """Format product data menjadi string yang bisa dibaca oleh LLM."""
    if not products:
        return "Maaf, tidak ada produk yang ditemukan."

    formatted = "PRODUK TERSEDIA:\n\n"

    for idx, p in enumerate(products, 1):
        formatted += f"{idx}. {p['name']} ({p['sku']})\n"
        formatted += f"   Kategori: {p['category']}"
        if p.get('subcategory'):
            formatted += f" - {p['subcategory']}"

        if p.get('vehicle_type'):
            formatted += f"\n   Tipe Kendaraan: {p['vehicle_type']}"

        if p.get('price'):
            formatted += f"\n   Harga: {p['price']}"

        formatted += f"\n   Deskripsi: {p.get('description', '-')}\n"

        # New fields display
        if p.get('can_shutdown_engine'):
            formatted += "   ✅ Bisa Matikan Mesin Jarak Jauh\n"

        if p.get('can_wiretap'):
            formatted += "   ✅ Bisa Sadap Suara\n"

        if p.get('portable'):
            formatted += "   ✅ Portable (bisa dipindah-pindah)\n"

        if p.get('battery_life'):
            formatted += f"   ⏱️ Ketahanan Baterai: {p['battery_life']}\n"

        if p.get('power_source'):
            formatted += f"   🔌 Sumber Daya: {p['power_source']}\n"

        if p.get('tracking_type'):
            formatted += f"   📡 Tipe Tracking: {p['tracking_type']}\n"

        if p.get('monthly_fee'):
            formatted += f"   💰 Biaya Bulanan: {p['monthly_fee']}\n"
        else:
            formatted += "   💰 Biaya Bulanan: Tidak ada\n"

        if p.get('features'):
            features = p['features']
            if isinstance(features, dict):
                if features.get('fitur_utama'):
                    fitur = features['fitur_utama']
                    if isinstance(fitur, list):
                        formatted += f"   Fitur Utama: {', '.join(fitur)}\n"
                    else:
                        formatted += f"   Fitur Utama: {fitur}\n"
                for key, value in features.items():
                    if key != 'fitur_utama':
                        formatted += f"   {key.replace('_', ' ').title()}: {value}\n"

        if p.get('specifications'):
            specs = p['specifications']
            if isinstance(specs, dict):
                formatted += "   Spesifikasi:\n"
                for key, value in specs.items():
                    if isinstance(value, list):
                        formatted += f"   • {key.replace('_', ' ').title()}: {', '.join(value)}\n"
                    else:
                        formatted += f"   • {key.replace('_', ' ').title()}: {value}\n"

        if p.get('ecommerce_links'):
            links = p['ecommerce_links']
            if isinstance(links, dict) and links:
                formatted += "   Link Beli:\n"
                for platform, url in links.items():
                    formatted += f"   • {platform.title()}: {url}\n"

        formatted += "\n"

    return formatted


def get_default_products_py_path() -> str:
    """Get path to default_products.py file"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "..", "custom", "hana_agent", "default_products.py")


def load_default_products_from_py() -> list:
    """Load default products from Python file in hana_agent folder."""
    py_path = get_default_products_py_path()

    try:
        # Load the Python module dynamically
        spec = importlib.util.spec_from_file_location("default_products", py_path)
        if spec is None or spec.loader is None:
            logger.error(f"Failed to load module spec from {py_path}")
            return []

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Get DEFAULT_PRODUCTS from the module
        default_products = getattr(module, 'DEFAULT_PRODUCTS', None)

        if default_products is None:
            logger.error(f"DEFAULT_PRODUCTS not found in {py_path}")
            return []

        if not isinstance(default_products, list):
            logger.error(f"DEFAULT_PRODUCTS is not a list in {py_path}")
            return []

        logger.info(f"Loaded {len(default_products)} default products from {py_path}")
        return default_products

    except FileNotFoundError:
        logger.error(f"Default products Python file not found: {py_path}")
        return []
    except Exception as e:
        logger.error(f"Error loading default products from Python file: {e}")
        return []


# ============================================================================
# AGENTIC TOOLS (@tool decorated - use .ainvoke() for non-agent contexts)
# ============================================================================

@tool
async def query_products_with_llm(
    question: str,
    customer_context: Optional[dict] = None
) -> dict:
    """
    Intelligent product query tool to query database about the products

    This is a universal tool for ANY product-related question:
    - Find products by category, vehicle type, price range, e-commerce link
    - Compare features between products
    - Get product details, specifications, prices
    - Search products by keywords
    - Filter products by any criteria

    Use this tool when:
    - Customer asks ANY product-related question and other product-related tools cant solve the user question

    Safety: Only SELECT queries are allowed (no DELETE, UPDATE, DROP, etc.)

    Args:
        question: Natural language question about products (e.g., "What GPS products for motorcycles?", "Products under 500k?", "Compare OBU F and OBU V")
        customer_context: Optional customer profile for personalization

    Returns:
        dict with: success (bool), data (list of products), answer (str), query (str)
    """
    logger.info(f"TOOL: query_products_with_llm - question: {question[:100]}...")

    # Get table schema information
    schema_info = """
TABLE: products

Columns:
- id (Integer, Primary Key)
- name (String) - Product name
- sku (String) - Product SKU/code
- category (String) - Product category: 'TANAM', 'INSTAN', 'KAMERA', 'AKSESORIS'
- subcategory (String) - Product subcategory
- vehicle_type (String) - Vehicle type: 'mobil', 'motor', 'alat berat', 'universal'
- description (Text) - Product description
- price (Integer) - Product price in IDR
- installation_type (String) - Installation type: 'pasang_technisi', 'pasang_sendiri'
- can_shutdown_engine (Boolean) - Can shutdown engine remotely
- is_realtime_tracking (Boolean) - Has real-time tracking feature
- features (JSON) - Product features as JSON
- specifications (JSON) - Product specifications as JSON
- ecommerce_links (JSON) - E-commerce links as JSON
- images (JSON) - Product images as JSON
- compatibility (JSON) - Vehicle compatibility as JSON
- is_active (Boolean) - Whether product is currently active"""

    customer_info = ""
    if customer_context:
        customer_info = f"""
Customer Context:
- Vehicle: {customer_context.get('vehicle_alias', '-')}
- Unit Qty: {customer_context.get('unit_qty', 0)}
- Budget/Preferences: {customer_context.get('preferences', '-')}
"""

    # Generate SQL query using LLM
    system_prompt = f"""You are a SQL expert. Generate a MySQL/MariaDB SELECT query to answer the user's question about GPS products.

{schema_info}

{customer_info}

CRITICAL CONTEXT:
- The products table is SMALL (10-15 rows only)
- PREFER BROAD queries that return more results rather than overly specific ones
- If exact match returns 0, use LIKE with wildcards
- Goal: Show relevant products, don't be too strict

IMPORTANT RULES:
1. ONLY generate SELECT queries (NO DELETE, UPDATE, DROP, INSERT, etc.)
2. Always include "WHERE is_active = 1" to get only active products
3. Use LIKE for fuzzy text matching - it's better to get more results than 0
4. Prefer LIKE over exact matches for text fields:
   - name LIKE '%GPS%' instead of name = 'GPS'
   - description LIKE '%motor%' instead of vehicle_type = 'motor'
   - category LIKE '%TANAM%' instead of category = 'TANAM'
5. Keep WHERE clauses SIMPLE - maximum 2-3 conditions
6. Order results by sort_order, name
7. Return ONLY the SQL query, no explanations

QUERY STRATEGY (in order of preference):
1. Start broad: Just filter by is_active = 1, add conditions only if explicitly mentioned
2. Use LIKE with wildcards for text matching
3. Avoid combining multiple AND conditions unless user is very specific
4. When in doubt, simpler is better

Generate the SQL query for: {question}"""

    try:
        # Generate SQL with LLM
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=question)
        ])

        generated_query = response.content.strip()

        # Clean up any markdown code blocks
        if generated_query.startswith('```'):
            generated_query = generated_query.split('```')[1]
            if generated_query.startswith('sql'):
                generated_query = generated_query[4:]
        generated_query = generated_query.strip()

        # Remove trailing semicolon if present
        if generated_query.endswith(';'):
            generated_query = generated_query[:-1].strip()

        # Convert PostgreSQL boolean syntax to MySQL for compatibility
        # PostgreSQL: true/false -> MySQL: 1/0
        generated_query = generated_query.replace(' = true', ' = 1')
        generated_query = generated_query.replace(' = false', ' = 0')
        generated_query = generated_query.replace(' IS true', ' = 1')
        generated_query = generated_query.replace(' IS false', ' = 0')
        generated_query = generated_query.replace(' IS NOT true', ' != 1')
        generated_query = generated_query.replace(' IS NOT false', ' != 0')

        logger.info(f"Generated SQL: {generated_query}")

        # Validate query is SELECT only

        # Validate query is SELECT only
        is_valid, error_msg = validate_select_only_query(generated_query)
        if not is_valid:
            logger.error(f"Query validation failed: {error_msg}")
            return {
                'success': False,
                'error': f"Invalid query: {error_msg}",
                'data': [],
                'query': generated_query
            }

        # Execute the query
        async with AsyncSessionLocal() as db:
            # Use mappings() to get dict-like rows
            result = await db.execute(text(generated_query))
            result_mappings = result.mappings()

            # Convert to list of dicts
            products_data = []
            for row in result_mappings:
                row_dict = dict(row)
                # Parse JSON fields
                for key, value in row_dict.items():
                    if value and isinstance(value, str):
                        try:
                            row_dict[key] = json.loads(value)
                        except:
                            pass
                products_data.append(row_dict)

            logger.info(f"Query executed successfully, returned {len(products_data)} rows")

            # FALLBACK: If 0 results, try a broader query
            if len(products_data) == 0:
                logger.info("No results found, attempting fallback with broader query...")

                # Generate fallback query - simpler, less restrictive
                fallback_prompt = f"""The previous query returned 0 results. Generate a BROADER, simpler MySQL/MariaDB SELECT query.

{schema_info}

{customer_info}

FALLBACK STRATEGY:
1. Use FEWER WHERE conditions
2. Use LIKE with wildcards more liberally
3. Try removing some filters
4. If unsure, just return all active products: SELECT * FROM products WHERE is_active = 1 ORDER BY sort_order, name

Examples of broadening:
- category = 'TANAM' → category LIKE '%TANAM%' or just is_active = 1
- vehicle_type = 'motor' → vehicle_type LIKE '%motor%' or remove it
- description LIKE '%GPS%' AND category = 'TANAM' → description LIKE '%GPS%'
- can_shutdown_engine = 1 → remove this condition

Original question: {question}

Generate ONLY the SQL query, no explanation."""

                fallback_response = await llm.ainvoke([
                    SystemMessage(content=fallback_prompt),
                    HumanMessage(content=question)
                ])

                fallback_query = fallback_response.content.strip()

                # Clean up markdown
                if fallback_query.startswith('```'):
                    fallback_query = fallback_query.split('```')[1]
                    if fallback_query.startswith('sql'):
                        fallback_query = fallback_query[4:]
                fallback_query = fallback_query.strip()
                if fallback_query.endswith(';'):
                    fallback_query = fallback_query[:-1].strip()

                # Convert boolean syntax
                fallback_query = fallback_query.replace(' = true', ' = 1')
                fallback_query = fallback_query.replace(' = false', ' = 0')
                fallback_query = fallback_query.replace(' IS true', ' = 1')
                fallback_query = fallback_query.replace(' IS false', ' = 0')

                logger.info(f"Fallback SQL: {fallback_query}")

                # Validate and execute fallback query
                is_valid, error_msg = validate_select_only_query(fallback_query)
                if is_valid:
                    # Execute fallback query
                    result_fallback = await db.execute(text(fallback_query))
                    result_mappings_fallback = result_fallback.mappings()

                    products_data = []
                    for row in result_mappings_fallback:
                        row_dict = dict(row)
                        for key, value in row_dict.items():
                            if value and isinstance(value, str):
                                try:
                                    row_dict[key] = json.loads(value)
                                except:
                                    pass
                        products_data.append(row_dict)

                    logger.info(f"Fallback query returned {len(products_data)} rows")
                    generated_query = f"{generated_query} [FALLBACK: {fallback_query}]"
                else:
                    logger.warning(f"Fallback query validation failed: {error_msg}")

        # Generate natural language answer from results
        if products_data:
            results_summary = f"Found {len(products_data)} product(s)\n\n"

            for idx, product in enumerate(products_data[:10], 1):  # Limit to 10 for brevity
                results_summary += f"{idx}. {product.get('name', 'N/A')} ({product.get('sku', 'N/A')})\n"

                if 'category' in product:
                    results_summary += f"   Category: {product['category']}"
                    if product.get('subcategory'):
                        results_summary += f" - {product['subcategory']}"
                    results_summary += "\n"

                if 'price' in product and product['price'] is not None:
                    price_val = product['price']
                    if isinstance(price_val, (int, float)):
                        results_summary += f"   Price: Rp {price_val:,}\n"
                    else:
                        results_summary += f"   Price: {price_val}\n"

                if 'description' in product:
                    desc = product['description']
                    if desc and len(str(desc)) > 100:
                        desc = str(desc)[:100] + "..."
                    results_summary += f"   Description: {desc}\n"

                if 'can_shutdown_engine' in product:
                    results_summary += f"   Engine Shutdown: {'Yes' if product['can_shutdown_engine'] else 'No'}\n"

                results_summary += "\n"

            if len(products_data) > 10:
                results_summary += f"... and {len(products_data) - 10} more product(s)\n"
        else:
            results_summary = "No products found matching your specific criteria. Try using the other products tool to see all available products, or try a broader search term."

        return {
            'success': True,
            'data': products_data,
            'count': len(products_data),
            'answer': results_summary,
            'query': generated_query
        }

    except Exception as e:
        logger.error(f"Error executing query: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'data': [],
            'query': generated_query if 'generated_query' in locals() else 'Failed to generate'
        }


# ============================================================================
# MORE AGENTIC TOOLS
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
    logger.info("TOOL: get_all_active_products")

    async with AsyncSessionLocal() as db:
        query = select(Product).where(
            Product.is_active == True
        ).order_by(Product.sort_order.asc(), Product.name.asc())

        result = await db.execute(query)
        products = result.scalars().all()

        product_list = []
        for p in products:
            product_dict = {
                "id": p.id,
                "sort_order": p.sort_order,
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
                "can_wiretap": p.can_wiretap,
                "is_realtime_tracking": p.is_realtime_tracking,
                "portable": p.portable,
                "battery_life": p.battery_life,
                "power_source": p.power_source,
                "tracking_type": p.tracking_type,
                "monthly_fee": p.monthly_fee,
                "ecommerce_links": json.loads(p.ecommerce_links) if p.ecommerce_links else {},
                "images": json.loads(p.images) if p.images else [],
                "specifications": json.loads(p.specifications) if p.specifications else {},
                "compatibility": json.loads(p.compatibility) if p.compatibility else {}
            }
            product_list.append(product_dict)

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
                'vehicle_type': p.vehicle_type,
                'can_wiretap': p.can_wiretap,
                'portable': p.portable,
                'battery_life': p.battery_life,
                'power_source': p.power_source,
                'tracking_type': p.tracking_type,
                'monthly_fee': p.monthly_fee,
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
    logger.info("TOOL: answer_product_question")

    # Get Hana persona from database (fresh on each invoke)
    hana_persona = await get_prompt_from_db("hana_ecommerce_agent")
    if not hana_persona:
        hana_persona = "Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker."

    result = await get_all_active_products.ainvoke({})
    products = result['products']
    products_context = format_products_for_llm(products)

    customer_name = customer_profile.get('name') or 'Kak'
    customer_info = f"""
Customer Profile:
- Nama: {customer_name}
- Kendaraan: {customer_profile.get('vehicle_alias', '-')}
- Jumlah Unit: {customer_profile.get('unit_qty', 0)}
- B2B: {customer_profile.get('is_b2b', False)}
"""

    prompt = f"""{hana_persona}

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
    state: Annotated[dict, InjectedState],
    product_type: str,
    vehicle_type: str,
    unit_qty: int
) -> dict:
    """
    Create a product inquiry record for tracking. Always call this tool when user ask about the GPS product.

    Use this tool when:
    - Customer asks about products

    Returns:
        dict with: success (bool), inquiry_id (int)
    """
    # Get customer_id from state (prevents LLM from using wrong customer_id)
    customer_id = state.get("customer_id")

    if not customer_id:
        logger.error("TOOL: create_product_inquiry - No customer_id in state!")
        return {'success': False, 'message': 'No customer_id in state', 'inquiry_id': None}

    logger.info(f"TOOL: create_product_inquiry - customer_id: {customer_id} (from state)")

    async with AsyncSessionLocal() as db:
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
    logger.info("TOOL: recommend_products_for_customer")

    # Get Hana persona from database (fresh on each invoke)
    hana_persona = await get_prompt_from_db("hana_ecommerce_agent")
    if not hana_persona:
        hana_persona = "Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker."

    vehicle_alias = customer_profile.get('vehicle_alias', '')
    vehicle_type = 'motor' if 'motor' in vehicle_alias.lower() else 'mobil'

    search_result = await search_products.ainvoke({
        'keyword': '',
        'vehicle_type': vehicle_type
    })

    products = search_result['products']

    if not products:
        all_products_result = await get_all_active_products.ainvoke({})
        products = all_products_result['products']

    products_context = format_products_for_llm(products)

    customer_name = customer_profile.get('name') or 'Kak'
    unit_qty = customer_profile.get('unit_qty', 1)

    prompt = f"""{hana_persona}

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


@tool
async def get_products_by_category(category: str) -> dict:
    """Get products by category (TANAM/INSTAN)"""
    logger.info(f"TOOL: get_products_by_category - category: {category}")

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
                "ecommerce_links": json.loads(p.ecommerce_links) if p.ecommerce_links else {},
                "vehicle_type": p.vehicle_type,
                "can_wiretap": p.can_wiretap,
                "portable": p.portable,
                "battery_life": p.battery_life,
                "power_source": p.power_source,
                "tracking_type": p.tracking_type,
                "monthly_fee": p.monthly_fee,
            })

        logger.info(f"Retrieved {len(product_list)} products for category: {category}")
        return {
            'products': product_list,
            'count': len(product_list)
        }


@tool
async def get_products_by_vehicle_type(vehicle_type: str) -> dict:
    """Get products by vehicle type (mobil, motor, alat berat, dll)"""
    logger.info(f"TOOL: get_products_by_vehicle_type - vehicle: {vehicle_type}")

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
                "features": json.loads(p.features) if p.features else {},
                "can_wiretap": p.can_wiretap,
                "portable": p.portable,
                "battery_life": p.battery_life,
                "power_source": p.power_source,
                "tracking_type": p.tracking_type,
                "monthly_fee": p.monthly_fee,
            })

        logger.info(f"Retrieved {len(product_list)} products for vehicle: {vehicle_type}")
        return {
            'products': product_list,
            'count': len(product_list)
        }


@tool
async def get_ecommerce_product(product_identifier: str) -> dict:
    """Get a product from the products table by name or SKU."""
    logger.info(f"TOOL: get_ecommerce_product - identifier: {product_identifier}")

    async with AsyncSessionLocal() as db:
        query = select(Product).where(
            (Product.name.ilike(f"%{product_identifier}%")) |
            (Product.sku.ilike(f"%{product_identifier}%"))
        ).where(Product.is_active == True)

        result = await db.execute(query)
        product = result.scalars().first()

        if not product:
            logger.warning(f"Product not found: {product_identifier}")
            return {
                'found': False,
                'product': None
            }

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
            "can_wiretap": product.can_wiretap,
            "is_realtime_tracking": product.is_realtime_tracking,
            "portable": product.portable,
            "battery_life": product.battery_life,
            "power_source": product.power_source,
            "tracking_type": product.tracking_type,
            "monthly_fee": product.monthly_fee,
            "ecommerce_links": json.loads(product.ecommerce_links) if product.ecommerce_links else {},
            "images": json.loads(product.images) if product.images else [],
            "specifications": json.loads(product.specifications) if product.specifications else {},
            "compatibility": json.loads(product.compatibility) if product.compatibility else {},
            "is_active": product.is_active,
            "sort_order": product.sort_order
        }

        logger.info(f"Product found: {product.name} ({product.sku})")
        return {
            'found': True,
            'product': product_dict
        }


@tool
async def reset_products_to_default() -> dict:
    """Reset all products in database to default values from Python file."""
    logger.info("TOOL: reset_products_to_default")

    default_products = load_default_products_from_py()

    if not default_products:
        logger.error("No default products found in Python file")
        return {"deleted": 0, "created": 0, "errors": ["Python file not found or empty"]}

    summary = {"deleted": 0, "created": 0, "errors": []}

    async with AsyncSessionLocal() as db:
        try:
            delete_stmt = delete(Product)
            result = await db.execute(delete_stmt)
            summary["deleted"] = result.rowcount
            logger.info(f"Deleted {summary['deleted']} existing products")

            for product_data in default_products:
                try:
                    features_json = json.dumps(product_data.get("features", {})) if product_data.get("features") else None
                    ecommerce_links_json = json.dumps(product_data.get("ecommerce_links", {})) if product_data.get("ecommerce_links") else None
                    images_json = json.dumps(product_data.get("images", [])) if product_data.get("images") else None
                    specifications_json = json.dumps(product_data.get("specifications", {})) if product_data.get("specifications") else None
                    compatibility_json = json.dumps(product_data.get("compatibility", {})) if product_data.get("compatibility") else None

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
                        can_wiretap=product_data.get("can_wiretap", False),
                        is_realtime_tracking=product_data.get("is_realtime_tracking", True),
                        portable=product_data.get("portable", False),
                        battery_life=product_data.get("battery_life"),
                        power_source=product_data.get("power_source"),
                        tracking_type=product_data.get("tracking_type"),
                        monthly_fee=product_data.get("monthly_fee"),
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

            await db.commit()
            logger.info(f"Products reset completed: {summary}")

        except Exception as e:
            await db.rollback()
            error_msg = f"Error during product reset: {str(e)}"
            logger.error(error_msg)
            summary["errors"].append(error_msg)

    return summary


@tool
async def initialize_default_products_if_empty() -> dict:
    """Initialize default products from JSON if the products table is empty."""
    logger.info("TOOL: initialize_default_products_if_empty")

    async with AsyncSessionLocal() as db:
        query = select(Product)
        result = await db.execute(query)
        existing_count = len(result.scalars().all())

        if existing_count > 0:
            logger.info(f"Products table already has {existing_count} products, skipping initialization")
            return {
                'initialized': False,
                'reason': f'Table already has {existing_count} products'
            }

        logger.info("Products table is empty, initializing from JSON")
        summary = await reset_products_to_default.ainvoke({})
        logger.info(f"Products initialization completed: {summary}")
        return {
            'initialized': True,
            'created': summary.get('created', 0)
        }


@tool
async def answer_product_question_from_db(
    question: str,
    customer_data: Optional[dict] = None
) -> dict:
    """
    Answer product questions using LLM with context from database products.

    Args:
        question: Customer's question
        customer_data: Customer profile data (vehicle, qty, etc.)

    Returns:
        dict with: answer (str) - AI-generated answer
    """
    logger.info(f"TOOL: answer_product_question_from_db - question: {question[:50]}...")

    result = await get_all_active_products.ainvoke({})
    all_products = result['products']

    if not all_products:
        return {
            'answer': "Maaf, saat ini data produk sedang tidak dapat diakses. Silakan coba lagi nanti atau hubungi CS kami."
        }

    products_context = format_products_for_llm(all_products)

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

    response = await llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=question)
    ])

    logger.info(f"Product answer generated: {response.content[:100]}...")
    return {
        'answer': response.content
    }


@tool
async def get_pending_inquiry(customer_id: int) -> dict:
    """Get pending product inquiry for customer (returns dict, not ORM object)"""
    logger.info(f"TOOL: get_pending_inquiry - customer_id: {customer_id}")

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
                    'customer_id': inquiry.customer_id,
                    'product_type': inquiry.product_type,
                    'vehicle_type': inquiry.vehicle_type,
                    'unit_qty': inquiry.unit_qty,
                    'status': inquiry.status,
                    'created_at': inquiry.created_at.isoformat() if inquiry.created_at else None
                }
            }

        return {
            'found': False,
            'inquiry': None
        }


@tool
async def send_product_images(
    sort_orders: Annotated[List[int], "List of product sort_order s to send images for"],
    state: Annotated[dict, InjectedState]
) -> str:
    """
    Send product images to customer.
    Before use this tools, make sure you've called get_all_active_products tools to get the sort_order of products you want to send the images.

    The tool will automatically build image URLs based on Product.sort_order:
    - Image filename: product_{sort_order}.png

    Returns JSON with update_state containing send_images list.
    """
    logger.info(f"TOOL: send_product_images - sort_orders: {sort_orders}")

    # Check if we have too many products
    if len(sort_orders) > 3:
        logger.info(f"Too many products ({len(sort_orders)} > 3), not sending images")
        return json.dumps({
            "update_state": {"send_images": []},
            "message": f"Produk terlalu banyak ({len(sort_orders)} item). Katalog akan dikirimkan terpisah."
        })

    # Get ASSETS_URL from environment
    assets_url = os.getenv("ASSETS_URL", "")
    if not assets_url:
        logger.warning("ASSETS_URL not set in environment variables")
        return json.dumps({
            "update_state": {"send_images": []},
            "error": "ASSETS_URL not configured"
        })

    # Fetch products to get their sort_order
    async with AsyncSessionLocal() as db:
        query = select(Product).where(Product.sort_order.in_(sort_orders))
        result = await db.execute(query)
        products = result.scalars().all()

    if not products:
        logger.warning(f"No products found for IDs: {sort_orders}")
        return json.dumps({
            "update_state": {"send_images": []},
            "error": "No products found"
        })

    # Build image URLs using sort_order (not ID)
    # sort_order is 1-9, so product_{sort_order}.png
    image_urls = []
    for product in products:
        if product.sort_order and product.sort_order > 0:
            image_url = f"{assets_url}/products/product_{product.sort_order}.png"
            image_urls.append(image_url)
            logger.info(f"Product {product.id} (sort_order={product.sort_order}) → {image_url}")
        else:
            logger.warning(f"Product {product.id} has invalid sort_order: {product.sort_order}")

    logger.info(f"Generated {len(image_urls)} image URLs: {image_urls}")

    # Return JSON with update_state for agent_node to process
    return json.dumps({
        "update_state": {"send_images": image_urls},
        # "count": len(image_urls),
        # "urls": image_urls
    })


# ============================================================================
# TOOL LISTS
# ============================================================================

PRODUCT_ECOMMERCE_TOOLS = [
    get_all_active_products,
    get_product_details,
    get_ecommerce_links,
    recommend_products_for_customer,
    get_products_by_category,
    get_products_by_vehicle_type,
    send_product_images,
    # Universal intelligent query tool - handles most product questions
    # query_products_with_llm,
    # search_products,
    # answer_product_question,
    # create_product_inquiry,
    # get_pending_product_inquiry,
    # get_ecommerce_product,
    # reset_products_to_default,
    # initialize_default_products_if_empty,
    # answer_product_question_from_db,
    # get_pending_inquiry,
]

__all__ = ['PRODUCT_ECOMMERCE_TOOLS', 'send_product_images']
