"""
Test script for ask_technical_support tool
Tests with real phone number from VPS DB
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from langchain_core.messages import HumanMessage, AIMessage
from src.orin_ai_crm.core.agents.tools.support_agent_tools import ask_technical_support

async def test_ask_technical_support():
    """Test the ask_technical_support tool with real phone number"""

    print("=" * 80)
    print("Testing ask_technical_support tool")
    print("=" * 80)

    # Prepare test state with real phone number from VPS DB
    phone_number = "081333370000"

    # Create sample messages_history (simulating a conversation)
    messages_history = [
        HumanMessage(content="Halo, saya punya masalah dengan GPS mobil saya"),
        AIMessage(content="Halo Kak! Ada yang bisa saya bantu dengan GPS mobil Kakak?"),
        HumanMessage(content="GPS mobil saya tidak update sejak 2 hari yang lalu"),
        AIMessage(content="Baik Kak, saya bantu cek ya. Mobil Kakak pakai GPS apa?"),
        HumanMessage(content="OBU V untuk Honda Jazz"),
    ]

    # The question that will be sent to technical support
    # This simulates the instruction from orchestrator to support agent
    question = "Berapa jarak tempuh kendaraan Honda Jazz dalam 7 hari terakhir?"

    # Create state
    state = {
        "phone_number": phone_number,
        "messages_history": messages_history,
        "customer_id": 1,  # Dummy customer_id
    }

    print(f"\n📱 Phone Number: {phone_number}")
    print(f"💬 Messages History: {len(messages_history)} messages")
    print(f"❓ Question to Technical Support: {question}")
    print(f"\n📨 Messages to be sent to API:")
    for i, msg in enumerate(messages_history):
        msg_type = "User" if isinstance(msg, HumanMessage) else "AI"
        content_preview = msg.content[:60] + "..." if len(msg.content) > 60 else msg.content
        print(f"  [{i+1}] {msg_type}: {content_preview}")

    print(f"\n🔧 API Endpoint: http://{os.getenv('ORINAI_API_IP')}:{os.getenv('ORINAI_API_PORT')}/chat_api")

    print("\n" + "=" * 80)
    print("Calling tool...")
    print("=" * 80 + "\n")

    try:
        # Call the tool - state and question are passed as arguments
        result = await ask_technical_support.ainvoke({"state": state, "question": question})

        print("=" * 80)
        print("Tool Result:")
        print("=" * 80)

        # Check for error
        if "error" in result and result["error"]:
            print(f"\n❌ ERROR: {result['error']}")
            print(f"   Responses: {result.get('responses', [])}")
        else:
            responses = result.get("responses", [])
            print(f"\n✅ SUCCESS: Received {len(responses)} response(s)")
            if responses:
                print(f"\n📨 Responses from Technical Support:")
                for i, response in enumerate(responses, 1):
                    print(f"\n--- Response {i} ---")
                    print(response)
                    print("-" * 40)

        print("\n" + "=" * 80)
        print("Full Result Dict:")
        print("=" * 80)
        import json
        print(json.dumps(result, indent=2, default=str))

    except Exception as e:
        print(f"\n❌ EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("Test completed")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_ask_technical_support())
