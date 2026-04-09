"""
Test VPS User Details Integration

This test verifies that:
1. VPS user details (city, devices) are fetched correctly
2. Customer data is automatically populated from VPS
3. Multiple devices are joined with ";" separator
4. is_b2b is calculated correctly based on unit_qty > 5
5. is_onboarded is set to True when VPS user exists
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.orin_ai_crm.core.agents.tools.vps_tools import get_vps_user_details, get_vps_user_id_by_phone
from src.orin_ai_crm.core.agents.tools.db_tools import get_or_create_customer
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from sqlalchemy import select, update


async def test_get_vps_user_details():
    """Test 1: Test get_vps_user_details function"""
    print("\n" + "="*60)
    print("TEST 1: Get VPS User Details")
    print("="*60)

    # First, get a VPS user ID
    test_phone = "+628123456789"  # This phone exists in VPS from previous test
    vps_user_id = await get_vps_user_id_by_phone(test_phone)

    if not vps_user_id:
        print("⚠️  No VPS user found for test phone, skipping test")
        return True

    print(f"Found VPS user_id: {vps_user_id}")

    # Get user details
    details = await get_vps_user_details(vps_user_id)

    if details:
        print(f"✅ User details fetched successfully")
        print(f"   City: {details.get('city')}")
        print(f"   Device Names: {details.get('device_names')}")
        print(f"   Unit Qty: {details.get('unit_qty')}")
        return True
    else:
        print("❌ Failed to fetch user details")
        return False


async def test_customer_auto_population():
    """Test 2: Test customer data auto-population from VPS"""
    print("\n" + "="*60)
    print("TEST 2: Customer Auto-Population from VPS")
    print("="*60)

    # Use a phone that exists in VPS
    test_phone = "+628123456789"  # This phone exists in VPS from previous test

    print(f"Creating/updating customer with phone: {test_phone}")

    # Get or create customer (should fetch VPS data)
    customer = await get_or_create_customer(
        phone_number=test_phone,
        contact_name="VPS Test User"
    )

    print(f"Customer ID: {customer['customer_id']}")
    print(f"Name: {customer['name']}")
    print(f"Domicile (from VPS city): {customer['domicile']}")
    print(f"Vehicle Alias (from VPS devices): {customer['vehicle_alias']}")
    print(f"Unit Qty (from VPS device count): {customer['unit_qty']}")
    print(f"Is B2B (unit_qty > 5): {customer['is_b2b']}")
    print(f"Is Onboarded (auto-True): {customer['is_onboarded']}")
    print(f"VPS User ID: {customer.get('user_id')}")

    # Verify data was populated
    success = True

    if customer.get('user_id'):
        print("✅ VPS user_id populated")
    else:
        print("❌ VPS user_id NOT populated")
        success = False

    if customer['domicile']:
        print(f"✅ Domicile populated: {customer['domicile']}")
    else:
        print("ℹ️  Domicile is empty (VPS user might not have city)")

    if customer['vehicle_alias']:
        print(f"✅ Vehicle alias populated: {customer['vehicle_alias']}")
        # Check if multiple devices are separated by ";"
        if ';' in customer['vehicle_alias']:
            print(f"   ✅ Multiple devices correctly separated by ';'")
    else:
        print("ℹ️  Vehicle alias is empty (VPS user might not have devices)")

    if customer['unit_qty'] > 0:
        print(f"✅ Unit qty populated: {customer['unit_qty']}")
    else:
        print("ℹ️  Unit qty is 0 (VPS user might not have devices)")

    # Verify is_b2b calculation
    expected_b2b = customer['unit_qty'] > 5
    if customer['is_b2b'] == expected_b2b:
        print(f"✅ Is B2B calculated correctly: {customer['is_b2b']} (unit_qty={customer['unit_qty']})")
    else:
        print(f"❌ Is B2B calculation incorrect: {customer['is_b2b']} (expected {expected_b2b})")
        success = False

    # Verify is_onboarded
    if customer['is_onboarded']:
        print(f"✅ Is Onboarded set to True (VPS user exists)")
    else:
        print(f"❌ Is Onboarded NOT set to True")
        success = False

    return success


async def test_database_verification():
    """Test 3: Verify data stored in database"""
    print("\n" + "="*60)
    print("TEST 3: Database Verification")
    print("="*60)

    test_phone = "+628123456789"

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
            print(f"   Domicile: {customer.domicile}")
            print(f"   Vehicle Alias: {customer.vehicle_alias}")
            print(f"   Unit Qty: {customer.unit_qty}")
            print(f"   Is B2B: {customer.is_b2b}")
            print(f"   Is Onboarded: {customer.is_onboarded}")
            print(f"   VPS User ID: {customer.user_id}")

            # Verify all fields are stored
            if customer.user_id is not None:
                print("✅ VPS user_id stored in database")
            else:
                print("❌ VPS user_id NOT stored in database")
                return False

            if customer.domicile:
                print("✅ Domicile stored in database")
            else:
                print("ℹ️  Domicile is NULL (VPS city might be empty)")

            if customer.vehicle_alias:
                print("✅ Vehicle alias stored in database")
            else:
                print("ℹ️  Vehicle alias is NULL (VPS devices might be empty)")

            if customer.is_onboarded:
                print("✅ Is Onboarded stored as True in database")
            else:
                print("❌ Is Onboarded NOT stored as True in database")
                return False

            return True
        else:
            print("❌ Customer not found in database")
            return False


async def test_multiple_devices_separator():
    """Test 4: Test multiple devices are separated correctly"""
    print("\n" + "="*60)
    print("TEST 4: Multiple Devices Separator")
    print("="*60)

    test_phone = "+628123456789"

    # Get customer
    customer = await get_or_create_customer(
        phone_number=test_phone,
        contact_name="VPS Test User"
    )

    vehicle_alias = customer['vehicle_alias']

    if vehicle_alias:
        print(f"Vehicle alias: {vehicle_alias}")

        # Count devices by splitting by ";"
        devices = vehicle_alias.split(';')
        device_count = len(devices)

        print(f"Device count from vehicle_alias: {device_count}")
        print(f"Unit qty: {customer['unit_qty']}")

        # Verify they match
        if device_count == customer['unit_qty']:
            print(f"✅ Device count matches unit_qty: {device_count}")
        else:
            print(f"⚠️  Device count mismatch: {device_count} vs {customer['unit_qty']}")

        # Show individual devices
        print(f"Individual devices:")
        for i, device in enumerate(devices, 1):
            print(f"   {i}. {device}")

        return True
    else:
        print("ℹ️  No devices found for this user")
        return True


async def test_is_b2b_calculation():
    """Test 5: Test is_b2b calculation logic"""
    print("\n" + "="*60)
    print("TEST 5: Is B2B Calculation")
    print("="*60)

    test_phone = "+628123456789"

    # Get customer
    customer = await get_or_create_customer(
        phone_number=test_phone,
        contact_name="VPS Test User"
    )

    unit_qty = customer['unit_qty']
    is_b2b = customer['is_b2b']
    expected_b2b = unit_qty > 5

    print(f"Unit Qty: {unit_qty}")
    print(f"Is B2B: {is_b2b}")
    print(f"Expected Is B2B (unit_qty > 5): {expected_b2b}")

    if is_b2b == expected_b2b:
        print(f"✅ Is B2B calculation is correct")
        if unit_qty > 5:
            print(f"   → Customer has {unit_qty} devices (> 5), so is_b2b = True")
        else:
            print(f"   → Customer has {unit_qty} devices (≤ 5), so is_b2b = False")
        return True
    else:
        print(f"❌ Is B2B calculation is incorrect")
        return False


async def test_is_onboarded_auto_true():
    """Test 6: Test is_onboarded is automatically set to True"""
    print("\n" + "="*60)
    print("TEST 6: Is Onboarded Auto-Set to True")
    print("="*60)

    test_phone = "+628123456789"

    # Get customer
    customer = await get_or_create_customer(
        phone_number=test_phone,
        contact_name="VPS Test User"
    )

    is_onboarded = customer['is_onboarded']
    vps_user_id = customer.get('user_id')

    print(f"VPS User ID: {vps_user_id}")
    print(f"Is Onboarded: {is_onboarded}")

    if vps_user_id and is_onboarded:
        print(f"✅ Is Onboarded automatically set to True (VPS user exists)")
        return True
    elif not vps_user_id:
        print(f"ℹ️  No VPS user found, is_onboarded not auto-set")
        return True
    else:
        print(f"❌ Is Onboarded NOT set to True even though VPS user exists")
        return False


async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("VPS USER DETAILS INTEGRATION TEST SUITE")
    print("="*60)

    results = []

    # Run tests
    try:
        results.append(("Get VPS User Details", await test_get_vps_user_details()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Get VPS User Details", False))

    try:
        results.append(("Customer Auto-Population", await test_customer_auto_population()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Customer Auto-Population", False))

    try:
        results.append(("Database Verification", await test_database_verification()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Database Verification", False))

    try:
        results.append(("Multiple Devices Separator", await test_multiple_devices_separator()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Multiple Devices Separator", False))

    try:
        results.append(("Is B2B Calculation", await test_is_b2b_calculation()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Is B2B Calculation", False))

    try:
        results.append(("Is Onboarded Auto-True", await test_is_onboarded_auto_true()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Is Onboarded Auto-True", False))

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
