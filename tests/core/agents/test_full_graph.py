"""
Test the full hana_agent graph to check for stuck issues
"""

import asyncio
import time

from src.orin_ai_crm.core.models.schemas import AgentState
from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import hana_agent


async def test_full_graph_with_images_request():
    """Test full graph: orchestrator → ecommerce_node with images request"""
    print("\n" + "="*80)
    print("FULL GRAPH TEST: Images request (ada gambarnya?)")
    print("="*80)

    state: AgentState = {
        "messages": [
            {"role": "user", "content": "Menarik, ada gambarnya?"}
        ],
        "phone_number": "628123456789",
        "lid_number": None,
        "contact_name": "Mosad",
    }

    start = time.time()
    try:
        result = await asyncio.wait_for(
            hana_agent.ainvoke(state, recursion_limit=15),
            timeout=120  # 2 minutes timeout
        )
        elapsed = time.time() - start
        print(f"\n✓ Completed in {elapsed:.2f}s")

        # Check orchestrator decision
        orch_decision = result.get("orchestrator_decision", {})
        print(f"\nOrchestrator decision: {orch_decision.get('next_agent', 'N/A')}")
        print(f"Reasoning: {orch_decision.get('reasoning', 'N/A')}")

        # Check agents called
        agents_called = result.get("agents_called", [])
        print(f"\nAgents called: {agents_called}")

        # Check if send_images was set
        send_images = result.get("send_images", [])
        if send_images:
            print(f"\n✓ SUCCESS: {len(send_images)} images to send")
            print(f"Images: {send_images}")
        else:
            print("\n✗ No images set to send")

        # Show final messages
        messages = result.get("messages", [])
        print(f"\nTotal messages: {len(messages)}")

        return len(send_images) > 0
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


async def test_full_graph_with_links_request():
    """Test full graph: orchestrator → ecommerce_node with links request"""
    print("\n" + "="*80)
    print("FULL GRAPH TEST: Links request (ada linknya?)")
    print("="*80)

    state: AgentState = {
        "messages": [
            {"role": "user", "content": "Ada link tokopedianya?"}
        ],
        "phone_number": "628123456789",
        "lid_number": None,
        "contact_name": "Customer",
    }

    start = time.time()
    try:
        result = await asyncio.wait_for(
            hana_agent.ainvoke(state, recursion_limit=15),
            timeout=120
        )
        elapsed = time.time() - start
        print(f"\n✓ Completed in {elapsed:.2f}s")

        orch_decision = result.get("orchestrator_decision", {})
        print(f"\nOrchestrator decision: {orch_decision.get('next_agent', 'N/A')}")

        agents_called = result.get("agents_called", [])
        print(f"Agents called: {agents_called}")

        # Check if ecommerce_links was set
        ecommerce_links = result.get("ecommerce_links", {})
        if ecommerce_links:
            print(f"\n✓ SUCCESS: Ecommerce links generated")
            print(f"Links: {list(ecommerce_links.keys())}")
        else:
            print("\n✗ No ecommerce links set")

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


async def main():
    """Run full graph tests"""
    print("\n" + "="*80)
    print("FULL HANA AGENT GRAPH TESTS")
    print("="*80)

    results = []

    # Test 1: Images request
    try:
        result1 = await test_full_graph_with_images_request()
        results.append(("Images request", result1))
    except Exception as e:
        print(f"Test crashed: {e}")
        results.append(("Images request", False))

    await asyncio.sleep(3)

    # Test 2: Links request
    try:
        result2 = await test_full_graph_with_links_request()
        results.append(("Links request", result2))
    except Exception as e:
        print(f"Test crashed: {e}")
        results.append(("Links request", False))

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")


if __name__ == "__main__":
    asyncio.run(main())
