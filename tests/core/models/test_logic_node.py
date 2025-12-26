import pytest
from src.orin_ai_crm.core.models.logic_node import IfNode

def test_if_node_equal():
    """Test the 'equal' operator."""
    node = IfNode(
        name="CheckStatus", 
        condition_key="status", 
        expected_value="active", 
        operator="equal"
    )
    
    # Positive case
    assert node.execute({"status": "active"}) == "true"
    # Negative case
    assert node.execute({"status": "inactive"}) == "false"
    # Missing key case
    assert node.execute({"other": "data"}) == "false"

def test_if_node_exists():
    """Test the 'exists' operator."""
    node = IfNode(
        name="CheckUser", 
        condition_key="user_id", 
        expected_value=None,  # Value doesn't matter for 'exists'
        operator="exists"
    )
    
    assert node.execute({"user_id": 123}) == "true"
    assert node.execute({"user_id": None}) == "false"
    assert node.execute({"other": "data"}) == "false"

def test_if_node_less_than():
    """Test the 'less_than' operator."""
    node = IfNode(
        name="CheckAge", 
        condition_key="age", 
        expected_value=18, 
        operator="less_than"
    )
    
    assert node.execute({"age": 17}) == "true"
    assert node.execute({"age": 18}) == "false"
    assert node.execute({"age": 21}) == "false"

def test_if_node_greater_than():
    """Test the 'greater_than' operator."""
    node = IfNode(
        name="CheckStock", 
        condition_key="count", 
        expected_value=0, 
        operator="greater_than"
    )
    
    assert node.execute({"count": 5}) == "true"
    assert node.execute({"count": 0}) == "false"
    assert node.execute({"count": -1}) == "false"

def test_if_node_invalid_operator():
    """Test that an unsupported operator returns 'false'."""
    node = IfNode(
        name="InvalidOp", 
        condition_key="key", 
        expected_value=1, 
        operator="not_a_real_operator"
    )
    
    assert node.execute({"key": 1}) == "false"

def test_if_node_missing_input_data():
    """Test behavior when input_data is empty."""
    node = IfNode("EmptyTest", "any_key", "any_val")
    # Should not crash, just return false because key isn't found
    assert node.execute({}) == "false"