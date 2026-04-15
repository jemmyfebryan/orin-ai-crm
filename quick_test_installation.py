"""
Quick test for get_installation_cost tool.
"""
import time
import requests
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8081"
TEST_TOKEN = os.getenv("FRESHCHAT_WEBHOOK_TOKEN", "")

# Create session with auth
session = requests.Session()
session.headers.update({
    "Content-Type": "application/json",
    "X-Test-Token": TEST_TOKEN
})

# Test questions
test_cases = [
    ("Berapa biaya instalasi?", "general_info"),
    ("Berapa biaya akomodasi di luar Jakarta Timur?", "human_takeover"),
    ("Di Surabaya ada teknisi?", "general_info"),
]

phone_number = "085555555555"
contact_name = "Quick Test"

print("Testing get_installation_cost tool...")
print("=" * 60)

for i, (question, expected) in enumerate(test_cases, 1):
    print(f"\nTest {i}: {question}")
    print(f"Expected: {expected}")

    # Send message
    response = session.post(
        f"{BASE_URL}/test/chat/send",
        json={
            "phone_number": phone_number,
            "contact_name": contact_name,
            "message": question
        }
    )
    result = response.json()
    print(f"Status: {result.get('status')}")

    # Wait for processing
    print("Waiting 20s...")
    time.sleep(20)

    # Get history
    customer_id = result.get("customer_id")
    history = session.get(
        f"{BASE_URL}/test/chat/history",
        params={"customer_id": customer_id}
    ).json()

    messages = history.get("messages", [])

    # Find last AI message
    ai_msg = None
    for msg in reversed(messages):
        if msg.get("role") == "ai":
            ai_msg = msg
            break

    if ai_msg:
        content = ai_msg.get("content", "")
        print(f"AI Response: {content[:100]}...")

        # Check result
        if expected == "human_takeover":
            if "tim CS" in content.lower() or "alihkan" in content.lower():
                print("✅ PASSED - Human takeover triggered")
            else:
                print("❌ FAILED - Expected human takeover")
        else:
            if "jakarta timur" in content.lower() or "surabaya" in content.lower():
                print("✅ PASSED - General info provided")
            else:
                print("❌ FAILED - Expected general info")
    else:
        print("❌ No AI response found")

print("\n" + "=" * 60)
print("Test complete!")
