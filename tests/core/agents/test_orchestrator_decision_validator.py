"""
Test OrchestratorDecision field validator normalizes various LLM outputs.
"""

from src.orin_ai_crm.core.agents.custom.hana_agent.agent_graph import OrchestratorDecision
from pydantic import ValidationError


def test_valid_next_agent_values():
    """Test that valid values work correctly."""
    print("\n" + "="*80)
    print("TEST: Valid Next Agent Values")
    print("="*80)

    valid_values = ["profiling", "sales", "ecommerce", "support", "final"]

    for value in valid_values:
        decision = OrchestratorDecision(
            next_agent=value,
            reasoning=f"Test reasoning for {value}",
            plan=f"Test plan for {value}"
        )
        assert decision.next_agent == value
        print(f"✓ '{value}' accepted correctly")

    print(f"\n✓ All {len(valid_values)} valid values accepted")


def test_normalize_agent_suffix():
    """Test that '_agent' suffix is stripped."""
    print("\n" + "="*80)
    print("TEST: Normalize '_agent' Suffix")
    print("="*80)

    test_cases = [
        ("profiling_agent", "profiling"),
        ("sales_agent", "sales"),
        ("ecommerce_agent", "ecommerce"),
        ("support_agent", "support"),
        ("final_agent", "final"),
    ]

    for input_val, expected in test_cases:
        decision = OrchestratorDecision(
            next_agent=input_val,
            reasoning=f"Test reasoning for {input_val}",
            plan=f"Test plan for {input_val}"
        )
        assert decision.next_agent == expected
        print(f"✓ '{input_val}' → '{expected}'")

    print(f"\n✓ All {len(test_cases)} '_agent' suffixes stripped correctly")


def test_normalize_node_suffix():
    """Test that '_node' suffix is stripped."""
    print("\n" + "="*80)
    print("TEST: Normalize '_node' Suffix")
    print("="*80)

    test_cases = [
        ("profiling_node", "profiling"),
        ("sales_node", "sales"),
        ("ecommerce_node", "ecommerce"),
    ]

    for input_val, expected in test_cases:
        decision = OrchestratorDecision(
            next_agent=input_val,
            reasoning=f"Test reasoning",
            plan=f"Test plan"
        )
        assert decision.next_agent == expected
        print(f"✓ '{input_val}' → '{expected}'")

    print(f"\n✓ All {len(test_cases)} '_node' suffixes stripped correctly")


def test_normalize_word_suffix():
    """Test that ' agent' word suffix is stripped."""
    print("\n" + "="*80)
    print("TEST: Normalize ' agent' Word Suffix")
    print("="*80)

    test_cases = [
        ("profiling agent", "profiling"),
        ("sales agent", "sales"),
        ("ecommerce agent", "ecommerce"),
        ("support agent", "support"),
    ]

    for input_val, expected in test_cases:
        decision = OrchestratorDecision(
            next_agent=input_val,
            reasoning=f"Test reasoning",
            plan=f"Test plan"
        )
        assert decision.next_agent == expected
        print(f"✓ '{input_val}' → '{expected}'")

    print(f"\n✓ All {len(test_cases)} ' agent' suffixes stripped correctly")


def test_normalize_common_variations():
    """Test that common variations are mapped correctly."""
    print("\n" + "="*80)
    print("TEST: Normalize Common Variations")
    print("="*80)

    test_cases = [
        ("profile", "profiling"),
        ("sale", "sales"),
        ("e-commerce", "ecommerce"),
        ("finalize", "final"),
        ("end", "final"),
        ("done", "final"),
    ]

    for input_val, expected in test_cases:
        decision = OrchestratorDecision(
            next_agent=input_val,
            reasoning=f"Test reasoning",
            plan=f"Test plan"
        )
        assert decision.next_agent == expected
        print(f"✓ '{input_val}' → '{expected}'")

    print(f"\n✓ All {len(test_cases)} common variations normalized correctly")


def test_case_insensitive():
    """Test that values are case-insensitive."""
    print("\n" + "="*80)
    print("TEST: Case Insensitive Normalization")
    print("="*80)

    test_cases = [
        ("PROFILING", "profiling"),
        ("Sales", "sales"),
        ("ECommerce", "ecommerce"),
        ("SuPpOrT", "support"),
        ("FINAL", "final"),
    ]

    for input_val, expected in test_cases:
        decision = OrchestratorDecision(
            next_agent=input_val,
            reasoning=f"Test reasoning",
            plan=f"Test plan"
        )
        assert decision.next_agent == expected
        print(f"✓ '{input_val}' → '{expected}'")

    print(f"\n✓ All {len(test_cases)} case variations handled correctly")


def test_invalid_value_rejected():
    """Test that invalid values raise ValidationError."""
    print("\n" + "="*80)
    print("TEST: Invalid Values Rejected")
    print("="*80)

    invalid_values = ["invalid", "random", "unknown", "xyz"]

    for value in invalid_values:
        try:
            OrchestratorDecision(
                next_agent=value,
                reasoning="Test reasoning",
                plan="Test plan"
            )
            assert False, f"Should have raised ValidationError for '{value}'"
        except ValidationError as e:
            print(f"✓ '{value}' correctly rejected with ValidationError")

    print(f"\n✓ All {len(invalid_values)} invalid values rejected correctly")


def test_combined_normalization():
    """Test complex cases with multiple issues."""
    print("\n" + "="*80)
    print("TEST: Combined Normalization")
    print("="*80)

    test_cases = [
        ("PROFILING_AGENT", "profiling"),  # Uppercase + _agent suffix
        ("  Sales  ", "sales"),  # Whitespace
        ("ecommerce_agent  ", "ecommerce"),  # Suffix + whitespace
        ("support_agent", "support"),  # Standard _agent case
    ]

    for input_val, expected in test_cases:
        decision = OrchestratorDecision(
            next_agent=input_val,
            reasoning=f"Test reasoning",
            plan=f"Test plan"
        )
        assert decision.next_agent == expected
        print(f"✓ '{input_val}' → '{expected}'")

    print(f"\n✓ All {len(test_cases)} complex normalizations handled correctly")


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("ORCHESTRATOR DECISION VALIDATOR TESTS")
    print("="*80)

    test_valid_next_agent_values()
    test_normalize_agent_suffix()
    test_normalize_node_suffix()
    test_normalize_word_suffix()
    test_normalize_common_variations()
    test_case_insensitive()
    test_invalid_value_rejected()
    test_combined_normalization()

    print("\n" + "="*80)
    print("✓ ALL TESTS PASSED")
    print("="*80)
    print("\nSummary:")
    print("  ✓ Valid values accepted")
    print("  ✓ '_agent' suffix stripped")
    print("  ✓ '_node' suffix stripped")
    print("  ✓ ' agent' word suffix stripped")
    print("  ✓ Common variations mapped correctly")
    print("  ✓ Case-insensitive matching")
    print("  ✓ Invalid values rejected")
    print("  ✓ Combined normalization works")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
