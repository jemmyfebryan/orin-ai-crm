"""
Support & Complaint Agent Tools

LangChain StructuredTool objects for support and complaint operations.
These tools are used by the LangGraph agent for support-related operations.
"""

import os
import json
from typing import Annotated
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import InjectedState

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config
from src.orin_ai_crm.core.models.database import AsyncSessionLocal, Customer
from sqlalchemy import select

logger = get_logger(__name__)
llm = ChatOpenAI(model=llm_config.DEFAULT_MODEL, api_key=os.getenv("OPENAI_API_KEY"))
WIB = timezone(timedelta(hours=7))


@tool
async def classify_issue_type(message: str) -> dict:
    """
    Classify customer issue type (complaint vs support question).

    Use this tool when:
    - Customer has a problem or question
    - Need to determine if it's a complaint or support inquiry

    Returns:
        dict with: issue_type (str: "complaint", "support", "general"), severity (str)
    """
    logger.info(f"TOOL: classify_issue_type")

    prompt = f"""Classify the customer message type.

Message: "{message}"

Classify as:
1. "complaint" - Customer is complaining, unhappy, reporting issues
2. "support" - Customer needs technical help, asks how to do something
3. "general" - General question, greeting, thanks

Also assess severity:
- "high" - Urgent, angry, critical issue
- "medium" - Needs attention but not urgent
- "low" - Simple question, inquiry

Return JSON: {{"issue_type": "...", "severity": "...", "reasoning": "..."}}"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    try:
        result = json.loads(response.content)
        return result
    except:
        return {
            'issue_type': 'general',
            'severity': 'low',
            'reasoning': 'Could not classify, defaulting to general'
        }


@tool
async def generate_empathetic_response(
    message: str,
    customer_name: str,
    issue_type: str
) -> dict:
    """
    Generate empathetic response for customer issues.

    Use this tool when:
    - Customer has a complaint or problem
    - Customer needs support
    - Need to show empathy and offer help

    Args:
        message: Customer's message
        customer_name: Customer's name
        issue_type: "complaint", "support", or "general"

    Returns:
        dict with: response (str) - Empathetic message
    """
    logger.info(f"TOOL: generate_empathetic_response - type: {issue_type}")

    if issue_type == "complaint":
        task = "Customer has a complaint. Apologize sincerely, acknowledge their frustration, ask for details to help, and assure them you'll resolve it."
    elif issue_type == "support":
        task = "Customer needs technical support. Offer help patiently, ask for specifics if needed, and provide guidance."
    else:
        task = "Customer sent a general message. Respond warmly and ask how you can help."

    prompt = f"""Customer: {customer_name}
Message: "{message}"

TASK:
{task}

RULES:
- Tunjukkan empati yang tulus
- Gunakan emoji yang sesuai
- Natural seperti chat WhatsApp asli
- Jika perlu, tanya detail masalahnya
- Berikan assurance bahwa tim akan membantu
- Response HANYA dengan pesan yang akan dikirim"""

    response = await llm.ainvoke([SystemMessage(content=prompt)])

    return {
        'response': response.content
    }


@tool
async def set_human_takeover_flag(
    state: Annotated[dict, InjectedState],
) -> dict:
    """
    Set human_takeover flag to true for a customer.

    Use this tool when:
    - Issue is too complex for AI to handle
    - Customer explicitly asks for human agent

    Returns:
        dict with: success (bool), message (str)
    """
    # Get customer_id from state (prevents LLM from using wrong customer_id)
    customer_id = state.get("customer_id")

    if not customer_id:
        logger.error("TOOL: set_human_takeover_flag - No customer_id in state!")
        return {'success': False, 'message': 'No customer_id in state'}

    logger.info(f"TOOL: set_human_takeover_flag - customer_id: {customer_id} (from state)")

    async with AsyncSessionLocal() as db:
        query = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(query)
        customer = result.scalars().first()

        if not customer:
            return {
                'success': False,
                'message': f'Customer {customer_id} not found'
            }

        customer.human_takeover = True
        await db.commit()

        logger.info(f"Human takeover flag SET for customer {customer_id}")

        return {
            'success': True,
            'message': 'Human takeover flag set'
        }


@tool
def forgot_password() -> dict:
    """
    Get the forgot password guide for customers.

    Use this tool when:
    - Customer asks about forgot password
    - Customer cannot login to their account
    - Customer needs password reset instructions

    Returns:
        dict with: message (str) - Password reset guide
    """
    logger.info("TOOL: forgot_password")

    message = """Halo Kak, maaf ya kendalanya 😔

Kalau Kakak lupa password, gampang banget kok caranya:

1️⃣ Buka website https://app.orin.id
2️⃣ Pilih menu "Lupa Password"
3️⃣ Ikuti langkah-langkahnya di sana

Kalau udah dicoba tapi masih belum bisa juga, tolong infoin ke Hana:
- Username untuk login
- Email yang dipakai

Nanti Hana bantu cek lebih lanjut ya 🙏"""

    return {
        'message': message
    }


# List of support tools for easy import
SUPPORT_TOOLS = [
    classify_issue_type,
    generate_empathetic_response,
    set_human_takeover_flag,
    forgot_password,
]

__all__ = ['SUPPORT_TOOLS']
