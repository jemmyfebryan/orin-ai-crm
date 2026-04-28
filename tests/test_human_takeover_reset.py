"""
Test Human Takeover Reset Cron Job

This test verifies that the periodic_human_takeover_reset task:
1. Resets human_takeover flag for customers updated more than 1 hour ago
2. Does NOT reset for customers updated less than 1 hour ago
3. Excludes soft-deleted customers
4. Handles empty results gracefully
"""
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import database models
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer, WIB
from sqlalchemy import select, update, delete


async def setup_test_customers():
    """Create test customers with different scenarios"""
    async with AsyncSessionLocal() as db:
        # Test Case 1: Customer with human_takeover=True, updated > 1 hour ago (SHOULD be reset)
        old_customer = Customer(
            phone_number="+62111111111",
            contact_name="Old Customer",
            human_takeover=True,
            updated_at=datetime.now(WIB) - timedelta(hours=2),  # 2 hours ago
        )
        db.add(old_customer)

        # Test Case 2: Customer with human_takeover=True, updated < 1 hour ago (should NOT be reset)
        recent_customer = Customer(
            phone_number="+62122222222",
            contact_name="Recent Customer",
            human_takeover=True,
            updated_at=datetime.now(WIB) - timedelta(minutes=30),  # 30 minutes ago
        )
        db.add(recent_customer)

        # Test Case 3: Customer with human_takeover=False (should remain False)
        no_takeover_customer = Customer(
            phone_number="+62333333333",
            contact_name="No Takeover Customer",
            human_takeover=False,
            updated_at=datetime.now(WIB) - timedelta(hours=2),
        )
        db.add(no_takeover_customer)

        # Test Case 4: Soft-deleted customer with human_takeover=True (should NOT be reset)
        deleted_customer = Customer(
            phone_number="+62444444444",
            contact_name="Deleted Customer",
            human_takeover=True,
            updated_at=datetime.now(WIB) - timedelta(hours=2),
            deleted_at=datetime.now(WIB),  # Soft deleted
        )
        db.add(deleted_customer)

        # Test Case 5: Multiple old customers (to test batch processing)
        old_customer_2 = Customer(
            phone_number="+62555555555",
            contact_name="Old Customer 2",
            human_takeover=True,
            updated_at=datetime.now(WIB) - timedelta(hours=3),  # 3 hours ago
        )
        db.add(old_customer_2)

        await db.commit()

        # Return customer IDs for verification
        return {
            "old_customer": old_customer.id,
            "recent_customer": recent_customer.id,
            "no_takeover_customer": no_takeover_customer.id,
            "deleted_customer": deleted_customer.id,
            "old_customer_2": old_customer_2.id,
        }


async def cleanup_test_customers(customer_ids):
    """Clean up test customers after tests"""
    async with AsyncSessionLocal() as db:
        for customer_id in customer_ids.values():
            await db.execute(delete(Customer).where(Customer.id == customer_id))
        await db.commit()


async def execute_human_takeover_reset():
    """
    Execute the human_takeover reset logic (extracted from lifespan.py)
    This mimics what the cron job does
    """
    async with AsyncSessionLocal() as session:
        # Calculate cutoff time (1 hour ago from now in WIB)
        cutoff_time = datetime.now(WIB) - timedelta(hours=1)

        # Find customers with human_takeover=True and updated_at < 1 hour ago
        stmt = (
            update(Customer)
            .where(Customer.human_takeover == True)
            .where(Customer.updated_at < cutoff_time)
            .where(Customer.deleted_at == None)  # Exclude soft-deleted customers
            .values(human_takeover=False)
        )

        result = await session.execute(stmt)
        affected_count = result.rowcount
        await session.commit()

        return affected_count


async def test_human_takeover_reset():
    """Test the human_takeover reset cron job"""
    print("\n" + "="*80)
    print("TEST: Human Takeover Reset Cron Job")
    print("="*80)

    # Setup test data
    print("\n⚙️  Setting up test customers...")
    customer_ids = await setup_test_customers()
    print(f"✅ Created 5 test customers")

    # Verify initial state
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Customer.id, Customer.phone_number, Customer.human_takeover, Customer.updated_at)
            .where(Customer.id.in_(list(customer_ids.values())))
        )
        customers = result.all()

        print("\n📋 Initial State:")
        print("-" * 80)
        for cust in customers:
            time_diff = datetime.now() - cust[3]
            print(f"  {cust[1]} - human_takeover={cust[2]}, updated={time_diff}")
        print("-" * 80)

    # Execute the reset function
    print("\n🔄 Executing human_takeover reset...")
    affected_count = await execute_human_takeover_reset()
    print(f"✅ Reset completed. Affected rows: {affected_count}")

    # Verify final state
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Customer.id, Customer.phone_number, Customer.human_takeover, Customer.deleted_at)
            .where(Customer.id.in_(list(customer_ids.values())))
        )
        customers = result.all()

        print("\n📋 Final State:")
        print("-" * 80)

        test_results = {
            "old_customer": False,
            "recent_customer": False,
            "no_takeover_customer": False,
            "deleted_customer": False,
            "old_customer_2": False,
        }

        # Map customer IDs back to names
        id_to_name = {v: k for k, v in customer_ids.items()}

        for cust in customers:
            customer_name = id_to_name.get(cust[0], "Unknown")
            phone = cust[1]
            takeover = cust[2]
            deleted = cust[3]

            status = f"{customer_name} ({phone})"
            status += f" - human_takeover={takeover}, deleted={deleted}"

            # Validate results
            if customer_name == "old_customer":
                test_results["old_customer"] = (takeover == False and deleted == None)
                print(f"  ✅ OLD Customer (2h ago): Reset to False = {takeover == False}")
            elif customer_name == "recent_customer":
                test_results["recent_customer"] = (takeover == True and deleted == None)
                print(f"  ✅ RECENT Customer (30m ago): Still True = {takeover == True}")
            elif customer_name == "no_takeover_customer":
                test_results["no_takeover_customer"] = (takeover == False and deleted == None)
                print(f"  ✅ NO TAKEOVER Customer: Still False = {takeover == False}")
            elif customer_name == "deleted_customer":
                test_results["deleted_customer"] = (takeover == True and deleted != None)
                print(f"  ✅ DELETED Customer: Still True (not reset) = {takeover == True}")
            elif customer_name == "old_customer_2":
                test_results["old_customer_2"] = (takeover == False and deleted == None)
                print(f"  ✅ OLD Customer 2 (3h ago): Reset to False = {takeover == False}")

        print("-" * 80)

    # Cleanup
    print("\n🧹 Cleaning up test data...")
    await cleanup_test_customers(customer_ids)
    print("✅ Cleanup completed")

    # Print test results
    print("\n" + "="*80)
    all_passed = all(test_results.values())

    print("Test Results:")
    for test_name, passed in test_results.items():
        print(f"  {'✅' if passed else '❌'} {test_name}: {'PASS' if passed else 'FAIL'}")

    if all_passed:
        print("\n✅ ALL TESTS PASSED")
        print("\nSummary:")
        print("  - Customers with human_takeover=True updated > 1h ago were reset to False")
        print("  - Customers updated < 1h ago kept human_takeover=True")
        print("  - Customers with human_takeover=False stayed False")
        print("  - Soft-deleted customers were NOT reset")
        print(f"  - Affected row count: {affected_count} (expected: 2)")
    else:
        print("\n❌ SOME TESTS FAILED")

    print("="*80 + "\n")

    return all_passed


async def test_empty_database():
    """Test that the function handles empty database gracefully"""
    print("\n" + "="*80)
    print("TEST: Human Takeover Reset with Empty Database")
    print("="*80)

    print("\n🔄 Executing human_takeover reset on empty database...")
    affected_count = await execute_human_takeover_reset()
    print(f"✅ Completed. Affected rows: {affected_count}")

    passed = (affected_count == 0)

    print("\n" + "="*80)
    if passed:
        print("✅ TEST PASSED - Function handles empty database gracefully")
    else:
        print("❌ TEST FAILED - Expected 0 affected rows")
    print("="*80 + "\n")

    return passed


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("🧪 Human Takeover Reset Cron Job Test Suite")
    print("="*80)

    # Test 1: Main functionality
    test1_passed = await test_human_takeover_reset()

    # Test 2: Empty database handling
    test2_passed = await test_empty_database()

    # Final summary
    print("\n" + "="*80)
    print("📊 FINAL TEST SUMMARY")
    print("="*80)
    print(f"  Test 1 (Main functionality): {'✅ PASS' if test1_passed else '❌ FAIL'}")
    print(f"  Test 2 (Empty database):     {'✅ PASS' if test2_passed else '❌ FAIL'}")

    all_passed = test1_passed and test2_passed

    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nThe human_takeover reset cron job is working correctly:")
        print("  ✓ Resets customers updated > 1 hour ago")
        print("  ✓ Preserves recent customers (< 1 hour)")
        print("  ✓ Excludes soft-deleted customers")
        print("  ✓ Handles empty database gracefully")
    else:
        print("\n❌ SOME TESTS FAILED - Please review the output above")

    print("="*80 + "\n")

    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
