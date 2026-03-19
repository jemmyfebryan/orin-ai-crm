"""
Prompt Management Tools

Utilities for managing prompts in the database.
Following the same pattern as product_agent_tools.py.
"""

import os
import importlib.util
from typing import Optional

from sqlalchemy import select, delete, text

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Prompt

logger = get_logger(__name__)

# ============================================================================
# CACHED AGENT NAME (loaded once at startup)
# ============================================================================

_AGENT_NAME: str = "Hana"  # Default fallback, will be loaded from DB on first access


def get_agent_name() -> str:
    """
    Get the cached agent name.

    Returns:
        str: The agent name (default "Hana" if not yet loaded from DB)
    """
    return _AGENT_NAME


async def initialize_agent_name() -> str:
    """
    Initialize agent name from database (should be called once at app startup).

    Returns:
        str: The loaded agent name
    """
    global _AGENT_NAME

    try:
        agent_name = await get_prompt_from_db("agent_name")
        if agent_name:
            _AGENT_NAME = agent_name
            logger.info(f"Initialized agent_name from DB: {_AGENT_NAME}")
        else:
            logger.warning("agent_name not found in DB, using default 'Hana'")
            _AGENT_NAME = "Hana"
    except Exception as e:
        logger.error(f"Error loading agent_name from DB: {e}, using default 'Hana'")
        _AGENT_NAME = "Hana"

    return _AGENT_NAME


# ============================================================================
# INTERNAL HELPER FUNCTIONS
# ============================================================================

def get_default_prompts_py_path() -> str:
    """Get path to default_prompts.py file in hana_agent folder"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "..", "custom", "hana_agent", "default_prompts.py")


def load_default_prompts_from_py() -> list:
    """
    Load default prompts from Python file in hana_agent folder.
    Returns list of prompt dicts matching Prompt schema.
    """
    py_path = get_default_prompts_py_path()

    try:
        # Load the Python module dynamically
        spec = importlib.util.spec_from_file_location("default_prompts", py_path)
        if spec is None or spec.loader is None:
            logger.error(f"Failed to load module spec from {py_path}")
            return []

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Get DEFAULT_PROMPTS from the module
        default_prompts = getattr(module, 'DEFAULT_PROMPTS', None)

        if default_prompts is None:
            logger.error(f"DEFAULT_PROMPTS not found in {py_path}")
            return []

        if not isinstance(default_prompts, list):
            logger.error(f"DEFAULT_PROMPTS is not a list in {py_path}")
            return []

        logger.info(f"Loaded {len(default_prompts)} default prompts from {py_path}")
        return default_prompts

    except FileNotFoundError:
        logger.error(f"Default prompts Python file not found: {py_path}")
        return []
    except Exception as e:
        logger.error(f"Error loading default prompts from Python file: {e}")
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
    Reset all prompts in database to default values from Python file.

    This is similar to reset_products_to_default in product_agent_tools.py.
    It will delete all existing prompts and create new ones from Python file.

    Returns:
        dict with: deleted (int), created (int), errors (list)
    """
    logger.info("Resetting prompts to default from Python file")

    default_prompts = load_default_prompts_from_py()

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
