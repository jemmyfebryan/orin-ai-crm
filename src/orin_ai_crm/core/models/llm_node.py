from typing import Any, Dict, List, Optional, Union

from openai import OpenAI

from src.orin_ai_crm.core.models import Node
from src.orin_ai_crm.core.openai import chat_completion

class LLMIfNode(Node):
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