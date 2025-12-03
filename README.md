# ragz - n8n RAG System

A simple RAG (Retrieval-Augmented Generation) agent for personal use, built with n8n, OpenAI, Pinecone, and Cohere.

## Features

- 📄 Upload and index PDF documents
- 💬 Chat with your documents using AI
- 🔍 Vector search with reranking
- 🐳 Dockerized deployment
- 🎨 Modern web frontend

## Quick Start

### Prerequisites

- Docker & Docker Compose installed
- API keys for:
  - OpenAI (for embeddings and chat)
  - Pinecone (for vector database)
  - Cohere (for reranking)

### Installation

1. **Clone and navigate to the project**:
   ```bash
   cd ragz
   ```

2. **Start all services**:
   ```bash
   # Option 1: Use the helper script
   ./start.sh
   
   # Option 2: Use docker-compose directly
   docker-compose up -d --build
   ```

3. **Wait for services to start** (about 30 seconds):
   ```bash
   # Check status
   docker-compose ps
   ```

4. **Access the application**:
   - **Frontend**: http://localhost:8080
   - **n8n Admin**: http://localhost:5678
     - Username: `admin`
     - Password: `admin123`

### Configure n8n Workflow

1. **Open n8n**: Navigate to http://localhost:5678 and log in

2. **Import the workflow**:
   - Click "Workflows" → "Import from File"
   - Select `rag-workflow.json`
   - The workflow will be imported

3. **Add API Credentials**:
   - Click on credential nodes in the workflow:
     - **OpenAI**: Add your OpenAI API key
     - **Pinecone**: Add your Pinecone API key and select your index
     - **Cohere**: Add your Cohere API key
   - Save each credential

4. **Activate the workflow**:
   - Click the toggle switch in the top-right corner
   - The workflow should show as "Active" (green indicator)
   - **IMPORTANT**: Webhooks only work when the workflow is active!

5. **Verify webhook URLs**:
   - Click on "On form submission" node → Copy the webhook URL
   - Click on "When chat message received" node → Copy the webhook URL
   - If the webhook IDs differ from those in `frontend/app.js`, update the `CONFIG.WEBHOOKS` object

### Test the Application

1. **Open the frontend**: http://localhost:8080
2. **Upload a PDF**: Drag and drop or click to upload a PDF file
3. **Wait for indexing**: The PDF will be processed and indexed
4. **Start chatting**: Ask questions about your uploaded document

## Project Structure

```
ragz/
├── docker-compose.yml      # Docker orchestration
├── rag-workflow.json       # n8n workflow definition
├── start.sh                # Helper script to start services
├── frontend/               # Web frontend
│   ├── index.html         # Main HTML file
│   ├── app.js             # Frontend JavaScript (n8n integration)
│   ├── styles.css         # Styling
│   ├── nginx.conf         # Nginx configuration
│   └── Dockerfile         # Frontend container definition
├── workflows/              # n8n workflows directory (mounted)
├── credentials/            # n8n credentials directory (mounted)
└── TROUBLESHOOTING.md      # Troubleshooting guide
```

## Docker Services

- **n8n**: Workflow automation server (port 5678)
- **postgres**: PostgreSQL database for n8n (internal)
- **frontend**: Nginx web server serving the frontend (port 8080)

## Common Issues

### Frontend shows connection errors
- Ensure n8n is running: `docker-compose ps`
- Check n8n logs: `docker-compose logs n8n`
- Verify workflow is **ACTIVE** in n8n UI
- Check webhook URLs match in `app.js`

### CORS errors
- n8n is configured with `N8N_CORS_ORIGIN=*` for development
- Restart n8n: `docker-compose restart n8n`

### Webhook returns 404
- Workflow must be **ACTIVE** (toggle switch in n8n UI)
- Verify webhook IDs in `frontend/app.js` match your workflow
- Check n8n logs for webhook registration

See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for detailed solutions.

## Development

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f n8n
docker-compose logs -f frontend
```

### Stop Services
```bash
docker-compose down
```

### Reset Everything
```bash
# Stop and remove containers and volumes
docker-compose down -v
```

### Rebuild After Changes
```bash
docker-compose up -d --build
```

## API Endpoints

The frontend connects to n8n webhooks:
- **PDF Upload**: `POST /webhook/{form-webhook-id}`
- **Chat Message**: `POST /webhook/{chat-webhook-id}`

Webhook IDs are configured in `frontend/app.js`.

## Requirements

- Docker 20.10+
- Docker Compose 2.0+
- API keys: OpenAI, Pinecone, Cohere
- 2GB+ RAM recommended
- Internet connection for API calls

## License

Personal use
