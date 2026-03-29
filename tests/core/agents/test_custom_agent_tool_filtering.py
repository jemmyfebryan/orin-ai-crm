"""
Test that custom_agent properly filters out tool_calls and ToolMessages
"""

import asyncio
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.custom.hana_agent.custom_agent import create_custom_agent
from src.orin_ai_crm.core.agents.config import get_llm
from src.orin_ai_crm.core.agents.tools.agent_tools import ECOMMERCE_AGENT_TOOLS
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db


async def test_custom_agent_filters_tool_messages():
    """
    Test: Custom agent filters out tool_calls and ToolMessages before sending to LLM
    This prevents OpenAI API errors about orphaned tool messages
    """
    print("\n" + "="*80)
    print("TEST: Custom Agent Tool Messages Filtering")
    print("="*80)

    # Get prompts
    system_prompt = await get_prompt_from_db("hana_ecommerce_agent")
    if not system_prompt:
        system_prompt = "You are a helpful assistant."

    from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import ECOMMERCE_REACT_PROMPT

    model = get_llm("advanced")

    agent = create_custom_agent(
        model=model,
        tools=ECOMMERCE_AGENT_TOOLS,
        system_prompt=system_prompt,
        react_prompt=ECOMMERCE_REACT_PROMPT,
        state_schema=AgentState,
        debug=True,
    )

    # Create a message with tool_calls (simulating previous agent execution)
    ai_with_tool_calls = AIMessage(
        content="Let me fetch product information for you",
        tool_calls=[{"id": "call_456", "name": "get_all_active_products", "args": {}}]
    )

    # Create ToolMessage that would normally follow the tool_calls
    tool_response = ToolMessage(
        content="Tool execution result: 9 products found",
        tool_call_id="call_456"
    )

    # Simulate conversation history with tool_calls and ToolMessage
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
    }

    print("\nMessages history includes:")
    print("  - AI message with tool_calls (should be filtered)")
    print("  - ToolMessage response (should be filtered)")
    print("  - 5 total messages")
    print("\nInvoking custom agent...")

    try:
        result = await agent.ainvoke(state, recursion_limit=10)

        print("\n" + "="*80)
        print("RESULT:")
        print("="*80)
        print(f"✓ SUCCESS: Custom agent completed without error")

        # Check final messages
        final_messages = result.get("messages", [])
        print(f"Final messages count: {len(final_messages)}")

        # Show last message
        if final_messages:
            last_msg = final_messages[-1]
            if hasattr(last_msg, 'content'):
                content_preview = last_msg.content[:100]
                print(f"Last message preview: {content_preview}...")

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
    success = await test_custom_agent_filters_tool_messages()

    if success:
        print("\n✓ Custom agent tool messages filtering is working correctly")
    else:
        print("\n✗ Custom agent tool messages filtering FAILED")


if __name__ == "__main__":
    asyncio.run(main())
