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

# Inisialisasi Graph
workflow = StateGraph(AgentState)

# Daftarkan Node
workflow.add_node("intent_classification", node_intent_classification)
workflow.add_node("greeting_profiling", node_greeting_and_profiling)
workflow.add_node("sales_node", node_sales)
workflow.add_node("ecommerce_node", node_ecommerce)
workflow.add_node("quality_check", node_quality_check)

# Tentukan Alur (Edges & Router)
# Entry point: Intent Classification dulu
workflow.set_entry_point("intent_classification")

# Dari intent classification, router menentukan next step
# ALL routes go to quality_check before END
workflow.add_conditional_edges(
    "intent_classification",
    lambda state: state.get("step", "profiling"),
    {
        "profiling": "greeting_profiling",
        "profiling_complete": "sales_node",
        "greeting": "quality_check",
        "complaint": "quality_check",
        "support": "quality_check",
        "product_qa": "quality_check",
        "handle_reschedule": "sales_node",
        "no_meeting_found": "quality_check",
        "need_identifier": "quality_check",
        "order_guidance": "quality_check",
        "general": "quality_check",
    }
)

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

# Sales and Ecommerce nodes → Quality Check (MUST before END)
workflow.add_edge("sales_node", "quality_check")
workflow.add_edge("ecommerce_node", "quality_check")

# Quality Check node → END (always ends after quality check)
workflow.add_edge("quality_check", END)

# Compile bot siap pakai
hana_bot = workflow.compile()
