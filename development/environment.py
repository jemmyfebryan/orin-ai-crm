import asyncio

from src.orin_ai_crm.core.openai import create_client
from src.orin_ai_crm.core.models import (
    AgentEnvironment,
    Agent,
    PassNode,
    LogNode,
    GetEnvironmentVarNode,
)
from src.orin_ai_crm.core.models.logic_node import (
    IfNode,
    LLMIfNode,
)

my_env = AgentEnvironment(env_vars={
    "DEBUG": "true",
    "OPENAI_MODEL_NAME": "gpt-4.1-nano",
})
my_env.set_client("llm_client", create_client())

# 1. Initialize Nodes
start = PassNode(name="Start")
get_debug = GetEnvironmentVarNode(name="GetDebug", key="DEBUG", env=my_env)
log_if_debug = IfNode("LogIfDebug", condition_key="DEBUG", expected_value="true")
debug_log = LogNode(name="DebugLog", message="Using debug!", log_type="info", pass_data=True)
llm_if_node = LLMIfNode(
    name="LLMNode",
    llm_client=my_env.clients.get("llm_client"),
    system_prompt="Is the input sentiment positive?",
    model_name=my_env.get_variable("OPENAI_MODEL_NAME"),
    use_temperature=True
)
end = PassNode(name="End")

# 2. Setup Workflow
agent_1 = Agent()
agent_1.add_node(start)
agent_1.add_node(get_debug)
agent_1.add_node(log_if_debug)
agent_1.add_node(debug_log)
agent_1.add_node(llm_if_node)
agent_1.add_node(end)

# 3. Define Connections (Edges)
agent_1.add_edge("Start", "GetDebug")

agent_1.add_edge("GetDebug", "LogIfDebug")
agent_1.add_edge("LogIfDebug", "DebugLog", branch="true")
agent_1.add_edge("DebugLog", "LLMNode")

agent_1.add_edge("LogIfDebug", "LLMNode", branch="false")

agent_1.add_edge("LLMNode", "End")

# 4. Run
if __name__ == "__main__":
    initial_data = {"data": "Hi man, have a great day"}
    print(asyncio.run(agent_1.run("Start", initial_data, is_return=True)))

    initial_data = {"data": "Hi girl you are so dumb"}
    print(asyncio.run(agent_1.run("Start", initial_data, is_return=True)))