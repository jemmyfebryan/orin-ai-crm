"""
Test JSON extraction from mixed text
"""

from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import extract_json_from_text
import json


def test_json_extraction():
    """Test that JSON can be extracted from mixed text"""
    print("\n" + "="*80)
    print("TEST: JSON Extraction from Mixed Text")
    print("="*80)

    # Test case 1: Clean JSON
    test1 = '{"next_agent":"ecommerce","reasoning":"test","plan":"test"}'
    result1 = extract_json_from_text(test1)
    data1 = json.loads(result1)
    assert data1["next_agent"] == "ecommerce"
    print("✓ Test 1 passed: Clean JSON")

    # Test case 2: JSON with text before
    test2 = 'Here is my decision:\n{"next_agent":"sales","reasoning":"test","plan":"test"}'
    result2 = extract_json_from_text(test2)
    data2 = json.loads(result2)
    assert data2["next_agent"] == "sales"
    print("✓ Test 2 passed: JSON with text before")

    # Test case 3: JSON with text after
    test3 = '{"next_agent":"final","reasoning":"test","plan":"test"}\n\nThis is my final decision.'
    result3 = extract_json_from_text(test3)
    data3 = json.loads(result3)
    assert data3["next_agent"] == "final"
    print("✓ Test 3 passed: JSON with text after")

    # Test case 4: JSON with text before and after
    test4 = 'Thinking...\n\n{"next_agent":"profiling","reasoning":"test","plan":"test"}\n\nI recommend profiling.'
    result4 = extract_json_from_text(test4)
    data4 = json.loads(result4)
    assert data4["next_agent"] == "profiling"
    print("✓ Test 4 passed: JSON with text before and after")

    # Test case 5: JSON with nested content (like reasoning field)
    # Note: Need double backslash to get literal backslash in string
    test5 = '{"next_agent":"ecommerce","reasoning":"Customer wants to buy. They said \\"boleh\\" which means yes.","plan":"Send link"}'
    result5 = extract_json_from_text(test5)
    data5 = json.loads(result5)
    assert data5["next_agent"] == "ecommerce"
    assert "boleh" in data5["reasoning"]
    print("✓ Test 5 passed: JSON with escaped quotes")

    # Test case 6: No JSON (return original)
    test6 = 'This is just plain text with no JSON'
    result6 = extract_json_from_text(test6)
    assert result6 == test6
    print("✓ Test 6 passed: No JSON returns original")

    print("\n" + "="*80)
    print("✓ ALL TESTS PASSED")
    print("="*80)


if __name__ == "__main__":
    test_json_extraction()
