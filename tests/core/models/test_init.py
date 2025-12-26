import pytest
import random
from unittest.mock import MagicMock, patch
from src.orin_ai_crm.core.models import Agent, Log, Pass, Random, HTTPRequestNode

# --- Node Tests ---

def test_random_node():
    """Verify that the Random node uses the random module correctly."""
    random.seed(42)
    # randint(1, 10) with seed 42 usually produces 2
    node = Random(name="Rand", random_type="randint", value=(1, 10))
    result = node.execute(None)
    
    assert "data" in result
    assert 1 <= result["data"] <= 10
    assert result["data"] == 2 

def test_pass_node():
    """Verify that Pass node returns the data it was initialized with."""
    test_data = {"key": "value"}
    node = Pass(name="Passer", input_data=test_data)
    result = node.execute(None)
    
    assert result == test_data

@patch("src.orin_ai_crm.core.models.logger")
def test_log_node(mock_logger):
    """Verify that the Log node calls the correct logger methods."""
    info_node = Log(name="InfoLog", message="Hello Info", log_type="info")
    error_node = Log(name="ErrorLog", message="Hello Error", log_type="error")
    
    info_node.execute(None)
    mock_logger.info.assert_called_with("Hello Info")
    
    error_node.execute(None)
    mock_logger.error.assert_called_with("Hello Error")

def test_http_request_node():
    """Verify the simulated output of the HTTP node."""
    node = HTTPRequestNode(name="FetchUser", url="https://api.test.com")
    result = node.execute(None)
    
    assert result["status"] == 200
    assert result["data"]["user_id"] == 123

# --- Agent/Workflow Tests ---

def test_agent_workflow_chain():
    """Test if the Agent correctly passes data from one node to the next."""
    agent = Agent()
    
    # Setup nodes
    pass_node = Pass(name="Start", input_data={"score": 10})
    # We'll use a mock execute for the second node to verify it received the first node's data
    log_node = Log(name="End", message="Done", log_type="info")
    
    agent.add_node(pass_node)
    agent.add_node(log_node)
    agent.add_edge("Start", "End")
    
    # We want to check if the data flows. 
    # Since Log.execute returns None, we check the flow logic.
    with patch.object(Log, 'execute', return_value="main") as mocked_execute:
        agent.run("Start", initial_data=None)
        # Verify Log received the output of Pass ({"score": 10})
        mocked_execute.assert_called_once_with({"score": 10})

def test_agent_branching_logic():
    """Test if the agent can handle custom branches."""
    class BranchNode(Pass):
        def execute(self, input_data):
            # Logic: if input is > 5, go to 'high', else 'low'
            return "high" if input_data["val"] > 5 else "low"

    agent = Agent()
    agent.add_node(BranchNode("Checker", input_data=None))
    agent.add_node(Log("HighNode", "Value is high", "info"))
    agent.add_node(Log("LowNode", "Value is low", "info"))
    
    agent.add_edge("Checker", "HighNode", branch="high")
    agent.add_edge("Checker", "LowNode", branch="low")
    
    with patch("src.orin_ai_crm.core.models.logger") as mock_logger:
        # Run with high value
        agent.run("Checker", initial_data={"val": 10})
        mock_logger.info.assert_called_with("Value is high")
        
        # Run with low value
        agent.run("Checker", initial_data={"val": 2})
        mock_logger.info.assert_called_with("Value is low")

def test_agent_return_result():
    """Verify that is_return=True returns the final node's output."""
    agent = Agent()
    node = Pass(name="Final", input_data={"status": "success"})
    agent.add_node(node)
    
    result = agent.run("Final", initial_data=None, is_return=True)
    assert result == {"status": "success"}