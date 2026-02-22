from langgraph.graph import StateGraph, END
from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.nodes import (
    node_greeting_and_profiling,
    node_intent_classification,
    node_sales,
    node_ecommerce,
    router_logic
)

# Inisialisasi Graph
workflow = StateGraph(AgentState)

# Daftarkan Node
workflow.add_node("intent_classification", node_intent_classification)
workflow.add_node("greeting_profiling", node_greeting_and_profiling)
workflow.add_node("sales_node", node_sales)
workflow.add_node("ecommerce_node", node_ecommerce)

# Tentukan Alur (Edges & Router)
# Entry point: Intent Classification dulu
workflow.set_entry_point("intent_classification")

# Dari intent classification, router menentukan next step
workflow.add_conditional_edges(
    "intent_classification",
    lambda state: state.get("step", "profiling"),
    {
        "profiling": "greeting_profiling",
        "profiling_complete": "sales_node",  # Will route via router_logic
        "greeting": END,
        "complaint": END,
        "support": END,
        "product_qa": END,
        "handle_reschedule": "sales_node",
        "no_meeting_found": END,
        "need_identifier": END,
        "order_guidance": END,
        "general": END,
    }
)

workflow.add_conditional_edges(
    "greeting_profiling",
    router_logic,
    {
        "__end__": END,
        "node_greeting_and_profiling": "greeting_profiling",
        "sales_node": "sales_node",
        "ecommerce_node": "ecommerce_node"
    }
)

workflow.add_edge("sales_node", END)
workflow.add_edge("ecommerce_node", END)

# Compile bot siap pakai
hana_bot = workflow.compile()
