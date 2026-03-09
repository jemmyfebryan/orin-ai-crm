"""
Agent Nodes Package
"""

from src.orin_ai_crm.core.agents.nodes.profiling_nodes import (
    get_natural_vehicle_type,
    get_user_identifier,
    extract_customer_info,
    determine_next_question,
    create_lead_routing,
    node_greeting_and_profiling,
    router_logic
)

from src.orin_ai_crm.core.agents.nodes.sales_nodes import node_sales
from src.orin_ai_crm.core.agents.nodes.ecommerce_nodes import node_ecommerce
from src.orin_ai_crm.core.agents.nodes.intent_classification_nodes import node_intent_classification
from src.orin_ai_crm.core.agents.nodes.quality_check_nodes import node_quality_check
from src.orin_ai_crm.core.agents.nodes.product_form_nodes import (
    node_product_form,
    handle_form_response
)

__all__ = [
    # Helper functions
    "get_natural_vehicle_type",
    "get_user_identifier",

    # Profiling nodes
    "extract_customer_info",
    "determine_next_question",
    "create_lead_routing",
    "node_greeting_and_profiling",

    # Intent Classification
    "node_intent_classification",

    # Product Form
    "node_product_form",
    "handle_form_response",

    # Quality Check
    "node_quality_check",

    # Router
    "router_logic",

    # Sales & Ecommerce nodes
    "node_sales",
    "node_ecommerce",
]
