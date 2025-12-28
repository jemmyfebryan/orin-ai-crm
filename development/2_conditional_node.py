from typing import Optional, Annotated, List, TypedDict

import operator
from langchain.messages import HumanMessage, AnyMessage

from src.orin_ai_crm.core.alpha_flow import FlowBuilder
from src.orin_ai_crm.core.models.states import CRMState

flow_dict = {
    "flow_id": "crm_alpha_1",
    "nodes": [
        {
            "name": "start",
            "node": "start",
            "to": ["classifier_node"]
        },
        {
            "name": "classifier_node",
            "node": "conditional_node",
            "args": {
                "rules": [
                    {
                        "state_path": "sentiment",
                        "condition": "is_equal",
                        "expected": "positive",
                        "output_node": "positive_node"
                    },
                    {
                        "state_path": "sentiment",
                        "condition": "is_equal",
                        "expected": "negative",
                        "output_node": "negative_node"
                    }
                ],
                "default_node": "neutral_node"
            },
            "to": ["positive_node", "negative_node", "neutral_node"]
        },
        {
            "name": "positive_node",
            "node": "llm_node",
            "args": {"system_prompt": "Response user message with positive sentiment"},
            "to": ["end"]
        },
        {
            "name": "negative_node",
            "node": "llm_node",
            "args": {"system_prompt": "Response user message with negative sentiment"},
            "to": ["end"]
        },
        {
            "name": "neutral_node",
            "node": "llm_node",
            "args": {"system_prompt": "Response user message"},
            "to": ["end"]
        },
    ]
}

class State(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    sentiment: str
    

builder = FlowBuilder(flow_dict)
builder.state_class = CRMState
agent = builder.build()

input_state = {
    "messages": [HumanMessage(content=
        "Hello bro"
    )],
    "sentiment": "positive"
}

for chunk in agent.stream(input_state):
    for node, values in chunk.items():
        print(f"Update from node: {node}")
        for msg in values.get("messages", []):
            msg.pretty_print()