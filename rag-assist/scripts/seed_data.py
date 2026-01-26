#!/usr/bin/env python3
"""Seed script for populating local OpenSearch with test data."""

import argparse
import json
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def create_sample_chunks() -> list[dict]:
    """Create sample chunks for testing."""
    return [
        {
            "chunk_id": "chunk_001",
            "document_id": "doc_001",
            "text": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed. It focuses on developing computer programs that can access data and use it to learn for themselves.",
            "filename": "intro_to_ml.pptx",
            "file_type": "pptx",
            "week_number": 1,
            "slide_number": 5,
            "section_title": "Introduction to Machine Learning",
            "keywords": ["machine learning", "artificial intelligence", "data", "algorithms"],
            "topic_tags": ["ml_fundamentals", "ai_overview"],
        },
        {
            "chunk_id": "chunk_002",
            "document_id": "doc_001",
            "text": "Supervised learning is a type of machine learning where the model is trained on labeled data. The algorithm learns from the training data to make predictions on new, unseen data. Common examples include classification and regression tasks.",
            "filename": "intro_to_ml.pptx",
            "file_type": "pptx",
            "week_number": 1,
            "slide_number": 7,
            "section_title": "Types of Machine Learning",
            "keywords": ["supervised learning", "labeled data", "classification", "regression"],
            "topic_tags": ["ml_fundamentals", "supervised_learning"],
        },
        {
            "chunk_id": "chunk_003",
            "document_id": "doc_001",
            "text": "Unsupervised learning works with unlabeled data. The algorithm tries to find patterns and relationships in the data without prior knowledge of outcomes. Clustering and dimensionality reduction are common unsupervised techniques.",
            "filename": "intro_to_ml.pptx",
            "file_type": "pptx",
            "week_number": 1,
            "slide_number": 10,
            "section_title": "Types of Machine Learning",
            "keywords": ["unsupervised learning", "clustering", "patterns", "unlabeled data"],
            "topic_tags": ["ml_fundamentals", "unsupervised_learning"],
        },
        {
            "chunk_id": "chunk_004",
            "document_id": "doc_002",
            "text": "Neural networks are computing systems inspired by biological neural networks in the human brain. They consist of interconnected nodes or neurons organized in layers. Deep learning uses neural networks with many layers to learn complex patterns.",
            "filename": "neural_networks.pdf",
            "file_type": "pdf",
            "week_number": 2,
            "page_number": 3,
            "section_title": "Neural Network Architecture",
            "keywords": ["neural networks", "deep learning", "neurons", "layers"],
            "topic_tags": ["neural_networks", "deep_learning"],
        },
        {
            "chunk_id": "chunk_005",
            "document_id": "doc_002",
            "text": "Convolutional Neural Networks (CNNs) are specialized neural networks designed for processing structured grid data like images. They use convolutional layers to automatically learn spatial hierarchies of features from input images.",
            "filename": "neural_networks.pdf",
            "file_type": "pdf",
            "week_number": 2,
            "page_number": 8,
            "section_title": "Convolutional Neural Networks",
            "keywords": ["CNN", "convolutional", "image processing", "feature extraction"],
            "topic_tags": ["neural_networks", "computer_vision"],
        },
        {
            "chunk_id": "chunk_006",
            "document_id": "doc_003",
            "text": "Natural Language Processing (NLP) is a field of AI focused on enabling computers to understand, interpret, and generate human language. Key tasks include sentiment analysis, named entity recognition, and machine translation.",
            "filename": "nlp_fundamentals.docx",
            "file_type": "docx",
            "week_number": 3,
            "page_number": 1,
            "section_title": "Introduction to NLP",
            "keywords": ["NLP", "natural language", "sentiment analysis", "text processing"],
            "topic_tags": ["nlp", "text_analysis"],
        },
        {
            "chunk_id": "chunk_007",
            "document_id": "doc_003",
            "text": "Transformers are a neural network architecture that uses self-attention mechanisms to process sequential data. They have revolutionized NLP with models like BERT, GPT, and T5 achieving state-of-the-art results on various language tasks.",
            "filename": "nlp_fundamentals.docx",
            "file_type": "docx",
            "week_number": 3,
            "page_number": 5,
            "section_title": "Transformer Architecture",
            "keywords": ["transformers", "attention", "BERT", "GPT"],
            "topic_tags": ["nlp", "transformers"],
        },
        {
            "chunk_id": "chunk_008",
            "document_id": "doc_004",
            "text": "Model evaluation metrics help assess the performance of machine learning models. For classification, common metrics include accuracy, precision, recall, and F1-score. For regression, we use metrics like MSE, RMSE, and R-squared.",
            "filename": "model_evaluation.pptx",
            "file_type": "pptx",
            "week_number": 4,
            "slide_number": 3,
            "section_title": "Evaluation Metrics",
            "keywords": ["evaluation", "metrics", "accuracy", "precision", "recall"],
            "topic_tags": ["ml_evaluation", "metrics"],
        },
    ]


def seed_local_opensearch():
    """Seed local OpenSearch with test data."""
    from opensearchpy import OpenSearch

    # Connect to local OpenSearch
    client = OpenSearch(
        hosts=[{"host": "localhost", "port": 9200}],
        http_auth=("admin", "Admin@123"),
        use_ssl=False,
        verify_certs=False,
    )

    index_name = "rag-assist-chunks"

    # Delete existing index if present
    if client.indices.exists(index=index_name):
        print(f"Deleting existing index: {index_name}")
        client.indices.delete(index=index_name)

    # Create index with mapping
    print(f"Creating index: {index_name}")
    mapping = {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 100,
            }
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "text": {"type": "text", "analyzer": "standard"},
                "content_embedding": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                        "parameters": {"ef_construction": 128, "m": 24},
                    },
                },
                "filename": {"type": "keyword"},
                "file_type": {"type": "keyword"},
                "week_number": {"type": "integer"},
                "slide_number": {"type": "integer"},
                "page_number": {"type": "integer"},
                "section_title": {"type": "text"},
                "keywords": {"type": "keyword"},
                "topic_tags": {"type": "keyword"},
                "content_hash": {"type": "keyword"},
            }
        },
    }

    client.indices.create(index=index_name, body=mapping)

    # Index sample chunks (without embeddings for now)
    chunks = create_sample_chunks()
    print(f"Indexing {len(chunks)} sample chunks...")

    for chunk in chunks:
        # Add a dummy embedding (in production, use Titan Embeddings)
        chunk["content_embedding"] = [0.0] * 1024
        chunk["content_hash"] = f"hash_{chunk['chunk_id']}"

        client.index(
            index=index_name,
            id=chunk["chunk_id"],
            body=chunk,
        )

    # Refresh to make documents searchable
    client.indices.refresh(index=index_name)

    print(f"Successfully indexed {len(chunks)} chunks to {index_name}")
    print("\nSample queries you can try:")
    print('  - "What is machine learning?"')
    print('  - "Explain supervised learning"')
    print('  - "What are neural networks?"')
    print('  - "Tell me about transformers in NLP"')


def seed_mock_data():
    """Create mock data files for testing without OpenSearch."""
    data_dir = Path(__file__).parent.parent / "tests" / "fixtures"
    data_dir.mkdir(parents=True, exist_ok=True)

    chunks = create_sample_chunks()

    # Save as JSON fixture
    fixture_path = data_dir / "sample_chunks.json"
    with open(fixture_path, "w") as f:
        json.dump(chunks, f, indent=2)

    print(f"Created mock data fixture: {fixture_path}")


def main():
    parser = argparse.ArgumentParser(description="Seed test data for RAG Assistant")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Seed local OpenSearch instance",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Create mock data files for unit tests",
    )

    args = parser.parse_args()

    if args.local:
        seed_local_opensearch()
    elif args.mock:
        seed_mock_data()
    else:
        # Default: create mock data
        seed_mock_data()


if __name__ == "__main__":
    main()
