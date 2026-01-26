"""Configuration module for RAG Assist."""

from rag_assist.config.aws_config import (
    clear_client_cache,
    get_bedrock_runtime_client,
    get_dynamodb_resource,
    get_s3_client,
    get_step_functions_client,
    get_textract_client,
)
from rag_assist.config.opensearch_config import (
    INDEX_NAME,
    SEARCH_PIPELINE_NAME,
    get_index_mapping,
    get_search_pipeline_config,
)
from rag_assist.config.settings import Settings, get_settings

__all__ = [
    "Settings",
    "get_settings",
    "get_s3_client",
    "get_textract_client",
    "get_bedrock_runtime_client",
    "get_dynamodb_resource",
    "get_step_functions_client",
    "clear_client_cache",
    "get_index_mapping",
    "get_search_pipeline_config",
    "INDEX_NAME",
    "SEARCH_PIPELINE_NAME",
]
