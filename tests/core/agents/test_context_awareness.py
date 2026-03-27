"""
Test context awareness - verify agent understands "produknya" refers to discussed product
"""

import asyncio
from langchain_core.messages import HumanMessage, AIMessage

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.custom.hana_agent.custom_agent import create_custom_agent
from src.orin_ai_crm.core.agents.config import get_llm
from src.orin_ai_crm.core.agents.tools.agent_tools import ECOMMERCE_AGENT_TOOLS
from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db


async def test_context_aware_product_request():
    """
    Test: When conversation discussed OBU V and user asks for "produknya",
    agent should only call tools for OBU V, not all products.
    """
    print("\n" + "="*80)
    print("TEST: Context-Aware Product Request")
    print("="*80)
    print("\nScenario:")
    print("1. Conversation discussed OBU V for gasoline motors")
    print("2. User asks: 'minta foto dan link produknya dong'")
    print("3. Expected: Agent should call tools for OBU V ONLY, not all 9 products")
    print("")

    # Get prompts
    system_prompt = await get_prompt_from_db("hana_ecommerce_agent")
    if not system_prompt:
        system_prompt = "You are a helpful assistant."

    from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import ECOMMERCE_REACT_PROMPT

    model = get_llm("advanced")

    agent = create_custom_agent(
        model=model,
        tools=ECOMMERCE_AGENT_TOOLS,
        system_prompt=system_prompt,
        react_prompt=ECOMMERCE_REACT_PROMPT,
        state_schema=AgentState,
        debug=False,
    )

    # Simulate conversation history where OBU V was discussed
    messages_history = [
        AIMessage(content="Halo! Untuk motor bensin, Kakak bisa pilih OBU V."),
        AIMessage(content="OBU V memiliki fitur lengkap: lacak real-time, matikan mesin jarak jauh, sadap suara."),
        AIMessage(content="Harga OBU V terjangkau, 25rb/bulan."),
    ]

    # Current request
    messages = [
        HumanMessage(content="minta foto dan link produknya dong")
    ]

    state: AgentState = {
        "messages": messages,
        "messages_history": messages_history,  # IMPORTANT: This provides context!
        "customer_id": 1,
        "customer_data": {
            "id": 1,
            "name": "Mojo",
            "domicile": "Surabaya",
            "vehicle_alias": "motor",
            "unit_qty": 0,
            "is_b2b": False,
            "is_onboarded": True,
        }
    }

    print("Invoking agent...")
    result = await agent.ainvoke(state, recursion_limit=10)

    # Analyze tool calls
    all_messages = result.get("messages", [])

    print("\n" + "="*80)
    print("ANALYSIS:")
    print("="*80)

    # Count tool calls
    get_ecommerce_links_calls = []
    send_product_images_calls = []

    for msg in all_messages:
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = tc.get('name')
                print(f"  Tool called: {tool_name}")

                if tool_name == 'get_ecommerce_links':
                    product_id = tc.get('args', {}).get('product_id')
                    get_ecommerce_links_calls.append(product_id)
                elif tool_name == 'send_product_images':
                    sort_orders = tc.get('args', {}).get('sort_orders', [])
                    send_product_images_calls.extend(sort_orders)

    print(f"\nget_ecommerce_links called {len(get_ecommerce_links_calls)} times")
    print(f"Product IDs: {get_ecommerce_links_calls}")

    print(f"\nsend_product_images called for sort_orders: {send_product_images_calls}")

    # Evaluate results
    print("\n" + "="*80)
    print("EVALUATION:")
    print("="*80)

    # OBU V has product_id=12 and sort_order=2
    obu_v_id = 12
    obu_v_sort_order = 2

    success = True
    reasons = []

    # Check if called too many products
    if len(get_ecommerce_links_calls) > 2:
        success = False
        reasons.append(f"✗ FAIL: Called get_ecommerce_links {len(get_ecommerce_links_calls)} times (expected 1-2)")
    else:
        reasons.append(f"✓ PASS: Called get_ecommerce_links {len(get_ecommerce_links_calls)} time(s)")

    # Check if OBU V was included
    if obu_v_id in get_ecommerce_links_calls:
        reasons.append(f"✓ PASS: OBU V (product_id={obu_v_id}) was included")
    else:
        success = False
        reasons.append(f"✗ FAIL: OBU V (product_id={obu_v_id}) was NOT included")

    # Check if send_product_images included OBU V
    if obu_v_sort_order in send_product_images_calls:
        reasons.append(f"✓ PASS: OBU V image (sort_order={obu_v_sort_order}) was included")
    else:
        reasons.append(f"⚠ WARNING: OBU V image not in send_product_images")

    for reason in reasons:
        print(f"  {reason}")

    print("\n" + "="*80)
    if success:
        print("✓ TEST PASSED: Agent showed context awareness")
    else:
        print("✗ TEST FAILED: Agent did not show context awareness")
    print("="*80)

    return success


async def test_no_context_general_request():
    """
    Test: When no specific product was discussed and user asks generally,
    agent should show top products.
    """
    print("\n" + "="*80)
    print("TEST: General Request (No Context)")
    print("="*80)
    print("\nScenario:")
    print("1. No previous product discussion")
    print("2. User asks: 'ada link tokopedianya?'")
    print("3. Expected: Agent shows multiple products")
    print("")

    # Get prompts
    system_prompt = await get_prompt_from_db("hana_ecommerce_agent")
    if not system_prompt:
        system_prompt = "You are a helpful assistant."

    from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import ECOMMERCE_REACT_PROMPT

    model = get_llm("advanced")

    agent = create_custom_agent(
        model=model,
        tools=ECOMMERCE_AGENT_TOOLS,
        system_prompt=system_prompt,
        react_prompt=ECOMMERCE_REACT_PROMPT,
        state_schema=AgentState,
        debug=False,
    )

    # No conversation history (or empty)
    messages_history = []

    messages = [
        HumanMessage(content="ada link tokopedianya?")
    ]

    state: AgentState = {
        "messages": messages,
        "messages_history": messages_history,
        "customer_id": 1,
        "customer_data": {
            "id": 1,
            "name": "Customer",
            "domicile": "Jakarta",
            "vehicle_alias": "motor",
            "unit_qty": 0,
            "is_b2b": False,
            "is_onboarded": True,
        }
    }

    print("Invoking agent...")
    result = await agent.ainvoke(state, recursion_limit=10)

    # Analyze
    all_messages = result.get("messages", [])

    print("\n" + "="*80)
    print("ANALYSIS:")
    print("="*80)

    get_ecommerce_links_calls = []

    for msg in all_messages:
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = tc.get('name')
                if tool_name == 'get_ecommerce_links':
                    product_id = tc.get('args', {}).get('product_id')
                    get_ecommerce_links_calls.append(product_id)
                    print(f"  Tool called: {tool_name} for product_id={product_id}")

    print(f"\nget_ecommerce_links called {len(get_ecommerce_links_calls)} times")
    print(f"Product IDs: {get_ecommerce_links_calls}")

    print("\n" + "="*80)
    print("EVALUATION:")
    print("="*80)

    # For general request, showing multiple products is acceptable
    if len(get_ecommerce_links_calls) >= 3:
        print(f"✓ PASS: Agent showed {len(get_ecommerce_links_calls)} products (appropriate for general request)")
        success = True
    else:
        print(f"✗ FAIL: Agent only showed {len(get_ecommerce_links_calls)} product(s)")
        success = False

    print("="*80)

    return success


async def main():
    """Run context awareness tests"""
    print("\n" + "="*80)
    print("CONTEXT AWARENESS TESTS")
    print("="*80)

    results = []

    # Test 1: Context-aware request
    try:
        result1 = await test_context_aware_product_request()
        results.append(("Context-aware product request", result1))
    except Exception as e:
        print(f"Test crashed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Context-aware product request", False))

    await asyncio.sleep(2)

    # Test 2: General request
    try:
        result2 = await test_no_context_general_request()
        results.append(("General request (no context)", result2))
    except Exception as e:
        print(f"Test crashed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("General request (no context)", False))

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\nTotal: {passed}/{total} tests passed")


if __name__ == "__main__":
    asyncio.run(main())
