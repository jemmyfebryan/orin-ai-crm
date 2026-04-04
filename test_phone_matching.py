#!/usr/bin/env python3
"""
Test script for Indonesian phone number matching functionality.

This tests the phone utility functions to ensure they correctly handle
different phone number formats.
"""

import sys
import os

# Import the functions directly from the module file
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/orin_ai_crm/core/utils'))

# Import directly from phone_utils module to avoid SQLAlchemy dependency
from phone_utils import (
    normalize_indonesian_phone_number,
    generate_phone_number_variations,
    build_phone_number_sql_conditions
)


def test_normalize_phone():
    """Test phone number normalization."""
    print("=" * 60)
    print("TEST 1: normalize_indonesian_phone_number()")
    print("=" * 60)

    test_cases = [
        ("+6285123456789", "6285123456789"),
        ("6285123456789", "6285123456789"),
        ("085123456789", "6285123456789"),
        ("+62123123123", "62123123123"),
        ("62123123123", "62123123123"),
        ("0123123123", "62123123123"),
    ]

    all_passed = True
    for input_phone, expected_output in test_cases:
        result = normalize_indonesian_phone_number(input_phone)
        passed = result == expected_output
        all_passed = all_passed and passed
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: '{input_phone}' → '{result}' (expected: '{expected_output}')")

    print()
    return all_passed


def test_generate_variations():
    """Test phone number variation generation."""
    print("=" * 60)
    print("TEST 2: generate_phone_number_variations()")
    print("=" * 60)

    test_cases = [
        {
            "input": "085123456789",
            "expected_variations": ["'085123456789'", "'6285123456789'", "'+6285123456789'"],
        },
        {
            "input": "6285123456789",
            "expected_variations": ["'6285123456789'", "'+6285123456789'", "'085123456789'"],
        },
        {
            "input": "+6285123456789",
            "expected_variations": ["'+6285123456789'", "'6285123456789'", "'085123456789'"],
        },
    ]

    all_passed = True
    for test_case in test_cases:
        input_phone = test_case["input"]
        result = generate_phone_number_variations(input_phone)
        expected = test_case["expected_variations"]

        # Check if all expected variations are present
        has_all = all(var in result for var in expected)
        # Check if result has the same number of variations
        same_count = len(result) == len(expected)

        passed = has_all and same_count
        all_passed = all_passed and passed
        status = "✅ PASS" if passed else "❌ FAIL"

        print(f"{status}: Input: '{input_phone}'")
        print(f"  Result:   {result}")
        print(f"  Expected: {expected}")
        if not passed:
            print(f"  Missing:  {[v for v in expected if v not in result]}")
            print(f"  Extra:    {[v for v in result if v not in expected]}")

    print()
    return all_passed


def test_build_sql_conditions():
    """Test SQL condition building."""
    print("=" * 60)
    print("TEST 3: build_phone_number_sql_conditions()")
    print("=" * 60)

    test_cases = [
        {
            "input": "085123456789",
            "column": "phone_number",
            "expected_contains": [
                "phone_number = '085123456789'",
                "phone_number = '6285123456789'",
                "phone_number = '+6285123456789'",
            ],
        },
        {
            "input": "628123456789",
            "column": "phone_number",
            "expected_contains": [
                "phone_number = '628123456789'",
                "phone_number = '+628123456789'",
                "phone_number = '08123456789'",
            ],
        },
    ]

    all_passed = True
    for test_case in test_cases:
        input_phone = test_case["input"]
        column = test_case["column"]
        result = build_phone_number_sql_conditions(input_phone, column)
        expected_contains = test_case["expected_contains"]

        # Check if all expected conditions are present in result
        has_all = all(cond in result for cond in expected_contains)
        # Check that result uses OR
        has_or = " OR " in result

        passed = has_all and has_or
        all_passed = all_passed and passed
        status = "✅ PASS" if passed else "❌ FAIL"

        print(f"{status}: Input: '{input_phone}', Column: '{column}'")
        print(f"  Result: {result}")
        if not passed:
            for cond in expected_contains:
                present = cond in result
                print(f"    {cond}: {'✓' if present else '✗ MISSING'}")

    print()
    return all_passed


def test_actual_sql_query():
    """Test actual SQL query that would be generated."""
    print("=" * 60)
    print("TEST 4: Actual SQL Query Generation")
    print("=" * 60)

    test_phone = "085123456789"
    phone_conditions = build_phone_number_sql_conditions(test_phone)

    sql_query = f"""SELECT api_token FROM users
WHERE ({phone_conditions})
AND deleted_at IS NULL"""

    print(f"Input phone number: {test_phone}")
    print()
    print("Generated SQL Query:")
    print("-" * 60)
    print(sql_query)
    print("-" * 60)
    print()

    # Verify the query contains all necessary conditions
    required_conditions = [
        "phone_number = '085123456789'",
        "phone_number = '6285123456789'",
        "phone_number = '+6285123456789'",
        "deleted_at IS NULL"
    ]

    all_present = all(cond in sql_query for cond in required_conditions)
    status = "✅ PASS" if all_present else "❌ FAIL"
    print(f"{status}: SQL query contains all required conditions")

    for cond in required_conditions:
        present = cond in sql_query
        print(f"  {'✓' if present else '✗'} {cond}")

    print()
    return all_present


def test_cross_format_matching():
    """Test that different formats of the same number match each other."""
    print("=" * 60)
    print("TEST 5: Cross-Format Matching (Same Number, Different Formats)")
    print("=" * 60)

    # Same phone number in different formats
    formats = [
        "+6285123456789",
        "6285123456789",
        "085123456789",
    ]

    # All should normalize to the same value
    normalized_results = [normalize_indonesian_phone_number(p) for p in formats]

    # Check if all normalize to the same value
    all_same = len(set(normalized_results)) == 1
    status = "✅ PASS" if all_same else "❌ FAIL"

    print(f"{status}: All formats normalize to the same value")
    for i, (original, normalized) in enumerate(zip(formats, normalized_results)):
        print(f"  {i+1}. '{original}' → '{normalized}'")

    print()
    return all_same


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("INDONESIAN PHONE NUMBER MATCHING TEST SUITE")
    print("=" * 60)
    print()

    results = []

    # Run all tests
    results.append(("Normalize Phone", test_normalize_phone()))
    results.append(("Generate Variations", test_generate_variations()))
    results.append(("Build SQL Conditions", test_build_sql_conditions()))
    results.append(("SQL Query Generation", test_actual_sql_query()))
    results.append(("Cross-Format Matching", test_cross_format_matching()))

    # Print summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        all_passed = all_passed and passed

    print()
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
