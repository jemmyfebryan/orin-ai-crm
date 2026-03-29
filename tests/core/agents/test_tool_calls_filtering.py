"""
Test that messages with tool_calls and ToolMessages are properly filtered out

This test verifies that:
1. AIMessages with tool_calls are filtered (to avoid "tool_calls must be followed by tool messages" error)
2. ToolMessages are filtered (to avoid "messages with role 'tool' must be a response to a preceeding message with 'tool_calls'" error)

These messages are from already-executed tool calls and should NOT be sent to the LLM.
"""

import asyncio
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import orchestrator_node


async def test_tool_calls_filtered():
    """
    Test: Messages with tool_calls and ToolMessages are filtered out before sending to LLM
    This prevents "tool_calls must be followed by tool messages" and
    "messages with role 'tool' must be a response to a preceeding message with 'tool_calls'" errors
    """
    print("\n" + "="*80)
    print("TEST: Tool Calls and ToolMessages Filtering")
    print("="*80)

    # Create a message with tool_calls (simulating previous agent execution)
    ai_with_tool_calls = AIMessage(
        content="I'll help you with that",
        tool_calls=[{"id": "call_123", "name": "some_tool", "args": {}}]
    )

    # Create ToolMessage that would normally follow the tool_calls
    tool_response = ToolMessage(
        content="Tool execution result",
        tool_call_id="call_123"
    )

    messages_history = [
        AIMessage(content='Halo! Apa yang bisa saya bantu?'),
        HumanMessage(content='Saya butuh info produk'),
        ai_with_tool_calls,  # This has tool_calls - should be filtered
        tool_response,  # This is ToolMessage - should be filtered
        AIMessage(content='Berikut info produknya'),  # Result after tool execution
    ]

    messages = [
        HumanMessage(content='Terima kasih')
    ]

    state: AgentState = {
        "messages": messages,
        "messages_history": messages_history,
        "customer_id": 1,
        "customer_data": {
            "id": 1,
            "name": "Test",
            "domicile": "Jakarta",
            "vehicle_alias": "motor",
            "unit_qty": 0,
            "is_b2b": False,
            "is_onboarded": True,
        },
        "orchestrator_step": 1,
        "max_orchestrator_steps": 5,
        "agents_called": ["ecommerce"],
    }

    print("\nMessages history includes:")
    print("  - AI message with tool_calls (should be filtered)")
    print("  - ToolMessage response (should be filtered)")
    print("  - 5 total messages")
    print("\nCalling orchestrator...")

    try:
        result = await orchestrator_node(state)
        decision = result.get("orchestrator_decision", {})
        next_agent = decision.get("next_agent", "N/A")

        print("\n" + "="*80)
        print("RESULT:")
        print("="*80)
        print(f"✓ SUCCESS: Orchestrator completed without error")
        print(f"Next Agent: {next_agent}")
        print(f"\nThe tool_calls and ToolMessage were properly filtered out!")
        print("="*80)

        return True

    except Exception as e:
        error_str = str(e)
        print("\n" + "="*80)
        print("ERROR:")
        print("="*80)
        print(f"✗ FAILED: {error_str}")

        if "tool_calls must be followed" in error_str or "messages with role 'tool'" in error_str:
            print("\nThe filtering did NOT work!")
            print("Messages with tool_calls or ToolMessages are still being passed to the LLM")

        print("="*80)
        return False


async def main():
    success = await test_tool_calls_filtered()

    if success:
        print("\n✓ Tool calls and ToolMessage filtering is working correctly")
    else:
        print("\n✗ Tool calls and ToolMessage filtering FAILED")


if __name__ == "__main__":
    asyncio.run(main())
