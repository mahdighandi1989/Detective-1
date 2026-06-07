"""
Application configuration using Pydantic Settings.

Loads all environment variables for the Detective-1 OSINT platform,
covering database, cache/queue, object storage, LLM providers,
authentication, and security settings.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, List, Optional, Union

from pydantic import (
    AnyHttpUrl,
    Field,
    PostgresDsn,
    field_validator,
    model_validator,
    SecretStr,
    AnyUrl,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # General / App                                                      #
    # ------------------------------------------------------------------ #
    PROJECT_NAME: str = "Detective-1"
    PROJECT_DESCRIPTION: str = (
        "OSINT intelligence encyclopedia & person-profiling platform"
    )
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(
        default="development",
        description="One of: development, staging, production, test",
    )
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Default port / host (used by uvicorn entrypoint helpers)
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ------------------------------------------------------------------ #
    # CORS                                                               #
    # ------------------------------------------------------------------ #
    BACKEND_CORS_ORIGINS: List[Union[AnyHttpUrl, str]] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8000"],
        description="Comma-separated list of origins for CORS. Can be URLs or '*'.",
    )

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        raise ValueError("Invalid format for BACKEND_CORS_ORIGINS")

    # ------------------------------------------------------------------ #
    # Database - PostgreSQL                                              #
    # ------------------------------------------------------------------ #
    DATABASE_URL: PostgresDsn = Field(
        ...,
        description="PostgreSQL database connection URL (e.g., postgresql+asyncpg://user:pass@host:port/db)",
    )

    # ------------------------------------------------------------------ #
    # Database - Neo4j (Graph Database)                                  #
    # ------------------------------------------------------------------ #
    NEO4J_URI: str = Field(
        ...,
        description="Neo4j connection URI (e.g., bolt://localhost:7687)",
    )
    NEO4J_USERNAME: str = Field(
        ...,
        description="Neo4j database username",
    )
    NEO4J_PASSWORD: SecretStr = Field(
        ...,
        description="Neo4j database password",
    )

    # ------------------------------------------------------------------ #
    # Cache & Queue - Redis / Celery                                     #
    # ------------------------------------------------------------------ #
    REDIS_URL: AnyUrl = Field(
        ...,
        description="Redis connection URL (e.g., redis://localhost:6379/0)",
    )
    CELERY_BROKER_URL: AnyUrl = Field(
        ...,
        description="Celery broker URL (e.g., redis://localhost:6379/1)",
    )
    CELERY_RESULT_BACKEND: AnyUrl = Field(
        ...,
        description="Celery result backend URL (e.g., redis://localhost:6379/2)",
    )

    # ------------------------------------------------------------------ #
    # Object Storage - MinIO / S3                                        #
    # ------------------------------------------------------------------ #
    MINIO_ENDPOINT: AnyHttpUrl = Field(
        ...,
        description="MinIO/S3 endpoint URL (e.g., http://localhost:9000)",
    )
    MINIO_ACCESS_KEY: SecretStr = Field(
        ...,
        description="MinIO/S3 access key",
    )
    MINIO_SECRET_KEY: SecretStr = Field(
        ...,
        description="MinIO/S3 secret key",
    )
    MINIO_BUCKET_NAME: str = Field(
        "detective-1-assets",
        description="MinIO/S3 bucket name for assets",
    )
    MINIO_SECURE: bool = Field(
        False,
        description="Use HTTPS for MinIO/S3 connection",
    )

    # ------------------------------------------------------------------ #
    # LLM Integration                                                    #
    # ------------------------------------------------------------------ #
    LLM_PROVIDER: str = Field(
        "openai",
        description="Primary LLM provider (e.g., 'openai', 'perplexity', 'gemini')",
    )
    OPENAI_API_KEY: Optional[SecretStr] = Field(
        None,
        description="OpenAI API key",
    )
    PERPLEXITY_API_KEY: Optional[SecretStr] = Field(
        None,
        description="Perplexity AI API key (for Sonar models)",
    )
    GEMINI_API_KEY: Optional[SecretStr] = Field(
        None,
        description="Google Gemini API key",
    )
    EMBEDDING_MODEL_NAME: str = Field(
        "text-embedding-ada-002",
        description="Name of the embedding model to use (e.g., 'text-embedding-ada-002', 'bge-small-en')",
    )

    # ------------------------------------------------------------------ #
    # Vector Database - Qdrant                                           #
    # ------------------------------------------------------------------ #
    QDRANT_URL: AnyHttpUrl = Field(
        ...,
        description="Qdrant service URL (e.g., http://localhost:6333)",
    )
    QDRANT_API_KEY: Optional[SecretStr] = Field(
        None,
        description="Qdrant API key (if Qdrant is hosted)",
    )
    QDRANT_COLLECTION_NAME: str = Field(
        "detective-1-encyclopedia",
        description="Qdrant collection name for encyclopedia articles",
    )

    # ------------------------------------------------------------------ #
    # Security - JWT                                                     #
    # ------------------------------------------------------------------ #
    SECRET_KEY: SecretStr = Field(
        ...,
        description="Secret key for JWT encoding/decoding. IMPORTANT: Change in production!",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        60 * 24 * 7, # 7 days
        description="Access token expiration time in minutes",
    )
    ALGORITHM: str = Field(
        "HS256",
        description="Algorithm for JWT signing (e.g., HS256)",
    )

    @model_validator(mode="after")
    def validate_llm_keys(self) -> "Settings":
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY must be set if LLM_PROVIDER is 'openai'")
        if self.LLM_PROVIDER == "perplexity" and not self.PERPLEXITY_API_KEY:
            raise ValueError("PERPLEXITY_API_KEY must be set if LLM_PROVIDER is 'perplexity'")
        if self.LLM_PROVIDER == "gemini" and not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY must be set if LLM_PROVIDER is 'gemini'")
        return self


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


# Module-level settings instance. The application imports this object directly
# (``from app.core.config import settings``) from many modules — including the
# FastAPI entrypoint and the Celery worker — and treats its absence as a
# fail-fast wiring error. It is built through the cached factory above so the
# entire process shares a single, validated Settings object.
settings = get_settings()