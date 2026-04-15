"""
Test script for get_installation_cost tool via actual chat with hana_agent.

This tests various customer questions in Indonesian through the /test/chat/send endpoint.
"""
import asyncio
import time
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BASE_URL = "http://localhost:8081"
TEST_TOKEN = os.getenv("FRESHCHAT_WEBHOOK_TOKEN", "")


def send_message(phone_number: str, contact_name: str, message: str, session: requests.Session) -> dict:
    """Send a message to the test chat endpoint."""
    url = f"{BASE_URL}/test/chat/send"
    payload = {
        "phone_number": phone_number,
        "contact_name": contact_name,
        "message": message
    }

    response = session.post(url, json=payload)
    return response.json()


def get_chat_history(customer_id: int, session: requests.Session) -> dict:
    """Get chat history for a customer."""
    url = f"{BASE_URL}/test/chat/history"
    params = {"customer_id": customer_id}

    response = session.get(url, params=params)
    return response.json()


def print_messages(messages: list, show_all: bool = False):
    """Print messages in a readable format."""
    if not messages:
        print("  (No messages)")
        return

    # Show last N messages
    if show_all:
        messages_to_show = messages
    else:
        messages_to_show = messages[-6:]  # Show last 6 messages

    for msg in messages_to_show:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        content_type = msg.get("content_type", "text")

        # Truncate long messages
        if len(content) > 200:
            content = content[:200] + "..."

        if role == "user":
            print(f"  👤 USER: {content}")
        elif role == "ai":
            if content_type == "image":
                print(f"  🤖 AI: [IMAGE] {content}")
            elif content_type == "pdf":
                print(f"  🤖 AI: [PDF] {content}")
            else:
                print(f"  🤖 AI: {content}")
        print()


def reset_chat(phone_number: str) -> bool:
    """Reset chat for a phone number (soft delete customer)."""
    url = f"{BASE_URL}/test/reset"
    params = {"phone_number": phone_number}
    headers = {
        "X-Test-Token": TEST_TOKEN
    }

    try:
        response = requests.post(url, params=params, headers=headers)
        result = response.json()
        print(f"Reset chat: {result}")
        return result.get("success", False)
    except Exception as e:
        print(f"Error resetting chat: {e}")
        return False


def test_installation_cost_questions():
    """Test installation cost questions through actual chat."""

    # Test phone number (unique for this test)
    phone_number = "086666666666"
    contact_name = "Test Installation Cost"

    # Reset chat first to clear any previous state
    print("Resetting chat to clear previous state...")
    reset_chat(phone_number)
    print()

    # Create a session with cookies for authentication
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Test-Token": TEST_TOKEN
    })

    print("=" * 80)
    print("TESTING get_installation_cost via hana_agent Chat")
    print("=" * 80)
    print()

    # Test cases: (question, expected_behavior, description)
    test_cases = [
        # General questions - should return general info
        (
            "Berapa biaya instalasi?",
            "general_info",
            "General installation cost question"
        ),
        (
            "Teknisi ada di area mana saja?",
            "general_info",
            "Technician coverage area question"
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
            "Berapa harga akomodasi kalau di luar area teknisi?",
            "human_takeover",
            "Specific accommodation price question"
        ),
    ]

    passed = 0
    failed = 0

    for i, (question, expected_behavior, description) in enumerate(test_cases, 1):
        print(f"\n{'=' * 80}")
        print(f"Test {i}: {description}")
        print(f"{'=' * 80}")
        print(f"Question: \"{question}\"")
        print(f"Expected: {expected_behavior}")
        print()

        try:
            # Send message
            print("Sending message...")
            response = send_message(phone_number, contact_name, question, session)
            print(f"Response: {response}")
            print()

            # Wait for AI to process (background task)
            print("Waiting for AI to process...")
            time.sleep(25)  # Wait 25 seconds for AI to respond (increased)

            # Get customer_id from response
            customer_id = response.get("customer_id")
            if not customer_id:
                print("❌ FAILED: No customer_id in response")
                failed += 1
                continue

            # Get chat history
            print("Fetching chat history...")
            history_response = get_chat_history(customer_id, session)
            messages = history_response.get("messages", [])

            # Debug: show all messages if no AI response
            if not any(msg.get("role") == "ai" for msg in messages):
                print("⚠️  No AI messages found. Showing all messages:")
                print_messages(messages, show_all=True)

            # Find the last AI message
            last_ai_message = None
            for msg in reversed(messages):
                if msg.get("role") == "ai":
                    last_ai_message = msg
                    break

            if not last_ai_message:
                print("❌ FAILED: No AI response found")
                failed += 1
                continue

            ai_response = last_ai_message.get("content", "")
            print(f"AI Response: \"{ai_response}\"")
            print()

            # Check if response contains expected keywords
            if expected_behavior == "human_takeover":
                # Should mention human agent/CS takeover
                takeover_keywords = ["tim CS", "human agent", "alihkan", "segera membantu"]
                is_takeover = any(keyword.lower() in ai_response.lower() for keyword in takeover_keywords)

                if is_takeover:
                    print("✅ PASSED: Correctly triggered human takeover")
                    passed += 1
                else:
                    print("❌ FAILED: Expected human takeover but got general info")
                    failed += 1

            else:  # general_info
                # Should mention Jakarta Timur, Surabaya, and FREE
                info_keywords = ["jakarta timur", "surabaya", "gratis", "teknisi"]
                has_info = any(keyword.lower() in ai_response.lower() for keyword in info_keywords)

                # Should NOT mention CS takeover for accommodation fee
                takeover_keywords = ["biaya akomodasi", "tim CS", "alihkan"]
                has_takeover = any(keyword.lower() in ai_response.lower() for keyword in takeover_keywords)

                if has_info and not has_takeover:
                    print("✅ PASSED: Correctly returned general installation info")
                    passed += 1
                else:
                    print(f"❌ FAILED: Expected general info but got something else")
                    print(f"   Has info keywords: {has_info}")
                    print(f"   Has takeover keywords: {has_takeover}")
                    failed += 1

            # Show recent messages
            print()
            print("Recent messages:")
            print_messages(messages, show_all=False)

        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = test_installation_cost_questions()
    exit(0 if success else 1)
