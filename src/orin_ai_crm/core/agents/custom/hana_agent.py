from langgraph.graph import StateGraph, END
from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.nodes import (
    node_greeting_and_profiling,
    node_sales,
    node_ecommerce,
    router_logic
)

# Inisialisasi Graph
workflow = StateGraph(AgentState)

# Daftarkan Node
workflow.add_node("greeting_profiling", node_greeting_and_profiling)
workflow.add_node("sales_node", node_sales)
workflow.add_node("ecommerce_node", node_ecommerce)

# Tentukan Alur (Edges & Router)
workflow.set_entry_point("greeting_profiling")

workflow.add_conditional_edges(
    "greeting_profiling",
    router_logic,
    {
        "node_greeting_and_profiling": END,
        "sales_node": "sales_node",
        "ecommerce_node": "ecommerce_node"
    }
)

workflow.add_edge("sales_node", END)
workflow.add_edge("ecommerce_node", END)

# Compile bot siap pakai
hana_bot = workflow.compile()
