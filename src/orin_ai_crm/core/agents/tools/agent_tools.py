"""
Agentic Tools for Hana AI - Granular Tool-Calling Architecture

This file imports and organizes tools that the LLM can compose together
to handle complex customer interactions. Each tool does ONE thing well.

IMPORTANT: The LLM CAN and SHOULD call MULTIPLE tools in parallel to handle
multi-intent messages. This is the power of the agentic approach!

Tool Categories:
1. CUSTOMER MANAGEMENT (2 tools)
2. PROFILING (7 tools)
3. SALES & MEETING (7 tools)
4. PRODUCT & E-COMMERCE (8 tools)
5. SUPPORT & COMPLAINTS (3 tools)
6. GREETING & CONVERSATION (2 tools)

Total: 30+ granular tools
"""

# Import all tool categories from their respective modules
from src.orin_ai_crm.core.agents.tools.customer_agent_tools import (
    CUSTOMER_MANAGEMENT_TOOLS,
)
from src.orin_ai_crm.core.agents.tools.profiling_agent_tools import (
    PROFILING_TOOLS,
)
from src.orin_ai_crm.core.agents.tools.meeting_agent_tools import (
    SALES_MEETING_TOOLS,
)
from src.orin_ai_crm.core.agents.tools.support_agent_tools import (
    SUPPORT_TOOLS,
)
from src.orin_ai_crm.core.agents.tools.product_agent_tools import (
    PRODUCT_ECOMMERCE_TOOLS,
    send_product_images,
    get_all_active_products,
)


# ============================================================================
# TOOL LIST FOR AGENT
# ============================================================================

# Profiling Agent Tools (used by main agent_node for customer profiling)
# Only includes customer management and profiling tools
AGENT_TOOLS = (
    CUSTOMER_MANAGEMENT_TOOLS
    + PROFILING_TOOLS
)

# Sales Agent Tools (used by sales_node for B2B/large orders)
SALES_AGENT_TOOLS = SALES_MEETING_TOOLS

# Ecommerce Agent Tools (used by ecommerce_node for B2C/small orders)
ECOMMERCE_AGENT_TOOLS = PRODUCT_ECOMMERCE_TOOLS

__all__ = [
    'AGENT_TOOLS',
    'SALES_AGENT_TOOLS',
    'ECOMMERCE_AGENT_TOOLS',
    'CUSTOMER_MANAGEMENT_TOOLS',
    'PROFILING_TOOLS',
    'SALES_MEETING_TOOLS',
    'PRODUCT_ECOMMERCE_TOOLS',
    'SUPPORT_TOOLS',
]
