#!/bin/bash
# LocalStack initialization script for RAG Learning Assistant
# Creates S3 bucket and DynamoDB table for local development

set -e

echo "Waiting for LocalStack to be ready..."
sleep 5

# Configure AWS CLI for LocalStack
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
ENDPOINT_URL="http://localhost:4566"

echo "Creating S3 bucket for course materials..."
awslocal s3 mb s3://rag-assist-data --region us-east-1 || true

# Create sample folder structure
echo "Creating sample folder structure..."
awslocal s3api put-object --bucket rag-assist-data --key "week 1/" || true
awslocal s3api put-object --bucket rag-assist-data --key "week 2/" || true
awslocal s3api put-object --bucket rag-assist-data --key "week 3/" || true

echo "Creating DynamoDB table for session memory..."
awslocal dynamodb create-table \
    --table-name rag-assist-sessions \
    --attribute-definitions \
        AttributeName=session_id,AttributeType=S \
        AttributeName=created_at,AttributeType=S \
    --key-schema \
        AttributeName=session_id,KeyType=HASH \
        AttributeName=created_at,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1 || true

# Enable TTL for automatic session cleanup
awslocal dynamodb update-time-to-live \
    --table-name rag-assist-sessions \
    --time-to-live-specification "Enabled=true,AttributeName=ttl" || true

echo "LocalStack initialization complete!"
echo ""
echo "Resources created:"
echo "  - S3 bucket: s3://rag-assist-data"
echo "  - DynamoDB table: rag-assist-sessions"
echo ""
echo "To upload test files:"
echo "  awslocal s3 cp your-file.pdf s3://rag-assist-data/week\ 1/"
