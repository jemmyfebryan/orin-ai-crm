"""
Meeting & Sales Agent Tools

**DEPRECATED**: This module is deprecated as of 2026-03-19.

The sales node has been simplified to use LLM-based classification instead of
meeting management tools. All meeting-related operations are now handled by
live human agents via the human_takeover flow.

These tools are kept for backward compatibility but are no longer used in the
active agent workflow. They may be removed in a future release.

LangChain StructuredTool objects for meeting and sales operations.
These tools are used by the LangGraph agent for meeting-related operations.
"""

import os
from typing import Optional, Annotated
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import InjectedState

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.models.schemas import MeetingInfo
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, CustomerMeeting
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db
from sqlalchemy import select

logger = get_logger(__name__)
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))


@tool
async def get_pending_meeting(
    state: Annotated[dict, InjectedState],
) -> dict:
    """
    Get pending or confirmed meeting for customer.

    Use this tool when:
    - Checking if customer has an existing meeting
    - Customer wants to reschedule
    - Customer mentions an existing meeting

    Returns:
        dict with: found (bool), meeting_id (int), date (str), time (str), status (str)
    """
    # Get customer_id from state (prevents LLM from using wrong customer_id)
    customer_id = state.get("customer_id")

    if not customer_id:
        logger.error("TOOL: get_pending_meeting - No customer_id in state!")
        return {
            'found': False,
            'meeting_id': None,
            'date': '',
            'time': '',
            'status': '',
            'notes': ''
        }

    logger.info(f"TOOL: get_pending_meeting - customer_id: {customer_id} (from state)")

    async with AsyncSessionLocal() as db:
        query = select(CustomerMeeting).where(
            (CustomerMeeting.customer_id == customer_id) &
            (CustomerMeeting.status.in_(["pending", "confirmed"]))
        ).order_by(CustomerMeeting.created_at.desc())

        result = await db.execute(query)
        meeting = result.scalars().first()

        if meeting:
            return {
                'found': True,
                'meeting_id': meeting.id,
                'date': meeting.notes.split(', ')[0].split(': ')[1] if meeting.notes else '',
                'time': meeting.notes.split(', ')[1].split(': ')[1] if meeting.notes and ', ' in meeting.notes else '',
                'status': meeting.status,
                'notes': meeting.notes
            }
        else:
            return {
                'found': False,
                'meeting_id': None,
                'date': '',
                'time': '',
                'status': '',
                'notes': ''
            }


@tool
async def extract_meeting_details(
    message: str,
    customer_name: str,
    has_existing_meeting: bool = False
) -> dict:
    """
    Extract meeting details from customer message using LLM.

    Use this tool when:
    - Customer mentions booking a meeting
    - Customer wants to reschedule
    - Customer agrees to a meeting time

    Extracts:
    - has_agreement: Did customer agree to book meeting?
    - wants_reschedule: Does customer want to change existing meeting?
    - date: Meeting date (can be "besok", "Senin depan", or "2024-01-15")
    - time: Meeting time (can be "jam 2", "pagi", or "14:00")

    Returns:
        dict with extracted meeting details
    """
    logger.info(f"TOOL: extract_meeting_details - has_existing: {has_existing_meeting}")

    existing_context = ""
    if has_existing_meeting:
        existing_context = "\nCustomer already has a meeting booked. Detect if they want to RESCHEDULE."

    prompt = f"""Extract meeting information from customer message.

Customer: {customer_name}
Message: "{message}"
{existing_context}

Extract:
1. has_meeting_agreement: true if customer AGREED to book (not just asking, but confirmed)
2. wants_reschedule: true if customer wants to change existing meeting
3. meeting_date: Date mentioned (can be natural like "besok", "Senin depan", or specific date)
4. meeting_time: Time mentioned (can be natural like "jam 2", "pagi", or specific time like "14:00")
5. meeting_format: "online", "offline", or null

Examples:
- "Boleh, booking meeting besok jam 2" → agreement: true, date: "besok", time: "jam 2"
- "Oke, Senin depan jam 10 pagi" → agreement: true, date: "Senin depan", time: "10 pagi"
- "Bisa ganti jadwal besok?" → wants_reschedule: true, agreement: true (new date)
- "Kira-kira kapan saja?" → agreement: false (still negotiating)

Return JSON format."""

    extractor_llm = llm.with_structured_output(MeetingInfo)
    meeting_info = extractor_llm.invoke([SystemMessage(content=prompt)])

    logger.info(f"Extracted meeting details: agreement={meeting_info.has_meeting_agreement}, reschedule={meeting_info.wants_reschedule}")

    return {
        'has_meeting_agreement': meeting_info.has_meeting_agreement,
        'wants_reschedule': meeting_info.wants_reschedule,
        'meeting_date': meeting_info.meeting_date or '',
        'meeting_time': meeting_info.meeting_time or '',
        'meeting_format': meeting_info.meeting_format or 'online',
        'notes': meeting_info.notes or ''
    }


@tool
async def book_or_update_meeting_db(
    state: Annotated[dict, InjectedState],
    meeting_date: str,
    meeting_time: str,
    meeting_format: str = "online",
    wants_reschedule: bool = False,
    existing_meeting_id: Optional[int] = None
) -> dict:
    """
    Book new meeting or update existing meeting in database.

    Use this tool when:
    - Customer has agreed to a meeting time
    - Need to create new meeting record
    - Need to update existing meeting (reschedule)

    Returns:
        dict with: success (bool), meeting_id (int), action (str)
    """
    # Get customer_id from state (prevents LLM from using wrong customer_id)
    customer_id = state.get("customer_id")

    if not customer_id:
        logger.error("TOOL: book_or_update_meeting_db - No customer_id in state!")
        return {'success': False, 'message': 'No customer_id in state', 'action': 'failed'}

    logger.info(f"TOOL: book_or_update_meeting_db - customer_id: {customer_id} (from state), reschedule: {wants_reschedule}")

    async with AsyncSessionLocal() as db:
        if wants_reschedule and existing_meeting_id:
            # Update existing meeting
            query = select(CustomerMeeting).where(CustomerMeeting.id == existing_meeting_id)
            result = await db.execute(query)
            existing_meeting = result.scalars().first()

            if existing_meeting:
                existing_meeting.notes = f"Date: {meeting_date}, Time: {meeting_time}"
                existing_meeting.status = "rescheduled"
                await db.commit()

                logger.info(f"Meeting RESCHEDULED: {existing_meeting.id}")

                return {
                    'success': True,
                    'meeting_id': existing_meeting.id,
                    'action': 'rescheduled',
                    'date': meeting_date,
                    'time': meeting_time
                }

        # Create new meeting
        meeting = CustomerMeeting(
            customer_id=customer_id,
            meeting_datetime=None,
            meeting_format=meeting_format,
            status="pending",
            notes=f"Date: {meeting_date}, Time: {meeting_time}"
        )
        db.add(meeting)
        await db.commit()
        await db.refresh(meeting)

        logger.info(f"Meeting CREATED: {meeting.id}")

        return {
            'success': True,
            'meeting_id': meeting.id,
            'action': 'created',
            'date': meeting_date,
            'time': meeting_time
        }


@tool
async def generate_meeting_negotiation_message(
    customer_name: str,
    conversation_context: str,
    is_reschedule: bool = False
) -> dict:
    """
    Generate message to negotiate meeting time with customer.

    Use this tool when:
    - Customer is in sales flow but hasn't agreed to specific time
    - Need to ask for specific meeting time
    - Continue meeting negotiation

    Args:
        customer_name: Customer's name
        conversation_context: Recent messages for context
        is_reschedule: True if rescheduling existing meeting

    Returns:
        dict with: message (str) - Negotiation message
    """
    logger.info(f"TOOL: generate_meeting_negotiation_message - reschedule: {is_reschedule}")

    # Get Hana persona from database (fresh on each invoke)
    hana_persona = await get_prompt_from_db("hana_sales_agent")
    if not hana_persona:
        hana_persona = "Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker."

    task = "reschedule meeting" if is_reschedule else "book new meeting"

    prompt = f"""{hana_persona}

Customer: {customer_name}
Context: {conversation_context}

TASK:
Generate message to negotiate meeting time for {task}.

RULES:
- Ask for SPECIFIC date and time
- If customer said "pagi/siang/sore", ask for specific hour
- Ramah dan membantu
- Gunakan emoji
- Natural seperti chat WhatsApp asli
- Response HANYA dengan pesan yang akan dikirim"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'message': response.content
    }


@tool
async def generate_meeting_confirmation(
    customer_name: str,
    meeting_date: str,
    meeting_time: str,
    meeting_format: str = "online"
) -> dict:
    """
    Generate meeting confirmation message for customer.

    Use this tool when:
    - Meeting has been successfully booked or rescheduled
    - Need to confirm details with customer

    Returns:
        dict with: confirmation_message (str)
    """
    logger.info(f"TOOL: generate_meeting_confirmation")

    confirmation = f"""Siap kak {customer_name}! 👍

Meeting sudah Hana catat:
📅 Tanggal: {meeting_date}
⏰ Jam: {meeting_time}
📍 Format: {meeting_format.title()}

Tim sales kami akan menghubungi kakak sesuai jadwal tersebut. Sampai jumpa di meeting ya kak! 🙏

Ada yang bisa Hana bantu sebelum meeting?"""

    return {
        'confirmation_message': confirmation
    }


@tool
async def generate_existing_meeting_reminder(
    customer_name: str,
    existing_meeting_info: dict,
    conversation_context: str
) -> dict:
    """
    Generate reminder message when customer has existing meeting.

    Use this tool when:
    - Customer with existing meeting contacts us again
    - Not trying to reschedule, just following up
    - Remind them of their scheduled meeting

    Returns:
        dict with: reminder_message (str)
    """
    logger.info(f"TOOL: generate_existing_meeting_reminder")

    # Get Hana persona from database (fresh on each invoke)
    hana_persona = await get_prompt_from_db("hana_sales_agent")
    if not hana_persona:
        hana_persona = "Kamu adalah Hana, Customer Service AI dari ORIN GPS Tracker."

    prompt = f"""{hana_persona}

Customer: {customer_name}
Existing Meeting: {existing_meeting_info}
Context: {conversation_context}

TASK:
Generate a friendly reminder about their existing meeting.
Don't create a new meeting, just remind them of the scheduled one.
Ask if there's anything you can help with before the meeting.

RULES:
- Ramah dan membantu
- Gunakan emoji
- Natural seperti chat WhatsApp asli
- Response HANYA dengan pesan yang akan dikirim"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'reminder_message': response.content
    }


# List of sales & meeting tools for easy import
SALES_MEETING_TOOLS = [
    get_pending_meeting,
    extract_meeting_details,
    book_or_update_meeting_db,
    generate_meeting_negotiation_message,
    generate_meeting_confirmation,
    generate_existing_meeting_reminder,
]

__all__ = ['SALES_MEETING_TOOLS']
