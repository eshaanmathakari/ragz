"""AWS client configuration and initialization."""

from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from rag_assist.config.settings import get_settings


def get_boto_config() -> Config:
    """Get boto3 config with retry settings."""
    return Config(
        retries={
            "max_attempts": 3,
            "mode": "adaptive",
        },
        connect_timeout=10,
        read_timeout=60,
    )


@lru_cache
def get_s3_client() -> Any:
    """Get cached S3 client."""
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws.region,
        config=get_boto_config(),
    )


@lru_cache
def get_textract_client() -> Any:
    """Get cached Textract client."""
    settings = get_settings()
    return boto3.client(
        "textract",
        region_name=settings.aws.region,
        config=get_boto_config(),
    )


@lru_cache
def get_bedrock_runtime_client() -> Any:
    """Get cached Bedrock Runtime client for model invocations."""
    settings = get_settings()
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.bedrock.region,
        config=get_boto_config(),
    )


@lru_cache
def get_dynamodb_resource() -> Any:
    """Get cached DynamoDB resource."""
    settings = get_settings()
    return boto3.resource(
        "dynamodb",
        region_name=settings.aws.region,
        config=get_boto_config(),
    )


@lru_cache
def get_step_functions_client() -> Any:
    """Get cached Step Functions client."""
    settings = get_settings()
    return boto3.client(
        "stepfunctions",
        region_name=settings.aws.region,
        config=get_boto_config(),
    )


def clear_client_cache() -> None:
    """Clear all cached clients. Useful for testing."""
    get_s3_client.cache_clear()
    get_textract_client.cache_clear()
    get_bedrock_runtime_client.cache_clear()
    get_dynamodb_resource.cache_clear()
    get_step_functions_client.cache_clear()
