"""
Example: Integrating Format Screener into Agentic AI System

This demonstrates how to use the format screener as part of
a larger document processing pipeline.
"""

import importlib.util
import json

# Load the format screener module
spec = importlib.util.spec_from_file_location("formatscreener", "formatscreener.py")
formatscreener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(formatscreener)

DocxFormatScreener = formatscreener.DocxFormatScreener
quick_score = formatscreener.quick_score


# Example 1: Simple scoring
def example_simple_scoring():
    """Quick score without details"""
    print("\n" + "="*60)
    print("Example 1: Simple Scoring")
    print("="*60)

    score = quick_score("Resumetnr.docx")
    print(f"Document score: {score}/10")

    if score >= 7.0:
        print("✓ Document meets formatting standards")
    else:
        print("✗ Document needs formatting improvements")


# Example 2: Detailed analysis
def example_detailed_analysis():
    """Get detailed violation breakdown"""
    print("\n" + "="*60)
    print("Example 2: Detailed Analysis")
    print("="*60)

    screener = DocxFormatScreener("Resume.docx")
    result = screener.score_document()

    print(f"Score: {result['score']}/10")
    print(f"Pass rate: {result['pass_rate']:.1%}")
    print(f"\nViolation breakdown:")

    for category, count in result['violations_by_category'].items():
        if count > 0:
            category_name = category.replace('_', ' ').title()
            print(f"  {category_name}: {count}")


# Example 3: Batch processing
def example_batch_processing():
    """Process multiple documents"""
    print("\n" + "="*60)
    print("Example 3: Batch Processing")
    print("="*60)

    documents = ["Resume.docx", "Resumetnr.docx"]
    results = {}

    for doc in documents:
        try:
            score = quick_score(doc)
            results[doc] = {"score": score, "status": "success"}
        except Exception as e:
            results[doc] = {"score": 0, "status": "error", "error": str(e)}

    print("\nBatch Results:")
    for doc, result in results.items():
        if result["status"] == "success":
            print(f"  {doc}: {result['score']}/10")
        else:
            print(f"  {doc}: ERROR - {result['error']}")


# Example 4: Agentic AI decision making
def example_agentic_decision():
    """Use score to make automated decisions"""
    print("\n" + "="*60)
    print("Example 4: Agentic AI Decision Making")
    print("="*60)

    def evaluate_document(docx_path: str, min_score: float = 7.0) -> dict:
        """
        Evaluate document and make automated decision

        This could be part of a larger agentic workflow that:
        - Receives uploaded documents
        - Validates formatting
        - Routes to appropriate next step
        """
        try:
            screener = DocxFormatScreener(docx_path)
            result = screener.score_document()

            # Make decisions based on score
            if result['score'] >= min_score:
                action = "APPROVE"
                next_step = "Send to review team"
            elif result['score'] >= 5.0:
                action = "CONDITIONAL_ACCEPT"
                next_step = "Minor formatting fixes needed"
            else:
                action = "REJECT"
                next_step = "Major formatting revision required"

            # Identify primary issues
            violations = result['violations_by_category']
            primary_issues = [
                k.replace('_', ' ')
                for k, v in violations.items()
                if v > 0
            ]

            return {
                "document": docx_path,
                "score": result['score'],
                "action": action,
                "next_step": next_step,
                "primary_issues": primary_issues,
                "full_result": result
            }

        except Exception as e:
            return {
                "document": docx_path,
                "score": 0,
                "action": "ERROR",
                "next_step": "Manual review required",
                "error": str(e)
            }

    # Process document
    decision = evaluate_document("Resumetnr.docx", min_score=6.0)

    print(f"Document: {decision['document']}")
    print(f"Score: {decision['score']}/10")
    print(f"Action: {decision['action']}")
    print(f"Next Step: {decision['next_step']}")

    if decision.get('primary_issues'):
        print(f"Primary Issues: {', '.join(decision['primary_issues'])}")


# Example 5: Integration with existing document processor
def example_document_processor_integration():
    """Show how to integrate with existing document_processor.py"""
    print("\n" + "="*60)
    print("Example 5: Integration with Document Processor")
    print("="*60)

    def process_document_with_validation(docx_path: str) -> dict:
        """
        Combined document processing and format validation

        This would integrate with your src/document_processor.py
        to add formatting validation to the RAG pipeline.
        """
        result = {
            "file_path": docx_path,
            "format_validation": None,
            "status": "pending"
        }

        try:
            # Step 1: Format validation
            screener = DocxFormatScreener(docx_path)
            validation = screener.score_document()

            result["format_validation"] = {
                "score": validation['score'],
                "meets_standards": validation['score'] >= 7.0,
                "violations": validation['violations_by_category']
            }

            # Step 2: If format is acceptable, proceed with text extraction
            if validation['score'] >= 5.0:
                result["status"] = "approved_for_processing"
                # Here you would call your document_processor.py
                # processor = DocumentProcessor()
                # content = processor.process_file(docx_path)
                # result["content"] = content
            else:
                result["status"] = "rejected_poor_formatting"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result

    # Demo
    result = process_document_with_validation("Resumetnr.docx")
    print(f"Status: {result['status']}")
    print(f"Format Score: {result['format_validation']['score']}/10")
    print(f"Meets Standards: {result['format_validation']['meets_standards']}")


# Example 6: JSON output for APIs
def example_json_output():
    """Generate JSON output for API responses"""
    print("\n" + "="*60)
    print("Example 6: JSON Output for APIs")
    print("="*60)

    screener = DocxFormatScreener("Resumetnr.docx")
    result = screener.score_document()

    # Clean JSON output (no text content)
    json_output = json.dumps(result, indent=2)
    print(json_output)


if __name__ == "__main__":
    print("\n" + "="*60)
    print("FORMAT SCREENER INTEGRATION EXAMPLES")
    print("="*60)

    # Run all examples
    example_simple_scoring()
    example_detailed_analysis()
    example_batch_processing()
    example_agentic_decision()
    example_document_processor_integration()
    example_json_output()

    print("\n" + "="*60)
    print("All examples completed!")
    print("="*60 + "\n")
