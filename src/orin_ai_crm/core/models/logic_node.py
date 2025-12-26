from typing import Any, Dict, List, Optional, Union

from openai import OpenAI

from src.orin_ai_crm.core.openai import chat_completion
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
    
class LLMIfNode(LogicNode):
    def __init__(
        self, 
        name: str,
        llm_client: OpenAI,
        system_prompt: str,
        model_name: str = "gpt-5-nano",
        use_temperature: bool = False,
    ):
        super().__init__(name)
        self.system_prompt = system_prompt
        self.llm_client = llm_client
        self.model_name = model_name
        self.use_temperature = use_temperature
        
        self.async_node = True
        
    async def execute(self, input_data: Dict[str, Any]) -> str:
        """
        Evaluates the condition and returns the name of the output branch.
        """
        system_prompt = self.system_prompt
        user_prompt = f"input_data:\n{str(input_data)}"
        
        formatted_schemas = {
            "name": "logic_result",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "logic_result": {
                        "type": "boolean"
                    }
                },
                "required": ["logic_result"],
                "additionalProperties": False
            }
        }
        
        logic_result = await chat_completion(
            openai_client=self.llm_client,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            formatted_schema=formatted_schemas,
            model_name=self.model_name,
            use_temperature=self.use_temperature,
        )

        return logic_result.get("logic_result")