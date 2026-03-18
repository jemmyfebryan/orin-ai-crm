"""
Agentic Tools for Hana AI - Granular Tool-Calling Architecture

This file imports and organizes tools that the LLM can compose together
to handle complex customer interactions. Each tool does ONE thing well.

IMPORTANT: The LLM CAN and SHOULD call MULTIPLE tools in parallel to handle
multi-intent messages. This is the power of the agentic approach!

Tool Categories:
1. ORCHESTRATOR (2 tools) - For routing decisions
2. CUSTOMER MANAGEMENT (2 tools) - For profiling agent
3. PROFILING (7 tools) - For profiling agent
4. SALES & MEETING (7 tools) - For sales agent
5. PRODUCT & E-COMMERCE (8 tools) - For ecommerce agent
6. SUPPORT & COMPLAINTS (3 tools) - Reserved for future use
7. GREETING & CONVERSATION (2 tools) - Reserved for future use

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
)


# ============================================================================
# TOOL LIST FOR ORCHESTRATOR-AGENT ARCHITECTURE
# ============================================================================

# Orchestrator Tools (minimal tools for routing decisions)
ORCHESTRATOR_TOOLS = (
    CUSTOMER_MANAGEMENT_TOOLS  # get_customer_profile, update_customer_data
    + PROFILING_TOOLS  # check_profiling_completeness
)

# Profiling Agent Tools (used by profiling_node for customer data collection)
PROFILING_AGENT_TOOLS = (
    CUSTOMER_MANAGEMENT_TOOLS
    + PROFILING_TOOLS
)

# Sales Agent Tools (used by sales_node for B2B/large orders)
SALES_AGENT_TOOLS = SALES_MEETING_TOOLS

# Ecommerce Agent Tools (used by ecommerce_node for B2C/small orders)
ECOMMERCE_AGENT_TOOLS = PRODUCT_ECOMMERCE_TOOLS

# Support Agent Tools (used by support_node for complaints and technical support)
SUPPORT_AGENT_TOOLS = SUPPORT_TOOLS

# Legacy: Keep old names for backward compatibility
AGENT_TOOLS = PROFILING_AGENT_TOOLS

__all__ = [
    'ORCHESTRATOR_TOOLS',
    'PROFILING_AGENT_TOOLS',
    'SALES_AGENT_TOOLS',
    'ECOMMERCE_AGENT_TOOLS',
    'SUPPORT_AGENT_TOOLS',
    'CUSTOMER_MANAGEMENT_TOOLS',
    'PROFILING_TOOLS',
    'SALES_MEETING_TOOLS',
    'PRODUCT_ECOMMERCE_TOOLS',
    'SUPPORT_TOOLS',
    # Legacy
    'AGENT_TOOLS',
]
