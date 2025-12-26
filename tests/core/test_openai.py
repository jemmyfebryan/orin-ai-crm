import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from openai import AsyncOpenAI
from src.orin_ai_crm.core.openai import create_client, chat_completion

# --- Fixtures ---

@pytest.fixture
def mock_openai_client():
    """Provides a mocked AsyncOpenAI client."""
    client = MagicMock(spec=AsyncOpenAI)
    # Mock the nested path: client.chat.completions.create
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock()
    return client

def create_mock_response(content: str):
    """Helper to create a mock OpenAI completion response object."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response

# --- Tests ---

def test_create_client():
    """Verify client creation and API key loading."""
    with patch("os.getenv", return_value="fake-api-key"):
        client = create_client()
        assert isinstance(client, AsyncOpenAI)
        assert client.api_key == "fake-api-key"

@pytest.mark.asyncio
async def test_chat_completion_string_input(mock_openai_client):
    """Test basic completion with a string prompt and no system prompt."""
    expected_text = "Hello! I am an AI."
    mock_openai_client.chat.completions.create.return_value = create_mock_response(expected_text)

    result = await chat_completion(
        openai_client=mock_openai_client,
        user_prompt="Hi there",
        model_name="gpt-4.1-nano"
    )

    assert result == expected_text
    # Verify the message structure sent to OpenAI
    args, kwargs = mock_openai_client.chat.completions.create.call_args
    assert kwargs["messages"] == [{"role": "user", "content": "Hi there"}]
    assert kwargs["model"] == "gpt-4.1-nano"

@pytest.mark.asyncio
async def test_chat_completion_with_system_prompt(mock_openai_client):
    """Test message construction when a system prompt is provided."""
    mock_openai_client.chat.completions.create.return_value = create_mock_response("Response")

    await chat_completion(
        openai_client=mock_openai_client,
        user_prompt="User msg",
        system_prompt="You are a helpful assistant"
    )

    args, kwargs = mock_openai_client.chat.completions.create.call_args
    assert kwargs["messages"] == [
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "User msg"}
    ]

@pytest.mark.asyncio
async def test_chat_completion_json_schema(mock_openai_client):
    """Test structured output (JSON schema) parsing."""
    schema = {"name": "test_schema"}
    fake_json_response = json.dumps({"status": "success", "id": 1})
    
    mock_openai_client.chat.completions.create.return_value = create_mock_response(fake_json_response)

    result = await chat_completion(
        openai_client=mock_openai_client,
        user_prompt="Get status",
        formatted_schema=schema
    )

    assert isinstance(result, dict)
    assert result["status"] == "success"
    
    # Verify response_format was passed correctly
    args, kwargs = mock_openai_client.chat.completions.create.call_args
    assert kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": schema
    }

@pytest.mark.asyncio
async def test_chat_completion_list_input(mock_openai_client):
    """Test passing a full list of messages directly."""
    custom_messages = [
        {"role": "user", "content": "Message 1"},
        {"role": "assistant", "content": "Reply 1"},
        {"role": "user", "content": "Message 2"},
    ]
    mock_openai_client.chat.completions.create.return_value = create_mock_response("Final reply")

    await chat_completion(
        openai_client=mock_openai_client,
        user_prompt=custom_messages
    )

    args, kwargs = mock_openai_client.chat.completions.create.call_args
    assert kwargs["messages"] == custom_messages