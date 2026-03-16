"""
Prompt Management Tools

Utilities for managing prompts in the database.
Following the same pattern as product_agent_tools.py.
"""

import os
import json
from typing import Optional

from sqlalchemy import select, delete, text

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Prompt

logger = get_logger(__name__)


# ============================================================================
# INTERNAL HELPER FUNCTIONS
# ============================================================================

def get_default_prompts_json_path() -> str:
    """Get path to default_prompts.json file in hana_agent folder"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "..", "custom", "hana_agent", "default_prompts.json")


def load_default_prompts_from_json() -> list:
    """
    Load default prompts from JSON file in hana_agent folder.
    Returns list of prompt dicts matching Prompt schema.
    """
    json_path = get_default_prompts_json_path()

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Extract prompts array from JSON structure
        if isinstance(data, dict) and "prompts" in data:
            default_prompts = data["prompts"]
        elif isinstance(data, list):
            default_prompts = data
        else:
            logger.error(f"Invalid JSON structure in {json_path}")
            return []

        logger.info(f"Loaded {len(default_prompts)} default prompts from {json_path}")
        return default_prompts if isinstance(default_prompts, list) else []
    except FileNotFoundError:
        logger.error(f"Default prompts JSON file not found: {json_path}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding default prompts JSON: {e}")
        return []


async def get_prompt_from_db(prompt_key: str) -> str:
    """
    Get a single prompt by key from database.

    Args:
        prompt_key: The prompt key to retrieve (e.g., "hana_base_agent")

    Returns:
        str: The prompt text, or empty string if not found
    """
    logger.info(f"Fetching prompt from DB: {prompt_key}")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Prompt).where(
                Prompt.prompt_key == prompt_key,
                Prompt.is_active == True
            )
        )
        prompt = result.scalars().first()

        if prompt:
            logger.info(f"Found prompt: {prompt_key}")
            return prompt.prompt_text
        else:
            logger.warning(f"Prompt not found: {prompt_key}")
            return ""


async def get_all_prompts_from_db() -> dict:
    """
    Get all active prompts as dict key -> prompt_text.

    Returns:
        dict: {prompt_key: prompt_text, ...}
    """
    logger.info("Fetching all prompts from DB")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Prompt).where(Prompt.is_active == True)
        )
        prompts = result.scalars().all()

        prompts_dict = {p.prompt_key: p.prompt_text for p in prompts}
        logger.info(f"Retrieved {len(prompts_dict)} prompts from DB")

        return prompts_dict


async def update_prompt_in_db(prompt_key: str, prompt_text: str) -> dict:
    """
    Update a specific prompt in database.

    Args:
        prompt_key: The prompt key to update
        prompt_text: The new prompt text

    Returns:
        dict with: success (bool), message (str)
    """
    logger.info(f"Updating prompt in DB: {prompt_key}")

    async with AsyncSessionLocal() as db:
        try:
            # Find existing prompt
            result = await db.execute(
                select(Prompt).where(Prompt.prompt_key == prompt_key)
            )
            prompt = result.scalars().first()

            if prompt:
                # Update existing
                prompt.prompt_text = prompt_text
                await db.commit()
                await db.refresh(prompt)
                logger.info(f"Prompt updated: {prompt_key}")
                return {
                    'success': True,
                    'message': f'Prompt {prompt_key} updated successfully'
                }
            else:
                return {
                    'success': False,
                    'message': f'Prompt {prompt_key} not found'
                }
        except Exception as e:
            logger.error(f"Error updating prompt: {str(e)}")
            await db.rollback()
            return {
                'success': False,
                'message': f'Error updating prompt: {str(e)}'
            }


async def reset_prompts_to_default() -> dict:
    """
    Reset all prompts in database to default values from JSON file.

    This is similar to reset_products_to_default in product_agent_tools.py.
    It will delete all existing prompts and create new ones from JSON.

    Returns:
        dict with: deleted (int), created (int), errors (list)
    """
    logger.info("Resetting prompts to default from JSON")

    default_prompts = load_default_prompts_from_json()

    if not default_prompts:
        logger.error("No default prompts found in JSON file")
        return {"deleted": 0, "created": 0, "errors": ["JSON file not found or empty"]}

    summary = {"deleted": 0, "created": 0, "errors": []}

    async with AsyncSessionLocal() as db:
        try:
            # Delete all existing prompts
            delete_stmt = delete(Prompt)
            result = await db.execute(delete_stmt)
            summary["deleted"] = result.rowcount
            logger.info(f"Deleted {summary['deleted']} existing prompts")

            # Create new prompts from JSON
            for prompt_data in default_prompts:
                try:
                    new_prompt = Prompt(
                        prompt_key=prompt_data.get("prompt_key"),
                        prompt_name=prompt_data.get("prompt_name"),
                        prompt_text=prompt_data.get("prompt_text"),
                        description=prompt_data.get("description"),
                        prompt_type=prompt_data.get("prompt_type", "system"),
                        is_active=prompt_data.get("is_active", True)
                    )
                    db.add(new_prompt)
                    summary["created"] += 1
                    logger.info(f"Created prompt: {prompt_data.get('prompt_key')}")

                except Exception as e:
                    error_msg = f"Error creating prompt '{prompt_data.get('prompt_key', 'unknown')}': {str(e)}"
                    logger.error(error_msg)
                    summary["errors"].append(error_msg)

            await db.commit()
            logger.info(f"Prompts reset completed: {summary}")

        except Exception as e:
            await db.rollback()
            error_msg = f"Error during prompt reset: {str(e)}"
            logger.error(error_msg)
            summary["errors"].append(error_msg)

    return summary


async def initialize_prompts_if_empty() -> dict:
    """
    Initialize prompts table with defaults if empty.
    This can be called during app startup to ensure prompts exist.

    Returns:
        dict with: initialized (bool), prompts_count (int)
    """
    logger.info("Checking if prompts table needs initialization")

    async with AsyncSessionLocal() as db:
        try:
            # Check if any prompts exist
            result = await db.execute(
                select(Prompt).limit(1)
            )
            existing_prompt = result.scalars().first()

            if existing_prompt:
                logger.info(f"Prompts already exist, skipping initialization")
                return {
                    'initialized': False,
                    'prompts_count': 0
                }

            # Table is empty, initialize from defaults
            logger.info("Prompts table is empty, initializing from defaults")
            reset_result = await reset_prompts_to_default()

            return {
                'initialized': True,
                'prompts_count': reset_result.get('created', 0)
            }

        except Exception as e:
            logger.error(f"Error during prompts initialization: {str(e)}")
            return {
                'initialized': False,
                'prompts_count': 0,
                'error': str(e)
            }
