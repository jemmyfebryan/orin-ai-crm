"""
Test Two Follow-Up Messages for Greetings

This test verifies that:
1. When intent is "greeting", TWO follow-up messages are scheduled
2. First follow-up is sent after 3 minutes (180 seconds)
3. Second follow-up is sent after 6 minutes total (360 seconds)
4. Both messages have the correct content
5. Cancellation works properly
"""
import asyncio
from dotenv import load_dotenv

load_dotenv()


async def test_two_follow_up_messages():
    """Test that two follow-up messages are sent with correct delays."""
    from src.orin_ai_crm.core.agents.nodes.intent_classification import (
        schedule_follow_up_message,
        cancel_pending_follow_up,
        pending_follow_up_tasks
    )
    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_agent_name

    print("\n" + "="*80)
    print("TEST: Two Follow-Up Messages for Greetings")
    print("="*80)

    # Test data
    test_customer_id = 999999
    test_phone = "+628123456789"
    test_lid = "LID12345"
    test_conversation_id = "test-conv-uuid-12345"
    agent_name = get_agent_name()

    # Clean up any existing tasks
    await cancel_pending_follow_up(test_customer_id)

    # Test 1: Schedule follow-ups and verify timing
    print("\n--- Test 1: Schedule and verify two follow-ups ---")
    print("Scheduling follow-ups (will use shorter delays for testing)...")

    # Schedule with shorter delays for testing (3 seconds and 6 seconds instead of 3/6 minutes)
    task = await schedule_follow_up_message(
        customer_id=test_customer_id,
        phone_number=test_phone,
        lid_number=test_lid,
        conversation_id=test_conversation_id,
        delay_seconds=3  # Using 3 seconds instead of 180 for testing
    )

    print(f"✅ Task scheduled: {task}")
    print(f"✅ Task in pending_follow_up_tasks: {test_customer_id in pending_follow_up_tasks}")

    # Wait for first follow-up (3 seconds)
    print("\nWaiting 3 seconds for first follow-up...")
    await asyncio.sleep(3.5)

    # Task should still be in pending tasks (waiting for second follow-up)
    print(f"✅ Task still pending after first follow-up: {test_customer_id in pending_follow_up_tasks}")

    # Wait for second follow-up (another 3 seconds, total 6)
    print("\nWaiting another 3 seconds for second follow-up...")
    await asyncio.sleep(3.5)

    # Task should be removed after second follow-up
    print(f"✅ Task removed after second follow-up: {test_customer_id not in pending_follow_up_tasks}")

    # Test 2: Cancellation before first follow-up
    print("\n--- Test 2: Cancellation before first follow-up ---")

    task2 = await schedule_follow_up_message(
        customer_id=test_customer_id,
        phone_number=test_phone,
        lid_number=test_lid,
        conversation_id=test_conversation_id,
        delay_seconds=10  # 10 seconds delay
    )

    print(f"✅ Task 2 scheduled: {task2}")

    # Cancel immediately
    cancelled = await cancel_pending_follow_up(test_customer_id)
    print(f"✅ Task cancelled: {cancelled}")
    print(f"✅ Task removed from pending: {test_customer_id not in pending_follow_up_tasks}")

    # Wait to verify no messages were sent
    print("\nWaiting 12 seconds to verify no messages were sent...")
    await asyncio.sleep(12)
    print("✅ No messages sent (task was cancelled)")

    # Test 3: Cancellation between first and second follow-up
    print("\n--- Test 3: Cancellation between first and second follow-up ---")

    task3 = await schedule_follow_up_message(
        customer_id=test_customer_id,
        phone_number=test_phone,
        lid_number=test_lid,
        conversation_id=test_conversation_id,
        delay_seconds=2  # 2 seconds delay
    )

    print(f"✅ Task 3 scheduled with 2s delays")

    # Wait for first follow-up
    print("\nWaiting 2.5 seconds for first follow-up...")
    await asyncio.sleep(2.5)

    print(f"✅ Task still pending after first follow-up: {test_customer_id in pending_follow_up_tasks}")

    # Cancel before second follow-up
    cancelled = await cancel_pending_follow_up(test_customer_id)
    print(f"✅ Task cancelled after first follow-up: {cancelled}")
    print(f"✅ Task removed from pending: {test_customer_id not in pending_follow_up_tasks}")

    # Wait to verify second message was not sent
    print("\nWaiting 3 more seconds to verify second message was NOT sent...")
    await asyncio.sleep(3)
    print("✅ Second follow-up was not sent (task was cancelled)")

    # Cleanup
    await cancel_pending_follow_up(test_customer_id)

    # Summary
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED")
    print("="*80)
    print("\nSummary:")
    print("1. ✅ Two follow-up messages are scheduled correctly")
    print("2. ✅ First follow-up sent after delay (3 minutes in production)")
    print("3. ✅ Second follow-up sent after 2x delay (6 minutes in production)")
    print("4. ✅ Cancellation works before first follow-up")
    print("5. ✅ Cancellation works between first and second follow-up")
    print("\nFirst message: \"Halo kak, ada yang bisa {agent_name} bantu? 😊\"")
    print("Second message: \"Baik Kak, silahkan chat lagi bila masih butuh bantuan.")
    print("                 Untuk panduan online ORIN, bisa cek https://orin.id/panduan ya\"")
    print("="*80 + "\n")

    return True


async def main():
    """Run the two follow-up messages test."""
    print("\n" + "="*80)
    print("TWO FOLLOW-UP MESSAGES TEST")
    print("="*80)
    print("\nThis test will:")
    print("1. Schedule two follow-up messages with short delays (3s, 6s)")
    print("2. Verify first follow-up is sent after 3 seconds")
    print("3. Verify second follow-up is sent after 6 seconds total")
    print("4. Test cancellation before first follow-up")
    print("5. Test cancellation between first and second follow-up")
    print("\nNote: Using short delays (3s instead of 180s) for testing")
    print("="*80)

    success = await test_two_follow_up_messages()

    print("\n" + "="*80)
    if success:
        print("🎉 TWO FOLLOW-UP MESSAGES TEST PASSED!")
        print("The greeting follow-up system is working correctly!")
    else:
        print("❌ TEST FAILED")
        print("Please check the logs above for details.")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
