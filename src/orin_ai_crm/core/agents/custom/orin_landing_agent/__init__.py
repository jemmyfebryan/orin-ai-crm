"""
Orin Landing AI Agent - API-based, text-only customer service agent

This module exports the compiled orin_landing_agent graph for use in API requests.

Key differences from hana_agent:
- NO intent classification (direct to orchestrator)
- Text-based only (no images/PDFs in ecommerce_agent)
- Limited tools in support_agent
- human_takeover sends wa.me link (does NOT set database flag)
- Uses lid_number for customer identification
- API-based (JSON request/response), not webhook-based

Usage:
    from src.orin_ai_crm.core.agents.custom.orin_landing_agent import orin_landing_agent

    # Prepare state with lid_number (not phone_number)
    state = {
        "lid_number": "customer_lid_number",
        "contact_name": "Customer Name",
        "messages": [HumanMessage(content="Hello")],
        "messages_history": [],  # Optional conversation history
    }

    # Invoke the agent
    result = await orin_landing_agent.ainvoke(state, recursion_limit=20)

    # Get final WhatsApp bubbles
    final_messages = result.get("final_messages", [])
"""

from .agent_graph import orin_landing_agent, build_orin_landing_agent_graph

__all__ = ['orin_landing_agent', 'build_orin_landing_agent_graph']
