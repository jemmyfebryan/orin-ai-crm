from typing import Callable, Dict, Any, Optional

from pydantic import BaseModel

from langchain.messages import SystemMessage, ToolMessage

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

def create_tool_node(tools_by_name: Dict[str, Any]) -> Callable:
    """
    Returns a tool_node callable that performs tool execution using the
    provided tools_by_name registry.
    """

    def tool_node(state: Dict[str, Any]):
        """Performs the tool call"""
        result = []

        # Get the tool calls from the last message
        last = state["messages"][-1]
        for tool_call in last.tool_calls:
            tool = tools_by_name[tool_call["name"]]
            observation = tool.invoke(tool_call["args"])
            result.append(
                ToolMessage(
                    content=observation,
                    tool_call_id=tool_call["id"],
                )
            )

        return {"messages": result}

    return tool_node