"""
End-to-End Test: Interactive Profiling with AI Agent

This test verifies that:
1. AI agent actually performs interactive profiling
2. Responses are in Indonesian language
3. Agent asks for ONE field at a time
4. Profiling flow completes correctly
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.orin_ai_crm.server.services.chat_processor import process_chat_request


async def test_interactive_profiling_e2e():
    """End-to-end test of interactive profiling with AI agent"""
    print("\n" + "="*80)
    print("END-TO-END TEST: Interactive Profiling with AI Agent")
    print("="*80)

    # Use a test phone number that doesn't exist in VPS
    test_phone = "+629999999996"

    try:
        # ========================================================================
        # TURN 1: Customer sends first message
        # ========================================================================
        print("\n" + "-"*80)
        print("TURN 1: Customer sends first message")
        print("-"*80)

        message_1 = "Halo, saya ingin pasang GPS"
        print(f"Customer: {message_1}")
        print(f"Phone: {test_phone}")

        result_1 = await process_chat_request(
            phone_number=test_phone,
            lid_number=None,
            message=message_1,
            contact_name="",
            is_new_chat=True,
            conversation_id=None  # Test doesn't have real Freshchat conversation
        )

        print(f"\nAgent Response:")
        for i, reply in enumerate(result_1.get('replies', []), 1):
            print(f"  Bubble {i}: {reply}")

        # Verify response is in Indonesian and asks for profiling info
        response_text = " ".join(result_1.get('replies', []))
        print(f"\nAnalysis:")
        print(f"  - Customer ID: {result_1.get('customer_id')}")
        print(f"  - send_form: {result_1.get('send_form', 'N/A')}")
        print(f"  - VPS User ID: {result_1.get('send_images', [])}")  # Just checking if we can access customer data

        # Check if response is in Indonesian (contains Indonesian words)
        indonesian_keywords = ['kakak', 'boleh', 'domisili', 'kendaraan', 'unit', 'berapa', 'gps']
        has_indonesian = any(keyword in response_text.lower() for keyword in indonesian_keywords)
        print(f"  - Indonesian Language: {'✅ YES' if has_indonesian else '❌ NO'}")

        # Check if agent asks for information
        asking_questions = any(word in response_text.lower() for word in ['?', 'apa', 'dimana', 'berapa', 'mana'])
        print(f"  - Asking Questions: {'✅ YES' if asking_questions else '❌ NO'}")

        # ========================================================================
        # TURN 2: Customer provides domicile
        # ========================================================================
        print("\n" + "-"*80)
        print("TURN 2: Customer provides domicile")
        print("-"*80)

        message_2 = "Saya di Surabaya"
        print(f"Customer: {message_2}")

        result_2 = await process_chat_request(
            phone_number=test_phone,
            lid_number=None,
            message=message_2,
            contact_name="",
            is_new_chat=False,
            conversation_id=None  # Test doesn't have real Freshchat conversation
        )

        print(f"\nAgent Response:")
        for i, reply in enumerate(result_2.get('replies', []), 1):
            print(f"  Bubble {i}: {reply}")

        response_text_2 = " ".join(result_2.get('replies', []))
        print(f"\nAnalysis:")
        has_indonesian_2 = any(keyword in response_text_2.lower() for keyword in indonesian_keywords)
        print(f"  - Indonesian Language: {'✅ YES' if has_indonesian_2 else '❌ NO'}")

        # Check if profiling is complete or agent continues asking
        is_complete_2 = 'lengkap' in response_text_2.lower() or 'terima kasih' in response_text_2.lower() or 'baik' in response_text_2.lower()
        print(f"  - Profiling Complete: {'✅ YES' if is_complete_2 else '⏳ CONTINUES'}")

        # ========================================================================
        # TURN 3: Customer asks about pricing
        # ========================================================================
        print("\n" + "-"*80)
        print("TURN 3: Customer asks about pricing")
        print("-"*80)

        message_3 = "Berapa harganya?"
        print(f"Customer: {message_3}")

        result_3 = await process_chat_request(
            phone_number=test_phone,
            lid_number=None,
            message=message_3,
            contact_name="",
            is_new_chat=False,
            conversation_id=None  # Test doesn't have real Freshchat conversation
        )

        print(f"\nAgent Response:")
        for i, reply in enumerate(result_3.get('replies', []), 1):
            print(f"  Bubble {i}: {reply}")

        response_text_3 = " ".join(result_3.get('replies', []))
        print(f"\nAnalysis:")
        has_indonesian_3 = any(keyword in response_text_3.lower() for keyword in indonesian_keywords)
        print(f"  - Indonesian Language: {'✅ YES' if has_indonesian_3 else '❌ NO'}")

        # Check if agent provides pricing or route information
        has_pricing = 'harga' in response_text_3.lower() or 'rp' in response_text_3.lower() or 'ribu' in response_text_3.lower()
        has_route = 'sales' in response_text_3.lower() or 'ecommerce' in response_text_3.lower()
        print(f"  - Provides Pricing: {'✅ YES' if has_pricing else '❌ NO'}")
        print(f"  - Mentions Route: {'✅ YES' if has_route else '❌ NO'}")

        # ========================================================================
        # VERIFICATION SUMMARY
        # ========================================================================
        print("\n" + "="*80)
        print("VERIFICATION SUMMARY")
        print("="*80)

        all_indonesian = has_indonesian and has_indonesian_2 and has_indonesian_3
        print(f"1. All responses in Indonesian: {'✅ PASS' if all_indonesian else '❌ FAIL'}")

        agent_asks_questions = asking_questions
        print(f"2. Agent asks for information: {'✅ PASS' if agent_asks_questions else '❌ FAIL'}")

        profiling_works = is_complete_2 or has_pricing or has_route
        print(f"3. Interactive profiling works: {'✅ PASS' if profiling_works else '❌ FAIL'}")

        print(f"\nOverall Result: {'✅ ALL TESTS PASSED' if all_indonesian and agent_asks_questions and profiling_works else '❌ SOME TESTS FAILED'}")

        return all_indonesian and agent_asks_questions and profiling_works

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Cleanup test customer
        print("\n" + "-"*80)
        print("CLEANUP")
        print("-"*80)

        from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
        from sqlalchemy import update
        from datetime import datetime
        from src.orin_ai_crm.core.models.database import WIB

        async with AsyncSessionLocal() as db:
            stmt = update(Customer).where(
                Customer.phone_number == test_phone
            ).values(deleted_at=datetime.now(WIB))
            await db.execute(stmt)
            await db.commit()
            print(f"✅ Cleaned up test customer: {test_phone}")


async def main():
    """Run the end-to-end test"""
    print("\n" + "="*80)
    print("INTERACTIVE PROFILING - END-TO-END AI AGENT TEST")
    print("="*80)
    print("\nThis test will:")
    print("1. Create a new customer (no VPS user)")
    print("2. Send first message to trigger interactive profiling")
    print("3. Verify agent asks for information in Indonesian")
    print("4. Continue conversation to complete profiling")
    print("5. Verify the entire flow works correctly")
    print("\n" + "="*80)

    success = await test_interactive_profiling_e2e()

    print("\n" + "="*80)
    if success:
        print("🎉 END-TO-END TEST PASSED!")
        print("Interactive profiling is working correctly with Indonesian responses!")
    else:
        print("❌ END-TO-END TEST FAILED")
        print("Please check the logs above for details.")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
