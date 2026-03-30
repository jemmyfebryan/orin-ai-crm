"""
Test that messages are not duplicated when passed through the graph
"""

import asyncio
from langchain_core.messages import HumanMessage

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import hana_agent


async def test_no_message_duplication():
    """Test that messages don't get duplicated through agent_entry_handler and orchestrator"""
    print("\n" + "="*80)
    print("TEST: No Message Duplication")
    print("="*80)

    state: AgentState = {
        "messages": [HumanMessage(content='hello')],
        "messages_history": [],
        "phone_number": "123123125",
        "lid_number": None,
        "contact_name": "test_user",
        "customer_id": None,
        "route": "DEFAULT",
        "customer_data": {},
        "send_form": False,
        "form_data": {},
        "step": "start",
        "send_images": [],
        "send_pdfs": [],
        "orchestrator_step": 0,
        "max_orchestrator_steps": 5,
        "agents_called": [],
        "orchestrator_plan": "",
        "orchestrator_decision": {},
        "human_takeover": False,
        "session_ending_detected": False,
    }

    print(f"\nInitial state:")
    print(f"  messages count: {len(state['messages'])}")
    print(f"  messages[0]: {state['messages'][0].content}")

    # Run just agent_entry_handler -> orchestrator (stop before routing)
    from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import agent_entry_handler, orchestrator_node

    # Step 1: agent_entry_handler
    state_after_entry = await agent_entry_handler(state)
    messages_after_entry = state_after_entry.get('messages', [])
    print(f"\nAfter agent_entry_handler:")
    print(f"  messages count: {len(messages_after_entry)}")
    for i, msg in enumerate(messages_after_entry):
        print(f"  messages[{i}]: {msg.content}")

    # Step 2: orchestrator receives the state
    # Note: orchestrator expects the full state including messages from entry handler
    full_state = {**state, **state_after_entry}
    messages_before_orchestrator = full_state.get('messages', [])
    print(f"\nState passed to orchestrator:")
    print(f"  messages count: {len(messages_before_orchestrator)}")
    for i, msg in enumerate(messages_before_orchestrator):
        print(f"  messages[{i}]: {msg.content}")

    # Check for duplication
    original_count = len(state['messages'])
    if len(messages_before_orchestrator) == original_count:
        print(f"\n✓ SUCCESS: No duplication! ({len(messages_before_orchestrator)} == {original_count})")
        return True
    else:
        print(f"\n✗ FAILED: Duplication detected! ({len(messages_before_orchestrator)} != {original_count})")
        return False


async def main():
    success = await test_no_message_duplication()

    if success:
        print("\n✓ No message duplication - fix is working!")
    else:
        print("\n✗ Message duplication still occurring")


if __name__ == "__main__":
    asyncio.run(main())
