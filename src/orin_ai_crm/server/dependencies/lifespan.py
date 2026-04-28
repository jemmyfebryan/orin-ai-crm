"""
Application lifespan management - startup and shutdown events.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import text

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import engine, Base, AsyncSessionLocal, Customer, WIB
from src.orin_ai_crm.core.agents.tools.product_agent_tools import initialize_default_products_if_empty
from src.orin_ai_crm.core.agents.tools.prompt_tools import initialize_prompts_if_empty, initialize_agent_name
from sqlalchemy import update

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
    - Start periodic human_takeover reset task

    Shutdown:
    - Cancel periodic pool refresh task
    - Cancel periodic human_takeover reset task
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

    # 🔄 Reset human_takeover flag after 1 hour
    # This runs every 10 minutes to reset human_takeover for customers updated more than 1 hour ago
    async def periodic_human_takeover_reset():
        """Periodically reset human_takeover flag for customers updated more than 1 hour ago"""
        while True:
            try:
                # Wait 10 minutes between checks
                await asyncio.sleep(600)

                async with AsyncSessionLocal() as session:
                    # Calculate cutoff time (1 hour ago from now in WIB)
                    cutoff_time = datetime.now(WIB) - timedelta(hours=1)

                    # Find customers with human_takeover=True and updated_at < 1 hour ago
                    stmt = (
                        update(Customer)
                        .where(Customer.human_takeover == True)
                        .where(Customer.updated_at < cutoff_time)
                        .where(Customer.deleted_at == None)  # Exclude soft-deleted customers
                        .values(human_takeover=False)
                    )

                    result = await session.execute(stmt)
                    affected_count = result.rowcount
                    await session.commit()

                    if affected_count > 0:
                        logger.info(f"🔄 Reset human_takeover flag for {affected_count} customer(s) (updated more than 1 hour ago)")
                    else:
                        logger.debug("🔄 No customers to reset human_takeover flag (all recent)")

            except Exception as e:
                logger.error(f"❌ Error resetting human_takeover flag: {e}")
                # Continue even if reset fails - will retry in 10 minutes

    # Start the background task
    human_takeover_reset_task = asyncio.create_task(periodic_human_takeover_reset())
    logger.info("🔄 Periodic human_takeover reset task started (runs every 10 minutes)")

    # Store task in app state for shutdown access
    app.state.human_takeover_reset_task = human_takeover_reset_task

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

    # Cancel the periodic human_takeover reset task
    if hasattr(app.state, 'human_takeover_reset_task'):
        app.state.human_takeover_reset_task.cancel()
        try:
            await app.state.human_takeover_reset_task
        except asyncio.CancelledError:
            logger.info("Periodic human_takeover reset task cancelled")
