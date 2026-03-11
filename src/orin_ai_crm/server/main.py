import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from sqlalchemy import select, or_, delete, inspect

# Import dari modular structure
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.models.database import engine, Base, AsyncSessionLocal, ChatSession, Customer

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

# OLD: Intent Classification Architecture (Legacy)
# from src.orin_ai_crm.core.agents.custom.hana_agent import hana_bot

# NEW: Agentic/Tool-Calling Architecture (30+ granular tools)
from src.orin_ai_crm.core.agents.custom.hana_agent import hana_agent

from langchain_core.messages import HumanMessage, AIMessage

logger = get_logger(__name__)

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

class ResetHistoryRequest(BaseModel):
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

class ResetHistoryResponse(BaseModel):
    success: bool
    message: str
    deleted_count: int
    customer_id: Optional[int] = None

class ResetProductsResponse(BaseModel):
    success: bool
    message: str
    deleted: int
    created: int
    errors: list[str]

# --- ENDPOINT UTAMA (OLD - Intent Classification Architecture) ---
# @app.post("/chat", response_model=ChatResponse)
# async def chat_endpoint(req: ChatRequest):
#     """
#     Legacy endpoint using intent classification architecture.
#     Use /chat-agent for the new agentic architecture with 30+ tools.
#     """
#     try:
#         # 1. Build identifier dict
#         identifier = {
#             "phone_number": req.phone_number,
#             "lid_number": req.lid_number
#         }

#         # 3. Build history list untuk LangGraph
#         is_new_chat = req.is_new_chat

#         # 2. Get or create customer (returns detached object)
#         customer = await get_or_create_customer(
#             identifier=identifier,
#             contact_name=req.contact_name,
#             is_onboarded=(not is_new_chat),
#         )
#         customer_id = customer.id

#         # If not new chat, try to fetch data from DB
#         # If there is no chat history in DB but the request is not a new chat
#         history = []
#         if not is_new_chat:
#             history_rows = await get_chat_history(customer_id)
#             for row in history_rows:
#                 if row.message_role == "user":
#                     history.append(HumanMessage(content=row.content))
#                 else:
#                     history.append(AIMessage(content=row.content))

#         # 5. Load customer data from database
#         customer_data = {}
#         if customer.id:
#             customer_data["id"] = customer_id
#         if customer.name:
#             customer_data["name"] = customer.name
#         if customer.domicile:
#             customer_data["domicile"] = customer.domicile
#         if customer.vehicle_id:
#             customer_data["vehicle_id"] = customer.vehicle_id
#         if customer.vehicle_alias:
#             customer_data["vehicle_alias"] = customer.vehicle_alias
#         if customer.unit_qty:
#             customer_data["unit_qty"] = customer.unit_qty
#         if customer.is_onboarded:
#             customer_data["is_onboarded"] = customer.is_onboarded
#         customer_data["is_b2b"] = customer.is_b2b if customer.is_b2b else False

#         logger.info(f"Customer data: {customer_data}")

#         # Check if form was already submitted (we have complete data)
#         is_data_filled = (
#             customer_data.get("domicile") or
#             customer_data.get("vehicle_alias") or
#             customer_data.get("unit_qty", 0) > 0
#         )
#         if is_data_filled:
#             logger.info(f"Customer has complete data - form_submitted=True")
#         customer_data["is_filled"] = is_data_filled

#         # Determine if we should send the form
#         # If customer is not onboarded (is_new_chat=True), send_form=True
#         send_form = not customer.is_onboarded if customer.is_onboarded is not None else is_new_chat
#         logger.info(f"send_form determined as: {send_form} (is_onboarded={customer.is_onboarded}, is_new_chat={is_new_chat})")

#         # 7. Simpan pesan baru dari user ke Database
#         await save_message_to_db(customer_id, "user", req.message)

#         # 8. Susun State untuk LangGraph
#         # Tambahkan pesan terbaru ke dalam history
#         current_messages = history + [HumanMessage(content=req.message)]

#         initial_state = {
#             "messages": current_messages,
#             "phone_number": req.phone_number,
#             "lid_number": req.lid_number,
#             "contact_name": req.contact_name,
#             "customer_id": customer_id,
#             "step": "start",
#             "route": "UNASSIGNED",
#             "customer_data": customer_data,
#             "send_form": send_form,
#             # "awaiting_form": awaiting_form,
#             # "form_submitted": form_submitted
#         }

#         # 9. Jalankan AI Workflow (LangGraph)
#         # Quality check is now handled within the workflow graph
#         final_state = await hana_bot.ainvoke(initial_state)

#         # logger.info(f"FINAL STATE:\n{final_state}")

#         # 10. Ambil balasan terakhir dari AI
#         last_message = final_state["messages"][-1]
#         ai_reply = last_message.content

#         # 11. Simpan balasan AI ke Database
#         await save_message_to_db(customer_id, "ai", ai_reply)

#         return ChatResponse(
#             customer_id=customer_id,
#             phone_number=req.phone_number,
#             lid_number=req.lid_number,
#             reply=ai_reply,
#             route=final_state.get("route", "UNASSIGNED"),
#             step=final_state.get("step", "unknown")
#         )

#     except ValueError as ve:
#         # Validation error
#         raise HTTPException(status_code=400, detail=str(ve))
#     except Exception as e:
#         print(f"Error: {str(e)}")
#         import traceback
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail="Terjadi kesalahan pada server AI.")


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
    reply: str
    tool_calls: Optional[list[str]] = None
    messages_count: int

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
        final_state = await hana_agent.ainvoke(initial_state)

        logger.info(f"FINAL STATE (Agent): messages_count={len(final_state['messages'])}")

        # 9. Extract AI reply from final state
        # The final message should be from node_final_message which synthesizes everything
        messages = final_state["messages"]
        ai_reply = ""
        tool_calls_used = []

        # Find all tool calls made during the conversation
        for msg in messages:
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc['name'] not in tool_calls_used:
                        tool_calls_used.append(tc['name'])

        # Get the last message content (should be from node_final_message or final agent response)
        last_message = messages[-1]
        if hasattr(last_message, 'content') and last_message.content:
            ai_reply = last_message.content
        else:
            # Fallback: find last AIMessage with content
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and hasattr(msg, 'content') and msg.content:
                    # Skip tool result messages
                    if not hasattr(msg, 'name') or msg.name != 'ToolMessage':
                        ai_reply = msg.content
                        break

        # If still no content, this is an error
        if not ai_reply:
            logger.error("No AI reply found in final state!")
            ai_reply = "Maaf, terjadi kesalahan sistem. Silakan coba lagi."

        # 10. Simpan balasan AI ke Database
        await save_message_to_db(customer_id, "ai", ai_reply)

        logger.info(f"Tool calls used: {tool_calls_used}")
        logger.info(f"AI reply (first 200 chars): {ai_reply[:200]}")

        return ChatAgentResponse(
            customer_id=customer_id,
            phone_number=req.phone_number,
            lid_number=req.lid_number,
            reply=ai_reply,
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

# --- ENDPOINT RESET HISTORY (UNTUK TESTING/DEV) ---
@app.post("/reset-history", response_model=ResetHistoryResponse)
async def reset_history_endpoint(req: ResetHistoryRequest):
    """
    Reset history chat dan data customer untuk testing/development.
    Ini akan menghapus semua chat history dan mereset data customer ke nilai default,
    tetapi mempertahankan phone_number dan lid_number.
    """
    try:
        identifier = {
            "phone_number": req.phone_number,
            "lid_number": req.lid_number
        }

        deleted_count = 0

        async with AsyncSessionLocal() as db:
            # 1. Cari customer berdasarkan identifier
            query = select(Customer).where(
                or_(
                    Customer.phone_number == identifier.get('phone_number'),
                    Customer.lid_number == identifier.get('lid_number')
                )
            )
            result = await db.execute(query)
            customer = result.scalars().first()

            if not customer:
                return ResetHistoryResponse(
                    success=True,
                    message=f"Tidak ditemukan customer untuk identifier: {identifier}",
                    deleted_count=0
                )

            customer_id = customer.id

            # 2. Hapus semua chat sessions untuk customer ini
            chat_delete = delete(ChatSession).where(ChatSession.customer_id == customer_id)
            chat_result = await db.execute(chat_delete)
            deleted_count += chat_result.rowcount

            # 3. Reset customer data ke nilai default dari model (dynamic approach)
            # Kolom yang di-preserve: phone_number, lid_number, created_at, id
            preserved_columns = {"id", "phone_number", "lid_number", "created_at"}

            # Get SQLAlchemy mapper untuk Customer
            mapper = inspect(Customer)

            for column_prop in mapper.attrs:
                column_name = column_prop.key

                # Skip preserved columns
                if column_name in preserved_columns:
                    continue

                # Get the SQLAlchemy Column object
                column = column_prop.columns[0]

                # Get default value from column definition
                default_value = column.default

                if default_value is not None:
                    # Handle callable defaults (like lambda functions for datetime)
                    if callable(default_value.arg):
                        # Skip callable defaults like datetime.now(WIB)
                        # Use None if column is nullable
                        setattr(customer, column_name, None if column.nullable else None)
                    else:
                        # Use the static default value
                        setattr(customer, column_name, default_value.arg)
                else:
                    # No default specified, use None if nullable
                    setattr(customer, column_name, None)

            # Explicitly set is_onboarded to False
            customer.is_onboarded = False

            # updated_at akan auto-update oleh onupdate

            await db.commit()

        return ResetHistoryResponse(
            success=True,
            message=f"Berhasil reset history untuk customer_id: {customer_id}",
            deleted_count=deleted_count,
            customer_id=customer_id
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        return ResetHistoryResponse(
            success=False,
            message=f"Gagal reset history: {str(e)}",
            deleted_count=0
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

# --- HEALTH CHECK ENDPOINT ---
@app.get("/health")
async def health_check():
    """Endpoint untuk health check"""
    return {
        "status": "healthy",
        "service": "HANA AI WhatsApp Chatbot",
        "version": "2.0 - Agentic Architecture",
        "endpoints": {
            "chat": "/chat (Legacy - Intent Classification)",
            "chat-agent": "/chat-agent (NEW - Agentic with 27 tools using LangGraph create_react_agent)",
            "reset-history": "/reset-history",
            "reset-products": "/reset-products",
            "health": "/health"
        },
        "agent_tools": {
            "total": 27,
            "categories": [
                "Customer Management (3)",
                "Profiling (7)",
                "Sales & Meeting (6)",
                "Product & E-commerce (8)",
                "Support & Complaints (3)"
            ]
        }
    }

# --- RUN SERVER ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
