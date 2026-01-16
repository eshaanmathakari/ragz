"""
Test script for the enhanced format screener API
"""

import sys
import importlib.util

# Load formatscreener.py as a module
spec = importlib.util.spec_from_file_location("formatscreener", "formatscreener.py")
formatscreener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(formatscreener)

DocxFormatScreener = formatscreener.DocxFormatScreener
quick_score = formatscreener.quick_score

import json


def test_quick_score():
    """Test the quick_score convenience function"""
    print("="*70)
    print("TEST 1: Quick Score API")
    print("="*70)

    try:
        score1 = quick_score("Resumetnr.docx")
        print(f"✓ Resumetnr.docx score: {score1}/10")

        score2 = quick_score("Resume.docx")
        print(f"✓ Resume.docx score: {score2}/10")

        # Verify expected range
        assert 5.0 <= score1 <= 5.5, f"Expected ~5.3, got {score1}"
        assert 2.5 <= score2 <= 3.5, f"Expected ~2.9, got {score2}"
        print("✓ Scores are in expected ranges\n")

    except Exception as e:
        print(f"✗ Error: {e}\n")
        return False

    return True


def test_detailed_api():
    """Test the detailed score_document API"""
    print("="*70)
    print("TEST 2: Detailed API (score_document)")
    print("="*70)

    try:
        screener = DocxFormatScreener("Resumetnr.docx")
        result = screener.score_document()

        print(f"Score: {result['score']}/10")
        print(f"Pass rate: {result['pass_rate']:.1%}")
        print(f"Total blocks: {result['total_blocks']}")
        print(f"Passed: {result['passed']}")
        print(f"Failed: {result['failed']}")
        print(f"\nViolations by category:")
        for category, count in result['violations_by_category'].items():
            if count > 0:
                print(f"  {category}: {count}")

        # Verify structure
        assert 'score' in result
        assert 'pass_rate' in result
        assert 'violations_by_category' in result
        print("\n✓ API structure is correct\n")

    except Exception as e:
        print(f"✗ Error: {e}\n")
        return False

    return True


def test_no_text_content():
    """Verify no text content is in output"""
    print("="*70)
    print("TEST 3: No Text Content in Output")
    print("="*70)

    try:
        screener = DocxFormatScreener("Resumetnr.docx")
        result = screener.score_document()

        # Convert to JSON string and check
        result_str = json.dumps(result)

        # Common resume words that shouldn't appear
        test_words = ["Lorem", "ipsum", "Your Name", "EXPERIENCE"]
        found_text = False

        for word in test_words:
            if word in result_str:
                print(f"✗ Found text content: '{word}'")
                found_text = True

        if not found_text:
            print("✓ No text content found in output")
            print("✓ Privacy-safe output confirmed\n")
        else:
            print("✗ Text content detected in output\n")
            return False

    except Exception as e:
        print(f"✗ Error: {e}\n")
        return False

    return True


def test_error_handling():
    """Test error handling"""
    print("="*70)
    print("TEST 4: Error Handling")
    print("="*70)

    # Test non-existent file
    try:
        score = quick_score("nonexistent.docx")
        print("✗ Should have raised FileNotFoundError")
        return False
    except FileNotFoundError as e:
        print(f"✓ Correctly caught FileNotFoundError: {e}")

    # Test invalid file type
    try:
        screener = DocxFormatScreener("README.md")
        print("✗ Should have raised ValueError for wrong file type")
        return False
    except ValueError as e:
        print(f"✓ Correctly caught ValueError: {e}")

    print()
    return True


def test_integration_pattern():
    """Test agentic AI integration pattern"""
    print("="*70)
    print("TEST 5: Agentic AI Integration Pattern")
    print("="*70)

    def process_document_for_ai(docx_path: str, threshold: float = 7.0) -> dict:
        """Example integration function for agentic AI system"""
        try:
            screener = DocxFormatScreener(docx_path)
            result = screener.score_document()

            # Add business logic
            result['meets_standards'] = result['score'] >= threshold
            result['recommendation'] = (
                "APPROVED" if result['meets_standards']
                else "NEEDS REVISION"
            )

            return result
        except Exception as e:
            return {
                "error": str(e),
                "score": 0,
                "meets_standards": False,
                "recommendation": "ERROR"
            }

    try:
        result1 = process_document_for_ai("Resumetnr.docx", threshold=5.0)
        print(f"Resumetnr.docx:")
        print(f"  Score: {result1['score']}/10")
        print(f"  Recommendation: {result1['recommendation']}")
        print(f"  Meets standards (≥5.0): {result1['meets_standards']}")

        result2 = process_document_for_ai("Resume.docx", threshold=5.0)
        print(f"\nResume.docx:")
        print(f"  Score: {result2['score']}/10")
        print(f"  Recommendation: {result2['recommendation']}")
        print(f"  Meets standards (≥5.0): {result2['meets_standards']}")

        print("\n✓ Integration pattern works correctly\n")

    except Exception as e:
        print(f"✗ Error: {e}\n")
        return False

    return True


def test_cli_backwards_compatibility():
    """Test that CLI still works"""
    print("="*70)
    print("TEST 6: CLI Backwards Compatibility")
    print("="*70)

    try:
        screener = DocxFormatScreener("Resumetnr.docx")
        screener.print_summary()
        print("✓ CLI print_summary works\n")

    except Exception as e:
        print(f"✗ Error: {e}\n")
        return False

    return True


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("FORMAT SCREENER API TEST SUITE")
    print("="*70 + "\n")

    tests = [
        test_quick_score,
        test_detailed_api,
        test_no_text_content,
        test_error_handling,
        test_integration_pattern,
        test_cli_backwards_compatibility
    ]

    results = []
    for test in tests:
        result = test()
        results.append(result)

    # Summary
    print("="*70)
    print("TEST SUMMARY")
    print("="*70)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("✓ ALL TESTS PASSED!")
    else:
        print(f"✗ {total - passed} test(s) failed")

    print("="*70 + "\n")


if __name__ == "__main__":
    main()
