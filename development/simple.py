from src.orin_ai_crm.core.models import Node, Agent, HTTPRequestNode, Log
from src.orin_ai_crm.core.models.logic_node import IfNode

# 1. Initialize Nodes
fetch_user = HTTPRequestNode("FetchUser", "https://api.example.com/user")
check_active = IfNode("IsActive", condition_key="active", expected_value=True)
success_node = Log("SuccessLog", message="Node success!", log_type="info")
fail_node = Log("FailureLog", message="Node fail!", log_type="error")

# 2. Setup Workflow
wf = Agent()
wf.add_node(fetch_user)
wf.add_node(check_active)
wf.add_node(success_node)
wf.add_node(fail_node)

# 3. Define Connections (Edges)
wf.add_edge("FetchUser", "IsActive")
wf.add_edge("IsActive", "SuccessLog", branch="true")
wf.add_edge("IsActive", "FailureLog", branch="false")

# 4. Run
wf.run("FetchUser", {})
# fetch_user.execute(None)