from typing import Callable, Dict, Any, Optional, List

from pydantic import BaseModel
from langchain.messages import SystemMessage, ToolMessage
from langchain.agents import create_agent
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession

from src.orin_ai_crm.core.agents.nodes.conditional import EVALUATORS, resolve_state_path


class Node:
    pass

class LLMNode(Node):
    def __init__(
        self,
        llm: Any,
        system_prompt: str,
        message_key: str = "messages",
        llm_calls_key: str = "llm_calls",
        extra_state_update: Optional[Callable[[Dict], Dict]] = None,
    ):
        """
        llm:            LLM or ChatModel instance (raw or with_tools)
        system_prompt:  The system instruction
        message_key:    Where conversation messages live in the state
        llm_calls_key:  Where to count LLM calls
        extra_state_update:
                        Optional function that accepts the node output
                        and returns extra state updates
        """
        self.llm = llm
        self.system_prompt = system_prompt
        self.message_key = message_key
        self.llm_calls_key = llm_calls_key
        self.extra_state_update = extra_state_update

    def __call__(self, state: Dict[str, Any], config=None) -> Dict[str, Any]:
        """LangGraph node handler"""

        messages = [
            SystemMessage(content=self.system_prompt)
        ] + state[self.message_key]

        llm_output = self.llm.invoke(messages)

        new_state = {
            self.message_key: [llm_output],
            self.llm_calls_key: state.get(self.llm_calls_key, 0) + 1,
        }

        # Optional extension hook
        if self.extra_state_update:
            new_state.update(self.extra_state_update(state | new_state))

        return new_state


class ConditionalNode:
    """A configuration-driven router for LangGraph."""
    def __init__(
        self,
        rules: List[Dict[str, Any]],
        operator: str = "or",  # 'or' returns first match, 'and' requires all
        default_node: str = "__end__"
    ):
        self.rules = rules
        self.operator = operator.lower()
        self.default_node = default_node

    def _evaluate_rule(self, rule: Dict, state: Dict) -> bool:
        """Evaluates a single rule dictionary against the state."""
        # 1. Get the value from the state
        state_path = rule.get("state_path")
        actual_value = resolve_state_path(state, state_path)

        # 2. Check the condition (e.g., 'is_equal')
        condition = rule.get("condition")
        expected_value = rule.get("expected")
        
        evaluator = EVALUATORS.get(condition)
        if not evaluator:
            raise ValueError(f"Unknown condition evaluator: {condition}")

        return evaluator(actual_value, expected_value)

    def __call__(self, state: Dict[str, Any]) -> str:
        """LangGraph routing interface."""
        matches = []

        for rule in self.rules:
            is_match = self._evaluate_rule(rule, state)
            target = rule.get("output_node")

            if is_match:
                if self.operator == "or":
                    return target  # Immediate exit on first match
                matches.append(target)
            elif self.operator == "and":
                # If any rule fails in an 'AND' logic, the whole node fails
                return self.default_node

        # If we reached here with 'AND' logic, return the last matching target
        return matches[-1] if matches else self.default_node

class MCPNode(Node):
    def __init__(
        self,
        llm: Any,
        mcp_client: ClientSession, # The MCP session/client
        system_prompt: str = "You are a helpful assistant.",
        message_key: str = "messages",
        recursion_limit: int = 3,
    ):
        self.llm = llm
        self.mcp_client = mcp_client
        self.system_prompt = system_prompt
        self.message_key = message_key
        self.recursion_limit = recursion_limit
        # self.llm = ChatOpenAI(model=model_name, temperature=0)

    async def __call__(self, state: Dict[str, Any], config=None) -> Dict[str, Any]:
        # 1. Dynamically fetch tools from the MCP server
        # This makes the node "live"—if the MCP server adds a tool, the agent gets it
        await self.mcp_client.initialize()
        tools = await load_mcp_tools(self.mcp_client)
        
        # 2. Create a temporary ReAct agent
        # We use create_react_agent from langgraph.prebuilt
        agent = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=(
                self.system_prompt
            )
        )

        # 3. Invoke the agent with the current state
        result = await agent.ainvoke(state, config={
            "recursion_limit": self.recursion_limit
        })

        # 4. Return the updated messages
        # LangGraph ReAct agents return the full message history
        return {
            self.message_key: result["messages"]
        }