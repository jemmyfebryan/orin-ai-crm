from typing import Any, Dict, List, Optional, Union

from src.orin_ai_crm.core.models import Node

class LogicNode(Node):
    """Base class for nodes that handle branching or data manipulation."""
    pass

class IfNode(LogicNode):
    def __init__(
        self, 
        name: str,
        condition_key: str, 
        expected_value: Any, 
        operator: str = "equal"
    ):
        super().__init__(name)
        self.condition_key = condition_key
        self.expected_value = expected_value
        self.operator = operator

    def execute(self, input_data: Dict[str, Any]) -> str:
        """
        Evaluates the condition and returns the name of the output branch.
        """
        self.input_data = input_data
        actual_value = input_data.get(self.condition_key)

        if self.operator == "equal":
            result = actual_value == self.expected_value
        elif self.operator == "exists":
            result = actual_value is not None
        elif self.operator == "less_than":
            result = actual_value < self.expected_value
        elif self.operator == "greater_than":
            result = actual_value > self.expected_value
        else:
            result = False

        return "true" if result else "false"