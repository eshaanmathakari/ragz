#!/bin/bash

set -e

echo "🚀 Starting RAGz Docker Stack..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install it and try again."
    exit 1
fi

# Start services
echo "📦 Starting containers..."
docker-compose up -d --build

echo "⏳ Waiting for services to be ready..."
sleep 10

# Check n8n health
echo "🔍 Checking n8n status..."
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -f http://localhost:5678/healthz > /dev/null 2>&1; then
        echo "✅ n8n is ready!"
        break
    fi
    attempt=$((attempt + 1))
    echo "   Waiting for n8n... ($attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "⚠️  n8n is taking longer than expected to start. Check logs with: docker-compose logs n8n"
fi

echo ""
echo "✅ RAGz is running!"
echo ""
echo "📍 Access points:"
echo "   - Frontend:  http://localhost:8080"
echo "   - n8n Admin: http://localhost:5678"
echo ""
echo "🔑 n8n Credentials:"
echo "   Username: admin"
echo "   Password: admin123"
echo ""
echo "📋 Next steps:"
echo "   1. Open n8n at http://localhost:5678"
echo "   2. Import the workflow from rag-workflow.json"
echo "   3. Add your API credentials (OpenAI, Pinecone, Cohere)"
echo "   4. Activate the workflow"
echo "   5. Test the frontend at http://localhost:8080"
echo ""
echo "📊 View logs:"
echo "   docker-compose logs -f"
echo ""
echo "🛑 Stop services:"
echo "   docker-compose down"
echo ""

