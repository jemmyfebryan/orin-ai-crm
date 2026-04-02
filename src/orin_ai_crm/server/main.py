"""
HANA AI WhatsApp Chatbot Backend - Main Entry Point

This is the main application file that wires together all modular components.
After refactoring, this file is now ~100 lines (down from 1210 lines).
"""
import uvicorn
from fastapi import FastAPI

from starlette.middleware.sessions import SessionMiddleware
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.server.dependencies.lifespan import lifespan
from src.orin_ai_crm.server.routes import health, admin, chat, freshchat, test_chat, dashboard
from src.orin_ai_crm.server.config.settings import settings

logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="HANA AI WhatsApp Chatbot Backend",
    lifespan=lifespan
)

# Add session middleware for test chat authentication
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.freshchat_webhook_token or "test-secret-key-change-in-production"
)

# Include all routers
app.include_router(health.router, tags=["Health"])
app.include_router(admin.router, tags=["Admin"])
app.include_router(chat.router, tags=["Chat"])
app.include_router(freshchat.router, tags=["Freshchat"])
app.include_router(test_chat.router, tags=["Test Chat"])
app.include_router(dashboard.router, tags=["Dashboard"])


# --- RUN SERVER ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
