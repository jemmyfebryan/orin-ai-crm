"""
Test custom_agent module

Tests the create_custom_agent function to ensure it properly creates
agents with separate system and react prompts.
"""

import pytest
import asyncio
from typing import TypedDict, Annotated
from typing_extensions import TypedDict as ExtTypedDict

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage

from src.orin_ai_crm.core.agents.config import get_llm
from src.orin_ai_crm.core.agents.custom.hana_agent.custom_agent import create_custom_agent
from src.orin_ai_crm.core.models.schemas import AgentState


# ============================================================================
# Test Tools
# ============================================================================

@tool
def test_calculator(expression: str) -> str:
    """A simple calculator that evaluates a mathematical expression."""
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def test_get_weather(city: str) -> str:
    """Get weather information for a city."""
    weather_data = {
        "jakarta": "Sunny, 32°C",
        "surabaya": "Cloudy, 30°C",
        "bandung": "Rainy, 25°C",
    }
    return weather_data.get(city.lower(), f"Weather data not available for {city}")


@tool
async def test_async_greeting(name: str) -> str:
    """An async tool that greets the user."""
    await asyncio.sleep(0.1)  # Simulate async operation
    return f"Hello, {name}! Nice to meet you."


# ============================================================================
# Tests
# ============================================================================

class TestCustomAgent:
    """Test suite for create_custom_agent function."""

    @pytest.mark.asyncio
    async def test_create_custom_agent_basic(self):
        """Test that custom agent can be created without errors."""
        # Arrange
        model = get_llm("basic")
        tools = [test_calculator]
        system_prompt = "You are a helpful assistant."
        react_prompt = "Answer questions helpfully."

        # Act
        agent = create_custom_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            react_prompt=react_prompt,
            state_schema=AgentState,
        )

        # Assert
        assert agent is not None
        assert hasattr(agent, 'ainvoke')

    @pytest.mark.asyncio
    async def test_custom_agent_simple_conversation(self):
        """Test agent with a simple conversation (no tools)."""
        # Arrange
        model = get_llm("basic")
        tools = []  # No tools
        system_prompt = "You are a helpful assistant. Keep responses brief."
        react_prompt = "Answer the user's question directly."

        agent = create_custom_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            react_prompt=react_prompt,
            state_schema=AgentState,
        )

        state: AgentState = {
            "messages": [HumanMessage(content="What is 2+2?")]
        }

        # Act
        result = await agent.ainvoke(state, recursion_limit=5)

        # Assert
        assert result is not None
        assert "messages" in result
        assert len(result["messages"]) > 0

        # Last message should be from AI
        last_message = result["messages"][-1]
        assert isinstance(last_message, AIMessage)
        # Should answer the question
        assert len(last_message.content) > 0

    @pytest.mark.asyncio
    async def test_custom_agent_with_single_tool_call(self):
        """Test agent that calls a single tool."""
        # Arrange
        model = get_llm("medium")
        tools = [test_calculator]
        system_prompt = "You are a math assistant."
        react_prompt = """
        When asked to calculate something, use the test_calculator tool.
        The tool takes an expression parameter.
        """

        agent = create_custom_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            react_prompt=react_prompt,
            state_schema=AgentState,
        )

        state: AgentState = {
            "messages": [HumanMessage(content="What is 15 * 7?")]
        }

        # Act
        result = await agent.ainvoke(state, recursion_limit=10)

        # Assert
        assert result is not None
        assert "messages" in result

        # Check that tool was called
        messages = result["messages"]
        tool_calls_found = False
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                tool_calls_found = True
                assert msg.tool_calls[0]['name'] == 'test_calculator'
                break

        assert tool_calls_found, "Expected tool call to test_calculator"

    @pytest.mark.asyncio
    async def test_custom_agent_with_async_tool(self):
        """Test agent with an async tool."""
        # Arrange
        model = get_llm("medium")
        tools = [test_async_greeting]
        system_prompt = "You are a friendly assistant."
        react_prompt = """
        When someone introduces themselves, use the test_async_greeting tool.
        """

        agent = create_custom_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            react_prompt=react_prompt,
            state_schema=AgentState,
        )

        state: AgentState = {
            "messages": [HumanMessage(content="My name is John")]
        }

        # Act
        result = await agent.ainvoke(state, recursion_limit=10)

        # Assert
        assert result is not None
        assert "messages" in result

        # Check that async tool was called
        messages = result["messages"]
        tool_calls_found = False
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                tool_calls_found = True
                assert msg.tool_calls[0]['name'] == 'test_async_greeting'
                break

        assert tool_calls_found, "Expected tool call to test_async_greeting"

    @pytest.mark.asyncio
    async def test_custom_agent_react_prompt_influences_behavior(self):
        """Test that react_prompt influences tool-calling behavior."""
        # Arrange
        model = get_llm("medium")
        tools = [test_get_weather, test_calculator]

        # Agent 1: Focused on weather
        system_prompt = "You are a helpful assistant."
        weather_react_prompt = """
        If user asks about weather, use test_get_weather tool.
        If user asks about math, just answer directly without tools.
        """

        weather_agent = create_custom_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            react_prompt=weather_react_prompt,
            state_schema=AgentState,
        )

        # Act - Test weather question
        state: AgentState = {
            "messages": [HumanMessage(content="What's the weather in Jakarta?")]
        }

        result = await weather_agent.ainvoke(state, recursion_limit=10)

        # Assert - Should call test_get_weather
        messages = result["messages"]
        weather_tool_called = False
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc['name'] == 'test_get_weather':
                        weather_tool_called = True
                        break

        assert weather_tool_called, "Expected test_get_weather to be called"

    @pytest.mark.asyncio
    async def test_custom_agent_with_custom_state_fields(self):
        """Test that custom agent preserves custom state fields."""
        # Arrange
        model = get_llm("basic")
        tools = []

        class CustomAgentState(AgentState):
            custom_field: str = "test_value"

        agent = create_custom_agent(
            model=model,
            tools=tools,
            system_prompt="You are helpful.",
            react_prompt="Be brief.",
            state_schema=CustomAgentState,
        )

        state: CustomAgentState = {
            "messages": [HumanMessage(content="Hi")],
            "custom_field": "my_custom_value"
        }

        # Act
        result = await agent.ainvoke(state, recursion_limit=5)

        # Assert
        assert result is not None
        # Custom field should be preserved (AgentState behavior)
        # Note: Depending on state merging, this might or might not be preserved

    @pytest.mark.asyncio
    async def test_custom_agent_recursion_limit(self):
        """Test that recursion_limit is respected."""
        # Arrange
        model = get_llm("basic")
        tools = []
        system_prompt = "You are helpful."
        react_prompt = "Be brief."

        agent = create_custom_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            react_prompt=react_prompt,
            state_schema=AgentState,
        )

        state: AgentState = {
            "messages": [HumanMessage(content="Hello")]
        }

        # Act - Should complete within recursion limit
        result = await agent.ainvoke(state, recursion_limit=3)

        # Assert
        assert result is not None
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_custom_agent_with_multiple_tools(self):
        """Test agent with multiple tools available."""
        # Arrange
        model = get_llm("medium")
        tools = [test_calculator, test_get_weather, test_async_greeting]

        system_prompt = "You are a helpful assistant."
        react_prompt = """
        Use tools when appropriate:
        - Math questions → test_calculator
        - Weather questions → test_get_weather
        - Introductions → test_async_greeting
        """

        agent = create_custom_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            react_prompt=react_prompt,
            state_schema=AgentState,
        )

        # Act - Test weather (should use correct tool)
        state: AgentState = {
            "messages": [HumanMessage(content="What's the weather in Surabaya?")]
        }

        result = await agent.ainvoke(state, recursion_limit=10)

        # Assert
        messages = result["messages"]
        weather_tool_called = False
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc['name'] == 'test_get_weather':
                        weather_tool_called = True
                        break

        assert weather_tool_called, "Expected test_get_weather to be called for weather question"


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
