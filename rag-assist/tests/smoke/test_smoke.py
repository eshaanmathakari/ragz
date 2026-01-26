"""Smoke tests to verify basic functionality before deployment.

Run these tests with:
    pytest tests/smoke/ -v

These tests verify:
1. Ingestion doesn't crash with sample files
2. Basic search returns valid responses
3. Guardrails block out-of-scope questions
4. API endpoints respond correctly
"""

import pytest
from unittest.mock import MagicMock, patch


class TestIngestionSmoke:
    """Smoke tests for ingestion pipeline."""

    def test_pptx_chunker_doesnt_crash(self, sample_pptx_content):
        """PPTX chunker should process documents without errors."""
        from rag_assist.ingestion.chunking.pptx_chunker import PPTXChunker

        chunker = PPTXChunker()
        chunks = chunker.chunk(sample_pptx_content)

        assert isinstance(chunks, list)
        assert all(hasattr(c, "text") for c in chunks)
        assert all(hasattr(c, "metadata") for c in chunks)

    def test_pdf_chunker_doesnt_crash(self, sample_pdf_content):
        """PDF chunker should process documents without errors."""
        from rag_assist.ingestion.chunking.pdf_chunker import PDFChunker

        chunker = PDFChunker()
        chunks = chunker.chunk(sample_pdf_content)

        assert isinstance(chunks, list)
        assert all(hasattr(c, "text") for c in chunks)

    def test_dedup_manager_doesnt_crash(self, sample_chunks):
        """Deduplication manager should process chunks without errors."""
        from rag_assist.ingestion.deduplication.dedup_manager import (
            DeduplicationManager,
        )

        manager = DeduplicationManager()
        result, stats = manager.deduplicate(sample_chunks)

        assert isinstance(result, list)
        assert hasattr(stats, "total_input_chunks")
        assert hasattr(stats, "final_unique_chunks")

    def test_metadata_extraction_doesnt_crash(self):
        """Metadata extraction should not crash."""
        from rag_assist.ingestion.metadata.keyword_extractor import KeywordExtractor

        extractor = KeywordExtractor()
        text = "Machine learning is a subset of artificial intelligence."

        keywords = extractor.extract(text)

        assert isinstance(keywords, list)


class TestGuardrailsSmoke:
    """Smoke tests for guardrails."""

    def test_policy_gate_blocks_coding(self):
        """Policy gate should block coding requests."""
        from rag_assist.agent.guardrails.policy_gate import PolicyGate

        gate = PolicyGate()
        result = gate.evaluate("Write Python code for sorting")

        assert not result.allowed
        assert result.category is not None
        assert result.reason is not None

    def test_policy_gate_allows_course_questions(self):
        """Policy gate should allow course-related questions."""
        from rag_assist.agent.guardrails.policy_gate import PolicyGate

        gate = PolicyGate()
        result = gate.evaluate("What is supervised learning?")

        assert result.allowed

    def test_guardrail_orchestrator_validates_input(self):
        """Guardrail orchestrator should validate inputs."""
        from rag_assist.agent.guardrails.guardrail_orchestrator import (
            GuardrailOrchestrator,
        )

        orchestrator = GuardrailOrchestrator(
            enable_bedrock_guardrails=False,  # Skip Bedrock for smoke test
        )

        # Valid question
        result = orchestrator.validate_input("Explain neural networks")
        assert result.passed

        # Invalid question
        result = orchestrator.validate_input("Hack this website")
        assert not result.passed


class TestAPISmoke:
    """Smoke tests for API endpoints."""

    def test_api_models_are_valid(self):
        """API request/response models should be valid."""
        from rag_assist.api.models import (
            QuestionRequest,
            AnswerResponse,
            SearchRequest,
            HealthResponse,
        )

        # Test QuestionRequest
        request = QuestionRequest(question="What is ML?")
        assert request.question == "What is ML?"

        # Test AnswerResponse
        response = AnswerResponse(
            answer_id="test-id",
            question="What is ML?",
            answer="ML is...",
            sources=[],
            confidence=0.9,
            in_scope=True,
            processing_time_ms=100,
        )
        assert response.answer_id == "test-id"

        # Test SearchRequest
        search = SearchRequest(query="machine learning")
        assert search.query == "machine learning"

        # Test HealthResponse
        health = HealthResponse(
            status="healthy",
            version="0.1.0",
            services={},
        )
        assert health.status == "healthy"

    def test_create_app_doesnt_crash(self):
        """FastAPI app creation should not crash."""
        from rag_assist.api.main import create_app

        app = create_app()

        assert app is not None
        assert app.title == "RAG Learning Assistant API"


class TestConfigSmoke:
    """Smoke tests for configuration."""

    def test_settings_load_without_error(self):
        """Settings should load without errors."""
        from rag_assist.config.settings import get_settings

        settings = get_settings()

        assert settings is not None
        assert hasattr(settings, "aws")
        assert hasattr(settings, "opensearch")
        assert hasattr(settings, "bedrock")

    def test_settings_have_defaults(self):
        """Settings should have sensible defaults."""
        from rag_assist.config.settings import get_settings

        settings = get_settings()

        assert settings.aws.region is not None
        assert settings.rag.top_k > 0
        assert settings.chunking.max_tokens > 0


class TestDataModelsSmoke:
    """Smoke tests for data models."""

    def test_text_chunk_model(self):
        """TextChunk model should work correctly."""
        from rag_assist.ingestion.models import TextChunk, ChunkMetadata

        metadata = ChunkMetadata(
            chunk_id="test-chunk",
            document_id="test-doc",
            filename="test.pdf",
            file_type="pdf",
            s3_uri="s3://bucket/test.pdf",
        )

        chunk = TextChunk(text="Test content", metadata=metadata)

        assert chunk.text == "Test content"
        assert chunk.metadata.chunk_id == "test-chunk"

    def test_document_types(self):
        """Document types enum should have expected values."""
        from rag_assist.ingestion.models import DocumentType

        assert DocumentType.PDF.value == "pdf"
        assert DocumentType.PPTX.value == "pptx"
        assert DocumentType.DOCX.value == "docx"


class TestIntegrationReadiness:
    """Tests to verify components are ready for integration."""

    @pytest.mark.skip(reason="Requires OpenSearch connection")
    def test_opensearch_client_can_connect(self):
        """OpenSearch client should be able to connect."""
        from rag_assist.vectorstore.opensearch_client import OpenSearchClient

        client = OpenSearchClient()
        health = client.health_check()

        assert health is not None

    @pytest.mark.skip(reason="Requires AWS credentials")
    def test_embedder_can_embed(self):
        """Embedder should be able to generate embeddings."""
        from rag_assist.vectorstore.embedder import TitanEmbedder

        embedder = TitanEmbedder()
        embedding = embedder.embed("Test text")

        assert embedding is not None
        assert len(embedding) == 1024  # Titan v2 dimension

    @pytest.mark.skip(reason="Requires AWS credentials")
    def test_learning_agent_can_initialize(self):
        """Learning agent should initialize without errors."""
        from rag_assist.agent.learning_agent import LearningAgent

        agent = LearningAgent()
        assert agent is not None
