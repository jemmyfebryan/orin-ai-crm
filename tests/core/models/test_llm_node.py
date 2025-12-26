import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.orin_ai_crm.core.models.llm_node import LLMNode, LLMIfNode

# LLM-based Node
def test_llm_node_initialization():
    """Verify that the node initializes with correct attributes."""
    mock_client = MagicMock()
    node = LLMNode(
        name="InitTest",
        llm_client=mock_client,
        system_prompt="Test Prompt",
        user_prompt="Test User Prompt",
        model_name="custom-model",
        use_temperature=True
    )
    
    assert node.name == "InitTest"
    assert node.model_name == "custom-model"
    assert node.system_prompt == "Test Prompt"
    assert node.user_prompt == "Test User Prompt"
    assert node.use_temperature is True
    assert node.async_node is True

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
    with patch("src.orin_ai_crm.core.models.llm_node.chat_completion", new_callable=AsyncMock) as mock_chat:
        # Define the mocked return value (structured output)
        mock_chat.return_value = {"logic_result": True}
        
        # 3. Execute
        input_data = {"message": "I want to buy a car"}
        result = await node.execute(input_data)
        
        # 4. Assertions
        assert result.get("data") is True
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

    with patch("src.orin_ai_crm.core.models.llm_node.chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {"logic_result": False}
        
        result = await node.execute({"message": "I am very happy"})
        
        assert result.get("data") is False

@pytest.mark.asyncio
async def test_llm_if_node_handles_none_result():
    """Test behavior if the LLM response is malformed or missing the key."""
    mock_client = MagicMock()
    node = LLMIfNode("ErrorCheck", mock_client, "Prompt")

    with patch("src.orin_ai_crm.core.models.llm_node.chat_completion", new_callable=AsyncMock) as mock_chat:
        # Mocking an empty dict to test .get("logic_result") logic
        mock_chat.return_value = {}
        
        result = await node.execute({"data": "test"})
        
        # .get() on empty dict returns None
        assert result.get("data") is None

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