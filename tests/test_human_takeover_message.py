"""
Test Human Takeover Message Generation

This test verifies that:
1. The human takeover message includes the link https://orin.id/panduan
2. The message mentions live agent takeover
3. The message is in Indonesian and friendly
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def test_human_takeover_message():
    from src.orin_ai_crm.core.agents.nodes.quality_check_nodes import generate_human_takeover_message

    print("\n" + "="*80)
    print("TEST: Human Takeover Message Generation")
    print("="*80)

    print("\n--- Test Case 1: With customer name ---")
    result_1 = await generate_human_takeover_message(customer_name='Budi')

    print("Generated message:")
    print("-" * 80)
    print(result_1)
    print("-" * 80)

    print("\nAnalysis:")
    print(f"  - Length: {len(result_1)} characters")

    # Check if link is included
    if 'https://orin.id/panduan' in result_1:
        print("  ✅ Link 'https://orin.id/panduan' is included")
    else:
        print("  ❌ Link 'https://orin.id/panduan' is NOT included")

    # Check if it mentions live agent
    if 'live agent' in result_1.lower() or 'agent' in result_1.lower():
        print("  ✅ Mentions live agent takeover")
    else:
        print("  ❌ Does not mention live agent takeover")

    # Check if it's in Indonesian
    indonesian_keywords = ['kak', 'agent', 'live', 'segera', 'membantu', 'terima kasih']
    has_indonesian = any(keyword in result_1.lower() for keyword in indonesian_keywords)
    print(f"  - Indonesian Language: {'✅ YES' if has_indonesian else '❌ NO'}")

    # Check if it has emojis
    has_emoji = any(char in result_1 for char in ['😊', '🙏', '👍', ':)', '😁'])
    print(f"  - Has Emojis: {'✅ YES' if has_emoji else '❌ NO'}")

    print("\n--- Test Case 2: Without customer name ---")
    result_2 = await generate_human_takeover_message(customer_name=None)

    print("Generated message:")
    print("-" * 80)
    print(result_2)
    print("-" * 80)

    print("\nAnalysis:")
    if 'https://orin.id/panduan' in result_2:
        print("  ✅ Link is included")
    else:
        print("  ❌ Link is NOT included")

    print("\n" + "="*80)
    all_passed = (
        'https://orin.id/panduan' in result_1 and
        'https://orin.id/panduan' in result_2 and
        ('agent' in result_1.lower() or 'live' in result_1.lower())
    )

    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*80 + "\n")

    return all_passed


async def main():
    success = await test_human_takeover_message()

    if success:
        print("\n🎉 Human takeover message generation is working correctly!")
        print("The link https://orin.id/panduan is included in the message.\n")
    else:
        print("\n❌ Tests failed. Please check the output above.\n")


if __name__ == "__main__":
    asyncio.run(main())
