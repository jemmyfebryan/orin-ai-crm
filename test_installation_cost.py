"""
Test script for get_installation_cost tool.

This tests various customer questions in Indonesian to verify the tool responds correctly.
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from langchain_core.messages import HumanMessage, AIMessage


async def test_installation_cost():
    """Test the get_installation_cost tool with various customer questions."""

    from src.orin_ai_crm.core.agents.tools.support_agent_tools import get_installation_cost

    # Test cases: (question, expected_behavior, description)
    test_cases = [
        # General questions - should return general info
        (
            "Berapa biaya instalasi?",
            "general_info",
            "General installation cost question"
        ),
        (
            "Berapa biaya pemasangan GPS?",
            "general_info",
            "GPS installation cost question"
        ),
        (
            "Teknisi ada di area mana saja?",
            "general_info",
            "Technician coverage area question"
        ),
        (
            "Apakah instalasi gratis?",
            "general_info",
            "Free installation question"
        ),
        (
            "Di Surabaya ada teknisi?",
            "general_info",
            "Surabaya technician availability"
        ),
        (
            "Kalau di Jakarta Timur berapa biayanya?",
            "general_info",
            "Jakarta Timur specific (should be free)"
        ),
        (
            "Biar jelas, biaya instalasi berapa sih?",
            "general_info",
            "General cost inquiry (not accommodation specific)"
        ),
        (
            "Instalasi di daerah saya bagaimana?",
            "general_info",
            "General area question"
        ),
        (
            "Apakah ada biaya tambahan untuk instalasi?",
            "general_info",
            "Additional cost question (general)"
        ),

        # Specific accommodation fee questions - should trigger human takeover
        (
            "Berapa biaya akomodasi di luar Jakarta Timur?",
            "human_takeover",
            "Specific accommodation fee outside Jakarta Timur"
        ),
        (
            "Kalau di luar Surabaya berapa biayanya?",
            "human_takeover",
            "Specific fee outside Surabaya"
        ),
        (
            "Berapa biaya akomodasi untuk area luar daerah?",
            "human_takeover",
            "Specific accommodation fee amount for outside areas"
        ),
        (
            "Kalau lokasi saya di Bandung, berapa biaya akomodasinya?",
            "human_takeover",
            "Specific accommodation fee for Bandung"
        ),
        (
            "Berapa harga akomodasi kalau di luar area teknisi?",
            "human_takeover",
            "Specific accommodation price question"
        ),
        (
            "Biaya akomodasinya berapa sih kalau di luar Jakarta dan Surabaya?",
            "human_takeover",
            "Direct accommodation fee question"
        ),
    ]

    print("=" * 80)
    print("TESTING get_installation_cost TOOL")
    print("=" * 80)
    print()

    passed = 0
    failed = 0

    for i, (question, expected_behavior, description) in enumerate(test_cases, 1):
        print(f"Test {i}: {description}")
        print(f"Question: \"{question}\"")
        print(f"Expected: {expected_behavior}")

        # Create a mock state with the customer question
        state = {
            "customer_id": 12345,
            "messages": [HumanMessage(content=question)]
        }

        try:
            # Call the tool using ainvoke with parameters dict
            result = await get_installation_cost.ainvoke({"state": state})

            # Check the result
            message = result.get('message', '')
            update_state = result.get('update_state', {})
            human_takeover_triggered = update_state.get('human_takeover', False)

            # Determine actual behavior
            if human_takeover_triggered:
                actual_behavior = "human_takeover"
            else:
                actual_behavior = "general_info"

            # Verify against expected
            if actual_behavior == expected_behavior:
                print(f"✅ PASSED")
                passed += 1
            else:
                print(f"❌ FAILED")
                print(f"   Expected: {expected_behavior}")
                print(f"   Got: {actual_behavior}")
                failed += 1

            # Show response preview
            if len(message) > 150:
                preview = message[:150] + "..."
            else:
                preview = message
            print(f"Response: \"{preview}\"")

        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            failed += 1

        print()

    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(test_installation_cost())
    sys.exit(0 if success else 1)
