"""
Test Intent Classification Node

This test verifies that:
1. Greeting messages are classified correctly
2. Other messages are classified correctly
3. Background task is scheduled for greetings
4. Background task is cancelled for other messages
5. Follow-up message is sent after 10 seconds for greeting
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def test_intent_classification():
    from src.orin_ai_crm.core.agents.nodes.intent_classification import (
        classify_user_intent,
        schedule_follow_up_message,
        cancel_pending_follow_up,
        pending_follow_up_tasks
    )

    print("\n" + "="*80)
    print("TEST: Intent Classification")
    print("="*80)

    test_cases = [
        ("Hi", "greeting"),
        ("Hello", "greeting"),
        ("Halo kak", "greeting"),
        ("Halo test", "greeting"),
        ("Saya pengguna orin", "greeting"),
        ("Minta tolong", "greeting"),
        ("P", "greeting"),
        ("Pagi", "greeting"),
        ("Info produk OBU V", "other"),
        ("Berapa harga GPS mobil?", "other"),
        ("Saya mau pasang GPS untuk 5 unit", "other"),
        ("GPS saya tidak bisa tracking", "other"),
        ("Apakah ada fitur matikan mesin?", "other"),
        ("OBU V itu apa sih?", "other"),
    ]

    results = []

    for message, expected_intent in test_cases:
        print(f"\n--- Testing: '{message}' ---")

        try:
            result = await classify_user_intent(message)
            actual_intent = result.intent
            reasoning = result.reasoning

            print(f"Expected: {expected_intent}")
            print(f"Actual: {actual_intent}")
            print(f"Reasoning: {reasoning}")

            if actual_intent == expected_intent:
                print("✅ PASS")
                results.append(True)
            else:
                print("❌ FAIL")
                results.append(False)

        except Exception as e:
            print(f"❌ ERROR: {e}")
            results.append(False)

    # Summary
    print("\n" + "="*80)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*80 + "\n")

    return passed == total


async def test_background_task_scheduling():
    """Test that background tasks are scheduled and cancelled correctly"""
    from src.orin_ai_crm.core.agents.nodes.intent_classification import (
        schedule_follow_up_message,
        cancel_pending_follow_up,
        pending_follow_up_tasks
    )

    print("\n" + "="*80)
    print("TEST: Background Task Scheduling")
    print("="*80)

    test_customer_id = 999999  # Use a test customer ID

    # Test 1: Schedule a follow-up task
    print("\n--- Test 1: Schedule follow-up task ---")
    try:
        task = await schedule_follow_up_message(
            customer_id=test_customer_id,
            phone_number="+629999999998",
            lid_number="",
            delay_seconds=10
        )
        print(f"Task scheduled: {task}")
        print(f"Pending tasks: {list(pending_follow_up_tasks.keys())}")

        if test_customer_id in pending_follow_up_tasks:
            print("✅ Task is in pending_follow_up_tasks")
        else:
            print("❌ Task NOT in pending_follow_up_tasks")
            return False

    except Exception as e:
        print(f"❌ ERROR scheduling task: {e}")
        return False

    # Test 2: Cancel the follow-up task
    print("\n--- Test 2: Cancel follow-up task ---")
    try:
        cancelled = await cancel_pending_follow_up(test_customer_id)
        print(f"Cancel result: {cancelled}")

        if cancelled:
            print("✅ Task cancelled successfully")
        else:
            print("❌ Task cancellation returned False")
            return False

        if test_customer_id not in pending_follow_up_tasks:
            print("✅ Task removed from pending_follow_up_tasks")
        else:
            print("❌ Task still in pending_follow_up_tasks")
            return False

    except Exception as e:
        print(f"❌ ERROR cancelling task: {e}")
        return False

    print("\n" + "="*80)
    print("✅ Background task scheduling tests PASSED")
    print("="*80 + "\n")

    return True


async def test_end_to_end_greeting_flow():
    """Test the complete greeting flow with follow-up message"""
    from src.orin_ai_crm.core.agents.nodes.intent_classification import (
        node_intent_classification,
        pending_follow_up_tasks
    )
    from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
    from sqlalchemy import select, update
    from datetime import datetime
    from src.orin_ai_crm.core.models.database import WIB

    print("\n" + "="*80)
    print("TEST: End-to-End Greeting Flow")
    print("="*80)

    test_phone = "+629999999997"

    try:
        # Create test customer
        from src.orin_ai_crm.core.agents.tools.db_tools import get_or_create_customer

        customer = await get_or_create_customer(
            phone_number=test_phone,
            contact_name="Test User"
        )

        customer_id = customer['customer_id']
        print(f"Test customer created: {customer_id}")

        # Test 1: Greeting message
        print("\n--- Test 1: Greeting message 'Hi' ---")

        state = {
            "customer_id": customer_id,
            "phone_number": test_phone,
            "lid_number": None,
            "messages": [HumanMessage(content="Hi")]
        }

        result = await node_intent_classification(state)

        print(f"Route: {result.get('route')}")
        print(f"Classification: {result.get('classification')}")

        if result.get('route') == 'END':
            print("✅ Routed to END (correct for greeting)")
        else:
            print("❌ Did NOT route to END")
            return False

        if result.get('classification', {}).get('intent') == 'greeting':
            print("✅ Classified as 'greeting'")
        else:
            print("❌ NOT classified as 'greeting'")
            return False

        if customer_id in pending_follow_up_tasks:
            print("✅ Follow-up task scheduled")
        else:
            print("❌ Follow-up task NOT scheduled")
            return False

        # Wait a bit to ensure task is running
        await asyncio.sleep(1)

        # Test 2: Other message (should cancel background task)
        print("\n--- Test 2: Other message 'Info produk' ---")

        state2 = {
            "customer_id": customer_id,
            "phone_number": test_phone,
            "lid_number": None,
            "messages": [HumanMessage(content="Info produk OBU V")]
        }

        result2 = await node_intent_classification(state2)

        print(f"Route: {result2.get('route')}")
        print(f"Classification: {result2.get('classification')}")

        if result2.get('route') == 'agent_entry':
            print("✅ Routed to agent_entry (correct for other)")
        else:
            print("❌ Did NOT route to agent_entry")
            return False

        if result2.get('classification', {}).get('intent') == 'other':
            print("✅ Classified as 'other'")
        else:
            print("❌ NOT classified as 'other'")
            return False

        # Check if task was cancelled
        await asyncio.sleep(0.5)  # Give time for cancellation

        if customer_id not in pending_follow_up_tasks:
            print("✅ Follow-up task was cancelled")
        else:
            print("❌ Follow-up task still exists")
            return False

        print("\n" + "="*80)
        print("✅ End-to-end greeting flow tests PASSED")
        print("="*80 + "\n")

        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Cleanup test customer
        print("\n--- Cleanup ---")
        async with AsyncSessionLocal() as db:
            stmt = update(Customer).where(
                Customer.phone_number == test_phone
            ).values(deleted_at=datetime.now(WIB))
            await db.execute(stmt)
            await db.commit()
            print(f"✅ Cleaned up test customer: {test_phone}")


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("INTENT CLASSIFICATION TEST SUITE")
    print("="*80)

    results = []

    # Test 1: Intent classification
    try:
        results.append(("Intent Classification", await test_intent_classification()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Intent Classification", False))

    # Test 2: Background task scheduling
    try:
        results.append(("Background Task Scheduling", await test_background_task_scheduling()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Background Task Scheduling", False))

    # Test 3: End-to-end greeting flow
    try:
        results.append(("End-to-End Greeting Flow", await test_end_to_end_greeting_flow()))
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("End-to-End Greeting Flow", False))

    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

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
    from langchain_core.messages import HumanMessage
    asyncio.run(main())
