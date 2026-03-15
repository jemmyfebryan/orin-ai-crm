"""
Application lifespan management - startup and shutdown events.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import engine, Base
from src.orin_ai_crm.core.agents.tools.product_agent_tools import initialize_default_products_if_empty

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan events.

    Startup:
    - Create database tables
    - Initialize default products if empty

    Shutdown:
    - Cleanup if needed
    """
    # Startup
    logger.info("Application startup...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize default products if table is empty
    await initialize_default_products_if_empty.ainvoke({})
    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Application shutdown...")
