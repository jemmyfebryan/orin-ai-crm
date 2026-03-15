"""
HANA AI WhatsApp Chatbot Backend - Main Entry Point

This is the main application file that wires together all modular components.
After refactoring, this file is now ~100 lines (down from 1210 lines).
"""
import uvicorn
from fastapi import FastAPI

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.server.dependencies.lifespan import lifespan
from src.orin_ai_crm.server.routes import health, admin, chat, freshchat

logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="HANA AI WhatsApp Chatbot Backend",
    lifespan=lifespan
)

# Include all routers
app.include_router(health.router, tags=["Health"])
app.include_router(admin.router, tags=["Admin"])
app.include_router(chat.router, tags=["Chat"])
app.include_router(freshchat.router, tags=["Freshchat"])


# --- RUN SERVER ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
