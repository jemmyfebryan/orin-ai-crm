from typing import Optional

from sqlalchemy import select

from src.orin_ai_crm.core.models.database import AsyncSessionLocal, ChatSession

async def get_chat_history(customer_id: int, limit: int = 20):
    """Mengambil riwayat chat dari database"""

    async with AsyncSessionLocal() as db:
        query = (
            select(ChatSession)
            .where(ChatSession.customer_id == customer_id)
            .order_by(ChatSession.created_at.asc())
            .limit(limit)
        )
        result = await db.execute(query)
        rows = result.scalars().all()

        # Detach semua objects dari session
        for row in rows:
            db.expunge(row)

        return rows
    


async def save_message_to_db(customer_id: Optional[int], role: str, content: str):
    """Simpan pesan ke database dengan customer_id"""
    from src.orin_ai_crm.core.models.database import ChatSession

    async with AsyncSessionLocal() as db:
        new_msg = ChatSession(
            customer_id=customer_id,
            message_role=role,
            content=content
        )
        db.add(new_msg)
        await db.commit()
