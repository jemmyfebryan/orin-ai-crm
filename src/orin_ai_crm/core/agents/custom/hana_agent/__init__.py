from langgraph.graph import StateGraph, END
from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.nodes import (
    node_greeting_and_profiling,
    node_intent_classification,
    node_sales,
    node_ecommerce,
    node_quality_check,
    router_logic
)
from src.orin_ai_crm.core.agents.nodes.product_form_nodes import (
    node_product_form,
    handle_form_response
)
from src.orin_ai_crm.core.agents.nodes.quality_check_nodes import (
    node_final_message,
    node_human_takeover,
    quality_router,
)

def intent_classification_router(state: AgentState) -> str:
    """
    Route after intent classification.
    TEMPORARY: All customers go through form (mandatory data collection).
    Interactive profiling is DISABLED.
    """
    
    step = state.get("step", "profiling")
    route = state.get("route", "UNASSIGNED")
    customer_data = state.get("customer_data", {})
    # form_submitted = state.get("form_submitted", False)
    # awaiting_form = state.get("awaiting_form", False)
    is_onboarded = customer_data.get("is_onboarded")
    is_customer_data_filled = customer_data.get("is_filled")


    # ROUTING
    
    # If the next route is Human Takeover because of incapability of the AI
    if route == "HUMAN_TAKEOVER":
        return "human_takeover"
    
    # If customer is not yet onboarded, or the customer data is not yet all filled
    # it go to handle_form node
    # if (not is_onboarded) or (not is_customer_data_filled):
    #     return "form_node"

    # If data is filled even partially, route directly to final node
    # if is_customer_data_filled:
    #     # Route based on is_b2b flag
    #     is_b2b = customer_data.get("is_b2b", False)
    #     if is_b2b:
    #         return "sales_node"
    #     else:
    #         return "ecommerce_node"

    # Show form for data collection (TEMPORARY MANDATORY)
    if step in ["profiling", "greeting"]:
        return "greeting_profiling"

    # Profiling complete → sales
    if step == "profiling_complete":
        is_b2b = customer_data.get("is_b2b", False)
        if is_b2b:
            return "sales_node"
        else:
            return "ecommerce_node"
        
    # Let the profiling become tools, where we have a mandatory llm_with_tools

    # Already handled routes → quality check
    if route in ["PRODUCT_INFO", "SALES", "SUPPORT", "ECOMMERCE", "UNASSIGNED"]:
        return "quality_check"

    # Default fallback → greeting
    return "greeting_profiling"


# Inisialisasi Graph
workflow = StateGraph(AgentState)

# Daftarkan Node
workflow.add_node("intent_classification", node_intent_classification)
workflow.add_node("greeting_profiling", node_greeting_and_profiling)
workflow.add_node("sales_node", node_sales)
workflow.add_node("ecommerce_node", node_ecommerce)
workflow.add_node("quality_check", node_quality_check)
workflow.add_node("final_message", node_final_message)
workflow.add_node("human_takeover", node_human_takeover)

# workflow.add_node("product_form", node_product_form)
# workflow.add_node("handle_form", handle_form_response)

# Tentukan Alur (Edges & Router)
# Entry point: Intent Classification dulu
workflow.set_entry_point("intent_classification")

# Dari intent classification, router menentukan next step
# ALL routes go to quality_check before END
workflow.add_conditional_edges(
    "intent_classification",
    intent_classification_router
)

# Product form edge - check if form submitted
# workflow.add_conditional_edges(
#     "product_form",
#     lambda state: "handle_form" if state.get("form_submitted") else "awaiting_form",
#     {
#         "awaiting_form": END,  # Wait for customer response
#         "handle_form": "handle_form"
#     }
# )

# After handling form, route to final node
# workflow.add_conditional_edges(
#     "handle_form",
#     lambda state: state.get("next_route", "ecommerce_node"),
#     {
#         "ecommerce_node": "ecommerce_node",
#         "sales_node": "sales_node"
#     }
# )

workflow.add_conditional_edges(
    "greeting_profiling",
    router_logic,
    {
        "__end__": "quality_check",  # Route through quality check before END
        "node_greeting_and_profiling": "greeting_profiling",
        "sales_node": "sales_node",
        "ecommerce_node": "ecommerce_node"
    }
)

workflow.add_conditional_edges(
    "quality_check",
    quality_router,
    {
        "final_message": "final_message",
        "human_takeover": "human_takeover"
    }
)

# Sales and Ecommerce nodes → Quality Check (MUST before END)
workflow.add_edge("sales_node", "quality_check")
workflow.add_edge("ecommerce_node", "quality_check")

# Quality Check node → END (always ends after quality check)
workflow.add_edge("final_message", END)
workflow.add_edge("human_takeover", END)

# Compile bot siap pakai
hana_bot = workflow.compile()
