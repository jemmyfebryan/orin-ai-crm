"""
Orin Landing Agent API Routes

This module provides API endpoints for the orin_landing_agent.
Key features:
- Uses lid_number for customer identification (not phone_number)
- API-based (JSON request/response)
- Text-based only (no images/PDFs)
- human_takeover sends wa.me link (does NOT set database flag)
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from pathlib import Path

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.server.config.settings import settings
from src.orin_ai_crm.server.services.orin_landing_processor import process_orin_landing_request

logger = get_logger(__name__)
router = APIRouter()

# Setup templates directory
TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent.parent / "templates" / "orin_landing"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================================
# SCHEMAS
# ============================================================================

class OrinLandingChatRequest(BaseModel):
    """Orin Landing Agent chat request schema."""
    lid_number: str = Field(..., description="Customer's LID number for identification")
    message: str = Field(..., description="User's message")
    contact_name: Optional[str] = Field(None, description="Optional contact name")

    is_new_chat: bool = Field(False, description="Whether this is a new chat")


class OrinLandingChatResponse(BaseModel):
    """Orin Landing Agent chat response schema."""
    customer_id: Optional[int]
    lid_number: str
    reply: str  # First message from replies (for backward compatibility)
    replies: list[str]  # All WhatsApp bubble messages
    messages_count: int
    human_takeover: bool = False


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/orin-landing/chat", response_model=OrinLandingChatResponse)
async def orin_landing_chat_endpoint(req: OrinLandingChatRequest):
    """
    Orin Landing Agent API endpoint.

    This is a simplified, text-only version of the Hana AI agent designed for
    landing page interactions. Key features:

    - Uses lid_number for customer identification (not phone_number)
    - Text-based only (no images/PDFs in responses)
    - Limited support tools (forgot_password, get_company_profile, human_takeover)
    - human_takeover sends wa.me/6281329293939 link (does NOT set database flag)

    Example request:
    ```json
    {
        "lid_number": "customer_lid_123",
        "message": "Halo, saya mau tanya tentang GPS tracker",
        "contact_name": "Budi"
    }
    ```

    Example response:
    ```json
    {
        "customer_id": 123,
        "lid_number": "customer_lid_123",
        "reply": "Halo Kak Budi! Ada yang bisa saya bantu? 😊",
        "replies": ["Halo Kak Budi! Ada yang bisa saya bantu? 😊"],
        "messages_count": 1,
        "human_takeover": false
    }
    ```
    """
    try:
        logger.info(f"Orin Landing API request - lid: {req.lid_number}, message: {req.message[:50]}...")

        result = await process_orin_landing_request(
            lid_number=req.lid_number,
            message=req.message,
            contact_name=req.contact_name,
            skip_user_save=False,
        )

        return OrinLandingChatResponse(
            customer_id=result["customer_id"],
            lid_number=result["lid_number"],
            reply=result["replies"][0] if result["replies"] else "",
            replies=result["replies"],
            messages_count=result["messages_count"],
            human_takeover=result.get("human_takeover", False),
        )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in orin_landing chat endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan pada server: {str(e)}")


# ============================================================================
# TEST FRONTEND ENDPOINTS
# ============================================================================

def verify_test_token(request) -> bool:
    """Verify the test token from cookie."""
    test_token = request.cookies.get("test_token", "")
    return test_token == settings.freshchat_webhook_token


@router.get("/orin-landing/test", response_class=HTMLResponse)
async def orin_landing_test_login(request: Request):
    """Login page for orin_landing test interface."""
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None}
    )


@router.post("/orin-landing/test/login")
async def orin_landing_test_login_submit(request: Request, token: str = Form(...)):
    """Handle login form submission."""
    if token != settings.freshchat_webhook_token:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid token. Please check your FRESHCHAT_WEBHOOK_TOKEN."}
        )

    response = RedirectResponse(url="/orin-landing/test/setup", status_code=303)
    response.set_cookie(
        key="test_token",
        value=token,
        httponly=False,
        max_age=3600,
        samesite="lax"
    )
    return response


@router.get("/orin-landing/test/setup", response_class=HTMLResponse)
async def orin_landing_test_setup(request: Request):
    """Setup page for entering lid_number and contact name."""
    if not verify_test_token(request):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/orin-landing/test", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={"error": None}
    )


@router.post("/orin-landing/test/setup")
async def orin_landing_test_setup_submit(
    request: Request,
    lid_number: str = Form(...),
    contact_name: str = Form(...)
):
    """Handle setup form submission and redirect to chat interface."""
    if not verify_test_token(request):
        return RedirectResponse(url="/orin-landing/test", status_code=303)

    # Store customer info in cookie
    response = RedirectResponse(url="/orin-landing/test/chat", status_code=303)
    response.set_cookie(
        key="test_lid_number",
        value=lid_number,
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


@router.get("/orin-landing/test/chat", response_class=HTMLResponse)
async def orin_landing_test_chat(request: Request):
    """Orin Landing test chat interface."""
    if not verify_test_token(request):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/orin-landing/test", status_code=303)

    lid_number = request.cookies.get("test_lid_number", "")
    contact_name = request.cookies.get("test_contact_name", "")
    test_token = request.cookies.get("test_token", "")

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "lid_number": lid_number,
            "contact_name": contact_name,
            "test_token": test_token,
        }
    )


@router.get("/orin-landing/test/chat/history")
async def orin_landing_get_chat_history(request: Request, lid_number: str):
    """API endpoint to fetch chat history for a customer (by lid_number)."""
    if not verify_test_token(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Get customer by lid_number
    from src.orin_ai_crm.core.agents.tools.db_tools import get_or_create_customer
    from src.orin_ai_crm.core.agents.tools.db_tools import get_chat_history

    customer = await get_or_create_customer(
        phone_number=None,
        lid_number=lid_number,
        contact_name=None
    )
    customer_id = customer['customer_id']

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


@router.post("/orin-landing/test/chat/send")
async def orin_landing_send_message(request: Request, req: OrinLandingChatRequest):
    """API endpoint to send a message to the orin_landing_agent."""
    # Verify token from header
    test_token = request.headers.get("X-Test-Token", "")
    if test_token != settings.freshchat_webhook_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        result = await process_orin_landing_request(
            lid_number=req.lid_number,
            message=req.message,
            contact_name=req.contact_name,
            skip_user_save=False,
        )

        return JSONResponse(content={
            "status": "success",
            "customer_id": result["customer_id"],
            "lid_number": result["lid_number"],
            "message": "Message sent successfully",
            "ai_replies": len(result["replies"]),
            "replies": result["replies"],
            "human_takeover": result.get("human_takeover", False),
        })

    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error sending message: {str(e)}")


@router.post("/orin-landing/test/reset")
async def orin_landing_reset_chat(request: Request, lid_number: str):
    """Reset chat for a lid_number (soft delete customer)."""
    from src.orin_ai_crm.core.agents.tools.db_tools import soft_delete_customer_by_lid

    if not verify_test_token(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = await soft_delete_customer_by_lid(lid_number)

    return JSONResponse(content=result)
