"""
Meeting & Sales Agent Tools

Simplified approach for B2B/high-volume customers:
- Single tool to ask customer about meeting interest
- If customer agrees, use human_takeover tool (imported from support_agent_tools)
"""

import os
from typing import Annotated
from datetime import timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from src.orin_ai_crm.core.logger import get_logger
from src.orin_ai_crm.core.agents.config import llm_config, get_llm
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_agent_name

logger = get_logger(__name__)

# Use medium model for meeting tasks (simple qualification flow)
llm = get_llm("medium")
WIB = timezone(timedelta(hours=7))


@tool
async def ask_customer_about_meeting(
    state: Annotated[dict, InjectedState],
) -> dict:
    """
    Ask customer if they want a meeting with sales team.

    This tool generates a friendly message to ask B2B/high-volume customers
    if they're interested in a meeting with our sales team for special pricing.

    Use this tool when:
    - Customer is B2B (is_b2b == True)
    - Customer wants 5+ units (unit_qty > 5)
    - You want to qualify them for a sales meeting

    Returns:
        dict with: message (str) - Friendly meeting invitation message
    """
    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    customer_data = state.get('customer_data', {})
    customer_name = customer_data.get('name', 'Kak')
    unit_qty = customer_data.get('unit_qty', 0)
    is_b2b = customer_data.get('is_b2b', False)

    logger.info(f"TOOL: ask_customer_about_meeting - customer: {customer_name}, qty: {unit_qty}, b2b: {is_b2b}")

    # Get agent name for dynamic messaging
    agent_name = get_agent_name()

    # Generate friendly meeting invitation message
    if is_b2b:
        context = f"karena Kakak adalah pelanggan B2B"
    elif unit_qty > 5:
        context = f"karena Kakak tertarik dengan {unit_qty} unit"
    else:
        context = "untuk kebutuhan Kakak"

    message = f"""Baik kak {customer_name}! 😊

Kami punya tim sales khusus yang bisa bantu Kakak {context}.

Mau Kakak kalau {agent_name} jadwalkan meeting online dengan tim sales kami? Mereka bisa kasih penawaran khusus dan jawab pertanyaan lebih detail.

Kira-kira kakak tertarik untuk meeting nggak ya? 🙏"""

    return {
        'message': message
    }


# List of sales & meeting tools for easy import
# Note: human_takeover tool is imported from support_agent_tools
SALES_MEETING_TOOLS = [
    ask_customer_about_meeting,
]

__all__ = ['SALES_MEETING_TOOLS']
