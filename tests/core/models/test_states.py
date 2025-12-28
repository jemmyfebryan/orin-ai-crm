import pytest
import operator
from langchain_core.messages import HumanMessage, AIMessage
from src.orin_ai_crm.core.models.states import CRMState, WAState

def test_wa_state_structure():
    """
    Test that WAState can be instantiated with expected keys.
    Note: TypedDict is for type checking, but we verify dict behavior here.
    """
    state: WAState = {
        "move_to_human_agent": True,
        "send_contact": ["+628123456789"],
        "send_sticker": ["sticker_id_123"],
        "messages_to_send": ["Hello from ORIN CRM"]
    }
    
    assert state["move_to_human_agent"] is True
    assert len(state["send_contact"]) == 1
    assert state["messages_to_send"][0] == "Hello from ORIN CRM"

def test_crm_state_reducer_logic():
    """
    Verifies that the Annotated messages list works with operator.add,
    which is the standard reducer for LangGraph states.
    """
    # Initial messages
    messages_initial = [HumanMessage(content="Halo ORIN")]
    
    # New messages to be added
    messages_new = [AIMessage(content="Ada yang bisa saya bantu?")]
    
    # Simulate LangGraph's state update behavior using the operator
    updated_messages = operator.add(messages_initial, messages_new)
    
    assert len(updated_messages) == 2
    assert isinstance(updated_messages[0], HumanMessage)
    assert isinstance(updated_messages[1], AIMessage)
    assert updated_messages[1].content == "Ada yang bisa saya bantu?"

def test_crm_state_initialization():
    """
    Verifies CRMState structure and Optional fields.
    """
    state: CRMState = {
        "messages": [HumanMessage(content="Test")],
        "customer_profile": None,
        "wa_state": {
            "move_to_human_agent": False,
            "send_contact": [],
            "send_sticker": [],
            "messages_to_send": []
        },
        "llm_calls": 1
    }
    
    assert len(state["messages"]) == 1
    assert state["llm_calls"] == 1
    assert state["wa_state"]["move_to_human_agent"] is False

@pytest.mark.parametrize("input_val, expected_count", [
    ([HumanMessage(content="1")], 1),
    ([HumanMessage(content="1"), AIMessage(content="2")], 2),
])
def test_message_list_length(input_val, expected_count):
    """Parametrized test to ensure message counting is accurate."""
    state: CRMState = {
        "messages": input_val,
        "customer_profile": {},
        "wa_state": {},
        "llm_calls": 0
    }
    assert len(state["messages"]) == expected_count