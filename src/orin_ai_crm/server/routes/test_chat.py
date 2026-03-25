"""
Test chat interface routes for local development and testing.

This module provides a WhatsApp-like web interface to test the AI agent
without deploying to Freshchat. It uses the same processing logic as the
/freshchat-webhook endpoint.
"""
import asyncio
import json
import os
from datetime import datetime
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer, ChatSession, WIB
from src.orin_ai_crm.server.config.settings import settings
from src.orin_ai_crm.core.agents.tools.db_tools import (
    get_or_create_customer,
    get_chat_history,
    save_message_to_db,
)

logger = get_logger(__name__)
router = APIRouter()

# In-memory storage for SSE connections (test mode only)
_active_sse_connections = {}

# Setup templates directory - use absolute path from project root
# The templates are at project root (templates/test/) not in src/
TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "test"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class SendMessageRequest(BaseModel):
    phone_number: str
    contact_name: str
    message: str


def verify_test_token(request: Request) -> bool:
    """
    Verify the test token from session or header.

    For testing purposes, we accept either:
    1. Session token (set during login)
    2. X-Test-Token header (for API calls)

    Returns:
        bool: True if token is valid
    """
    # Check session first
    session_token = request.session.get("test_token") if hasattr(request, "session") else None
    if session_token and session_token == settings.freshchat_webhook_token:
        return True

    # Check header
    header_token = request.headers.get("X-Test-Token", "")
    if header_token == settings.freshchat_webhook_token:
        return True

    return False


@router.get("/test", response_class=HTMLResponse)
async def test_login_page(request: Request):
    """
    Login page for test interface.

    User must enter FRESHCHAT_WEBHOOK_TOKEN to access the test interface.
    """
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None}
    )


@router.post("/test/login")
async def test_login(request: Request, token: str = Form(...)):
    """
    Handle login form submission.

    Validates the FRESHCHAT_WEBHOOK_TOKEN and stores it in session.
    """
    from fastapi.responses import RedirectResponse

    if token != settings.freshchat_webhook_token:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid token. Please check your FRESHCHAT_WEBHOOK_TOKEN."}
        )

    # Store token in cookie (accessible to JavaScript for fetch requests)
    response = RedirectResponse(url="/test/setup", status_code=303)
    response.set_cookie(
        key="test_token",
        value=token,
        httponly=False,  # Allow JavaScript to read the token
        max_age=3600,  # 1 hour
        samesite="lax"  # Allow cookie to be sent with same-site requests
    )
    return response


@router.get("/test/setup", response_class=HTMLResponse)
async def test_setup_page(request: Request):
    """
    Setup page for entering phone number and contact name.
    """
    # Verify token
    test_token = request.cookies.get("test_token", "")
    if test_token != settings.freshchat_webhook_token:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/test", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={"error": None}
    )


@router.post("/test/setup")
async def test_setup_submit(
    request: Request,
    phone_number: str = Form(...),
    contact_name: str = Form(...)
):
    """
    Handle setup form submission and redirect to chat interface.
    """
    from fastapi.responses import RedirectResponse

    # Verify token
    test_token = request.cookies.get("test_token", "")
    if test_token != settings.freshchat_webhook_token:
        return RedirectResponse(url="/test", status_code=303)

    # Get or create customer
    customer = await get_or_create_customer(
        phone_number=phone_number,
        lid_number=None,
        contact_name=contact_name
    )
    customer_id = customer['customer_id']

    # Store customer info in cookie (accessible to JavaScript)
    response = RedirectResponse(url=f"/test/chat?customer_id={customer_id}", status_code=303)
    response.set_cookie(
        key="test_customer_id",
        value=str(customer_id),
        httponly=False,
        max_age=3600
    )
    response.set_cookie(
        key="test_phone_number",
        value=phone_number,
        httponly=False,
        max_age=3600
    )
    response.set_cookie(
        key="test_contact_name",
        value=contact_name,
        httponly=False,
        max_age=3600
    )

    return response


@router.get("/test/chat", response_class=HTMLResponse)
async def test_chat_page(request: Request, customer_id: Optional[int] = None):
    """
    WhatsApp-like chat interface.
    """
    # Verify token
    test_token = request.cookies.get("test_token", "")
    if test_token != settings.freshchat_webhook_token:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/test", status_code=303)

    # Get customer info
    phone_number = request.cookies.get("test_phone_number", "")
    contact_name = request.cookies.get("test_contact_name", "")

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "customer_id": customer_id,
            "phone_number": phone_number,
            "contact_name": contact_name,
            "test_token": test_token,  # Pass token directly to template
        }
    )


@router.get("/test/chat/history")
async def get_chat_history_api(request: Request, customer_id: int):
    """
    API endpoint to fetch chat history for a customer.

    Returns messages in chronological order (oldest first).
    """
    # Verify token
    test_token = request.cookies.get("test_token", "")
    if test_token != settings.freshchat_webhook_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Get chat history from DB
    history = await get_chat_history(customer_id, limit=100)

    # Convert to JSON-serializable format
    messages = []
    for msg in history:
        messages.append({
            "id": msg.id,
            "role": msg.message_role,
            "content": msg.content,
            "content_type": msg.content_type,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })

    return JSONResponse(content={"messages": messages})


@router.post("/test/chat/send")
async def send_message_api(request: Request, req: SendMessageRequest):
    """
    API endpoint to send a message to the AI agent.

    This endpoint processes chat requests directly using the same AI processing
    logic as /freshchat-webhook but bypasses Freshchat API calls for testing.

    Authentication: X-Test-Token header must match FRESHCHAT_WEBHOOK_TOKEN
    """
    # Verify token from header
    test_token = request.headers.get("X-Test-Token", "")
    if test_token != settings.freshchat_webhook_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Get or create customer
        customer = await get_or_create_customer(
            phone_number=req.phone_number,
            lid_number=None,
            contact_name=req.contact_name
        )
        customer_id = customer['customer_id']

        # Check human_takeover flag
        human_takeover = customer.get('human_takeover', False)
        if human_takeover:
            logger.info(f"Human takeover is active for customer_id={customer_id}. Skipping AI processing.")
            # Still save message to DB for record keeping
            await save_message_to_db(customer_id, "user", req.message, content_type="text")
            return JSONResponse(content={
                "status": "human_takeover",
                "customer_id": customer_id,
                "message": "Human takeover is active"
            })

        # Save user message to DB
        await save_message_to_db(customer_id, "user", req.message, content_type="text")

        # Process chat directly using the shared chat processor
        # Import here to avoid circular dependency
        from src.orin_ai_crm.server.services.chat_processor import process_chat_request

        result = await process_chat_request(
            phone_number=req.phone_number,
            lid_number=None,
            message=req.message,
            contact_name=req.contact_name,
            is_new_chat=True,
            skip_user_save=True  # Already saved above
        )

        logger.info(f"Test chat processed for customer_id={customer_id}: {len(result.get('replies', []))} AI replies")

        return JSONResponse(content={
            "status": "success",
            "customer_id": customer_id,
            "message": "Message sent successfully",
            "ai_replies": len(result.get('replies', []))
        })

    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error sending message: {str(e)}")


@router.get("/test/chat/stream")
async def chat_stream(request: Request, customer_id: int):
    """
    SSE endpoint for real-time chat updates.

    Streams new messages as they are added to the database for this customer.
    """
    # Verify token
    test_token = request.cookies.get("test_token", "")
    if test_token != settings.freshchat_webhook_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    async def event_stream():
        """Generator function for SSE events."""
        last_message_id = 0
        connection_id = f"{customer_id}_{id(request)}"

        try:
            # Register this connection
            _active_sse_connections[connection_id] = {
                "customer_id": customer_id,
                "last_message_id": last_message_id
            }

            logger.info(f"SSE connection opened: {connection_id}")

            # Send initial keepalive
            yield f": keepalive\n\n"

            while True:
                try:
                    # Check for new messages
                    async with AsyncSessionLocal() as db:
                        query = (
                            select(ChatSession)
                            .where(
                                ChatSession.customer_id == customer_id,
                                ChatSession.id > last_message_id
                            )
                            .order_by(ChatSession.created_at.asc())
                            .limit(10)
                        )
                        result = await db.execute(query)
                        new_messages = result.scalars().all()

                    # Send new messages via SSE
                    for msg in new_messages:
                        message_data = {
                            "id": msg.id,
                            "role": msg.message_role,
                            "content": msg.content,
                            "content_type": msg.content_type,
                            "created_at": msg.created_at.isoformat() if msg.created_at else None,
                        }
                        yield f"event: message\n"
                        yield f"data: {json.dumps(message_data)}\n\n"

                        last_message_id = max(last_message_id, msg.id)

                    # Update connection state
                    if connection_id in _active_sse_connections:
                        _active_sse_connections[connection_id]["last_message_id"] = last_message_id

                    # Send keepalive every 15 seconds
                    yield f": keepalive\n\n"

                    # Wait before next poll
                    await asyncio.sleep(2)

                except asyncio.CancelledError:
                    logger.info(f"SSE connection cancelled: {connection_id}")
                    break
                except Exception as e:
                    logger.error(f"Error in SSE stream for {connection_id}: {str(e)}")
                    yield f"event: error\n"
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    await asyncio.sleep(5)

        finally:
            # Clean up connection
            if connection_id in _active_sse_connections:
                del _active_sse_connections[connection_id]
            logger.info(f"SSE connection closed: {connection_id}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.post("/test/reset")
async def reset_chat(request: Request, phone_number: str):
    """
    Reset chat for a phone number (soft delete customer).

    This is a testing feature to clear chat history.
    """
    from src.orin_ai_crm.core.agents.tools.db_tools import soft_delete_customer

    # Verify token
    test_token = request.cookies.get("test_token", "")
    if test_token != settings.freshchat_webhook_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = await soft_delete_customer(phone_number)

    return JSONResponse(content=result)
