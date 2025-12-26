import pytest
import random
from unittest.mock import MagicMock, patch
from src.orin_ai_crm.core.models import (
    Agent,
    LogNode,
    PassNode,
    RandomNode,
    HTTPRequestNode,
    AgentEnvironment,
    GetEnvironmentVarNode,
)

# --- Node Tests ---
@pytest.mark.asyncio
async def test_random_node():
    """Verify that the Random node uses the Random module correctly."""
    random.seed(42)
    # randint(1, 10) with seed 42 usually produces 2
    node = RandomNode(name="Rand", random_type="randint", value=(1, 10))
    result = node.execute(None)
    
    assert "data" in result
    assert 1 <= result["data"] <= 10
    assert result["data"] == 2 

@pytest.mark.asyncio
async def test_pass_node():
    """Verify that PassNode node returns the data it was initialized with."""
    agent = Agent()
    
    test_data = {"key": "value"}
    node = PassNode(name="Passer")
    
    agent.add_node(node)
    
    result = await agent.run(start_node_name="Passer", initial_data=test_data, is_return=True)
    
    assert result == test_data


@pytest.mark.asyncio
@patch("src.orin_ai_crm.core.models.logger")
async def test_log_node(mock_logger):
    """Verify that the LogNode node calls the correct logger methods."""
    info_node = LogNode(name="InfoLog", message="Hello Info", log_type="info")
    error_node = LogNode(name="ErrorLog", message="Hello Error", log_type="error")
    
    info_node.execute(None)
    mock_logger.info.assert_called_with("Hello Info")
    
    error_node.execute(None)
    mock_logger.error.assert_called_with("Hello Error")

@pytest.mark.asyncio
async def test_http_request_node():
    """Verify the simulated output of the HTTP node."""
    node = HTTPRequestNode(name="FetchUser", url="https://api.test.com")
    result = node.execute(None)
    
    assert result["status"] == 200
    assert result["data"]["user_id"] == 123

# --- Agent/Workflow Tests ---

@pytest.mark.asyncio
async def test_agent_return_result():
    """Verify that is_return=True returns the final node's output."""
    agent = Agent()
    node = PassNode(name="Final")
    agent.add_node(node)
    
    result = await agent.run("Final", initial_data={"status": "success"}, is_return=True)
    assert result == {"status": "success"}

@pytest.mark.asyncio
async def test_agent_workflow_chain():
    """Test if the Agent correctly passes data from one node to the next."""
    agent = Agent()
    
    # Setup nodes
    pass_node = PassNode(name="Start")
    # We'll use a mock execute for the second node to verify it received the first node's data
    log_node = LogNode(name="End", message="Done", log_type="info")
    
    agent.add_node(pass_node)
    agent.add_node(log_node)
    agent.add_edge("Start", "End")
    
    # We want to check if the data flows. 
    # Since LogNode.execute returns None, we check the flow logic.
    with patch.object(LogNode, 'execute', return_value="main") as mocked_execute:
        await agent.run("Start", initial_data={"score": 10})
        # Verify LogNode received the output of PassNode ({"score": 10})
        mocked_execute.assert_called_once_with({"score": 10})

@pytest.mark.asyncio
async def test_agent_branching_logic():
    """Test if the agent can handle custom branches."""
    class BranchNode(PassNode):
        def __init__(self, name: str):
            super().__init__(name)
            self.async_node = True
            
        async def execute(self, input_data):
            # Logic: if input is > 5, go to 'high', else 'low'
            return "high" if input_data["val"] > 5 else "low"

    agent = Agent()
    agent.add_node(BranchNode("Checker"))
    agent.add_node(LogNode("HighNode", "Value is high", "info"))
    agent.add_node(LogNode("LowNode", "Value is low", "info"))
    
    agent.add_edge("Checker", "HighNode", branch="high")
    agent.add_edge("Checker", "LowNode", branch="low")
    
    with patch("src.orin_ai_crm.core.models.logger") as mock_logger:
        # Run with high value
        await agent.run("Checker", initial_data={"val": 10})
        mock_logger.info.assert_any_call("Value is high")
        
        # Run with low value
        await agent.run("Checker", initial_data={"val": 2})
        mock_logger.info.assert_any_call("Value is low")

# --- AgentEnvironment Tests ---

def test_agent_environment_variables():
    """Verify that environment variables can be set and retrieved."""
    env = AgentEnvironment(env_vars={"API_KEY": "12345", "DB_URL": "localhost"})
    
    assert env.get_variable("API_KEY") == "12345"
    assert env.get_variable("DB_URL") == "localhost"
    
    # Test missing key returns None
    assert env.get_variable("MISSING_KEY") is None

def test_agent_environment_clients():
    """Verify that client instances can be stored and retrieved."""
    env = AgentEnvironment()
    mock_db_client = MagicMock()
    
    env.set_client("postgres", mock_db_client)
    
    assert "postgres" in env.clients
    assert env.clients["postgres"] == mock_db_client

# --- GetEnvironmentVarNode Tests ---

@pytest.mark.asyncio
async def test_get_environment_var_node_success():
    """Verify that the node correctly injects env vars into the data dictionary."""
    env = AgentEnvironment(env_vars={"target_key": "secret_value"})
    node = GetEnvironmentVarNode(name="GetEnv", key="target_key", env=env)
    
    input_data = {"existing_field": "hello"}
    result = node.execute(input_data)
    
    # Check that the new key is merged into the dictionary
    assert result["target_key"] == "secret_value"
    assert result["existing_field"] == "hello"

@pytest.mark.asyncio
@patch("src.orin_ai_crm.core.models.logger")
async def test_get_environment_var_node_invalid_input(mock_logger):
    """Verify node behavior when input_data is not a dictionary."""
    env = AgentEnvironment(env_vars={"foo": "bar"})
    node = GetEnvironmentVarNode(name="GetEnv", key="foo", env=env)
    
    # Input is a string instead of a Dict
    input_data = "not-a-dict"
    result = node.execute(input_data)
    
    # Should return original data and log a warning
    assert result == "not-a-dict"
    mock_logger.warning.assert_called()

@pytest.mark.asyncio
async def test_get_environment_var_node_missing_var():
    """Verify node behavior when the requested key does not exist in env."""
    env = AgentEnvironment(env_vars={}) # Empty env
    node = GetEnvironmentVarNode(name="GetEnv", key="missing_key", env=env)
    
    input_data = {"data": 1}
    result = node.execute(input_data)
    
    # Key should be added as None (or however get_variable handles misses)
    assert "missing_key" in result
    assert result["missing_key"] is None