from langchain.messages import HumanMessage

from src.orin_ai_crm.core.alpha_flow import FlowBuilder

flow_dict = {
    "flow_id": "crm_alpha_1",
    "state_schema": "crm_state",
    "nodes": [
        {
            "name": "start",
            "node": "start",
            "to": ["classifier_node"]
        },
        {
            "name": "classifier_node",
            "node": "llm_node",
            "args": {"system_prompt": "Always answer user with humour"},
            "to": ["end"]
        }
    ]
}

builder = FlowBuilder(flow_dict)
agent = builder.build()

input_state = {
    "messages": [HumanMessage(content=
        "Hello bro"
    )]
}

for chunk in agent.stream(input_state):
    for node, values in chunk.items():
        print(f"Update from node: {node}")
        for msg in values.get("messages", []):
            msg.pretty_print()