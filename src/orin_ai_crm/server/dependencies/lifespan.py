"""
Application lifespan management - startup and shutdown events.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

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
    - Verify database connection
    - Create database tables
    - Initialize default products if empty
    - Initialize default prompts if empty
    - Start periodic pool refresh task

    Shutdown:
    - Cancel periodic pool refresh task
    - Cleanup if needed
    """
    # Startup
    logger.info("Application startup...")

    # Verify database connection with retries
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection verified")
            break
        except Exception as e:
            logger.error(f"❌ Database connection attempt {attempt + 1}/{max_attempts}: {e}")
            if attempt < max_attempts - 1:
                logger.info(f"Retrying in 5 seconds...")
                await asyncio.sleep(5)
            else:
                logger.error("❌ Failed to connect to database after multiple attempts")
                raise Exception("Database connection failed. Please check your database configuration.")

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

    # 🔥 FIX: Start periodic pool refresh task to prevent stale connections
    # This runs every 5 minutes to recycle all connections in the pool
    async def periodic_pool_refresh():
        """Periodically recycle all connections in the pool to prevent stale connections"""
        while True:
            try:
                # Wait 5 minutes between refreshes
                await asyncio.sleep(300)
                logger.info("🔄 Refreshing connection pool (recycling all connections)...")
                await engine.dispose()
                logger.info("✅ Connection pool refreshed successfully")
            except Exception as e:
                logger.error(f"❌ Error refreshing connection pool: {e}")
                # Continue even if refresh fails - will retry in 5 minutes

    # Start the background task
    pool_refresh_task = asyncio.create_task(periodic_pool_refresh())
    logger.info("🔄 Periodic pool refresh task started (runs every 5 minutes)")

    # Store task in app state for shutdown access
    app.state.pool_refresh_task = pool_refresh_task

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Application shutdown...")

    # Cancel the periodic pool refresh task
    if hasattr(app.state, 'pool_refresh_task'):
        app.state.pool_refresh_task.cancel()
        try:
            await app.state.pool_refresh_task
        except asyncio.CancelledError:
            logger.info("Periodic pool refresh task cancelled")
