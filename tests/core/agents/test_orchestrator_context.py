"""
Test orchestrator context awareness - verify it can see message_history
"""

import asyncio
from langchain_core.messages import HumanMessage, AIMessage

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import orchestrator_node


async def test_orchestrator_with_context():
    """
    Test: When user says "boleh" (yes/okay) after AI asked a question,
    orchestrator should understand the context and route appropriately.
    """
    print("\n" + "="*80)
    print("TEST: Orchestrator Message History Context")
    print("="*80)
    print("\nScenario:")
    print("1. AI asked: 'Kakak mau saya kirimkan detail produknya?'")
    print("2. User replied: 'boleh' (yes/okay)")
    print("3. Expected: Orchestrator should understand user wants product details")
    print("")

    # Setup state with message history
    messages_history = [
        AIMessage(content='Untuk motor bensin, Kakak bisa pilih OBU V.'),
        AIMessage(content='OBU V memiliki fitur lengkap: lacak real-time, matikan mesin jarak jauh.'),
        AIMessage(content='Kakak mau saya kirimkan detail produknya?'),
    ]

    messages = [
        HumanMessage(content='boleh')
    ]

    state: AgentState = {
        "messages": messages,
        "messages_history": messages_history,
        "customer_id": 1,
        "customer_data": {
            "id": 1,
            "name": "Mojo",
            "domicile": "Surabaya",
            "vehicle_alias": "motor",
            "unit_qty": 0,
            "is_b2b": False,
            "is_onboarded": True,
        },
        "orchestrator_step": 0,
        "max_orchestrator_steps": 5,
        "agents_called": [],
    }

    print("Invoking orchestrator...")
    result = await orchestrator_node(state)

    # Check decision
    decision = result.get("orchestrator_decision", {})
    next_agent = decision.get("next_agent", "N/A")
    reasoning = decision.get("reasoning", "")

    print("\n" + "="*80)
    print("ORCHESTRATOR DECISION:")
    print("="*80)
    print(f"Next Agent: {next_agent}")
    print(f"Reasoning: {reasoning}")

    # Evaluate
    print("\n" + "="*80)
    print("EVALUATION:")
    print("="*80)

    # When user says "boleh" to product details question, should route to ecommerce
    if next_agent == "ecommerce":
        print("✓ PASS: Orchestrator correctly routed to ecommerce")
        print("  Orchestrator understood the context of 'boleh' response")
        success = True
    elif next_agent == "final":
        print("⚠ WARNING: Orchestrator routed to final")
        print("  May not have fully understood the context")
        success = False
    else:
        print(f"✗ FAIL: Orchestrator routed to {next_agent}")
        print("  Expected ecommerce based on context")
        success = False

    # Check if reasoning mentions context
    if "detail" in reasoning.lower() or "produk" in reasoning.lower():
        print("✓ PASS: Reasoning shows understanding of product context")
    elif "boleh" in reasoning.lower() and "context" in reasoning.lower():
        print("✓ PASS: Reasoning acknowledges the response")
    else:
        print("⚠ WARNING: Reasoning may not show full context understanding")

    print("="*80)

    return success


async def test_orchestrator_without_context():
    """
    Test: When user says "boleh" without context (no message history),
    orchestrator should note lack of context.
    """
    print("\n" + "="*80)
    print("TEST: Orchestrator Without Context")
    print("="*80)
    print("\nScenario:")
    print("1. No previous conversation")
    print("2. User says: 'boleh' (yes/okay)")
    print("3. Expected: Orchestrator notes lack of context")
    print("")

    # Empty message history
    messages_history = []

    messages = [
        HumanMessage(content='boleh')
    ]

    state: AgentState = {
        "messages": messages,
        "messages_history": messages_history,
        "customer_id": 1,
        "customer_data": {
            "id": 1,
            "name": "Customer",
            "domicile": "Jakarta",
            "vehicle_alias": "motor",
            "unit_qty": 0,
            "is_b2b": False,
            "is_onboarded": True,
        },
        "orchestrator_step": 0,
        "max_orchestrator_steps": 5,
        "agents_called": [],
    }

    print("Invoking orchestrator...")
    result = await orchestrator_node(state)

    # Check decision
    decision = result.get("orchestrator_decision", {})
    next_agent = decision.get("next_agent", "N/A")
    reasoning = decision.get("reasoning", "")

    print("\n" + "="*80)
    print("ORCHESTRATOR DECISION:")
    print("="*80)
    print(f"Next Agent: {next_agent}")
    print(f"Reasoning: {reasoning}")

    print("\n" + "="*80)
    print("EVALUATION:")
    print("="*80)

    # Without context, routing to final is acceptable
    # Or orchestrator should mention lack of context
    if "context" in reasoning.lower() or "without" in reasoning.lower():
        print("✓ PASS: Orchestrator noted lack of context")
    elif next_agent == "final":
        print("✓ PASS: Routed to final (appropriate without context)")
    else:
        print(f"⚠ INFO: Routed to {next_agent}")

    print("="*80)

    return True


async def main():
    """Run orchestrator context tests"""
    print("\n" + "="*80)
    print("ORCHESTRATOR CONTEXT AWARENESS TESTS")
    print("="*80)

    results = []

    # Test 1: With context
    try:
        result1 = await test_orchestrator_with_context()
        results.append(("Orchestrator with context", result1))
    except Exception as e:
        print(f"Test crashed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Orchestrator with context", False))

    await asyncio.sleep(1)

    # Test 2: Without context
    try:
        result2 = await test_orchestrator_without_context()
        results.append(("Orchestrator without context", result2))
    except Exception as e:
        print(f"Test crashed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Orchestrator without context", False))

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\nTotal: {passed}/{total} tests passed")


if __name__ == "__main__":
    asyncio.run(main())
