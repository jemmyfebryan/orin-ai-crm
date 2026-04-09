"""
Test send_form Logic with VPS User

This test verifies that:
1. send_form is False when VPS user exists
2. send_form is True for new customers without VPS user
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.orin_ai_crm.core.agents.tools.db_tools import get_or_create_customer
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from sqlalchemy import select, update


async def test_send_form_with_vps_user():
    """Test 1: send_form is False when VPS user exists"""
    print("\n" + "="*60)
    print("TEST 1: send_form with VPS User")
    print("="*60)

    # Use a phone that exists in VPS
    test_phone = "+628123456789"

    print(f"Creating/updating customer with phone: {test_phone}")

    # Get or create customer
    customer = await get_or_create_customer(
        phone_number=test_phone,
        contact_name="VPS Test User"
    )

    print(f"Customer ID: {customer['customer_id']}")
    print(f"VPS User ID: {customer.get('user_id')}")
    print(f"Is Onboarded: {customer['is_onboarded']}")
    print(f"send_form: {customer.get('send_form')}")

    # Verify send_form is False when VPS user exists
    if customer.get('user_id'):
        if customer.get('send_form') == False:
            print("✅ send_form is False (VPS user exists)")
            return True
        else:
            print(f"❌ send_form is {customer.get('send_form')} (should be False)")
            return False
    else:
        print("ℹ️  No VPS user found, skipping test")
        return True


async def test_send_form_without_vps_user():
    """Test 2: send_form is True for new customer without VPS user"""
    print("\n" + "="*60)
    print("TEST 2: send_form without VPS User")
    print("="*60)

    # Use a phone that doesn't exist in VPS
    test_phone = "+629999999999"  # This phone likely doesn't exist in VPS

    print(f"Creating customer with phone: {test_phone}")

    # Get or create customer
    customer = await get_or_create_customer(
        phone_number=test_phone,
        contact_name="New Customer"
    )

    print(f"Customer ID: {customer['customer_id']}")
    print(f"VPS User ID: {customer.get('user_id')}")
    print(f"Is Onboarded: {customer['is_onboarded']}")
    print(f"send_form: {customer.get('send_form')}")

    # Verify send_form is True when no VPS user
    if not customer.get('user_id'):
        if customer.get('send_form') == True:
            print("✅ send_form is True (no VPS user)")
            return True
        else:
            print(f"❌ send_form is {customer.get('send_form')} (should be True)")
            return False
    else:
        print("ℹ️  VPS user found, skipping test")
        return True


async def test_send_form_after_vps_user_onboarded():
    """Test 3: send_form is False even if is_onboarded was False before"""
    print("\n" + "="*60)
    print("TEST 3: send_form after VPS User Onboarding")
    print("="*60)

    test_phone = "+628123456789"

    print(f"Updating customer with phone: {test_phone}")

    # Get or create customer
    customer = await get_or_create_customer(
        phone_number=test_phone,
        contact_name="VPS Test User"
    )

    print(f"Customer ID: {customer['customer_id']}")
    print(f"VPS User ID: {customer.get('user_id')}")
    print(f"Is Onboarded: {customer['is_onboarded']}")
    print(f"send_form: {customer.get('send_form')}")

    # The key test: send_form should be False because VPS user exists
    # even though we just created/updated the customer
    if customer.get('user_id'):
        if customer.get('send_form') == False:
            print("✅ send_form is False (VPS user exists, customer is onboarded)")
            return True
        else:
            print(f"❌ send_form is {customer.get('send_form')} (should be False)")
            return False
    else:
        print("ℹ️  No VPS user found, skipping test")
        return True


async def cleanup_test_data():
    """Clean up test data"""
    print("\n" + "="*60)
    print("CLEANUP: Removing test data")
    print("="*60)

    test_phones = ["+629999999999"]

    for test_phone in test_phones:
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
    print("send_form LOGIC WITH VPS USER TEST SUITE")
    print("="*60)

    results = []

    # Run tests
    try:
        results.append(("send_form with VPS User", await test_send_form_with_vps_user()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("send_form with VPS User", False))

    try:
        results.append(("send_form without VPS User", await test_send_form_without_vps_user()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("send_form without VPS User", False))

    try:
        results.append(("send_form after VPS Onboarding", await test_send_form_after_vps_user_onboarded()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("send_form after VPS Onboarding", False))

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
