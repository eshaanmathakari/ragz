# RAG Learning Assistant

A production-grade RAG-based Q&A learning assistant using AWS Strands SDK. Processes week-wise educational content (PDFs, PPTs, DOCX) and provides grounded answers with citations.

## Features

- **Document Processing**: PDF, PPTX, DOCX parsing with selective OCR (Amazon Textract)
- **Hybrid Search**: Vector + BM25 keyword search via Amazon OpenSearch
- **Smart Chunking**: Content-aware chunking strategies per document type
- **Deduplication**: Two-stage (hash + semantic) deduplication to save tokens
- **Guardrails**: Multi-layer content filtering and scope enforcement
- **Citations**: Grounded answers with [Week X, Slide/Page Y] citations
- **Multi-turn Memory**: Session-based conversation context

## Architecture

```
S3 (Weekly Data) → Step Functions → Document Processing
                                   ├── Textract (scanned PDFs)
                                   ├── PyMuPDF (text PDFs)
                                   ├── python-pptx (PowerPoints)
                                   └── python-docx (Word docs)
                                           ↓
                   Chunking + Metadata Extraction + Deduplication
                                           ↓
                        Amazon OpenSearch Serverless
                        (Vector + Keyword Hybrid Search)
                                           ↓
                         AWS Strands Agent Runtime
                   ┌─────────────────────────────────┐
                   │ PolicyGate → Retrieval → Dedup  │
                   │    → Answer Generation          │
                   │    → Citation Formatting        │
                   └─────────────────────────────────┘
                                           ↓
                   FastAPI + API Gateway + CloudFront
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- AWS credentials (for production) or LocalStack (for local development)

### Local Development Setup

1. **Clone and install dependencies**:
   ```bash
   cd rag-assist
   pip install -e ".[dev]"
   ```

2. **Copy environment file**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start local services**:
   ```bash
   docker-compose up -d
   ```

4. **Initialize LocalStack** (optional, for S3/DynamoDB simulation):
   ```bash
   chmod +x scripts/localstack-init.sh
   ./scripts/localstack-init.sh
   ```

5. **Seed test data**:
   ```bash
   python scripts/seed_data.py --local
   ```

6. **Run the API**:
   ```bash
   uvicorn rag_assist.api.main:app --reload
   ```

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/ -v

# Run smoke tests
pytest tests/smoke/ -v

# Run with coverage
pytest --cov=rag_assist --cov-report=html
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ask` | POST | Q&A with grounded answer + citations |
| `/api/v1/search` | POST | Direct search in indexed content |
| `/api/v1/ingest` | POST | Trigger document ingestion |
| `/api/v1/health` | GET | Health check |
| `/api/v1/weeks` | GET | List indexed weeks |

### Example Request

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is supervised learning?",
    "week_filter": 1,
    "include_sources": true
  }'
```

### Example Response

```json
{
  "answer_id": "abc123",
  "question": "What is supervised learning?",
  "answer": "Supervised learning is a type of machine learning where the model is trained on labeled data...",
  "sources": [
    {
      "chunk_id": "chunk_001",
      "filename": "intro_to_ml.pptx",
      "week_number": 1,
      "slide_number": 5,
      "relevance_score": 0.95,
      "snippet": "Supervised learning uses labeled data..."
    }
  ],
  "confidence": 0.92,
  "in_scope": true,
  "processing_time_ms": 1250
}
```

## Configuration

Key environment variables (see `.env.example` for full list):

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region | `us-east-1` |
| `OPENSEARCH_ENDPOINT` | OpenSearch endpoint URL | `http://localhost:9200` |
| `BEDROCK_MODEL_ID` | Claude model for agent | `anthropic.claude-sonnet-4-20250514-v1:0` |
| `EMBEDDING_MODEL_ID` | Titan embedding model | `amazon.titan-embed-text-v2:0` |
| `S3_BUCKET_NAME` | S3 bucket for documents | `rag-assist-data` |

## Project Structure

```
rag-assist/
├── src/rag_assist/
│   ├── config/          # Settings and AWS configuration
│   ├── ingestion/
│   │   ├── parsers/     # PDF, PPTX, DOCX parsers
│   │   ├── chunking/    # Document chunking strategies
│   │   ├── metadata/    # Keyword, entity extraction
│   │   └── deduplication/  # Hash + semantic dedup
│   ├── vectorstore/
│   │   ├── embedder.py  # Titan Embeddings wrapper
│   │   ├── opensearch_client.py  # OpenSearch operations
│   │   └── hybrid_search.py  # Vector + BM25 search
│   ├── agent/
│   │   ├── learning_agent.py  # Main Strands agent
│   │   ├── tools/       # Agent tools
│   │   └── guardrails/  # Policy gate, Bedrock Guardrails
│   └── api/
│       └── main.py      # FastAPI application
├── tests/
│   ├── unit/            # Unit tests
│   ├── smoke/           # Smoke tests
│   └── fixtures/        # Test data
├── scripts/             # Setup and utility scripts
├── docker-compose.yml   # Local development services
└── Dockerfile           # Production container
```

## Guardrails

The system enforces content policies through multiple layers:

1. **Policy Gate** (pattern-based, fast):
   - Blocks general knowledge questions
   - Blocks coding assistance requests
   - Blocks personal advice
   - Blocks harmful/jailbreak content

2. **Bedrock Guardrails** (comprehensive):
   - Content filtering
   - PII detection and anonymization

3. **Grounding Check**:
   - Verifies answers are based on source materials

## License

Proprietary - All rights reserved.
