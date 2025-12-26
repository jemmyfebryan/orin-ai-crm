from src.orin_ai_crm.core.models import Pass, Agent, Random, Log
from src.orin_ai_crm.core.models.logic_node import IfNode

# 1. Initialize Nodes
passing = Random(name="Randomizer", random_type="uniform", value=(0, 10))
check_number = IfNode("IsLessThan5", condition_key="data", expected_value=5, operator = "less_than")
success_node = Log("SuccessLog", message="Node success!", log_type="info")
fail_node = Log("FailureLog", message="Node fail!", log_type="error")

# 2. Setup Workflow
agent_1 = Agent()
agent_1.add_node(passing)
agent_1.add_node(check_number)
agent_1.add_node(success_node)
agent_1.add_node(fail_node)

# 3. Define Connections (Edges)
agent_1.add_edge("Randomizer", "IsLessThan5")
agent_1.add_edge("IsLessThan5", "SuccessLog", branch="true")
agent_1.add_edge("IsLessThan5", "FailureLog", branch="false")

# 4. Run
agent_1.run("Randomizer", {})
# fetch_user.execute(None)