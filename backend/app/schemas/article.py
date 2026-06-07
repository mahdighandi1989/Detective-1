"""Pydantic schemas for Article (encyclopedia) and semantic search.

This module defines request/response models for the intelligence
encyclopedia (دانشنامهٔ اطلاعاتی): raw or processed content ingestion,
LLM-based categorization/summarization, and semantic search via
embeddings.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContentFormat(str, Enum):
    """Whether the submitted content is raw or already processed."""

    RAW = "raw"  # خام
    PROCESSED = "processed"  # پخته / خلاصه‌شده / کامل


class ClassificationLevel(str, Enum):
    """Confidentiality classification level (سطوح طبقه‌بندی محرمانگی)."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"


class ArticleCategory(str, Enum):
    """Top-level intelligence categories for encyclopedia articles."""

    INFILTRATION = "infiltration"  # نفوذ
    INFILTRATION_SKILLS = "infiltration_skills"  # مهارت‌های نفوذ
    INTELLIGENCE = "intelligence"  # اطلاعات
    COUNTER_ESPIONAGE = "counter_espionage"  # ضد جاسوسی
    ESPIONAGE = "espionage"  # جاسوسی
    TRADECRAFT = "tradecraft"  # فنون عملیاتی
    OTHER = "other"


class ArticleStatus(str, Enum):
    """Processing lifecycle status of an article."""

    DRAFT = "draft"
    PENDING_ANALYSIS = "pending_analysis"  # در صف تحلیل LLM
    ANALYZED = "analyzed"
    PUBLISHED = "published"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Base / shared
# ---------------------------------------------------------------------------


class ArticleBase(BaseModel):
    """Shared fields for article create/update operations."""

    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field(..., min_length=1, description="Raw or processed body text")
    content_format: ContentFormat = Field(default=ContentFormat.RAW)
    summary: Optional[str] = Field(
        default=None,
        max_length=8192,
        description="Optional human-provided summary; LLM may regenerate.",
    )
    category: Optional[ArticleCategory] = Field(
        default=None,
        description="Optional manual category; LLM auto-categorizes if absent.",
    )
    tags: list[str] = Field(default_factory=list)
    classification: ClassificationLevel = Field(
        default=ClassificationLevel.INTERNAL
    )
    source_ids: list[UUID] = Field(
        default_factory=list,
        description="Linked source records used for credibility scoring.",
    )

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for tag in value:
            cleaned = tag.strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                result.append(cleaned)
        return result

    @field_validator("title", "content")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty or whitespace only")
        return cleaned


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------


class ArticleCreate(ArticleBase):
    """Payload for creating a new encyclopedia article."""

    auto_analyze: bool = Field(
        default=True,
        description="Queue LLM categorization/summarization/embedding on create.",
    )


class ArticleUpdate(BaseModel):
    """Partial update payload. All fields optional."""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    content: Optional[str] = Field(default=None, min_length=1)
    content_format: Optional[ContentFormat] = None
    summary: Optional[str] = Field(default=None, max_length=8192)
    category: Optional[ArticleCategory] = None
    tags: Optional[list[str]] = None
    classification: Optional[ClassificationLevel] = None
    status: Optional[ArticleStatus] = None
    source_ids: Optional[list[UUID]] = None
    re_analyze: bool = Field(
        default=False,
        description="Re-run LLM analysis & re-embed after this update.",
    )

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        seen: set[str] = set()
        result: list[str] = []
        for tag in value:
            cleaned = tag.strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                result.append(cleaned)
        return result


# ---------------------------------------------------------------------------
# LLM analysis result (produced by services/llm_adapter + workers/tasks)
# ---------------------------------------------------------------------------


class ArticleAnalysis(BaseModel):
    """Structured output of LLM categorization/summarization."""

    summary: Optional[str] = None
    category: Optional[ArticleCategory] = None
    tags: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    entities: list[str] = Field(
        default_factory=list,
        description="Named persons/orgs extracted for graph linking.",
    )
    model_name: Optional[str] = Field(
        default=None, description="LLM model that produced this analysis."
    )
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Read / Response
# ---------------------------------------------------------------------------


class ArticleRead(ArticleBase):
    """Full article representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ArticleStatus = ArticleStatus.DRAFT
    key_points: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    analysis_model: Optional[str] = None
    analysis_confidence: Optional[float] = None
    has_embedding: bool = False
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class ArticleListItem(BaseModel):
    """Lightweight article representation for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    category: Optional[ArticleCategory] = None
    content_format: ContentFormat
    classification: ClassificationLevel
    status: ArticleStatus
    tags: list[str] = Field(default_factory=list)
    summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ArticleListResponse(BaseModel):
    """Paginated list of articles."""

    items: list[ArticleListItem]
    total: int
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------


class SemanticSearchRequest(BaseModel):
    """Request body for semantic (embedding-based) search over articles."""

    query: str = Field(..., min_length=1, max_length=2048)
    limit: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity to include a result.",
    )
    categories: Optional[list[ArticleCategory]] = Field(
        default=None, description="Restrict search to these categories."
    )
    classification_max: Optional[ClassificationLevel] = Field(
        default=None,
        description="Only return articles at or below this classification.",
    )

    @field_validator("query")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query must not be empty")
        return cleaned


class SemanticSearchHit(BaseModel):
    """A single semantic search result with similarity score."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    summary: Optional[str] = None
    category: Optional[ArticleCategory] = None
    classification: ClassificationLevel = ClassificationLevel.INTERNAL
    score: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity.")
    snippet: Optional[str] = Field(
        default=None, description="Highlighted/extracted relevant passage."
    )


class SemanticSearchResponse(BaseModel):
    """Response wrapper for semantic search results."""

    query: str
    hits: list[SemanticSearchHit]
    total: int
    took_ms: Optional[float] = None


# ---------------------------------------------------------------------------
# Ingestion job (async LLM analysis queued via Celery)
# ---------------------------------------------------------------------------


class ArticleAnalysisJob(BaseModel):
    """Status of an async LLM analysis/embedding job for an article."""

    article_id: UUID
    job_id: str
    status: str = Field(
        default="queued",
        description="queued | running | completed | failed",
    )
    detail: Optional[str] = None
    result: Optional[ArticleAnalysis] = None


# ---------------------------------------------------------------------------
# Embedding helper (internal contract with services/embeddings)
# ---------------------------------------------------------------------------


class EmbeddingPayload(BaseModel):
    """Internal contract passed to the embeddings service."""

    article_id: UUID
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)