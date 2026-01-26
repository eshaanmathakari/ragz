"""OpenSearch index configuration and schema."""

from typing import Any

from rag_assist.config.settings import get_settings


def get_index_mapping() -> dict[str, Any]:
    """Get OpenSearch index mapping for learning content."""
    settings = get_settings()

    return {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 100,
                "number_of_shards": 2,
                "number_of_replicas": 1,
            },
            "analysis": {
                "analyzer": {
                    "content_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "stop", "snowball"],
                    }
                }
            },
        },
        "mappings": {
            "properties": {
                # Identifiers
                "chunk_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                # Content
                "content": {
                    "type": "text",
                    "analyzer": "content_analyzer",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                },
                # Vector embedding
                "content_embedding": {
                    "type": "knn_vector",
                    "dimension": settings.opensearch.vector_dimension,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "faiss",
                        "parameters": {
                            "ef_construction": settings.opensearch.ef_construction,
                            "m": settings.opensearch.m,
                        },
                    },
                },
                # Source metadata
                "filename": {"type": "keyword"},
                "file_type": {"type": "keyword"},
                "s3_uri": {"type": "keyword"},
                # Location metadata (for citations)
                "module_name": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "folder_path": {"type": "keyword"},
                "week_number": {"type": "integer"},
                "page_number": {"type": "integer"},
                "slide_number": {"type": "integer"},
                "section_title": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                # Structure metadata
                "heading_hierarchy": {"type": "keyword"},
                "content_type": {"type": "keyword"},  # title, body, table, list, note
                "chunk_index": {"type": "integer"},
                "position_in_section": {"type": "keyword"},  # beginning, middle, end
                # Semantic metadata
                "keywords": {"type": "keyword"},
                "entities": {
                    "type": "nested",
                    "properties": {
                        "text": {"type": "keyword"},
                        "type": {"type": "keyword"},
                    },
                },
                "topic_tags": {"type": "keyword"},
                "document_intent": {"type": "keyword"},  # overview, tutorial, reference
                # Deduplication metadata
                "content_hash": {"type": "keyword"},
                "semantic_fingerprint": {"type": "keyword"},
                "canonical_chunk_id": {"type": "keyword"},
                # Technical metadata
                "char_count": {"type": "integer"},
                "token_count": {"type": "integer"},
                "extraction_method": {"type": "keyword"},  # native, textract
                "extraction_confidence": {"type": "float"},
                # Timestamps
                "ingested_at": {"type": "date"},
                "document_modified_at": {"type": "date"},
            }
        },
    }


def get_search_pipeline_config() -> dict[str, Any]:
    """Get hybrid search normalization pipeline configuration."""
    settings = get_settings()

    return {
        "description": "Hybrid search normalization pipeline for RAG",
        "phase_results_processors": [
            {
                "normalization-processor": {
                    "normalization": {"technique": "min_max"},
                    "combination": {
                        "technique": "arithmetic_mean",
                        "parameters": {
                            "weights": [
                                settings.rag.vector_weight,
                                settings.rag.keyword_weight,
                            ]
                        },
                    },
                }
            }
        ],
    }


# Index name constant
INDEX_NAME = "learning-content"

# Search pipeline name
SEARCH_PIPELINE_NAME = "hybrid-normalization-pipeline"
