import os
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List

# Import dari file modular sebelumnya
from src.orin_ai_crm.core.models.database import engine, Base, AsyncSessionLocal, ChatSession
from src.orin_ai_crm.core.agents.nodes.hana_nodes import save_message_to_db
from src.orin_ai_crm.core.agents.custom.hana_agent import hana_bot
from sqlalchemy import select
from langchain_core.messages import HumanMessage, AIMessage

app = FastAPI(title="HANA AI WhatsApp Chatbot Backend")

# --- SCHEMAS UNTUK REQUEST POSTMAN ---
class ChatRequest(BaseModel):
    phone_number: str
    message: str
    traffic_source: Optional[str] = "direct" # direct, freshchat, sosmed, dll

class ChatResponse(BaseModel):
    phone_number: str
    reply: str
    route: str
    step: str

# --- DATABASE INITIALIZATION ---
@app.on_event("startup")
async def startup_event():
    # Membuat tabel saat server mulai jika belum ada
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# --- HELPER: AMBIL HISTORY DARI DB ---
async def get_chat_history(phone_number: str):
    """Mengambil riwayat chat dari MySQL untuk menyusun context LangGraph"""
    async with AsyncSessionLocal() as db:
        query = (
            select(ChatSession)
            .where(ChatSession.phone_number == phone_number)
            .order_by(ChatSession.created_at.asc())
            .limit(20) # Ambil 20 pesan terakhir agar context tidak terlalu gemuk
        )
        result = await db.execute(query)
        rows = result.scalars().all()
        
        history = []
        for row in rows:
            if row.message_role == "user":
                history.append(HumanMessage(content=row.content))
            else:
                history.append(AIMessage(content=row.content))
        return history

# --- ENDPOINT UTAMA ---
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    try:
        # 1. Tarik riwayat chat lama dari Database
        history = await get_chat_history(req.phone_number)
        
        # 2. Simpan pesan baru dari user ke Database
        await save_message_to_db(req.phone_number, "user", req.message)
        
        # 3. Susun State untuk LangGraph
        # Tambahkan pesan terbaru ke dalam history
        current_messages = history + [HumanMessage(content=req.message)]
        
        initial_state = {
            "messages": current_messages,
            "phone_number": req.phone_number,
            "traffic_source": req.traffic_source,
            "step": "start", # Akan diupdate oleh node profiling
            "route": "UNASSIGNED",
            "customer_data": {}
        }
        
        # 4. Jalankan AI Workflow (LangGraph)
        final_state = await hana_bot.ainvoke(initial_state)
        
        # 5. Ambil balasan terakhir dari AI
        last_message = final_state["messages"][-1]
        ai_reply = last_message.content
        
        # 6. Simpan balasan AI ke Database
        await save_message_to_db(req.phone_number, "ai", ai_reply)
        
        return ChatResponse(
            phone_number=req.phone_number,
            reply=ai_reply,
            route=final_state.get("route", "UNASSIGNED"),
            step=final_state.get("step", "unknown")
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Terjadi kesalahan pada server AI.")

# --- RUN SERVER ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)