from typing import Callable, Dict, Any, Optional, List

from pydantic import BaseModel
from langchain.messages import SystemMessage, ToolMessage

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
    """
    A configuration-driven router for LangGraph.
    It evaluates a list of rules against the current state and returns 
    the name of the next node to execute.
    """
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

# class ConditionalNode(Node):
#     """
#         ConditionalNode is used as a substitute of conditional_edges in LangGraph
#         While conditional_edges using separate function to check the state,
#         ConditionalNode do the same but with strict, Dictionary args
        
#         Supported condition:
#         state: Checking whether a state has to do with something, multiple output nodes
        
#         For example we check whether the user message positive, negative, neutral will decide the node output, with extra condition from state "force_sentiment":
#         **args = {
#             "conditions": [
#                 {
#                     "condition": "state",
#                     "state_name": "messages",
#                     "tools": [
#                         {
#                             "tool": "llm_tool",
#                             "args": {
#                                 "system_prompt": "If the message from user is positive sentiment return 'positive_node', if the message is negative sentiment return 'negative_node', if the message is neutral sentiment return 'neutral_node'."
#                             }
#                         }
#                     ]
#                 },
#                 {
#                     "condition": "state",
#                     "state_name": "force_sentiment",
#                     "tools": [
#                         {
#                             "tool": "is_equal",
#                             "args": {
#                                 "a": "state",
#                                 "b": "positive"
#                             },
#                             "output_node": "positive"
#                         },
#                         {
#                             "tool": "is_equal",
#                             "args": {
#                                 "a": "state",
#                                 "b": "negative"
#                             },
#                             "output_node": "negative"
#                         },
#                         {
#                             "tool": "is_equal",
#                             "args": {
#                                 "a": "state",
#                                 "b": "neutral"
#                             },
#                             "output_node": "neutral"
#                         }
#                     ]
#                 }
#             ],
#             "operator": "and"
#         }
#     """

# def create_tool_node(tools_by_name: Dict[str, Any]) -> Callable:
#     """
#     Returns a tool_node callable that performs tool execution using the
#     provided tools_by_name registry.
#     """

#     def tool_node(state: Dict[str, Any]):
#         """Performs the tool call"""
#         result = []

#         # Get the tool calls from the last message
#         last = state["messages"][-1]
#         for tool_call in last.tool_calls:
#             tool = tools_by_name[tool_call["name"]]
#             observation = tool.invoke(tool_call["args"])
#             result.append(
#                 ToolMessage(
#                     content=observation,
#                     tool_call_id=tool_call["id"],
#                 )
#             )

#         return {"messages": result}

#     return tool_node