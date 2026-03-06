"""
Test script for ecommerce product tools.

Usage:
    python test_ecommerce_products.py
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from orin_ai_crm.core.agents.tools import (
    get_ecommerce_product,
    reset_products_to_default,
    load_default_products_from_json
)


async def test_load_default_products():
    """Test loading default products from JSON"""
    print("\n" + "="*60)
    print("TEST 1: Load Default Products from JSON")
    print("="*60)

    default_products = load_default_products_from_json()

    print(f"\nLoaded {len(default_products)} default products from JSON:")
    for name, desc in default_products.items():
        preview = desc[:100] + "..." if len(desc) > 100 else desc
        print(f"\n- {name}")
        print(f"  Description: {preview}")

    return default_products


async def test_get_ecommerce_product(product_identifier: str):
    """Test getting a product from database"""
    print("\n" + "="*60)
    print(f"TEST 2: Get Product '{product_identifier}' from Database")
    print("="*60)

    product = await get_ecommerce_product(product_identifier)

    if product:
        print(f"\n✅ Product Found:")
        print(f"  ID: {product['id']}")
        print(f"  Name: {product['name']}")
        print(f"  SKU: {product['sku']}")
        print(f"  Category: {product['category']}")
        print(f"  Description: {product['description'][:200]}...")
    else:
        print(f"\n❌ Product not found: {product_identifier}")
        print("   Tip: You may need to run reset_products_to_default() first")

    return product


async def test_reset_products():
    """Test resetting products to default values"""
    print("\n" + "="*60)
    print("TEST 3: Reset Products to Default Values")
    print("="*60)

    print("\n⚠️  This will:")
    print("  - Create new products from JSON if they don't exist")
    print("  - Update existing products with JSON descriptions")
    print("\nProceeding...")

    summary = await reset_products_to_default()

    print(f"\n✅ Reset Complete:")
    print(f"  - Created: {summary['created']} products")
    print(f"  - Updated: {summary['updated']} products")
    print(f"  - Errors: {len(summary['errors'])}")

    if summary['errors']:
        print("\n❌ Errors encountered:")
        for error in summary['errors']:
            print(f"  - {error}")

    return summary


async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("ECOMMERCE PRODUCT TOOLS - TEST SCRIPT")
    print("="*60)

    # Test 1: Load default products from JSON
    default_products = await test_load_default_products()

    # Test 2: Get products from database (will be empty initially)
    test_products = ["OBU V", "OBU F", "AI CAM"]
    for product_name in test_products:
        await test_get_ecommerce_product(product_name)

    # Test 3: Reset products to default (initialize database)
    print("\n\n" + "="*60)
    print("Would you like to reset products to default values?")
    print("This will create/update products in the database.")
    print("="*60)

    # Auto-proceed for testing
    await test_reset_products()

    # Test 4: Get products again (should now exist)
    print("\n\n" + "="*60)
    print("TEST 4: Verify Products After Reset")
    print("="*60)

    for product_name in test_products:
        await test_get_ecommerce_product(product_name)

    print("\n\n" + "="*60)
    print("ALL TESTS COMPLETE!")
    print("="*60)
    print("\nTo use these tools in your code:")
    print("""
    from orin_ai_crm.core.agents.tools import (
        get_ecommerce_product,
        reset_products_to_default
    )

    # Get a product
    product = await get_ecommerce_product("OBU V")

    # Reset to defaults (creates/updates from JSON)
    summary = await reset_products_to_default()
    """)


if __name__ == "__main__":
    asyncio.run(main())
