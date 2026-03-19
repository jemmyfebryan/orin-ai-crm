"""
Application lifespan management - startup and shutdown events.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import engine, Base
from src.orin_ai_crm.core.agents.tools.product_agent_tools import initialize_default_products_if_empty
from src.orin_ai_crm.core.agents.tools.prompt_tools import initialize_prompts_if_empty, initialize_agent_name

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan events.

    Startup:
    - Create database tables
    - Initialize default products if empty
    - Initialize default prompts if empty

    Shutdown:
    - Cleanup if needed
    """
    # Startup
    logger.info("Application startup...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize default products if table is empty
    await initialize_default_products_if_empty.ainvoke({})

    # Initialize default prompts if table is empty
    prompts_init_result = await initialize_prompts_if_empty()
    if prompts_init_result.get('initialized'):
        logger.info(f"Initialized {prompts_init_result.get('prompts_count', 0)} default prompts")

    # Initialize agent name from database
    agent_name = await initialize_agent_name()
    logger.info(f"Agent name initialized: {agent_name}")

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Application shutdown...")
