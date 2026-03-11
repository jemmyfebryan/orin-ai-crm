"""
AI Agent Tools Package

IMPORTANT: Import from specific submodules to avoid confusion between:
- Actual functions (in customer_tools.py, meeting_tools.py, product_tools.py)
- LangChain StructuredTool objects (in agent_tools.py - for use with agents only)

USAGE:
- For legacy nodes (profiling_nodes, sales_nodes, etc.): Use original function names
- For server/main.py: Import from specific modules (customer_tools, product_tools, etc.)
- For agent graph: Use AGENT_TOOLS from agent_tools module
"""

# ============================================================================
# AGENTIC TOOLS (for LangGraph agent only - these are StructuredTool objects)
# ============================================================================

from src.orin_ai_crm.core.agents.tools.agent_tools import (
    # All tools combined (30+ StructuredTool objects for LangGraph)
    AGENT_TOOLS,

    # Tool categories (lists of StructuredTool objects)
    CUSTOMER_MANAGEMENT_TOOLS,
    PROFILING_TOOLS,
    SALES_MEETING_TOOLS,
    PRODUCT_ECOMMERCE_TOOLS,
    _SUPPORT_TOOLS,
    CONVERSATION_TOOLS,
)

# ============================================================================
# ACTUAL CALLABLE FUNCTIONS (for use in server, legacy nodes, etc.)
# ============================================================================

# Customer Tools (actual functions)
from src.orin_ai_crm.core.agents.tools.customer_tools import (
    get_or_create_customer,
    update_customer_profile,
    get_chat_history,
    save_message_to_db
)

# Meeting Tools (actual functions)
from src.orin_ai_crm.core.agents.tools.meeting_tools import (
    get_pending_meeting,
    create_meeting,
    update_meeting,
    extract_meeting_info,
    book_or_update_meeting,
    MeetingInfo,
)

# Product Tools (actual functions) - KEEP ORIGINAL NAMES for backward compatibility
from src.orin_ai_crm.core.agents.tools.product_tools import (
    get_pending_inquiry,
    create_product_inquiry,
    update_product_inquiry,
    extract_product_type,
    ProductInfo,
    # Product query tools - KEEP ORIGINAL NAMES
    get_all_active_products,
    get_products_by_category,
    get_products_by_vehicle_type,
    search_products,
    format_products_for_llm,
    answer_product_question,
    recommend_products,
    # Ecommerce product management tools
    get_ecommerce_product,
    reset_products_to_default,
    initialize_default_products_if_empty,
    load_default_products_from_json,
    get_default_products_json_path,
    # Product recommendation & Q&A tools (with database)
    recommend_products_from_db,
    answer_product_question_from_db
)

__all__ = [
    # ============================================================================
    # AGENTIC TOOLS (StructuredTool objects for LangGraph agent)
    # ============================================================================
    'AGENT_TOOLS',
    'CUSTOMER_MANAGEMENT_TOOLS',
    'PROFILING_TOOLS',
    'SALES_MEETING_TOOLS',
    'PRODUCT_ECOMMERCE_TOOLS',
    '_SUPPORT_TOOLS',
    'CONVERSATION_TOOLS',

    # ============================================================================
    # ACTUAL CALLABLE FUNCTIONS (original names for backward compatibility)
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

    # Product Tools (original names - for legacy nodes)
    'get_pending_inquiry',
    'create_product_inquiry',
    'update_product_inquiry',
    'extract_product_type',
    'ProductInfo',
    'get_all_active_products',  # Original name from product_tools.py
    'get_products_by_category',
    'get_products_by_vehicle_type',
    'search_products',
    'format_products_for_llm',
    'answer_product_question',
    'recommend_products',
    'get_ecommerce_product',
    'reset_products_to_default',
    'initialize_default_products_if_empty',
    'load_default_products_from_json',
    'get_default_products_json_path',
    'recommend_products_from_db',
    'answer_product_question_from_db',
]
