import asyncio

from src.orin_ai_crm.core.openai import create_client
from src.orin_ai_crm.core.models import PassNode, Agent
from src.orin_ai_crm.core.models.logic_node import LLMIfNode

openai_client = create_client()

# 1. Initialize Nodes
start = PassNode(name="Start")
llm_if_node = LLMIfNode(
    name="LLMNode",
    llm_client=openai_client,
    system_prompt="Is the input sentiment positive?",
    model_name="gpt-4.1-nano",
    use_temperature=True
)
end = PassNode(name="End")

# 2. Setup Workflow
agent_1 = Agent()
agent_1.add_node(start)
agent_1.add_node(llm_if_node)
agent_1.add_node(end)

# 3. Define Connections (Edges)
agent_1.add_edge("Start", "LLMNode")
agent_1.add_edge("LLMNode", "End")

# 4. Run
if __name__ == "__main__":
    initial_data = {"data": "Hi man, have a great day"}
    print(asyncio.run(agent_1.run("Start", initial_data, is_return=True)))

    initial_data = {"data": "Hi girl you are so dumb"}
    print(asyncio.run(agent_1.run("Start", initial_data, is_return=True)))

    initial_data = {"data": "Hi"}
    print(asyncio.run(agent_1.run("Start", initial_data, is_return=True)))