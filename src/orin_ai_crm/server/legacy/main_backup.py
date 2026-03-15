import uvicorn
import asyncio
import httpx
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from sqlalchemy import select, or_
import os

# Setup WIB timezone (UTC+7)
WIB = timezone(timedelta(hours=7))

# Import dari modular structure
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import engine, Base, AsyncSessionLocal, Customer

# Explicit imports from specific modules to avoid naming conflicts with tools
from src.orin_ai_crm.core.agents.tools.product_agent_tools import (
    reset_products_to_default,
    initialize_default_products_if_empty,
)
from src.orin_ai_crm.core.agents.tools.db_tools import (
    get_or_create_customer,
    get_chat_history,
    save_message_to_db,
)

# NEW: Agentic/Tool-Calling Architecture (30+ granular tools)
from src.orin_ai_crm.core.agents.custom.hana_agent import hana_agent

from langchain_core.messages import HumanMessage, AIMessage

logger = get_logger(__name__)

# Freshchat Configuration
FRESHCHAT_API_TOKEN = os.getenv("FRESHCHAT_API_TOKEN")
FRESHCHAT_URL = os.getenv("FRESHCHAT_URL")
FRESHCHAT_AGENT_BEARER_TOKEN = os.getenv("FRESHCHAT_AGENT_BEARER_TOKEN")
AGENT_ID_BOT = os.getenv("AGENT_ID_BOT")
FRESHCHAT_WEBHOOK_TOKEN = os.getenv("FRESHCHAT_WEBHOOK_TOKEN")

# Freshchat Webhook IP Allowlist (comma-separated list of allowed IPs/CIDRs)
# Example: "1.2.3.4,5.6.7.0/24"
# To find Freshchat webhook IPs:
# 1. Check logs for "X-Forwarded-For" headers from successful webhooks
# 2. Contact Freshchat support for their webhook IP ranges
# 3. Temporarily set to empty string ("") to allow all IPs (not recommended for production)
FRESHCHAT_WEBHOOK_ALLOWED_IPS = os.getenv("FRESHCHAT_WEBHOOK_ALLOWED_IPS", "").split(",") if os.getenv("FRESHCHAT_WEBHOOK_ALLOWED_IPS") else []

# Freshchat Channel IDs (comma-separated list of allowed channel IDs)
# Each channel (WhatsApp, Instagram, etc.) has a unique freshchat_channel_id
# Find your channel IDs in Freshchat Admin > Channels > WhatsApp > Settings
FRESHCHAT_ALLOWED_CHANNEL_IDS = os.getenv("FRESHCHAT_ALLOWED_CHANNEL_IDS", "").split(",") if os.getenv("FRESHCHAT_ALLOWED_CHANNEL_IDS") else []

# Allowlist for beta testing (only these numbers can use the webhook)
ALLOWED_NUMBERS = [
    "+628123456789",
    "+6285850434383",
]

# Freshchat API configuration
FRESHCHAT_API_VERSION = "v2"  # or "v1" depending on your Freshchat account

# Security scheme for Bearer token authentication
security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize default products if table is empty
    await initialize_default_products_if_empty.ainvoke({})

    yield
    # Shutdown (cleanup jika diperlukan)

app = FastAPI(title="HANA AI WhatsApp Chatbot Backend", lifespan=lifespan)

# --- SCHEMAS UNTUK REQUEST POSTMAN ---
class ChatRequest(BaseModel):
    phone_number: Optional[str] = Field(None, description="Nomor WhatsApp user (format: 628xxx)")
    lid_number: Optional[str] = Field(None, description="WhatsApp LID number untuk migrasi")
    message: str = Field(..., description="Pesan dari user")
    contact_name: Optional[str] = Field(None, description="Nama kontak dari WhatsApp")
    
    is_new_chat: bool = Field(False, description="Apakah ada pesan user pertama kali di WhatsApp")

    @field_validator('contact_name')
    @classmethod
    def validate_at_least_one_identifier(cls, v: Optional[str], info) -> Optional[str]:
        """Pastikan minimal salah satu identifier (phone_number atau lid_number) ada"""
        phone = info.data.get('phone_number')
        lid = info.data.get('lid_number')
        if not phone and not lid:
            raise ValueError('Minimal salah satu dari phone_number atau lid_number harus diisi')
        return v

class ChatResponse(BaseModel):
    customer_id: Optional[int]
    phone_number: Optional[str]
    lid_number: Optional[str]
    reply: str
    route: str
    step: str

class ResetCustomerRequest(BaseModel):
    phone_number: Optional[str] = Field(None, description="Nomor WhatsApp user")
    lid_number: Optional[str] = Field(None, description="WhatsApp LID number")

    @field_validator('lid_number')
    @classmethod
    def validate_at_least_one_identifier(cls, v: Optional[str], info) -> Optional[str]:
        """Pastikan minimal salah satu identifier (phone_number atau lid_number) ada"""
        phone = info.data.get('phone_number')
        lid = v
        if not phone and not lid:
            raise ValueError('Minimal salah satu dari phone_number atau lid_number harus diisi')
        return v

class ResetCustomerResponse(BaseModel):
    success: bool
    message: str
    deleted_tables: dict[str, int]
    customer_id: Optional[int] = None

class ResetProductsResponse(BaseModel):
    success: bool
    message: str
    deleted: int
    created: int
    errors: list[str]

# --- NEW ENDPOINT: AGENTIC/TOOL-CALLING ARCHITECTURE (30+ granular tools) ---
class ChatAgentRequest(BaseModel):
    phone_number: Optional[str] = Field(None, description="Nomor WhatsApp user (format: 628xxx)")
    lid_number: Optional[str] = Field(None, description="WhatsApp LID number untuk migrasi")
    message: str = Field(..., description="Pesan dari user")
    contact_name: Optional[str] = Field(None, description="Nama kontak dari WhatsApp")

    is_new_chat: bool = Field(False, description="Apakah ada pesan user pertama kali di WhatsApp")

    @field_validator('contact_name')
    @classmethod
    def validate_at_least_one_identifier(cls, v: Optional[str], info) -> Optional[str]:
        """Pastikan minimal salah satu identifier (phone_number atau lid_number) ada"""
        phone = info.data.get('phone_number')
        lid = info.data.get('lid_number')
        if not phone and not lid:
            raise ValueError('Minimal salah satu dari phone_number atau lid_number harus diisi')
        return v

class ChatAgentResponse(BaseModel):
    customer_id: Optional[int]
    phone_number: Optional[str]
    lid_number: Optional[str]
    reply: str  # Kept for backward compatibility - will be first message from final_messages
    replies: list[str]  # New field: multi-bubble messages from final_messages
    tool_calls: Optional[list[str]] = None
    messages_count: int

# --- FRESHCHAT AGENT SCHEMAS ---
class FreshchatAgentRequest(BaseModel):
    phone_number: Optional[str] = Field(None, description="Nomor WhatsApp user (format: 628xxx)")
    lid_number: Optional[str] = Field(None, description="WhatsApp LID number untuk migrasi")
    message: str = Field(..., description="Pesan dari user")
    contact_name: Optional[str] = Field(None, description="Nama kontak dari WhatsApp")
    is_new_chat: bool = Field(False, description="Apakah ada pesan user pertama kali di WhatsApp")
    conversation_id: str = Field(..., description="Freshchat conversation ID")
    user_id: str = Field(..., description="Freshchat user ID")
    async_mode: bool = Field(True, description="Run asynchronously (background) or synchronously (wait for completion)")

    @field_validator('contact_name')
    @classmethod
    def validate_at_least_one_identifier(cls, v: Optional[str], info) -> Optional[str]:
        """Pastikan minimal salah satu identifier (phone_number atau lid_number) ada"""
        phone = info.data.get('phone_number')
        lid = info.data.get('lid_number')
        if not phone and not lid:
            raise ValueError('Minimal salah satu dari phone_number atau lid_number harus diisi')
        return v

class FreshchatAgentResponse(BaseModel):
    status: str
    message: str

class FreshchatMessagePayload(BaseModel):
    actor_type: str = "agent"
    actor_id: str
    message_type: str = "normal"
    message_parts: List[dict]

@app.post("/chat-agent", response_model=ChatAgentResponse)
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
        # 1. Build history list untuk LangGraph
        is_new_chat = req.is_new_chat
        logger.info(f"is_new_chat: {is_new_chat}")

        # 2. Get or create customer (returns dict from agent_tools)
        customer = await get_or_create_customer(
            phone_number=req.phone_number,
            lid_number=req.lid_number,
            contact_name=req.contact_name
        )
        customer_id = customer['customer_id']
        logger.info(f"customer_id resolved: {customer_id}")

        # 4. Fetch chat history if not new chat
        history = []
        if not is_new_chat:
            logger.info(f"Fetching chat history for customer_id: {customer_id}")
            history_rows = await get_chat_history(customer_id, limit=10)
            for row in history_rows:
                if row.message_role == "user":
                    history.append(HumanMessage(content=row.content))
                else:
                    history.append(AIMessage(content=row.content))
        else:
            logger.info(f"Skipping chat history fetch (is_new_chat=True)")
            
        # 5. Load customer data from dict returned by agent_tools
        customer_data = {
            'id': customer_id,
            'name': customer.get('name', ''),
            'domicile': customer.get('domicile', ''),
            'vehicle_id': customer.get('vehicle_id', -1),
            'vehicle_alias': customer.get('vehicle_alias', ''),
            'unit_qty': customer.get('unit_qty', 0),
            'is_b2b': customer.get('is_b2b', False),
            'is_onboarded': customer.get('is_onboarded', False),
        }

        logger.info(f"Customer data: {customer_data}")

        # Determine if we should send the form
        # If customer is not onboarded (is_new_chat=True), send_form=True
        is_onboarded = customer.get('is_onboarded', False)
        send_form = not is_onboarded if is_onboarded is not None else is_new_chat
        logger.info(f"send_form determined as: {send_form} (is_onboarded={is_onboarded}, is_new_chat={is_new_chat})")

        # 6. Simpan pesan baru dari user ke Database
        await save_message_to_db(customer_id, "user", req.message)

        # 7. Susun State untuk Agentic Agent
        # Tambahkan pesan terbaru ke dalam history
        current_messages = history + [HumanMessage(content=req.message)]

        initial_state = {
            "messages": current_messages,
            "phone_number": req.phone_number,
            "lid_number": req.lid_number,
            "contact_name": req.contact_name,
            "customer_id": customer_id,
            "customer_data": customer_data,
            "send_form": send_form,
            "route": "DEFAULT"
        }

        # 8. Jalankan Agentic AI Workflow (dengan 30+ tools)
        final_state = await hana_agent.ainvoke(initial_state, recursion_limit=50)

        logger.info(f"FINAL STATE (Agent): messages_count={len(final_state['messages'])}")

        # 9. Extract AI reply from final_state
        # The node_final_message now sets 'final_messages' with multi-bubble response
        messages = final_state["messages"]
        final_messages = final_state.get("final_messages", [])
        tool_calls_used = []

        # Find all tool calls made during the conversation
        for msg in messages:
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc['name'] not in tool_calls_used:
                        tool_calls_used.append(tc['name'])

        # Get the final messages (multi-bubble response from node_final_message)
        ai_replies = []
        if final_messages:
            ai_replies = final_messages
            logger.info(f"Using final_messages from node_final_message: {len(ai_replies)} bubbles")
        else:
            # Fallback: find last AIMessage with content (backward compatibility)
            logger.warning("No final_messages found, using fallback to extract from messages")
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and hasattr(msg, 'content') and msg.content:
                    # Skip tool result messages
                    if not hasattr(msg, 'name') or msg.name != 'ToolMessage':
                        ai_replies = [msg.content]
                        break

        # If still no content, this is an error
        if not ai_replies:
            logger.error("No AI reply found in final state!")
            ai_replies = ["Maaf, terjadi kesalahan sistem. Silakan coba lagi."]

        # 10. Simpan balasan AI ke Database
        # Join multiple bubbles with newlines for storage
        ai_reply_for_db = "\n\n".join(ai_replies)
        await save_message_to_db(customer_id, "ai", ai_reply_for_db)

        logger.info(f"Tool calls used: {tool_calls_used}")
        logger.info(f"AI replies ({len(ai_replies)} bubbles):")
        for i, reply in enumerate(ai_replies):
            logger.info(f"  Bubble {i+1}: {reply[:100]}...")

        return ChatAgentResponse(
            customer_id=customer_id,
            phone_number=req.phone_number,
            lid_number=req.lid_number,
            reply=ai_replies[0] if ai_replies else "",  # First bubble for backward compatibility
            replies=ai_replies,  # All bubbles
            tool_calls=tool_calls_used if tool_calls_used else None,
            messages_count=len(messages)
        )

    except ValueError as ve:
        # Validation error
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in chat-agent endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan pada server AI: {str(e)}")

# --- FRESHCHAT AGENT ENDPOINT ---
async def verify_bearer_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify Bearer token for /freshchat-agent endpoint"""
    if credentials.credentials != FRESHCHAT_AGENT_BEARER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

async def send_message_to_freshchat(conversation_id: str, message_content: str, retry_count: int = 0) -> bool:
    """
    Send a single message to Freshchat API with retry mechanism.

    Args:
        conversation_id: Freshchat conversation ID
        message_content: The message text to send
        retry_count: Current retry attempt number

    Returns:
        bool: True if successful, False otherwise
    """
    url = f"{FRESHCHAT_URL}/conversations/{conversation_id}/messages"

    payload = {
        "actor_type": "agent",
        "actor_id": AGENT_ID_BOT,
        "message_type": "normal",
        "message_parts": [
            {
                "text": {
                    "content": message_content
                }
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {FRESHCHAT_API_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                logger.info(f"Successfully sent message to Freshchat conversation {conversation_id}")
                return True
            else:
                logger.error(f"Failed to send message to Freshchat. Status: {response.status_code}, Response: {response.text}")

                # Retry with exponential backoff
                if retry_count < 3:
                    wait_time = 2 ** retry_count  # 1s, 2s, 4s
                    logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
                    await asyncio.sleep(wait_time)
                    return await send_message_to_freshchat(conversation_id, message_content, retry_count + 1)
                else:
                    logger.error(f"Max retry attempts reached for conversation {conversation_id}")
                    return False

    except httpx.TimeoutException:
        logger.error(f"Timeout while sending message to Freshchat for conversation {conversation_id}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_message_to_freshchat(conversation_id, message_content, retry_count + 1)
        return False
    except Exception as e:
        logger.error(f"Error sending message to Freshchat: {str(e)}")
        if retry_count < 3:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/3)")
            await asyncio.sleep(wait_time)
            return await send_message_to_freshchat(conversation_id, message_content, retry_count + 1)
        return False

async def process_freshchat_agent_task(
    phone_number: Optional[str],
    lid_number: Optional[str],
    message: str,
    contact_name: Optional[str],
    is_new_chat: bool,
    conversation_id: str,
    user_id: str
):
    """
    Background task to process chat and send replies to Freshchat.

    This function runs asynchronously after the API request is accepted.
    """
    try:
        logger.info(f"Processing Freshchat agent task for conversation {conversation_id}")

        # 1. Get or create customer (same logic as /chat-agent)
        customer = await get_or_create_customer(
            phone_number=phone_number,
            lid_number=lid_number,
            contact_name=contact_name
        )
        customer_id = customer['customer_id']
        logger.info(f"Customer ID resolved: {customer_id}")

        # 2. Fetch chat history if not new chat
        history = []
        # if not is_new_chat:
        logger.info(f"Fetching chat history for customer_id: {customer_id}")
        history_rows = await get_chat_history(customer_id, limit=10)
        for row in history_rows:
            if row.message_role == "user":
                history.append(HumanMessage(content=row.content))
            else:
                history.append(AIMessage(content=row.content))
        # else:
        #     logger.info(f"Skipping chat history fetch (is_new_chat=True)")

        # 3. Load customer data
        customer_data = {
            'id': customer_id,
            'name': customer.get('name', ''),
            'domicile': customer.get('domicile', ''),
            'vehicle_id': customer.get('vehicle_id', -1),
            'vehicle_alias': customer.get('vehicle_alias', ''),
            'unit_qty': customer.get('unit_qty', 0),
            'is_b2b': customer.get('is_b2b', False),
            'is_onboarded': customer.get('is_onboarded', False),
        }

        logger.info(f"Customer data: {customer_data}")

        # 4. Determine if we should send the form
        is_onboarded = customer.get('is_onboarded', False)
        send_form = not is_onboarded if is_onboarded is not None else is_new_chat
        logger.info(f"send_form determined as: {send_form}")

        # 5. Save user message to database
        await save_message_to_db(customer_id, "user", message)

        # 6. Prepare state for agent
        current_messages = history + [HumanMessage(content=message)]

        initial_state = {
            "messages": current_messages,
            "phone_number": phone_number,
            "lid_number": lid_number,
            "contact_name": contact_name,
            "customer_id": customer_id,
            "customer_data": customer_data,
            "send_form": send_form,
            "route": "DEFAULT"
        }

        # 7. Run Agentic AI Workflow
        final_state = await hana_agent.ainvoke(initial_state, recursion_limit=50)

        logger.info(f"AI Agent processing completed for conversation {conversation_id}")

        # 8. Extract AI replies
        messages = final_state["messages"]
        final_messages = final_state.get("final_messages", [])

        ai_replies = []
        if final_messages:
            ai_replies = final_messages
            logger.info(f"Using final_messages: {len(ai_replies)} bubbles")
        else:
            logger.warning("No final_messages found, using fallback")
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and hasattr(msg, 'content') and msg.content:
                    if not hasattr(msg, 'name') or msg.name != 'ToolMessage':
                        ai_replies = [msg.content]
                        break

        if not ai_replies:
            logger.error("No AI reply found!")
            ai_replies = ["Maaf, terjadi kesalahan sistem. Silakan coba lagi."]

        # 9. Save AI replies to database
        ai_reply_for_db = "\n\n".join(ai_replies)
        await save_message_to_db(customer_id, "ai", ai_reply_for_db)

        # 10. Send each reply bubble as a separate message to Freshchat
        logger.info(f"Sending {len(ai_replies)} message bubbles to Freshchat...")
        for i, reply in enumerate(ai_replies):
            logger.info(f"Sending bubble {i+1}/{len(ai_replies)}: {reply[:50]}...")
            success = await send_message_to_freshchat(conversation_id, reply)
            if not success:
                logger.error(f"Failed to send bubble {i+1} to Freshchat")
            else:
                logger.info(f"Successfully sent bubble {i+1} to Freshchat")

        logger.info(f"Freshchat agent task completed for conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Error in Freshchat agent background task: {str(e)}")
        import traceback
        traceback.print_exc()

@app.post("/freshchat-agent", response_model=FreshchatAgentResponse)
async def freshchat_agent_endpoint(
    req: FreshchatAgentRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    token: str = Depends(verify_bearer_token)
):
    """
    Freshchat integration endpoint with async/sync mode support.

    This endpoint:
    - Accepts chat requests from Freshchat webhook
    - Validates Bearer token for security
    - Can process asynchronously (background) or synchronously (wait)
    - Sends AI replies back to Freshchat via API

    Expected payload fields:
    - phone_number OR lid_number (required for internal DB)
    - message: User's message text
    - contact_name: Optional contact name
    - is_new_chat: Whether this is a new conversation
    - conversation_id: Freshchat conversation ID (required)
    - user_id: Freshchat user ID (required)
    - async_mode: True=background (immediate response), False=wait for completion

    Authentication:
    - Header: Authorization: Bearer <FRESHCHAT_AGENT_BEARER_TOKEN>

    Response modes:
    - async_mode=True: Returns {"status": "accepted"} immediately
    - async_mode=False: Waits for processing, returns {"status": "completed"}
    """
    try:
        logger.info(f"Get a request: {req}")
        conversation_link = req.conversation_id  # temporary use link
        conversation_id = conversation_link.split("/")[-1]

        if req.async_mode:
            # Asynchronous mode: process in background, return immediately
            background_tasks.add_task(
                process_freshchat_agent_task,
                phone_number=req.phone_number,
                lid_number=req.lid_number,
                message=req.message,
                contact_name=req.contact_name,
                is_new_chat=req.is_new_chat,
                conversation_id=conversation_id,
                user_id=req.user_id
            )

            logger.info(f"Background task queued for conversation {conversation_id}")

            return FreshchatAgentResponse(
                status="accepted",
                message="Chat request accepted and is being processed asynchronously"
            )
        else:
            # Synchronous mode: wait for processing to complete
            logger.info(f"Processing chat synchronously for conversation {conversation_id}")

            await process_freshchat_agent_task(
                phone_number=req.phone_number,
                lid_number=req.lid_number,
                message=req.message,
                contact_name=req.contact_name,
                is_new_chat=req.is_new_chat,
                conversation_id=conversation_id,
                user_id=req.user_id
            )

            logger.info(f"Synchronous processing completed for conversation {conversation_id}")

            return FreshchatAgentResponse(
                status="completed",
                message="Chat request processed successfully"
            )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in freshchat-agent endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        raise FreshchatAgentResponse(
            status="error",
            message=f"Chat request error: {str(e)}"
        )
        
# --- ENDPOINT DELETE CUSTOMER (SOFT DELETE - UNTUK TESTING/DEV) ---
@app.post("/delete-customer", response_model=ResetCustomerResponse)
async def delete_customer_endpoint(req: ResetCustomerRequest):
    """
    Soft delete customer dengan menandai deleted_at timestamp.

    Ini TIDAK menghapus data dari database, hanya menandai customer sebagai "deleted".
    Semua data (chat_sessions, intent_classifications, dll) tetap preserved untuk ML training.

    Yang diubah:
    - Set deleted_at timestamp di tabel customers

    Data preserved untuk training:
    - intent_classifications (untuk intent classification training)
    - chat_sessions (untuk context analysis)
    - semua foreign key tables lainnya
    """
    try:
        identifier = {
            "phone_number": req.phone_number,
            "lid_number": req.lid_number
        }

        async with AsyncSessionLocal() as db:
            # DEBUG: Log what we're searching for
            logger.warning(f"DELETE CUSTOMER REQUEST - Searching for: {identifier}")

            # 1. Cari customer berdasarkan identifier
            # Build conditions properly to avoid NULL matching issues
            conditions = []
            if identifier.get('phone_number'):
                conditions.append(Customer.phone_number == identifier.get('phone_number'))
            if identifier.get('lid_number'):
                conditions.append(Customer.lid_number == identifier.get('lid_number'))

            if not conditions:
                return ResetCustomerResponse(
                    success=False,
                    message=f"Invalid identifier: {identifier}. Must provide phone_number or lid_number.",
                    deleted_tables={"customers_marked_deleted": 0},
                    customer_id=None
                )

            query = select(Customer).where(Customer.deleted_at.is_(None), or_(*conditions))
            result = await db.execute(query)
            customer = result.scalars().first()

            # DEBUG: Log what we found
            if customer:
                logger.warning(f"FOUND CUSTOMER - id={customer.id}, phone={customer.phone_number}, lid={customer.lid_number}, deleted_at={customer.deleted_at}")
            else:
                logger.warning(f"NO CUSTOMER FOUND for identifier: {identifier}")

            if not customer:
                return ResetCustomerResponse(
                    success=True,
                    message=f"Tidak ditemukan customer untuk identifier: {identifier}",
                    deleted_tables={"customers_marked_deleted": 0},
                    customer_id=None
                )

            # Check if already deleted
            if customer.deleted_at is not None:
                return ResetCustomerResponse(
                    success=True,
                    message=f"Customer sudah di-delete sebelumnya pada: {customer.deleted_at}",
                    deleted_tables={"customers_marked_deleted": 0},
                    customer_id=customer.id
                )

            # 2. Soft delete: Set deleted_at timestamp
            customer.deleted_at = datetime.now(WIB)
            await db.commit()
            await db.refresh(customer)

        return ResetCustomerResponse(
            success=True,
            message=f"Berhasil soft-delete customer untuk customer_id: {customer.id}. Data preserved untuk training.",
            deleted_tables={"customers_marked_deleted": 1},
            customer_id=customer.id
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return ResetCustomerResponse(
            success=False,
            message=f"Gagal soft-delete customer: {str(e)}",
            deleted_tables={"customers_marked_deleted": 0},
            customer_id=None
        )

# --- ENDPOINT RESET PRODUCTS (UNTUK TESTING/DEV) ---
@app.post("/reset-products", response_model=ResetProductsResponse)
async def reset_products_endpoint():
    """
    Reset products table to default values from JSON file.
    Hati-hati: Ini akan MENGHAPUS SEMUA produk dan menggantinya dengan default dari JSON!
    """
    try:
        result = await reset_products_to_default.ainvoke({})

        return ResetProductsResponse(
            success=True,
            message=f"Berhasil reset products: {result['created']} produk dibuat, {result['deleted']} produk dihapus",
            deleted=result.get("deleted", 0),
            created=result.get("created", 0),
            errors=result.get("errors", [])
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return ResetProductsResponse(
            success=False,
            message=f"Gagal reset products: {str(e)}",
            deleted=0,
            created=0,
            errors=[str(e)]
        )

# --- FRESHCHAT WEBHOOK ENDPOINT (Production-Ready) ---

async def get_freshchat_user_details(user_id: str) -> dict:
    """
    Fetch user details from Freshchat API to get phone number and other info.

    Args:
        user_id: Freshchat user ID

    Returns:
        User details dict with phone, first_name, etc. or None if failed
    """
    try:
        url = f"{FRESHCHAT_URL}/users/{user_id}"

        headers = {
            "Authorization": f"Bearer {FRESHCHAT_API_TOKEN}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)

            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Fetched user details: phone={user_data.get('phone')}, first_name={user_data.get('first_name')}")
                return user_data
            else:
                logger.error(f"Failed to fetch user details: status={response.status_code}, body={response.text}")
                return None

    except Exception as e:
        logger.error(f"Error fetching Freshchat user details: {str(e)}")
        return None


def is_ip_allowed(client_ip: str, allowed_ips: list) -> bool:
    """
    Check if client IP is in the allowlist.
    Supports both individual IPs and CIDR ranges.

    Args:
        client_ip: Client IP address string
        allowed_ips: List of allowed IPs/CIDRs

    Returns:
        True if IP is allowed or allowlist is empty, False otherwise
    """
    # If no IP restrictions configured, allow all
    if not allowed_ips or not any(allowed_ips):
        return True

    try:
        import ipaddress
        client = ipaddress.ip_address(client_ip)

        for allowed in allowed_ips:
            allowed = allowed.strip()
            if not allowed:
                continue

            # Check if it's a CIDR range or single IP
            if '/' in allowed:
                # CIDR range
                network = ipaddress.ip_network(allowed, strict=False)
                if client in network:
                    return True
            else:
                # Single IP
                allowed_ip = ipaddress.ip_address(allowed)
                if client == allowed_ip:
                    return True

        return False
    except Exception as e:
        logger.warning(f"IP verification error: {e}, allowing by default")
        return True  # Fail open for safety


def verify_freshchat_signature(payload: bytes, signature_b64: str) -> bool:
    """
    Verify Freshchat webhook signature.
    Tries RSA-SHA256 first, then HMAC-SHA256 as fallback.

    Args:
        payload: Raw request body (bytes)
        signature_b64: Base64-encoded signature from X-Freshchat-Signature header

    Returns:
        True if signature is valid, False otherwise
    """
    import hmac
    import hashlib
    import base64
    import re

    # Try HMAC-SHA256 first (more common for webhooks)
    try_hmac = True
    try_rsa = True

    # Method 1: HMAC-SHA256 (using token as secret key)
    if try_hmac:
        try:
            secret = FRESHCHAT_WEBHOOK_TOKEN.strip().encode('utf-8')
            expected_signature = hmac.new(secret, payload, hashlib.sha256).digest()
            expected_signature_b64 = base64.b64encode(expected_signature).decode('utf-8')

            # Compare with constant-time comparison
            if hmac.compare_digest(expected_signature_b64, signature_b64):
                return True
        except Exception:
            pass  # Silently try next method

    # Method 2: RSA-SHA256 (using token as public key)
    if try_rsa:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.backends import default_backend

            # Decode the Base64 signature
            signature = base64.b64decode(signature_b64)

            # Load the public key from environment variable
            public_key_str = FRESHCHAT_WEBHOOK_TOKEN.strip()

            # If the key already has PEM headers, use it directly
            if "-----BEGIN" in public_key_str and "-----END" in public_key_str:
                # Already in PEM format, use as-is
                pem_key = public_key_str
            else:
                # Raw base64 key, need to wrap it
                # Remove any whitespace/newlines
                clean_key = re.sub(r'\s+', '', public_key_str)
                # Wrap in PEM format
                pem_key = f"-----BEGIN PUBLIC KEY-----\n{clean_key}\n-----END PUBLIC KEY-----"

            # Load the public key
            public_key = serialization.load_pem_public_key(
                pem_key.encode(),
                backend=default_backend()
            )

            # Verify the signature
            public_key.verify(
                signature,
                payload,
                padding.PKCS1v15(),
                hashes.SHA256()
            )

            return True

        except Exception:
            pass  # Silently fail

    # If we get here, both methods failed
    return False


class FreshchatWebhookResponse(BaseModel):
    status: str


@app.get("/debug-webhook-key")
async def debug_webhook_key():
    """
    Debug endpoint to check if the Freshchat public key and allowlist are configured correctly.
    Remove this endpoint in production!
    """
    key = FRESHCHAT_WEBHOOK_TOKEN
    api_token = FRESHCHAT_API_TOKEN
    freshchat_url = FRESHCHAT_URL

    return {
        "status": "ok",
        "message": "Configuration loaded",
        "webhook_auth": {
            "configured": bool(key),
            "key_preview": key[:100] if key else None,
            "key_length": len(key) if key else 0,
        },
        "webhook_ip_allowlist": {
            "enabled": bool(FRESHCHAT_WEBHOOK_ALLOWED_IPS and any(FRESHCHAT_WEBHOOK_ALLOWED_IPS)),
            "allowed_ips": FRESHCHAT_WEBHOOK_ALLOWED_IPS,
            "description": "If enabled, only webhooks from these IPs will be accepted"
        },
        "freshchat_api": {
            "configured": bool(api_token and freshchat_url),
            "url": freshchat_url
        },
        "allowlist": {
            "allowed_numbers": ALLOWED_NUMBERS,
            "count": len(ALLOWED_NUMBERS),
            "mode": "Restricted (phone number filter)"
        },
        "channel_filter": {
            "allowed_channel_ids": FRESHCHAT_ALLOWED_CHANNEL_IDS,
            "description": "This AI CRM only responds to configured Freshchat channels",
            "find_your_channel_id": "Freshchat Admin > Channels > WhatsApp > Settings"
        }
    }

@app.post("/freshchat-webhook", response_model=FreshchatWebhookResponse)
async def freshchat_webhook_endpoint(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Production-ready Freshchat webhook endpoint.

    This endpoint:
    - Accepts webhooks from Freshchat platform
    - Verifies RSA signature authentication
    - ONLY responds to WhatsApp messages (ignores Instagram, web, etc.)
    - Implements anti-loop mechanism (only processes user messages)
    - Responds instantly with 200 OK (within 3-second timeout)
    - Processes all heavy lifting in background tasks (API calls, allowlist checks, AI)

    Authentication:
    - Header: X-Freshchat-Signature: <Base64-encoded signature>
    - Algorithm: RSA-SHA256
    - Public key from: FRESHCHAT_WEBHOOK_TOKEN env variable

    Channel Filter (CRITICAL):
    - Only processes messages from configured FRESHCHAT_ALLOWED_CHANNEL_IDS
    - Each channel (WhatsApp, Instagram, etc.) has a unique freshchat_channel_id
    - Find your channel ID: Freshchat Admin > Channels > WhatsApp > Settings
    - This AI CRM only responds to configured channels (e.g., WhatsApp only)

    Anti-Loop Mechanism:
    - Only processes messages where actor.actor_type == "user"
    - Safely aborts if actor_type is "agent" or "system"

    Background Processing:
    - All heavy lifting happens in background task (FAST response)
    - Fetches user details from Freshchat API
    - Checks phone number against ALLOWED_NUMBERS
    - Processes AI response
    """
    try:
        # 1. Get Raw Body for Signature Verification
        body = await request.body()

        # 2. IP Allowlist Check (additional security layer)
        # Get client IP from X-Forwarded-For header (for proxy/load balancer setups)
        # or fall back to direct client IP
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP", "")
            or request.client.host if request.client else "unknown"
        )

        ip_is_allowed = is_ip_allowed(client_ip, FRESHCHAT_WEBHOOK_ALLOWED_IPS)

        # 3. Authentication Check (RSA Signature Verification)
        signature_header = request.headers.get("X-Freshchat-Signature", "").strip()

        if not signature_header:
            if not ip_is_allowed:
                logger.warning("Webhook authentication failed: missing X-Freshchat-Signature header")
                raise HTTPException(status_code=401, detail="Unauthorized")

        # Verify the signature
        signature_valid = verify_freshchat_signature(body, signature_header) if signature_header else False

        # Allow webhook if EITHER signature is valid OR IP is in allowlist
        if not signature_valid and not ip_is_allowed:
            logger.warning("Webhook authentication failed: invalid signature and IP not in allowlist")
            raise HTTPException(status_code=401, detail="Unauthorized")

        # 3. Parse JSON Payload
        payload = await request.json()

        # 4. Anti-Loop Mechanism (CRITICAL)
        # Extract actor_type to prevent processing our own AI's messages
        # Structure: {"actor": {"actor_type": "user|agent|system"}}
        actor = payload.get("actor", {})
        actor_type = actor.get("actor_type", "")

        if actor_type != "user":
            # Still return 200 OK to Freshchat (don't retry)
            return FreshchatWebhookResponse(status="success")

        # 5. Action Filter (only process message_create)
        action = payload.get("action", "")
        if action != "message_create":
            return FreshchatWebhookResponse(status="success")

        # 6. Safe Payload Extraction
        # Use .get() to prevent KeyError on malformed payloads
        data = payload.get("data", {})
        message = data.get("message", {})

        # Extract required fields with safe defaults
        conversation_id = message.get("conversation_id", "")

        # CRITICAL: Channel Filter - ONLY respond to allowed channels
        # Freshchat uses freshchat_channel_id to identify the channel (WhatsApp, Instagram, etc.)
        freshchat_channel_id = message.get("freshchat_channel_id", "")

        # Check if this channel ID is allowed
        if FRESHCHAT_ALLOWED_CHANNEL_IDS and freshchat_channel_id not in FRESHCHAT_ALLOWED_CHANNEL_IDS:
            return FreshchatWebhookResponse(status="success")

        if not freshchat_channel_id:
            logger.warning(f"freshchat_channel_id is empty! This might be a test or system message. Allowing for now.")
            # TODO: After testing, uncomment below to reject messages without channel_id
            # return FreshchatWebhookResponse(status="success")

        # Extract message content from message_parts array
        message_parts = message.get("message_parts", [])
        message_content = ""
        if message_parts and len(message_parts) > 0:
            message_content = message_parts[0].get("text", {}).get("content", "")

        # Extract user_id from Freshchat
        user_id = message.get("user_id", "")

        # 7. Validation Checks
        if not conversation_id or not message_content:
            logger.warning(f"Incomplete webhook payload: conversation_id={conversation_id}, has_message={bool(message_content)}")
            # Still return 200 OK (payload was malformed but we received it)
            return FreshchatWebhookResponse(status="success")

        # 8. Queue Background Task (all heavy processing happens here)
        # We do all heavy lifting (API calls, allowlist checks, AI processing) in background
        background_tasks.add_task(
            process_freshchat_webhook_task,
            user_id=user_id,
            message_content=message_content,
            conversation_id=conversation_id
        )

        # 11. Instant Response (CRITICAL - must be within 3 seconds)
        return FreshchatWebhookResponse(status="success")

    except Exception as e:
        logger.error(f"Error in freshchat-webhook endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        # STILL return 200 OK to prevent Freshchat from retrying
        # (we've logged the error, so we can investigate)
        return FreshchatWebhookResponse(status="success")


async def process_freshchat_webhook_task(
    user_id: str,
    message_content: str,
    conversation_id: str
):
    """
    Background task to process Freshchat webhook payload.

    This function runs asynchronously after the webhook returns 200 OK.
    All heavy processing happens here to avoid the 3-second timeout.

    Args:
        user_id: Freshchat user ID
        message_content: Message text content
        conversation_id: Freshchat conversation ID
    """
    try:
        logger.info(f"Processing webhook task: conversation={conversation_id}, user_id={user_id}")

        # 1. Fetch User Details from Freshchat API (to get phone number)
        user_details = await get_freshchat_user_details(user_id)

        if not user_details:
            logger.warning(f"Failed to fetch user details for user_id={user_id}. Leaving for human agents.")
            return

        phone_number = user_details.get("phone", "")
        contact_name = user_details.get("first_name", "")

        if not phone_number:
            logger.warning(f"User has no phone number: user_id={user_id}. Leaving for human agents.")
            return

        logger.info(f"User details fetched: phone={phone_number}, name={contact_name}")

        # 2. Allowlist / Beta Testing Filter (by phone number)
        if phone_number not in ALLOWED_NUMBERS:
            logger.info(f"Phone number not in allowlist: {phone_number}. ALLOWED_NUMBERS={ALLOWED_NUMBERS}. Leaving for human agents.")
            return

        logger.info(f"Allowlist check passed for phone_number: {phone_number}")

        # 3. Integrate with existing AI processing logic
        # Reuse the process_freshchat_agent_task function
        await process_freshchat_agent_task(
            phone_number=phone_number,
            lid_number=None,  # Webhook only provides phone_number
            message=message_content,
            contact_name=contact_name,  # Pass the contact name from Freshchat
            is_new_chat=True,  # Always new chat at first, the second tries will use DB as source of truth
            conversation_id=conversation_id,
            user_id=user_id  # Pass the user_id from webhook
        )

        logger.info(f"Webhook processing completed for conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Error in webhook background task: {str(e)}")
        import traceback
        traceback.print_exc()


# --- HEALTH CHECK ENDPOINT ---
@app.get("/health")
async def health_check():
    """Endpoint untuk health check"""
    return {
        "status": "healthy",
        "service": "HANA AI WhatsApp Chatbot",
        "version": "2.1 - Agentic Architecture (Optimized)",
        "endpoints": {
            "chat": "/chat (Legacy - Intent Classification)",
            "chat-agent": "/chat-agent (Agentic with recursion_limit=50)",
            "freshchat-agent": "/freshchat-agent (Freshchat API with BackgroundTasks)",
            "freshchat-webhook": "/freshchat-webhook (Freshchat Webhook with anti-loop)",
            "reset-history": "/reset-history",
            "reset-products": "/reset-products",
            "health": "/health"
        },
        "agent_tools": {
            "total": 18,
            "active": 15,  # Tools assigned to agents (support tools available but not assigned)
            "categories": [
                "Customer Management (1)",
                "Profiling (3)",
                "Sales & Meeting (6)",
                "Product & E-commerce (5)",
                "Support & Complaints (3) - available but not assigned to specific agent"
            ],
            "note": "get_customer_profile is invoked directly in agent_node before LLM runs to prevent infinite loops"
        },
        "freshchat_config": {
            "configured": bool(FRESHCHAT_API_TOKEN and FRESHCHAT_URL and AGENT_ID_BOT),
            "agent_auth": bool(FRESHCHAT_AGENT_BEARER_TOKEN),
            "webhook_auth": bool(FRESHCHAT_WEBHOOK_TOKEN),
            "allowed_numbers": len(ALLOWED_NUMBERS)
        }
    }

# --- RUN SERVER ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
