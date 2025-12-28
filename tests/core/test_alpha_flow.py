import pytest
from unittest.mock import MagicMock, patch
from langgraph.graph import START, END
from src.orin_ai_crm.core.alpha_flow import NodeConfig
from src.orin_ai_crm.core.alpha_flow import FlowBuilder, registry

# --- Mocking State Schema ---
class MockState(dict):
    """A simple dict-like class to simulate a TypedDict/BaseModel state."""
    pass

@pytest.fixture
def mock_flow_schema():
    """Returns a valid schema for testing the FlowBuilder."""
    return {
        "flow_id": "test_crm_flow",
        "state_schema": "CRMState",  # This will be resolved by get_state_schema
        "nodes": [
            {
                "name": "start_node",
                "node": "start",
                "to": ["agent_node"]
            },
            {
                "name": "agent_node",
                "node": "llm_node",
                "args": {
                    "system_prompt": "You are a helpful assistant.",
                    "message_key": "messages"
                },
                "to": ["end"]
            }
        ]
    }

@patch("src.orin_ai_crm.core.alpha_flow.get_state_schema")
@patch("src.orin_ai_crm.core.alpha_flow.ChatOpenAI")
def test_flow_builder_initialization(mock_llm, mock_get_state, mock_flow_schema):
    """Verify that FlowBuilder initializes models and state correctly."""
    mock_get_state.return_value = MockState
    
    builder = FlowBuilder(mock_flow_schema)
    
    assert builder.data.flow_id == "test_crm_flow"
    assert len(builder.data.nodes) == 2
    assert builder.state_class == MockState

@patch("src.orin_ai_crm.core.alpha_flow.get_state_schema")
@patch("src.orin_ai_crm.core.alpha_flow.ChatOpenAI")
def test_flow_builder_graph_construction(mock_llm, mock_get_state, mock_flow_schema):
    """Verify nodes and edges are added to the StateGraph."""
    mock_get_state.return_value = MockState
    
    builder = FlowBuilder(mock_flow_schema)
    graph = builder.build()
    
    # Verify nodes in the underlying workflow
    # Note: LangGraph internal structure stores nodes in .nodes
    assert "agent_node" in builder.workflow.nodes
    
    # Verify graph can be compiled
    assert graph is not None

def test_node_registry_error():
    """Verify registry raises error for unregistered types."""
    with pytest.raises(ValueError, match="Node type ghost_node not registered"):
        registry.build("ghost_node", {})

@patch("src.orin_ai_crm.core.alpha_flow.get_state_schema")
@patch("src.orin_ai_crm.core.alpha_flow.ChatOpenAI")
def test_flow_builder_start_end_mapping(mock_llm, mock_get_state):
    """Verify that 'start' and 'end' strings are correctly mapped to START/END constants."""
    mock_get_state.return_value = MockState
    schema = {
        "flow_id": "simple_path",
        "state_schema": "MockState",
        "nodes": [
            {"name": "any_name", "node": "start", "to": ["end"]}
        ]
    }
    
    builder = FlowBuilder(schema)
    builder.build()
    
    # Check edges directly in the StateGraph
    # We expect a direct edge from START to END based on this schema
    edges = builder.workflow.edges
    # edges is usually a set of tuples: {(START, END)}
    assert (START, END) in edges

def test_node_config_alias():
    """Verify Pydantic alias for 'node' works."""
    cfg = NodeConfig(name="test", node="llm_node", args={"x": 1})
    assert cfg.node_type == "llm_node"