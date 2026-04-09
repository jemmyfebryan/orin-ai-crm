"""
Chat agent endpoint using the agentic architecture.
"""
from fastapi import APIRouter, HTTPException

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.server.schemas.chat import ChatAgentRequest, ChatAgentResponse
from src.orin_ai_crm.server.services.chat_processor import process_chat_request

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat-agent", response_model=ChatAgentResponse)
async def chat_agent_endpoint(req: ChatAgentRequest):
    """
    NEW: Agentic endpoint using tool-calling architecture with 30+ granular tools.

    This endpoint allows the AI to:
    - Call multiple tools simultaneously for multi-intent messages
    - Handle complex customer requests more flexibly
    - Compose tools together (e.g., profile + answer products + book meeting in one turn)

    Tool Categories:
    - Customer Management (3 tools): get_or_create_customer, get_customer_profile, update_customer_data
    - Profiling (7 tools): extract info, check completeness, determine next field, generate questions, etc.
    - Sales & Meeting (6 tools): get meetings, extract details, book/update meetings, confirmations
    - Product & E-commerce (8 tools): get products, search, answer questions, get links, recommend
    - Support & Complaints (3 tools): classify issues, generate empathetic responses, trigger human takeover
    - Conversation (2 tools): thank you, conversation starters

    Example multi-intent message:
    "Saya Budi dari Surabaya, mau tanya GPS motor"
    → Agent will call: get_or_create_customer + extract_customer_info_from_message + search_products + answer_product_question
    """
    try:
        result = await process_chat_request(
            phone_number=req.phone_number,
            lid_number=req.lid_number,
            message=req.message,
            contact_name=req.contact_name,
            is_new_chat=req.is_new_chat,
            conversation_id=None  # /chat-agent endpoint doesn't have Freshchat conversation
        )

        return ChatAgentResponse(
            customer_id=result["customer_id"],
            phone_number=req.phone_number,
            lid_number=req.lid_number,
            reply=result["replies"][0] if result["replies"] else "",  # First bubble for backward compatibility
            replies=result["replies"],  # All bubbles
            tool_calls=result["tool_calls"],
            messages_count=result["messages_count"]
        )

    except ValueError as ve:
        # Validation error
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in chat-agent endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan pada server AI: {str(e)}")
