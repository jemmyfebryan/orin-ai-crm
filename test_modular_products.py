"""
Test script for modular product structure demonstration.

Usage:
    python test_modular_products.py
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from orin_ai_crm.core.agents.tools import (
    get_ecommerce_product,
    get_all_active_products,
    format_products_for_llm
)


async def main():
    """Test the modular product structure"""
    print("\n" + "="*60)
    print("MODULAR PRODUCT STRUCTURE - DEMONSTRATION")
    print("="*60)

    # Test 1: Load and display a single product with all fields
    print("\n" + "-"*60)
    print("TEST 1: Single Product with Modular Fields")
    print("-"*60)

    product = await get_ecommerce_product("OBU V")

    if product:
        print(f"\n📦 Product: {product['name']}")
        print(f"   SKU: {product['sku']}")
        print(f"   Category: {product['category']}")
        print(f"   Subcategory: {product['subcategory']}")
        print(f"   Price: {product.get('price', 'N/A')}")
        print(f"   Installation: {product['installation_type']}")
        print(f"   Can Shutdown: {product['can_shutdown_engine']}")
        print(f"   Real-time Tracking: {product['is_realtime_tracking']}")
        print(f"\n   Description: {product.get('description', 'N/A')[:100]}...")

        print("\n   📋 Specifications:")
        for key, value in product.get('specifications', {}).items():
            if isinstance(value, list):
                print(f"   • {key}: {', '.join(value)}")
            else:
                print(f"   • {key}: {value}")

        print("\n   ⚡ Features:")
        for key, value in product.get('features', {}).items():
            if isinstance(value, list):
                print(f"   • {key}: {', '.join(value)}")
            else:
                print(f"   • {key}: {value}")

        print("\n   🛒 E-commerce Links:")
        for platform, url in product.get('ecommerce_links', {}).items():
            print(f"   • {platform.title()}: {url}")
    else:
        print("\n❌ Product not found. You may need to run reset first.")

    # Test 2: Format products for LLM
    print("\n" + "-"*60)
    print("TEST 2: Products Formatted for LLM")
    print("-"*60)

    all_products = await get_all_active_products()
    formatted_text = format_products_for_llm(all_products[:3])  # First 3 products

    print("\n" + formatted_text)

    # Test 3: Show modular benefits
    print("\n" + "-"*60)
    print("TEST 3: Benefits of Modular Structure")
    print("-"*60)

    print("""
✅ Benefits:
   1. Price is now flexible String: "25rb/bulan", "350k/6 bulan"
   2. Features are structured as JSON arrays/objects
   3. Specifications are separated from description
   4. Description is now clean and concise
   5. LLM can easily access specific product attributes
   6. Each field can be queried independently

📝 Example queries now possible:
   - Get all products with price < "500rb"
   - Get all products with "matikan mesin" feature
   - Get products by category (TANAM, INSTAN, KAMERA)
   - Format customized responses for different use cases
    """)


if __name__ == "__main__":
    asyncio.run(main())
