"""
AI Agent Tools Package

This package contains modular tools organized by category for the Hana AI agent.

IMPORTANT: All tools are @tool decorated (LangChain StructuredTool objects).
For non-agent contexts, use .ainvoke() or .invoke() to call these tools.

USAGE:
- For agent graph: Use AGENT_TOOLS or specific tool categories
- For server/nodes (non-agent): Import tools and call with .ainvoke()/.invoke()

MODULE STRUCTURE:
- customer_agent_tools.py: Customer management tools (@tool decorated)
- profiling_agent_tools.py: Profiling tools (@tool decorated)
- meeting_agent_tools.py: Sales & meeting tools (@tool decorated)
- support_agent_tools.py: Support & complaint tools (@tool decorated)
- product_agent_tools.py: Product & e-commerce tools (@tool decorated)
- agent_tools.py: Main module that imports and combines all agent tools
"""

# ============================================================================
# AGENTIC TOOLS (StructuredTool objects for LangGraph agent)
# ============================================================================

from src.orin_ai_crm.core.agents.tools.agent_tools import (
    # All tools combined
    AGENT_TOOLS,

    # Tool categories (lists of StructuredTool objects)
    CUSTOMER_MANAGEMENT_TOOLS,
    PROFILING_TOOLS,
    SALES_MEETING_TOOLS,
    PRODUCT_ECOMMERCE_TOOLS,
    SUPPORT_TOOLS,
)

# ============================================================================
# HELPER FUNCTIONS FROM LEGACY MODULES (Non-tool functions)
# ============================================================================

# Customer Tools (actual functions)
from src.orin_ai_crm.core.agents.tools.hana_legacy.customer_tools import (
    get_or_create_customer,
    update_customer_profile,
    get_chat_history,
    save_message_to_db
)

# Meeting Tools (actual functions)
from src.orin_ai_crm.core.agents.tools.hana_legacy.meeting_tools import (
    get_pending_meeting,
    create_meeting,
    update_meeting,
    extract_meeting_info,
    book_or_update_meeting,
    MeetingInfo,
)

# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # ============================================================================
    # AGENTIC TOOLS (@tool decorated StructuredTool objects)
    # ============================================================================
    'AGENT_TOOLS',
    'CUSTOMER_MANAGEMENT_TOOLS',
    'PROFILING_TOOLS',
    'SALES_MEETING_TOOLS',
    'PRODUCT_ECOMMERCE_TOOLS',
    'SUPPORT_TOOLS',

    # ============================================================================
    # HELPER FUNCTIONS (Legacy non-tool functions)
    # ============================================================================

    # Customer Tools
    'get_or_create_customer',
    'update_customer_profile',
    'get_chat_history',
    'save_message_to_db',

    # Meeting Tools
    'get_pending_meeting',
    'create_meeting',
    'update_meeting',
    'extract_meeting_info',
    'book_or_update_meeting',
    'MeetingInfo',
]
