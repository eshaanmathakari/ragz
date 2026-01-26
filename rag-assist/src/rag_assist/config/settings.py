"""Centralized settings management using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AWSSettings(BaseSettings):
    """AWS-specific configuration."""

    model_config = SettingsConfigDict(env_prefix="AWS_")

    region: str = Field(default="us-east-1", description="AWS region")
    access_key_id: str | None = Field(default=None, description="AWS access key ID")
    secret_access_key: str | None = Field(default=None, description="AWS secret access key")


class S3Settings(BaseSettings):
    """S3 bucket configuration."""

    model_config = SettingsConfigDict(env_prefix="S3_")

    bucket_name: str = Field(default="rag-assist-weekly-data", description="S3 bucket name")
    data_prefix: str = Field(default="data/", description="S3 prefix for data files")


class OpenSearchSettings(BaseSettings):
    """OpenSearch Serverless configuration."""

    model_config = SettingsConfigDict(env_prefix="OPENSEARCH_")

    endpoint: str = Field(..., description="OpenSearch endpoint URL")
    index_name: str = Field(default="learning-content", description="Index name")
    use_ssl: bool = Field(default=True, description="Use SSL for connection")
    verify_certs: bool = Field(default=True, description="Verify SSL certificates")

    # Index settings
    vector_dimension: int = Field(default=1024, description="Embedding vector dimension")
    ef_construction: int = Field(default=128, description="HNSW ef_construction parameter")
    m: int = Field(default=16, description="HNSW m parameter")


class BedrockSettings(BaseSettings):
    """AWS Bedrock configuration."""

    model_config = SettingsConfigDict(env_prefix="BEDROCK_")

    region: str = Field(default="us-east-1", description="Bedrock region")
    llm_model_id: str = Field(
        default="anthropic.claude-sonnet-4-20250514-v1:0",
        description="LLM model ID for Strands agent",
    )
    embedding_model_id: str = Field(
        default="amazon.titan-embed-text-v2:0",
        description="Embedding model ID",
    )
    guardrail_id: str | None = Field(default=None, description="Bedrock Guardrail ID")
    guardrail_version: str = Field(default="DRAFT", description="Guardrail version")


class DynamoDBSettings(BaseSettings):
    """DynamoDB configuration for session memory."""

    model_config = SettingsConfigDict(env_prefix="DYNAMODB_")

    table_name: str = Field(default="rag-assist-sessions", description="DynamoDB table name")
    ttl_hours: int = Field(default=24, description="Session TTL in hours")


class APISettings(BaseSettings):
    """API server configuration."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = Field(default="0.0.0.0", description="API host")
    port: int = Field(default=8000, description="API port")
    debug: bool = Field(default=False, description="Debug mode")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="CORS allowed origins",
    )


class RAGSettings(BaseSettings):
    """RAG pipeline configuration."""

    model_config = SettingsConfigDict(env_prefix="RAG_")

    max_context_tokens: int = Field(default=4000, description="Max tokens for context")
    top_k_retrieval: int = Field(default=10, description="Top K for retrieval")
    vector_weight: float = Field(default=0.7, description="Weight for vector search")
    keyword_weight: float = Field(default=0.3, description="Weight for keyword search")
    similarity_threshold: float = Field(default=0.85, description="Similarity threshold for dedup")

    @field_validator("vector_weight", "keyword_weight")
    @classmethod
    def validate_weights(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("Weight must be between 0 and 1")
        return v


class ChunkingSettings(BaseSettings):
    """Chunking configuration."""

    model_config = SettingsConfigDict(env_prefix="CHUNK_")

    size_tokens: int = Field(default=500, description="Target chunk size in tokens")
    overlap_tokens: int = Field(default=50, description="Chunk overlap in tokens")
    min_size_tokens: int = Field(default=100, description="Minimum chunk size")
    max_size_tokens: int = Field(default=1000, description="Maximum chunk size")


class DedupSettings(BaseSettings):
    """Deduplication configuration."""

    model_config = SettingsConfigDict(env_prefix="DEDUP_")

    exact_hash: bool = Field(default=True, description="Enable exact hash deduplication")
    semantic: bool = Field(default=True, description="Enable semantic deduplication")
    semantic_threshold: float = Field(default=0.92, description="Semantic similarity threshold")
    minhash_num_perm: int = Field(default=128, description="MinHash permutations")
    minhash_threshold: float = Field(default=0.5, description="MinHash LSH threshold")


class MemorySettings(BaseSettings):
    """Conversation memory configuration."""

    model_config = SettingsConfigDict(env_prefix="MEMORY_")

    enabled: bool = Field(default=True, description="Enable conversation memory")
    window_size: int = Field(default=10, description="Number of turns to remember")


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Log level",
    )
    format: Literal["json", "console"] = Field(default="json", description="Log format")


class Settings(BaseSettings):
    """Main settings class aggregating all configuration sections."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Nested settings
    aws: AWSSettings = Field(default_factory=AWSSettings)
    s3: S3Settings = Field(default_factory=S3Settings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    bedrock: BedrockSettings = Field(default_factory=BedrockSettings)
    dynamodb: DynamoDBSettings = Field(default_factory=DynamoDBSettings)
    api: APISettings = Field(default_factory=APISettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    dedup: DedupSettings = Field(default_factory=DedupSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
