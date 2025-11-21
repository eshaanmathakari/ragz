# ragz - n8n RAG System

A simple RAG (Retrieval-Augmented Generation) agent for personal use, built with n8n, OpenAI, Pinecone, and Cohere.

## Features

- 📄 Upload and index PDF documents
- 💬 Chat with your documents using AI
- 🔍 Vector search with reranking
- 🐳 Dockerized deployment
- 🎨 Modern web frontend

## Quick Start

1. **Activate virtual environment** (optional):
   ```bash
   source venv/bin/activate
   ```

2. **Start the system**:
   ```bash
   docker-compose up -d --build
   ```

3. **Access the application**:
   - Frontend: http://localhost:8080
   - n8n Admin: http://localhost:5678

4. **Configure n8n**:
   - Import `rag-workflow.json`
   - Add API credentials (OpenAI, Pinecone, Cohere)
   - Activate the workflow

For detailed deployment instructions, see [DEPLOYMENT.md](./DEPLOYMENT.md).

## Project Structure

```
ragz/
├── docker-compose.yml      # Docker orchestration
├── rag-workflow.json       # n8n workflow
├── frontend/               # Web frontend
├── workflows/              # n8n workflows directory
├── credentials/            # n8n credentials directory
└── venv/                   # Python virtual environment
```

## Requirements

- Docker & Docker Compose
- API keys: OpenAI, Pinecone, Cohere

## License

Personal use
