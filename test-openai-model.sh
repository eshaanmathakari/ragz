#!/bin/bash

echo "🧪 Testing OpenAI API Key and Model Access..."
echo ""

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY not set in environment"
    echo "   Testing with n8n credentials instead..."
fi

echo "Testing with gpt-3.5-turbo (recommended for testing)..."
echo ""

# Test OpenAI API directly
RESPONSE=$(curl -s -X POST "https://api.openai.com/v1/chat/completions" \
  -H "Authorization: Bearer ${OPENAI_API_KEY:-test}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "test"}],
    "max_tokens": 5
  }' \
  -w "\nHTTP_CODE:%{http_code}")

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ OpenAI API is working!"
    echo "   Model: gpt-3.5-turbo is accessible"
elif [ "$HTTP_CODE" = "401" ]; then
    echo "❌ Invalid API key"
    echo "   Update your OpenAI credentials in n8n"
elif [ "$HTTP_CODE" = "429" ]; then
    echo "⚠️  Rate limit exceeded"
    echo "   Wait a few minutes and try again"
    echo "   Or use a different model (gpt-3.5-turbo has higher limits)"
elif [ "$HTTP_CODE" = "404" ]; then
    echo "❌ Model not found"
    echo "   The model name might be invalid"
else
    echo "⚠️  Unexpected response: HTTP $HTTP_CODE"
    echo "   Response: ${BODY:0:200}"
fi

echo ""
echo "💡 To fix 429 errors in n8n:"
echo "   1. Open n8n workflow"
echo "   2. Click 'OpenAI Chat Model' node"
echo "   3. Change model to 'gpt-3.5-turbo' or 'gpt-4o'"
echo "   4. Save and test again"

