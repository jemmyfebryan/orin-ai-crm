import pytest
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from src.orin_ai_crm.core.agents.nodes import LLMNode #, create_tool_node

# --- LLMNode Tests ---

def test_llm_node_basic_invocation():
    """Verify LLMNode correctly prepends system prompt and updates state."""
    # Mock LLM
    mock_llm = MagicMock()
    mock_response = AIMessage(content="Hello! I am ORIN AI.")
    mock_llm.invoke.return_value = mock_response

    node = LLMNode(
        llm=mock_llm,
        system_prompt="You are a helpful CRM assistant.",
        message_key="messages",
        llm_calls_key="llm_calls"
    )

    initial_state = {
        "messages": [HumanMessage(content="Hi")],
        "llm_calls": 0
    }

    output = node(initial_state)

    # Check state updates
    assert output["messages"] == [mock_response]
    assert output["llm_calls"] == 1

    # Verify messages sent to LLM: [SystemMessage, HumanMessage]
    args, _ = mock_llm.invoke.call_args
    sent_messages = args[0]
    assert isinstance(sent_messages[0], SystemMessage)
    assert sent_messages[0].content == "You are a helpful CRM assistant."
    assert sent_messages[1].content == "Hi"

def test_llm_node_extra_state_update():
    """Verify the extra_state_update hook is called and merges results."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="Processing...")

    # Hook that sets a flag based on LLM output
    def my_hook(combined_state):
        return {"hook_triggered": True}

    node = LLMNode(
        llm=mock_llm,
        system_prompt="Prompt",
        extra_state_update=my_hook
    )

    state = {"messages": [], "llm_calls": 0}
    output = node(state)

    assert output["hook_triggered"] is True
    assert output["llm_calls"] == 1

# # --- ToolNode Tests ---

# def test_create_tool_node_execution():
#     """Verify tool_node retrieves the correct tool and returns a ToolMessage."""
#     # Mock a tool
#     mock_tool = MagicMock()
#     mock_tool.invoke.return_value = "Success: Profile Updated"
    
#     tools_registry = {"update_profile": mock_tool}
#     tool_node = create_tool_node(tools_registry)

#     # State must have an AIMessage with tool_calls as the last message
#     tool_call_id = "call_123"
#     last_message = AIMessage(
#         content="",
#         tool_calls=[{
#             "name": "update_profile",
#             "args": {"phone": "+62812"},
#             "id": tool_call_id
#         }]
#     )
    
#     state = {"messages": [last_message]}
    
#     output = tool_node(state)

#     # Check if tool was called with right args
#     mock_tool.invoke.assert_called_once_with({"phone": "+62812"})

#     # Check if ToolMessage is returned in state
#     assert len(output["messages"]) == 1
#     assert isinstance(output["messages"][0], ToolMessage)
#     assert output["messages"][0].content == "Success: Profile Updated"
#     assert output["messages"][0].tool_call_id == tool_call_id

# def test_tool_node_missing_tool():
#     """Ensure tool_node raises a KeyError if tool is not in registry."""
#     tools_registry = {} # Empty
#     tool_node = create_tool_node(tools_registry)
    
#     last_message = AIMessage(
#         content="",
#         tool_calls=[{"name": "unknown_tool", "args": {}, "id": "1"}]
#     )
    
#     with pytest.raises(KeyError):
#         tool_node({"messages": [last_message]})