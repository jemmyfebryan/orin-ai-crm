import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.orin_ai_crm.core.models.logic_node import IfNode, LLMIfNode

def test_if_node_equal():
    """Test the 'equal' operator."""
    node = IfNode(
        name="CheckStatus", 
        condition_key="status", 
        expected_value="active", 
        operator="equal"
    )
    
    # Positive case
    assert node.execute({"status": "active"}) == "true"
    # Negative case
    assert node.execute({"status": "inactive"}) == "false"
    # Missing key case
    assert node.execute({"other": "data"}) == "false"

def test_if_node_exists():
    """Test the 'exists' operator."""
    node = IfNode(
        name="CheckUser", 
        condition_key="user_id", 
        expected_value=None,  # Value doesn't matter for 'exists'
        operator="exists"
    )
    
    assert node.execute({"user_id": 123}) == "true"
    assert node.execute({"user_id": None}) == "false"
    assert node.execute({"other": "data"}) == "false"

def test_if_node_less_than():
    """Test the 'less_than' operator."""
    node = IfNode(
        name="CheckAge", 
        condition_key="age", 
        expected_value=18, 
        operator="less_than"
    )
    
    assert node.execute({"age": 17}) == "true"
    assert node.execute({"age": 18}) == "false"
    assert node.execute({"age": 21}) == "false"

def test_if_node_greater_than():
    """Test the 'greater_than' operator."""
    node = IfNode(
        name="CheckStock", 
        condition_key="count", 
        expected_value=0, 
        operator="greater_than"
    )
    
    assert node.execute({"count": 5}) == "true"
    assert node.execute({"count": 0}) == "false"
    assert node.execute({"count": -1}) == "false"

def test_if_node_invalid_operator():
    """Test that an unsupported operator returns 'false'."""
    node = IfNode(
        name="InvalidOp", 
        condition_key="key", 
        expected_value=1, 
        operator="not_a_real_operator"
    )
    
    assert node.execute({"key": 1}) == "false"

def test_if_node_missing_input_data():
    """Test behavior when input_data is empty."""
    node = IfNode("EmptyTest", "any_key", "any_val")
    # Should not crash, just return false because key isn't found
    assert node.execute({}) == "false"
    
# LLM-based Node
@pytest.mark.asyncio
async def test_llm_if_node_true_branch():
    """Test LLMIfNode when the LLM returns a True result."""
    # 1. Setup Mocks
    mock_client = MagicMock() # OpenAI client
    system_prompt = "Determine if the user is interested in buying."
    
    node = LLMIfNode(
        name="InterestCheck",
        llm_client=mock_client,
        system_prompt=system_prompt,
        model_name="gpt-5-nano"
    )

    # 2. Mock the chat_completion utility function
    # Note: Replace 'path.to.chat_completion' with the actual import path used in your node file
    with patch("src.orin_ai_crm.core.models.logic_node.chat_completion", new_callable=AsyncMock) as mock_chat:
        # Define the mocked return value (structured output)
        mock_chat.return_value = {"logic_result": True}
        
        # 3. Execute
        input_data = {"message": "I want to buy a car"}
        result = await node.execute(input_data)
        
        # 4. Assertions
        assert result is True
        mock_chat.assert_called_once()
        # Verify the user prompt format matches your class implementation
        args, kwargs = mock_chat.call_args
        assert kwargs["user_prompt"] == f"input_data:\n{str(input_data)}"
        assert kwargs["system_prompt"] == system_prompt

@pytest.mark.asyncio
async def test_llm_if_node_false_branch():
    """Test LLMIfNode when the LLM returns a False result."""
    mock_client = MagicMock()
    node = LLMIfNode("NegativeCheck", mock_client, "Check for anger.")

    with patch("src.orin_ai_crm.core.models.logic_node.chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {"logic_result": False}
        
        result = await node.execute({"message": "I am very happy"})
        
        assert result is False

@pytest.mark.asyncio
async def test_llm_if_node_handles_none_result():
    """Test behavior if the LLM response is malformed or missing the key."""
    mock_client = MagicMock()
    node = LLMIfNode("ErrorCheck", mock_client, "Prompt")

    with patch("src.orin_ai_crm.core.models.logic_node.chat_completion", new_callable=AsyncMock) as mock_chat:
        # Mocking an empty dict to test .get("logic_result") logic
        mock_chat.return_value = {}
        
        result = await node.execute({"data": "test"})
        
        # .get() on empty dict returns None
        assert result is None

def test_llm_if_node_initialization():
    """Verify that the node initializes with correct attributes."""
    mock_client = MagicMock()
    node = LLMIfNode(
        name="InitTest",
        llm_client=mock_client,
        system_prompt="Test Prompt",
        model_name="custom-model",
        use_temperature=True
    )
    
    assert node.name == "InitTest"
    assert node.model_name == "custom-model"
    assert node.use_temperature is True
    assert node.async_node is True