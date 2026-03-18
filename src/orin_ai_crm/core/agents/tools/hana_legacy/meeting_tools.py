"""
Meeting Tools - Meeting extraction, booking, and rescheduling

Legacy meeting management functions. These are still used by the meeting agent tools
for extracting meeting information from conversations.
"""

import os
from typing import Optional
from datetime import timedelta, timezone
from datetime import datetime as dt
from sqlalchemy import select
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

from src.orin_ai_crm.core.models.database import AsyncSessionLocal, CustomerMeeting
from src.orin_ai_crm.core.models.schemas import MeetingInfo
from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config

logger = get_logger(__name__)
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))


async def get_pending_meeting(customer_id: int) -> Optional[CustomerMeeting]:
    """Get pending meeting untuk customer"""
    async with AsyncSessionLocal() as db:
        query = select(CustomerMeeting).where(
            (CustomerMeeting.customer_id == customer_id) &
            (CustomerMeeting.status.in_(["pending", "confirmed"]))
        ).order_by(CustomerMeeting.created_at.desc())

        result = await db.execute(query)
        meeting = result.scalars().first()

        if meeting:
            db.expunge(meeting)
            return meeting
        return None


async def create_meeting(
    customer_id: int,
    meeting_date: str,
    meeting_time: str,
    meeting_format: str = "online"
) -> CustomerMeeting:
    """Create new meeting record"""
    logger.info(f"Creating new meeting - customer_id: {customer_id}, date: {meeting_date}, time: {meeting_time}")

    async with AsyncSessionLocal() as db:
        meeting = CustomerMeeting(
            customer_id=customer_id,
            meeting_datetime=None,  # Will be parsed and set
            meeting_format=meeting_format,
            status="pending",
            notes=f"Date: {meeting_date}, Time: {meeting_time}"
        )
        db.add(meeting)
        await db.commit()
        await db.refresh(meeting)
        db.expunge(meeting)

        logger.info(f"New meeting CREATED - id: {meeting.id}")
        return meeting


async def update_meeting(
    meeting_id: int,
    meeting_date: Optional[str] = None,
    meeting_time: Optional[str] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None
) -> bool:
    """Update existing meeting"""
    logger.info(f"Updating meeting - id: {meeting_id}, status: {status}")

    async with AsyncSessionLocal() as db:
        query = select(CustomerMeeting).where(CustomerMeeting.id == meeting_id)
        result = await db.execute(query)
        meeting = result.scalars().first()

        if not meeting:
            logger.warning(f"Meeting NOT FOUND for id: {meeting_id}")
            return False

        if notes:
            meeting.notes = notes
        if status:
            meeting.status = status

        await db.commit()
        logger.info(f"Meeting {meeting_id} UPDATED successfully")
        return True


def extract_meeting_info(
    messages: list,
    customer_name: str,
    has_existing_meeting: bool = False
) -> MeetingInfo:
    """
    Extract meeting info dari pesan user.
    Check apakah user sudah sepakat booking meeting dan extract tanggal/jam.
    Jika ada existing meeting, detect apakah user ingin reschedule.
    """
    logger.info(f"extract_meeting_info called for {customer_name}, has_existing_meeting: {has_existing_meeting}")

    existing_context = ""
    if has_existing_meeting:
        existing_context = """
Customer sudah punya meeting yang di-book. Detect apakah customer ingin:
1. Reschedule (ganti jadwal)
2. Confirm meeting
3. Complain/tanya lain"""

    system_prompt = f"""Extract informasi meeting dari percakapan dengan customer {customer_name}.{existing_context}

Check apakah:
1. Customer sudah SEPAKAT untuk booking meeting (bukan hanya tanya, tapi sudah fix)
2. Tanggal dan jam yang disepakati
3. Format meeting (online/offline)
4. Apakah customer ingin reschedule (jika has_existing_meeting=True)

Contoh agreement:
- "Boleh, booking meeting besok jam 2" → has_meeting_agreement: True
- "Oke, Senin depan jam 10 pagi" → has_meeting_agreement: True
- "Besok jam 2 siang" → has_meeting_agreement: True
- "Bisa gak jadwalnya diulang?" → has_meeting_agreement: False (masih negosiasi)

Contoh reschedule:
- "Saya mau ganti jadwal" → wants_reschedule: True
- "Besok tidak bisa, bisa diganti lusa?" → wants_reschedule: True, has_meeting_agreement: True (baru jadwal)

Return format:
- meeting_date: dalam format YYYY-MM-DD jika jelas, atau natural seperti "besok", "Senin depan"
- meeting_time: dalam format HH:MM jika jelas, atau natural seperti "jam 2 siang", "pagi", "sore"
- Jika time tidak spesifik (pagi/siang), set meeting_time to natural text agar AI bisa follow-up"""

    extractor_llm = llm.with_structured_output(MeetingInfo)
    result = extractor_llm.invoke([SystemMessage(content=system_prompt)] + messages)

    logger.info(f"extract_meeting_info result: agreement={result.has_meeting_agreement}, wants_reschedule={result.wants_reschedule}, date={result.meeting_date}, time={result.meeting_time}")
    return result


async def book_or_update_meeting(
    customer_id: int,
    meeting_info: MeetingInfo,
    existing_meeting: Optional[CustomerMeeting] = None
) -> dict:
    """
    Book new meeting atau update existing meeting.
    Return dict dengan status dan formatted meeting info.
    """
    logger.info(f"book_or_update_meeting called - customer_id: {customer_id}, existing_meeting: {existing_meeting.id if existing_meeting else None}")

    meeting_date = meeting_info.meeting_date
    meeting_time = meeting_info.meeting_time
    meeting_format = meeting_info.meeting_format

    # Check if time is specific enough
    needs_clarification = False
    clarification_msg = ""

    # Check apakah time perlu clarification (pagi/siang/sore tidak spesifik)
    vague_times = ["pagi", "siang", "sore", "malam", "morning", "afternoon", "evening"]
    if meeting_time and any(vt in meeting_time.lower() for vt in vague_times):
        needs_clarification = True
        clarification_msg = "\n\nKira-kira lebih spesifik jam berapa kak? Misalnya jam 9 pagi atau jam 2 siang?"

    if existing_meeting and meeting_info.wants_reschedule:
        # Reschedule existing meeting
        logger.info(f"Rescheduling meeting {existing_meeting.id}")
        await update_meeting(
            meeting_id=existing_meeting.id,
            meeting_date=meeting_date,
            meeting_time=meeting_time,
            status="rescheduled",
            notes=f"Rescheduled to: {meeting_date}, {meeting_time}. Original: {existing_meeting.notes}"
        )
        meeting_id = existing_meeting.id
        status = "rescheduled"
    elif existing_meeting:
        # Update existing meeting confirmation
        logger.info(f"Confirming existing meeting {existing_meeting.id}")
        await update_meeting(
            meeting_id=existing_meeting.id,
            status="confirmed",
            notes=f"Confirmed: {meeting_date}, {meeting_time}. {meeting_info.notes or ''}"
        )
        meeting_id = existing_meeting.id
        status = "confirmed"
    else:
        # Create new meeting
        logger.info(f"Creating new meeting for customer {customer_id}")
        meeting = await create_meeting(
            customer_id=customer_id,
            meeting_date=meeting_date,
            meeting_time=meeting_time,
            meeting_format=meeting_format
        )
        meeting_id = meeting.id
        status = "pending"

    logger.info(f"Meeting processed - id: {meeting_id}, status: {status}")

    # Format untuk response ke customer
    formatted_response = {
        "date": meeting_date,
        "time": meeting_time,
        "format": meeting_format,
        "needs_clarification": needs_clarification,
        "clarification_msg": clarification_msg
    }

    return formatted_response
