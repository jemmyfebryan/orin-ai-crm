import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from sqlalchemy import select, or_, delete

# Import dari modular structure
from src.orin_ai_crm.core.models.database import engine, Base, AsyncSessionLocal, ChatSession, Customer
from src.orin_ai_crm.core.agents.tools import (
    get_or_create_customer,
    get_chat_history,
    save_message_to_db
)
from src.orin_ai_crm.core.agents.custom.hana_agent import hana_bot
from langchain_core.messages import HumanMessage, AIMessage

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown (cleanup jika diperlukan)

app = FastAPI(title="HANA AI WhatsApp Chatbot Backend", lifespan=lifespan)

# --- SCHEMAS UNTUK REQUEST POSTMAN ---
class ChatRequest(BaseModel):
    phone_number: Optional[str] = Field(None, description="Nomor WhatsApp user (format: 628xxx)")
    lid_number: Optional[str] = Field(None, description="WhatsApp LID number untuk migrasi")
    message: str = Field(..., description="Pesan dari user")
    contact_name: Optional[str] = Field(None, description="Nama kontak dari WhatsApp")

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

# --- ENDPOINT UTAMA ---
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    try:
        # 1. Build identifier dict
        identifier = {
            "phone_number": req.phone_number,
            "lid_number": req.lid_number
        }

        # 2. Get or create customer (returns detached object)
        customer = await get_or_create_customer(identifier, req.contact_name)
        customer_id = customer.id

        # 3. Tarik riwayat chat lama dari Database
        history_rows = await get_chat_history(customer_id)

        # 4. Build history list untuk LangGraph
        history = []
        for row in history_rows:
            if row.message_role == "user":
                history.append(HumanMessage(content=row.content))
            else:
                history.append(AIMessage(content=row.content))

        # 5. Simpan pesan baru dari user ke Database
        await save_message_to_db(customer_id, "user", req.message)

        # 6. Susun State untuk LangGraph
        # Tambahkan pesan terbaru ke dalam history
        current_messages = history + [HumanMessage(content=req.message)]

        initial_state = {
            "messages": current_messages,
            "phone_number": req.phone_number,
            "lid_number": req.lid_number,
            "contact_name": req.contact_name,
            "customer_id": customer_id,
            "step": "start", # Akan diupdate oleh node profiling
            "route": "UNASSIGNED",
            "customer_data": {}
        }

        # 7. Jalankan AI Workflow (LangGraph)
        # Quality check is now handled within the workflow graph
        final_state = await hana_bot.ainvoke(initial_state)

        # 8. Ambil balasan terakhir dari AI
        last_message = final_state["messages"][-1]
        ai_reply = last_message.content

        # 9. Simpan balasan AI ke Database
        await save_message_to_db(customer_id, "ai", ai_reply)

        return ChatResponse(
            customer_id=customer_id,
            phone_number=req.phone_number,
            lid_number=req.lid_number,
            reply=ai_reply,
            route=final_state.get("route", "UNASSIGNED"),
            step=final_state.get("step", "unknown")
        )

    except ValueError as ve:
        # Validation error
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Terjadi kesalahan pada server AI.")

# --- ENDPOINT RESET HISTORY (UNTUK TESTING/DEV) ---
@app.post("/reset-history", response_model=ResetHistoryResponse)
async def reset_history_endpoint(req: ResetHistoryRequest):
    """
    Reset history chat dan data customer untuk testing/development.
    Hati-hati: Ini akan menghapus semua data customer dan chat history!
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

            # 3. Hapus customer
            cust_delete = delete(Customer).where(Customer.id == customer_id)
            await db.execute(cust_delete)
            deleted_count += 1

            await db.commit()

        return ResetHistoryResponse(
            success=True,
            message=f"Berhasil reset history untuk customer_id: {customer_id}",
            deleted_count=deleted_count
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        return ResetHistoryResponse(
            success=False,
            message=f"Gagal reset history: {str(e)}",
            deleted_count=0
        )

# --- HEALTH CHECK ENDPOINT ---
@app.get("/health")
async def health_check():
    """Endpoint untuk health check"""
    return {"status": "healthy", "service": "HANA AI WhatsApp Chatbot"}

# --- RUN SERVER ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
