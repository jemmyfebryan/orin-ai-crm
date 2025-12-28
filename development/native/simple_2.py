import asyncio

from src.orin_ai_crm.core.models import PassNode, Agent, HTTPRequestNode, LogNode
from src.orin_ai_crm.core.models.logic_node import IfNode

# 1. Initialize Nodes
passing = PassNode(name="Pass")
check_hello = IfNode("IsHello", condition_key="data", expected_value="Helloo")
success_node = LogNode("SuccessLog", message="Node success!", log_type="info")
fail_node = LogNode("FailureLog", message="Node fail!", log_type="error")

# 2. Setup Workflow
agent_1 = Agent()
agent_1.add_node(passing)
agent_1.add_node(check_hello)
agent_1.add_node(success_node)
agent_1.add_node(fail_node)

# 3. Define Connections (Edges)
agent_1.add_edge("Pass", "IsHello")
agent_1.add_edge("IsHello", "SuccessLog", branch="true")
agent_1.add_edge("IsHello", "FailureLog", branch="false")

# 4. Run
if __name__ == "__main__":
    asyncio.run(agent_1.run("Pass", {"data": "Hello"}))
# fetch_user.execute(None)