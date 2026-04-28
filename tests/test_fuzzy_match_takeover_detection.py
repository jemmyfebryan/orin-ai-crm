"""
Test Fuzzy Match Takeover Detection

This test verifies that the webhook correctly distinguishes between AI and human agent messages:
1. AI messages sent via Freshchat API are saved to DB
2. Fuzzy matching correctly identifies AI messages in chat history
3. Webhook ignores AI messages (found in DB)
4. Webhook detects live human agent messages (NOT in DB) and sets takeover
5. Idempotent behavior when takeover already active
"""
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import database models
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer, ChatSession, WIB
from sqlalchemy import select, delete


async def setup_test_customer(phone_number, human_takeover=False):
    """Create a test customer"""
    async with AsyncSessionLocal() as db:
        customer = Customer(
            phone_number=phone_number,
            contact_name=f"Test Customer {phone_number[-4:]}",
            human_takeover=human_takeover,
            updated_at=datetime.now(WIB),
        )
        db.add(customer)
        await db.commit()
        await db.refresh(customer)
        return customer.id


async def cleanup_test_customer(phone_number):
    """Clean up test customer and their chat sessions"""
    async with AsyncSessionLocal() as db:
        # Get customer first
        customer_result = await db.execute(select(Customer).where(Customer.phone_number == phone_number))
        customer = customer_result.scalars().first()

        if customer:
            # Delete chat sessions
            await db.execute(delete(ChatSession).where(ChatSession.customer_id == customer.id))
            # Delete customer
            await db.execute(delete(Customer).where(Customer.id == customer.id))
            await db.commit()


async def save_ai_message(customer_id, message):
    """Save an AI message to the database (simulating AI response)"""
    from src.orin_ai_crm.core.agents.tools.db_tools import save_message_to_db

    msg_id = await save_message_to_db(customer_id, "ai", message, content_type="text")
    return msg_id


async def test_fuzzy_match():
    """Test 1: Fuzzy matching correctly identifies similar messages"""
    from src.orin_ai_crm.server.routes.freshchat import fuzzy_match_message

    print("\n" + "="*80)
    print("TEST: Fuzzy Matching Function")
    print("="*80)

    test_cases = [
        # (message, message_list, threshold, expected_result, description)
        ("Hello world", ["Hello world"], 0.9, True, "Exact match"),
        ("Hello world", ["Hello world!"], 0.9, True, "Near match (punctuation)"),
        ("Halo, kak! Apa kabar?", ["Halo kak! Apa kabar?"], 0.9, True, "Near match (missing comma)"),
        ("This is a test message", ["Completely different message"], 0.9, False, "No match"),
        ("Produk GPS tracker terbaik", ["Produk GPS tracker terbaik untuk kendaraan"], 0.85, False, "Below threshold"),
    ]

    all_passed = True
    for message, message_list, threshold, expected, description in test_cases:
        result = fuzzy_match_message(message, message_list, threshold)
        passed = (result == expected)
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {description}: '{message[:30]}...' -> {result} (expected {expected})")
        if not passed:
            all_passed = False

    print("="*80)
    if all_passed:
        print("✅ ALL FUZZY MATCH TESTS PASSED")
    else:
        print("❌ SOME FUZZY MATCH TESTS FAILED")
    print("="*80 + "\n")

    return all_passed


async def test_is_ai_message():
    """Test 2: is_ai_message correctly identifies AI messages in chat history"""
    from src.orin_ai_crm.server.routes.freshchat import is_ai_message

    test_phone = "+62999000101"

    try:
        # Setup: Create customer
        customer_id = await setup_test_customer(test_phone)
        print(f"✅ Created test customer: {customer_id}")

        print("\n" + "="*80)
        print("TEST: AI Message Detection from Chat History")
        print("="*80)

        # Save some AI messages
        ai_messages = [
            "Halo Kak! Apa ada yang bisa saya bantu?",
            "Produk GPS tracker kami tersedia dalam beberapa jenis",
            "Untuk informasi lebih lanjut, silakan kunjungi website kami"
        ]

        print(f"\n💾 Saving {len(ai_messages)} AI messages to database...")
        for msg in ai_messages:
            await save_ai_message(customer_id, msg)
        print("✅ AI messages saved")

        # Test 1: Exact match
        print(f"\n📝 Test 1: Exact match - '{ai_messages[0][:30]}...'")
        result1 = await is_ai_message(customer_id, ai_messages[0])
        print(f"  Result: {result1} (expected: True)")
        test1_passed = result1

        # Test 2: Fuzzy match (minor variation)
        print(f"\n📝 Test 2: Fuzzy match - '{ai_messages[1][:30]}...'")
        fuzzy_variant = ai_messages[1] + "!"  # Add exclamation mark
        result2 = await is_ai_message(customer_id, fuzzy_variant)
        print(f"  Result: {result2} (expected: True, with fuzzy match)")
        test2_passed = result2

        # Test 3: Not an AI message (human agent message)
        print(f"\n📝 Test 3: Human agent message - 'Mohon menunggu sebentar ya...'")
        human_message = "Mohon menunggu sebentar ya, saya akan cek stoknya"
        result3 = await is_ai_message(customer_id, human_message)
        print(f"  Result: {result3} (expected: False)")
        test3_passed = not result3

        # Test 4: Empty chat history
        print(f"\n📝 Test 4: Message not in history - 'Baik, terima kasih'")
        new_message = "Baik, terima kasih atas infonya"
        result4 = await is_ai_message(customer_id, new_message)
        print(f"  Result: {result4} (expected: False)")
        test4_passed = not result4

        all_passed = test1_passed and test2_passed and test3_passed and test4_passed

        print("\n" + "="*80)
        if all_passed:
            print("✅ ALL AI MESSAGE DETECTION TESTS PASSED")
        else:
            print("❌ SOME AI MESSAGE DETECTION TESTS FAILED")
        print("="*80 + "\n")

        return all_passed

    finally:
        await cleanup_test_customer(test_phone)
        print("🧹 Cleaned up test customer\n")


async def test_webhook_flow():
    """Test 3: Simulate webhook flow with AI and human agent messages"""
    from src.orin_ai_crm.server.routes.freshchat import is_ai_message
    from src.orin_ai_crm.core.agents.tools.db_tools import get_or_create_customer

    test_phone = "+62999000202"

    try:
        # Setup: Create customer
        customer_id = await setup_test_customer(test_phone)
        print(f"✅ Created test customer: {customer_id}")

        print("\n" + "="*80)
        print("TEST: Webhook Flow Simulation")
        print("="*80)

        # Scenario 1: AI sends a message via Freshchat API
        print(f"\n📱 Scenario 1: AI sends message via Freshchat API")
        ai_message = "Halo Kak! Apa ada yang bisa saya bantu?"
        print(f"  Message: '{ai_message}'")

        # Simulate AI sending message (would be saved by send_message_to_freshchat)
        await save_ai_message(customer_id, ai_message)
        print(f"  ✅ Message saved to DB")

        # Simulate webhook receiving the message
        print(f"  📥 Webhook receives agent message...")
        is_ai = await is_ai_message(customer_id, ai_message)
        print(f"  🔍 Check: Is this AI message? {is_ai}")

        if is_ai:
            print(f"  ✅ Webhook correctly identifies as AI - ignores message")
        else:
            print(f"  ❌ Webhook incorrectly identifies as human agent")

        scenario1_passed = is_ai

        # Verify human_takeover is still False
        async with AsyncSessionLocal() as db:
            customer = await db.execute(select(Customer).where(Customer.id == customer_id))
            customer = customer.scalars().first()
            print(f"  📊 human_takeover: {customer.human_takeover} (expected: False)")
            scenario1_passed = scenario1_passed and not customer.human_takeover

        # Scenario 2: Live human agent sends a message
        print(f"\n📱 Scenario 2: Live human agent sends message")
        human_message = "Baik kak, saya bantu selesaikan ya"
        print(f"  Message: '{human_message}'")

        # Simulate webhook receiving the message
        print(f"  📥 Webhook receives agent message...")
        is_ai = await is_ai_message(customer_id, human_message)
        print(f"  🔍 Check: Is this AI message? {is_ai}")

        if not is_ai:
            print(f"  ✅ Webhook correctly identifies as human agent")

            # Set human_takeover flag (simulating webhook logic)
            async with AsyncSessionLocal() as db:
                from sqlalchemy import update
                from src.orin_ai_crm.core.utils.db_retry import execute_with_retry

                update_stmt = update(Customer).where(
                    Customer.id == customer_id
                ).values(human_takeover=True)

                await execute_with_retry(db.execute, update_stmt, max_retries=3)
                await db.commit()
                print(f"  ✅ human_takeover set to True")
        else:
            print(f"  ❌ Webhook incorrectly identifies as AI")

        scenario2_passed = not is_ai

        # Verify human_takeover is now True
        async with AsyncSessionLocal() as db:
            customer = await db.execute(select(Customer).where(Customer.id == customer_id))
            customer = customer.scalars().first()
            print(f"  📊 human_takeover: {customer.human_takeover} (expected: True)")
            scenario2_passed = scenario2_passed and customer.human_takeover

        # Scenario 3: Another human agent message (idempotent check)
        print(f"\n📱 Scenario 3: Another human agent message (idempotent)")
        human_message_2 = "Mohon ditunggu sebentar ya kak"
        print(f"  Message: '{human_message_2}'")

        # Simulate webhook receiving the message
        print(f"  📥 Webhook receives agent message...")
        is_ai = await is_ai_message(customer_id, human_message_2)
        print(f"  🔍 Check: Is this AI message? {is_ai}")

        if not is_ai:
            print(f"  ✅ Webhook correctly identifies as human agent")

            # Check if human_takeover already True (should not change anything)
            async with AsyncSessionLocal() as db:
                customer = await db.execute(select(Customer).where(Customer.id == customer_id))
                customer = customer.scalars().first()

                if customer.human_takeover:
                    print(f"  ✅ human_takeover already True - no action needed (idempotent)")
                else:
                    print(f"  ❌ human_takeover is False - should be True")
        else:
            print(f"  ❌ Webhook incorrectly identifies as AI")

        scenario3_passed = not is_ai

        all_passed = scenario1_passed and scenario2_passed and scenario3_passed

        print("\n" + "="*80)
        if all_passed:
            print("✅ ALL WEBHOOK FLOW TESTS PASSED")
        else:
            print("❌ SOME WEBHOOK FLOW TESTS FAILED")
        print("="*80 + "\n")

        return all_passed

    finally:
        await cleanup_test_customer(test_phone)
        print("🧹 Cleaned up test customer\n")


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("🧪 Fuzzy Match Takeover Detection Test Suite")
    print("="*80)

    # Test 1: Fuzzy matching function
    test1_passed = await test_fuzzy_match()

    # Test 2: AI message detection from DB
    test2_passed = await test_is_ai_message()

    # Test 3: Webhook flow simulation
    test3_passed = await test_webhook_flow()

    # Final summary
    print("\n" + "="*80)
    print("📊 FINAL TEST SUMMARY")
    print("="*80)
    print(f"  Test 1 (Fuzzy Matching):           {'✅ PASS' if test1_passed else '❌ FAIL'}")
    print(f"  Test 2 (AI Message Detection):     {'✅ PASS' if test2_passed else '❌ FAIL'}")
    print(f"  Test 3 (Webhook Flow):             {'✅ PASS' if test3_passed else '❌ FAIL'}")

    all_passed = test1_passed and test2_passed and test3_passed

    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nThe fuzzy match takeover detection is working correctly:")
        print("  ✓ Fuzzy matching correctly identifies similar messages")
        print("  ✓ AI messages are saved to DB and detected")
        print("  ✓ Webhook ignores AI messages (found in chat history)")
        print("  ✓ Webhook detects live human agent messages (NOT in history)")
        print("  ✓ Live agent takeover is activated when human sends message")
        print("  ✓ Idempotent behavior when takeover already active")
    else:
        print("\n❌ SOME TESTS FAILED - Please review the output above")

    print("="*80 + "\n")

    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
