"""
Integration test for custom agent - tests real ecommerce flow
"""

import asyncio
import time
from langchain_core.messages import HumanMessage

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.custom.hana_agent.custom_agent import create_custom_agent
from src.orin_ai_crm.core.agents.config import get_llm
from src.orin_ai_crm.core.agents.tools.agent_tools import ECOMMERCE_AGENT_TOOLS


async def test_ecommerce_agent_basic():
    """Test ecommerce agent with a simple question"""
    print("\n" + "="*80)
    print("TEST 1: Simple question (no tools)")
    print("="*80)

    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    # Get the actual system prompt from DB
    system_prompt = await get_prompt_from_db("hana_ecommerce_agent")
    if not system_prompt:
        system_prompt = "You are a helpful assistant from ORIN GPS Tracker."

    from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import ECOMMERCE_REACT_PROMPT

    model = get_llm("advanced")

    agent = create_custom_agent(
        model=model,
        tools=ECOMMERCE_AGENT_TOOLS,
        system_prompt=system_prompt,
        react_prompt=ECOMMERCE_REACT_PROMPT,
        state_schema=AgentState,
        debug=True,
    )

    state: AgentState = {
        "messages": [HumanMessage(content="Halo, apa kabar?")],
        "customer_id": 1,
        "customer_data": {
            "id": 1,
            "name": "Test Customer",
            "domicile": "Jakarta",
            "vehicle_alias": "motor",
            "unit_qty": 0,
            "is_b2b": False,
            "is_onboarded": True,
        }
    }

    start = time.time()
    try:
        result = await asyncio.wait_for(
            agent.ainvoke(state, recursion_limit=10),
            timeout=30  # 30 second timeout
        )
        elapsed = time.time() - start
        print(f"\n✓ Completed in {elapsed:.2f}s")

        messages = result.get("messages", [])
        print(f"\nTotal messages in response: {len(messages)}")
        for i, msg in enumerate(messages[-3:]):  # Show last 3 messages
            print(f"\n[Message {i+1}] {type(msg).__name__}: {msg.content[:200]}...")

        return True
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"\n✗ TIMEOUT after {elapsed:.2f}s")
        return False
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n✗ ERROR after {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ecommerce_agent_with_tool_calls():
    """Test ecommerce agent asking for product images (the original problem)"""
    print("\n" + "="*80)
    print("TEST 2: Product images request (should call tools)")
    print("="*80)

    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    system_prompt = await get_prompt_from_db("hana_ecommerce_agent")
    if not system_prompt:
        system_prompt = "You are a helpful assistant from ORIN GPS Tracker."

    from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import ECOMMERCE_REACT_PROMPT

    model = get_llm("advanced")

    agent = create_custom_agent(
        model=model,
        tools=ECOMMERCE_AGENT_TOOLS,
        system_prompt=system_prompt,
        react_prompt=ECOMMERCE_REACT_PROMPT,
        state_schema=AgentState,
        debug=True,
    )

    state: AgentState = {
        "messages": [HumanMessage(content="Menarik, ada gambarnya?")],
        "customer_id": 13,
        "customer_data": {
            "id": 13,
            "name": "Mosad",
            "domicile": "Surabaya",
            "vehicle_alias": "motor",
            "unit_qty": 0,
            "is_b2b": False,
            "is_onboarded": True,
        }
    }

    start = time.time()
    try:
        result = await asyncio.wait_for(
            agent.ainvoke(state, recursion_limit=10),
            timeout=60  # 60 second timeout for tool calls
        )
        elapsed = time.time() - start
        print(f"\n✓ Completed in {elapsed:.2f}s")

        messages = result.get("messages", [])
        print(f"\nTotal messages in response: {len(messages)}")

        # Check which tools were called
        tool_calls = []
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append(tc['name'])

        print(f"\nTools called: {tool_calls}")

        # Check if send_product_images was called
        if 'send_product_images' in tool_calls:
            print("\n✓ SUCCESS: send_product_images was called!")
        else:
            print("\n✗ FAIL: send_product_images was NOT called!")

        # Show last few messages
        print("\nLast 3 messages:")
        for i, msg in enumerate(messages[-3:]):
            msg_type = type(msg).__name__
            content = msg.content[:200] if hasattr(msg, 'content') else str(msg)[:200]
            print(f"\n[{i+1}] {msg_type}: {content}...")

        return 'send_product_images' in tool_calls
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"\n✗ TIMEOUT after {elapsed:.2f}s")
        return False
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n✗ ERROR after {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ecommerce_agent_links_request():
    """Test ecommerce agent asking for links"""
    print("\n" + "="*80)
    print("TEST 3: Product links request")
    print("="*80)

    from src.orin_ai_crm.core.agents.tools.prompt_tools import get_prompt_from_db

    system_prompt = await get_prompt_from_db("hana_ecommerce_agent")
    if not system_prompt:
        system_prompt = "You are a helpful assistant from ORIN GPS Tracker."

    from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import ECOMMERCE_REACT_PROMPT

    model = get_llm("advanced")

    agent = create_custom_agent(
        model=model,
        tools=ECOMMERCE_AGENT_TOOLS,
        system_prompt=system_prompt,
        react_prompt=ECOMMERCE_REACT_PROMPT,
        state_schema=AgentState,
        debug=False,  # Less verbose
    )

    state: AgentState = {
        "messages": [HumanMessage(content="Ada linknya untuk tokopedia?")],
        "customer_id": 1,
        "customer_data": {
            "id": 1,
            "name": "Test Customer",
            "domicile": "Jakarta",
            "vehicle_alias": "motor",
            "unit_qty": 0,
            "is_b2b": False,
            "is_onboarded": True,
        }
    }

    start = time.time()
    try:
        result = await asyncio.wait_for(
            agent.ainvoke(state, recursion_limit=10),
            timeout=60
        )
        elapsed = time.time() - start
        print(f"\n✓ Completed in {elapsed:.2f}s")

        messages = result.get("messages", [])

        # Check which tools were called
        tool_calls = []
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append(tc['name'])

        print(f"Tools called: {tool_calls}")

        # Check if get_ecommerce_links was called
        if 'get_ecommerce_links' in tool_calls:
            print("✓ SUCCESS: get_ecommerce_links was called!")
            return True
        else:
            print("✗ FAIL: get_ecommerce_links was NOT called!")
            return False

    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"\n✗ TIMEOUT after {elapsed:.2f}s")
        return False
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n✗ ERROR after {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all integration tests"""
    print("\n" + "="*80)
    print("CUSTOM AGENT INTEGRATION TESTS")
    print("="*80)

    results = []

    # Test 1: Basic conversation
    try:
        result1 = await test_ecommerce_agent_basic()
        results.append(("Basic conversation", result1))
    except Exception as e:
        print(f"Test 1 crashed: {e}")
        results.append(("Basic conversation", False))

    await asyncio.sleep(2)  # Breather

    # Test 2: Product images (the main problem)
    try:
        result2 = await test_ecommerce_agent_with_tool_calls()
        results.append(("Product images", result2))
    except Exception as e:
        print(f"Test 2 crashed: {e}")
        results.append(("Product images", False))

    await asyncio.sleep(2)  # Breather

    # Test 3: Links request
    try:
        result3 = await test_ecommerce_agent_links_request()
        results.append(("Product links", result3))
    except Exception as e:
        print(f"Test 3 crashed: {e}")
        results.append(("Product links", False))

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

    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")


if __name__ == "__main__":
    asyncio.run(main())
