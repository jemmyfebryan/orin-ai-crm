import os
import json
from typing import List

from dotenv import load_dotenv

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

load_dotenv(override=True)

def create_client():
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return openai_client

async def chat_completion(
    openai_client: AsyncOpenAI,
    user_prompt: str | List[ChatCompletionMessageParam],
    system_prompt: str = None,
    formatted_schema: dict = None,
    model_name: str = "gpt-4.1-nano",
    use_temperature: bool = True
) -> str | dict:
    """
        Fast chat completion implementation, just use client, user prompt,
        and system prompt. You get the response.
        
        Args:
        openai_client: OpenAI Client
        user_prompt: User prompt string, or chat completion's messages
        system_prompt: System prompt string
        formatted_schema: Using this arg automatically uses formatted schema output
        model_name: Model used for the completion
        use_temperature: If True, sets temperature to 0. If False, temperature is omitted.
    """
    
    messages = []
    # Messages Schema logic
    if system_prompt is None:
        if isinstance(user_prompt, str):
            messages.append({"role": "user", "content": user_prompt})
        else:
            messages = user_prompt
    else:
        messages.append({"role": "system", "content": system_prompt})
        if isinstance(user_prompt, str):
            messages.append({"role": "user", "content": user_prompt})
        else:
            messages.extend(user_prompt)

    # Prepare common arguments for the API call
    api_params = {
        "model": model_name,
        "messages": messages,
    }

    # Conditionally add temperature
    if use_temperature:
        api_params["temperature"] = 0

    # Is Response using Formatted Schema?
    if formatted_schema is None:
        completions = await openai_client.chat.completions.create(**api_params)
        completions_result: str = completions.choices[0].message.content
    else:
        # Add schema specific params
        api_params["response_format"] = {
            "type": "json_schema",
            "json_schema": formatted_schema
        }
        completions = await openai_client.chat.completions.create(**api_params)
        completions_result: dict = json.loads(completions.choices[0].message.content)
        
    return completions_result