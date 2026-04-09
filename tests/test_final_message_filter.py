"""
Test Final Message Filter

This test verifies that the rule-based message filter works correctly.
"""
import asyncio
from dotenv import load_dotenv

load_dotenv()


def test_filter_final_messages():
    from src.orin_ai_crm.core.agents.nodes.quality_check_nodes import filter_final_messages

    print("\n" + "="*80)
    print("TEST: Final Message Filter")
    print("="*80)

    test_cases = [
        {
            "name": "Replace exclamation after customer name with comma",
            "customer_name": "Budi",
            "input_messages": [
                "Halo kak Budi! Ada yang bisa saya bantu?",
                "Terima kasih Budi! sudah saya catat.",
            ],
            "expected_output": [
                "Halo kak Budi, Ada yang bisa saya bantu?",
                "Terima kasih Budi, sudah saya catat.",
            ]
        },
        {
            "name": "Replace exclamation with 'Kak' prefix",
            "customer_name": "Siti",
            "input_messages": [
                "Kak Siti! Mohon tunggu sebentar ya.",
                "Halo Kak Siti! Selamat datang di ORIN.",
            ],
            "expected_output": [
                "Kak Siti, Mohon tunggu sebentar ya.",
                "Halo Kak Siti, Selamat datang di ORIN.",
            ]
        },
        {
            "name": "Replace exclamation with 'Kakak' prefix",
            "customer_name": "Andi",
            "input_messages": [
                "Kakak Andi! Silakan cek katalog di atas.",
            ],
            "expected_output": [
                "Kakak Andi, Silakan cek katalog di atas.",
            ]
        },
        {
            "name": "No exclamation to replace",
            "customer_name": "Rina",
            "input_messages": [
                "Halo Rina, apa kabar?",
                "Terima kasih sudah menghubungi kami.",
            ],
            "expected_output": [
                "Halo Rina, apa kabar?",
                "Terima kasih sudah menghubungi kami.",
            ]
        },
        {
            "name": "Empty customer name",
            "customer_name": "",
            "input_messages": [
                "Halo kak! Ada yang bisa dibantu?",
            ],
            "expected_output": [
                "Halo kak! Ada yang bisa dibantu?",
            ]
        },
        {
            "name": "Exclamation in middle of sentence (should not be affected)",
            "customer_name": "Dewi",
            "input_messages": [
                "Halo Dewi! Ada promo! Cek katalog ya!",
            ],
            "expected_output": [
                "Halo Dewi, Ada promo! Cek katalog ya!",
            ]
        },
    ]

    results = []

    for test_case in test_cases:
        print(f"\n--- Test: {test_case['name']} ---")

        input_messages = test_case["input_messages"]
        customer_name = test_case["customer_name"]
        expected_output = test_case["expected_output"]

        # Run filter
        filtered = filter_final_messages(input_messages, customer_name)

        # Check results
        if filtered == expected_output:
            print("✅ PASS")
            results.append(True)
        else:
            print("❌ FAIL")
            print(f"Input: {input_messages}")
            print(f"Expected: {expected_output}")
            print(f"Got: {filtered}")
            results.append(False)

    # Summary
    print("\n" + "="*80)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*80 + "\n")

    return passed == total


def main():
    success = test_filter_final_messages()

    if success:
        print("\n🎉 Final message filter is working correctly!")
    else:
        print("\n❌ Some tests failed. Please check the output above.\n")


if __name__ == "__main__":
    main()
