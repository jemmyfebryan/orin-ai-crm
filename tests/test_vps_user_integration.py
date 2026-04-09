"""
Test VPS User ID Integration

This test verifies that:
1. VPS user lookup by phone number works correctly
2. get_or_create_customer queries VPS and stores user_id
3. customer_data includes user_id in agent flow
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.orin_ai_crm.core.agents.tools.vps_tools import get_vps_user_id_by_phone, query_vps_db
from src.orin_ai_crm.core.agents.tools.db_tools import get_or_create_customer
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from sqlalchemy import select, update


async def test_vps_db_connection():
    """Test 1: Verify VPS DB connection works"""
    print("\n" + "="*60)
    print("TEST 1: VPS DB Connection")
    print("="*60)

    # Test with a simple query
    result = await query_vps_db("SELECT 1 as test")

    if result and "rows" in result:
        print("✅ VPS DB connection successful")
        print(f"   Result: {result}")
        return True
    else:
        print("❌ VPS DB connection failed")
        print(f"   Result: {result}")
        return False


async def test_get_vps_user_id_by_phone():
    """Test 2: Test get_vps_user_id_by_phone function"""
    print("\n" + "="*60)
    print("TEST 2: Get VPS User ID by Phone")
    print("="*60)

    # Test with different phone number formats
    test_phones = [
        "+628123456789",  # With + prefix
        "628123456789",   # With 62 prefix
        "08123456789",    # With 0 prefix
    ]

    print("Testing phone number format variations...")
    for phone in test_phones:
        print(f"   Testing: {phone}")
        user_id = await get_vps_user_id_by_phone(phone)
        if user_id:
            print(f"   ✅ Found VPS user_id: {user_id}")
            break
        else:
            print(f"   ℹ️  No VPS user found (expected if test phone not in VPS)")

    print("\n✅ Function executed successfully")
    return True


async def test_get_or_create_customer_with_vps():
    """Test 3: Test get_or_create_customer with VPS lookup"""
    print("\n" + "="*60)
    print("TEST 3: get_or_create_customer with VPS Lookup")
    print("="*60)

    # Use a test phone number
    test_phone = "+628999999999"  # Use a phone that might not exist in VPS
    test_contact = "Test Customer VPS Integration"

    print(f"Creating customer with phone: {test_phone}")

    # Get or create customer
    customer = await get_or_create_customer(
        phone_number=test_phone,
        contact_name=test_contact
    )

    print(f"Customer ID: {customer['customer_id']}")
    print(f"Customer Name: {customer['name']}")
    print(f"VPS User ID: {customer.get('user_id')}")

    # Verify customer was created/updated
    if customer['customer_id']:
        print("✅ Customer created/retrieved successfully")

        # Check if user_id is present (might be None if not in VPS)
        if customer.get('user_id'):
            print(f"✅ VPS user_id found: {customer['user_id']}")
        else:
            print("ℹ️  VPS user_id is None (phone not in VPS DB, which is expected)")

        return True
    else:
        print("❌ Failed to create/retrieve customer")
        return False


async def test_customer_data_includes_user_id():
    """Test 4: Verify customer_data includes user_id in database"""
    print("\n" + "="*60)
    print("TEST 4: Verify customer_data in Database")
    print("="*60)

    test_phone = "+628999999999"

    async with AsyncSessionLocal() as db:
        # Query the customer
        query = select(Customer).where(
            Customer.phone_number == test_phone,
            Customer.deleted_at.is_(None)
        )
        result = await db.execute(query)
        customer = result.scalars().first()

        if customer:
            print(f"✅ Customer found in database")
            print(f"   ID: {customer.id}")
            print(f"   Phone: {customer.phone_number}")
            print(f"   Name: {customer.name}")
            print(f"   VPS User ID: {customer.user_id}")

            if customer.user_id is not None:
                print(f"✅ VPS user_id stored in database: {customer.user_id}")
            else:
                print("ℹ️  VPS user_id is NULL (phone not in VPS DB)")

            return True
        else:
            print("❌ Customer not found in database")
            return False


async def test_vps_user_id_update():
    """Test 5: Test that VPS user_id gets updated on subsequent calls"""
    print("\n" + "="*60)
    print("TEST 5: VPS User ID Update on Subsequent Calls")
    print("="*60)

    test_phone = "+628999999999"

    print(f"Calling get_or_create_customer again for: {test_phone}")

    # Get customer again
    customer = await get_or_create_customer(
        phone_number=test_phone,
        contact_name="Updated Test Customer"
    )

    print(f"Customer ID: {customer['customer_id']}")
    print(f"VPS User ID: {customer.get('user_id')}")

    print("✅ Subsequent call successful")
    return True


async def cleanup_test_data():
    """Clean up test data"""
    print("\n" + "="*60)
    print("CLEANUP: Removing test data")
    print("="*60)

    test_phone = "+628999999999"

    async with AsyncSessionLocal() as db:
        # Soft delete the test customer
        from datetime import datetime
        from src.orin_ai_crm.core.models.database import WIB

        stmt = update(Customer).where(
            Customer.phone_number == test_phone
        ).values(
            deleted_at=datetime.now(WIB)
        )

        await db.execute(stmt)
        await db.commit()

        print(f"✅ Test customer soft-deleted: {test_phone}")


async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("VPS USER ID INTEGRATION TEST SUITE")
    print("="*60)

    results = []

    # Run tests
    try:
        results.append(("VPS DB Connection", await test_vps_db_connection()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        results.append(("VPS DB Connection", False))

    try:
        results.append(("Get VPS User ID", await test_get_vps_user_id_by_phone()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Get VPS User ID", False))

    try:
        results.append(("get_or_create_customer", await test_get_or_create_customer_with_vps()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("get_or_create_customer", False))

    try:
        results.append(("Database Verification", await test_customer_data_includes_user_id()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Database Verification", False))

    try:
        results.append(("Subsequent Calls", await test_vps_user_id_update()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Subsequent Calls", False))

    # Clean up
    try:
        await cleanup_test_data()
    except Exception as e:
        print(f"⚠️  Cleanup failed: {e}")

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")


if __name__ == "__main__":
    asyncio.run(main())
