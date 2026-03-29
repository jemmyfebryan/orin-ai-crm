"""
Custom Agent Implementation with Separate System and React Prompts

This module provides a custom ReAct agent implementation that separates:
- system_prompt: Defines the agent's role, personality, and behavior
- react_prompt: Controls the agent's decision-making for tool selection and stopping

This gives finer control over agent behavior compared to LangChain's default create_agent().
"""

from typing import Dict, Any, Optional, Sequence, Union
from typing_extensions import TypedDict
import operator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from src.orin_ai_crm.core.logger import get_logger

logger = get_logger(__name__)


def create_custom_agent(
    model: BaseChatModel,
    tools: Sequence[Union[BaseTool, callable, dict[str, Any]]],
    system_prompt: str,
    state_schema: type,
    react_prompt: Optional[str] = None,
    debug: bool = False,
) -> Any:
    """
    Create a custom ReAct agent with separate system and react prompts.

    This implementation gives you more control over agent behavior by separating:
    - system_prompt: Agent's role, personality, and general behavior
    - react_prompt: Instructions for tool selection and when to stop the loop

    Args:
        model: The language model (e.g., ChatOpenAI instance)
        tools: List of tools the agent can use
        system_prompt: The agent's role and personality (converted to SystemMessage)
        state_schema: The state schema (e.g., AgentState TypedDict)
        react_prompt: Optional prompt for controlling react loop behavior.
                     If not provided, uses a default ReAct prompt.
        debug: Enable verbose logging

    Returns:
        A compiled StateGraph that can be invoked with:
            result = await agent.ainvoke(state, recursion_limit=10)

    Example:
        agent = create_custom_agent(
            model=ecommerce_llm,
            tools=ECOMMERCE_AGENT_TOOLS,
            system_prompt="You are a helpful assistant...",
            react_prompt="Continue calling tools until you have complete information...",
            state_schema=AgentState,
        )
        result = await agent.ainvoke(state, recursion_limit=10)
    """

    # Default react prompt if not provided
    if react_prompt is None:
        react_prompt = """You are a helpful AI assistant with access to tools.

Your task is to thoughtfully answer the user's question by:
1. Analyzing what information you need
2. Calling appropriate tools to gather that information
3. Synthesizing the results into a helpful response

Tool Calling Rules:
- Call tools when you need information you don't have
- Use the most specific tool available for the task
- Read tool outputs carefully before deciding next action
- You can call multiple tools in one response if needed

When to Stop:
- Stop calling tools when you have enough information to answer the user's question
- If no tools can help with the request, respond directly with your knowledge
- If you've called 3+ tools and still don't have a complete answer, provide your best response with what you have

Respond to the user in a friendly, helpful manner.
"""

    class CustomAgentState(state_schema):
        """Extended state for the custom agent loop."""
        pass

    def should_continue(state: CustomAgentState) -> str:
        """
        Decide whether to continue the agent loop or stop.

        This function checks if the last message has tool calls to execute.
        """
        messages = state.get("messages", [])

        if not messages:
            return "end"

        last_message = messages[-1]

        # If last message is from AI and has tool calls, continue to tools
        if isinstance(last_message, AIMessage):
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                if debug:
                    logger.info(f"Agent has tool calls: {last_message.tool_calls}")
                return "continue"
            else:
                if debug:
                    logger.info("Agent has no tool calls, ending loop")
                return "end"

        # If last message is from tool, go back to agent
        if isinstance(last_message, ToolMessage):
            if debug:
                logger.info(f"Tool result received, continuing to agent")
            return "continue"

        return "end"

    # Create tool node once (handles InjectedState properly)
    tool_node_instance = ToolNode(tools)

    async def agent_node(state: CustomAgentState, config: RunnableConfig) -> Dict:
        """
        Agent node - runs the LLM with tools bound.

        This node combines system_prompt + react_prompt for the LLM.
        """
        if debug:
            logger.info(f"ENTER: agent_node with {len(state.get('messages', []))} messages")

        messages = state.get("messages", [])
        messages_history = state.get("messages_history", [])

        # Build messages for LLM
        # Start with system prompt
        all_messages = []

        # Add system prompt (combination of system and react prompts)
        combined_system = f"{system_prompt}\n\n{react_prompt}"
        all_messages.append(SystemMessage(content=combined_system))

        # IMPORTANT: Add messages_history FIRST for conversation context
        # Then add current messages
        # This ensures LLM has context when user says "produknya" (the product)

        # CRITICAL: Filter messages_history to remove tool_calls and ToolMessages
        # These are from previous agent runs and cause OpenAI API errors:
        # "messages with role 'tool' must be a response to a preceeding message with 'tool_calls'"
        def should_include_history_message(msg):
            """Check if history message should be included (filter out tool_calls and ToolMessages)"""
            # Filter out AIMessages with tool_calls
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                return False
            # Filter out dict messages with tool_calls
            if isinstance(msg, dict) and 'tool_calls' in msg and msg['tool_calls']:
                return False
            # Filter out ToolMessages (they're responses to already-executed tool calls)
            if isinstance(msg, ToolMessage):
                return False
            # Filter out dict messages with role='tool'
            if isinstance(msg, dict) and msg.get('role') == 'tool':
                return False
            return True

        # Add messages_history (filtering out tool_calls and ToolMessages)
        for msg in messages_history:
            if not isinstance(msg, SystemMessage) and should_include_history_message(msg):
                all_messages.append(msg)

        # Add current messages WITHOUT filtering
        # These are part of the current agent loop and include ToolMessages that the agent needs to see
        for msg in messages:
            if not isinstance(msg, SystemMessage):
                all_messages.append(msg)

        if debug:
            logger.info(f"Calling LLM with {len(all_messages)} messages")
            logger.info(f"System prompt length: {len(combined_system)} chars")

        # Bind tools to model and invoke
        try:
            # Bind tools to model
            if tools:
                model_with_tools = model.bind_tools(tools)
            else:
                model_with_tools = model

            response = await model_with_tools.ainvoke(all_messages, config)

            if debug:
                logger.info(f"LLM response type: {type(response).__name__}")
                if hasattr(response, 'tool_calls'):
                    logger.info(f"Tool calls: {response.tool_calls}")

            return {"messages": [response]}

        except Exception as e:
            logger.error(f"Error in agent_node: {e}", exc_info=True)
            # Return error message
            error_msg = AIMessage(content=f"I encountered an error: {str(e)}")
            return {"messages": [error_msg]}

    async def tool_node(state: CustomAgentState, config: RunnableConfig) -> Dict:
        """
        Tool node - executes tool calls from the last AI message.

        Uses LangChain's built-in ToolNode which properly handles InjectedState.
        """
        if debug:
            logger.info("ENTER: tool_node")
            messages = state.get("messages", [])
            if messages:
                last_message = messages[-1]
                if isinstance(last_message, AIMessage) and hasattr(last_message, 'tool_calls'):
                    logger.info(f"Executing {len(last_message.tool_calls)} tool calls")

        # Use the pre-created ToolNode instance which handles InjectedState correctly
        result = await tool_node_instance.ainvoke(state, config)

        # ToolNode returns a dict with messages
        return result

    # Build the agent graph
    workflow = StateGraph(CustomAgentState)

    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    # Set entry point
    workflow.set_entry_point("agent")

    # Add conditional edges from agent
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "tools",
            "end": END,
        }
    )

    # Edge from tools back to agent
    workflow.add_edge("tools", "agent")

    # Compile the graph
    agent = workflow.compile()

    logger.info("Custom agent created with separate system and react prompts")
    logger.info(f"Tools: {len(tools)}, System prompt: {len(system_prompt)} chars")

    return agent
