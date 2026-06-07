"""
Encyclopedia API routes for Detective-1.

Handles:
- Ingesting raw or processed intelligence content (articles).
- Automatic LLM-based categorization and summarization.
- Semantic (vector) search over encyclopedia articles via embeddings.

Dependencies (DB session, current user, role guard) are imported directly
from ``app.api.deps``. The previous defensive try/except fallback stubs
(which silently degraded to 503 mocks) have been removed: they masked real
wiring errors and produced misleading runtime behavior. If a dependency is
missing, importing this module should fail loudly so the misconfiguration is
caught at startup rather than at request time.

Optional backing *services* (LLM adapter, embeddings, Celery tasks) are still
loaded lazily inside handlers so that the API surface can degrade gracefully
(synchronous fallback / informative errors) when those services are not
configured — but the core request-scoped dependencies are always required.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_roles
from app.models.article import Article

logger = logging.getLogger("detective.encyclopedia")

router = APIRouter(prefix="/encyclopedia", tags=["encyclopedia"])


# ---------------------------------------------------------------------------
# Enums & constants
# ---------------------------------------------------------------------------


class ContentForm(str, Enum):
    """Form in which the source content was supplied."""

    RAW = "raw"
    PROCESSED = "processed"


class ArticleCategory(str, Enum):
    """High-level intelligence taxonomy for encyclopedia articles."""

    INFILTRATION = "infiltration"
    COUNTER_INTELLIGENCE = "counter_intelligence"
    ESPIONAGE = "espionage"
    INTELLIGENCE_SKILLS = "intelligence_skills"
    TRADECRAFT = "tradecraft"
    GENERAL = "general"
    UNCLASSIFIED = "unclassified"


class ClassificationLevel(str, Enum):
    """Confidentiality classification levels (RBAC-aware)."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


# Roles allowed to ingest / mutate encyclopedia content.
WRITE_ROLES = ("admin", "analyst", "editor")
# Roles allowed to read confidential+ content.
PRIVILEGED_READ_ROLES = ("admin", "analyst")


# ---------------------------------------------------------------------------
# Pydantic schemas (request/response contracts)
# ---------------------------------------------------------------------------


class ArticleIngestRequest(BaseModel):
    """Payload for ingesting new intelligence content into the encyclopedia."""

    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field(..., min_length=1)
    form: ContentForm = Field(
        default=ContentForm.RAW,
        description="Whether the content is raw or already processed/summarized.",
    )
    category: Optional[ArticleCategory] = Field(
        default=None,
        description="Optional manual category; if omitted, LLM auto-categorizes.",
    )
    classification: ClassificationLevel = Field(
        default=ClassificationLevel.INTERNAL,
        description="Confidentiality classification level.",
    )
    source_url: Optional[str] = Field(default=None, max_length=2048)
    tags: List[str] = Field(default_factory=list)
    auto_process: bool = Field(
        default=True,
        description="If true, schedule async LLM categorization/summarization.",
    )


class ArticleResponse(BaseModel):
    """Encyclopedia article representation."""

    id: int
    title: str
    content: str
    summary: Optional[str] = None
    form: str
    category: Optional[str] = None
    classification: str
    source_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    processed: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ArticleListResponse(BaseModel):
    items: List[ArticleResponse]
    total: int
    page: int
    page_size: int


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2048)
    top_k: int = Field(default=10, ge=1, le=100)
    category: Optional[ArticleCategory] = None
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class SemanticSearchHit(BaseModel):
    article: ArticleResponse
    score: float


class SemanticSearchResponse(BaseModel):
    query: str
    hits: List[SemanticSearchHit]
    total: int


# ---------------------------------------------------------------------------
# Lazy service loaders (optional backends degrade gracefully)
# ---------------------------------------------------------------------------


def _get_llm_adapter():
    """Lazily import the LLM adapter; return ``None`` if unavailable."""
    try:
        from app.services.llm_adapter import LLMAdapter

        return LLMAdapter()
    except Exception as exc:  # pragma: no cover - optional backend
        logger.warning("LLM adapter unavailable: %s", exc)
        return None


def _get_embeddings_service():
    """Lazily import the embeddings service; return ``None`` if unavailable."""
    try:
        from app.services.embeddings import EmbeddingsService

        return EmbeddingsService()
    except Exception as exc:  # pragma: no cover - optional backend
        logger.warning("Embeddings service unavailable: %s", exc)
        return None


def _enqueue_processing(article_id: int) -> bool:
    """
    Try to schedule async LLM processing via Celery.

    Returns ``True`` if the task was enqueued, ``False`` if Celery is not
    available (caller may then fall back to synchronous processing).
    """
    try:
        from app.workers.tasks import process_article

        process_article.delay(article_id)
        return True
    except Exception as exc:  # pragma: no cover - optional backend
        logger.warning("Could not enqueue article processing: %s", exc)
        return False


async def _process_article_sync(article: Article) -> None:
    """
    Synchronously categorize/summarize an article using the LLM adapter,
    used as a fallback when Celery is unavailable.
    """
    adapter = _get_llm_adapter()
    if adapter is None:
        logger.info(
            "Skipping synchronous processing for article %s: no LLM adapter.",
            getattr(article, "id", "?"),
        )
        return

    try:
        result = await adapter.categorize_and_summarize(
            title=article.title,
            content=article.content,
        )
    except Exception as exc:  # pragma: no cover - depends on external LLM
        logger.error("LLM processing failed for article %s: %s", article.id, exc)
        return

    if not result:
        return

    summary = result.get("summary")
    category = result.get("category")
    if summary:
        article.summary = summary
    if category and getattr(article, "category", None) in (None, "", "general"):
        article.category = category
    article.processed = True


def _can_access_classification(
    user: Any, classification: str
) -> bool:
    """Return whether ``user`` may access content at ``classification``."""
    if classification in (
        ClassificationLevel.PUBLIC.value,
        ClassificationLevel.INTERNAL.value,
    ):
        return True
    roles = set(getattr(user, "roles", []) or [])
    return bool(roles.intersection(PRIVILEGED_READ_ROLES))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/articles",
    response_model=ArticleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest raw or processed intelligence content",
)
async def ingest_article(
    payload: ArticleIngestRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_roles(*WRITE_ROLES)),
) -> ArticleResponse:
    """
    Ingest a new encyclopedia article (raw or processed). When
    ``auto_process`` is set, schedule (or synchronously perform) LLM-based
    categorization and summarization.
    """
    article = Article(
        title=payload.title,
        content=payload.content,
        summary=None,
        form=payload.form.value,
        category=payload.category.value if payload.category else None,
        classification=payload.classification.value,
        source_url=payload.source_url,
        tags=list(payload.tags),
        processed=False,
        created_at=datetime.now(timezone.utc),
    )

    db.add(article)
    await db.flush()  # obtain article.id without committing

    if payload.auto_process:
        enqueued = _enqueue_processing(article.id)
        if not enqueued:
            # Fall back to synchronous processing so behavior is observable.
            await _process_article_sync(article)

    await db.commit()
    await db.refresh(article)

    logger.info(
        "Article ingested id=%s by user=%s auto_process=%s",
        article.id,
        getattr(user, "id", getattr(user, "username", "?")),
        payload.auto_process,
    )
    return ArticleResponse.model_validate(article)


@router.get(
    "/articles",
    response_model=ArticleListResponse,
    summary="List encyclopedia articles",
)
async def list_articles(
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_current_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: Optional[ArticleCategory] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=512),
) -> ArticleListResponse:
    """List articles with optional category filter and keyword search."""
    stmt = select(Article)
    count_stmt = select(func.count()).select_from(Article)

    if category is not None:
        stmt = stmt.where(Article.category == category.value)
        count_stmt = count_stmt.where(Article.category == category.value)

    if search:
        like = f"%{search}%"
        cond = or_(Article.title.ilike(like), Article.content.ilike(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total_result = await db.execute(count_stmt)
    total = int(total_result.scalar_one() or 0)

    stmt = (
        stmt.order_by(Article.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    articles = result.scalars().all()

    return ArticleListResponse(
        items=[ArticleResponse.model_validate(a) for a in articles],
        total=total,
        page=page,
        page_size=page_size,
    )