"""
Article model for the intelligence encyclopedia (دانشنامهٔ اطلاعاتی).

Stores raw or processed (cooked/summarized) intelligence-related content
(influence skills, counterintelligence, espionage, etc.), classified and
summarized automatically by LLMs, with a pgvector embedding for semantic
search across the encyclopedia.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    Table,  # Added for association table
    Column, # Added for association table
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    # pgvector provides a SQLAlchemy column type for semantic search.
    from pgvector.sqlalchemy import Vector  # type: ignore
    _HAS_PGVECTOR = True
except ImportError:  # pragma: no cover - graceful fallback when pgvector absent
    # Fallback for when pgvector is not installed.
    # We'll use a JSONB column to store the vector as a list of floats.
    _HAS_PGVECTOR = False

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.source import Source
    from app.models.person import Person # Added for relationship


# Default dimensionality for embeddings (e.g. OpenAI text-embedding-3-small).
EMBEDDING_DIM = 1536


class ContentStatus(str, enum.Enum):
    """Lifecycle of an encyclopedia article's content processing."""

    RAW = "raw"            # خام — entered as-is, not yet processed
    PROCESSING = "processing"  # in the LLM pipeline
    COOKED = "cooked"      # پخته — classified & summarized by an LLM
    REVIEWED = "reviewed"  # human-reviewed / validated
    ARCHIVED = "archived"


class ClassificationLevel(str, enum.Enum):
    """Confidentiality / classification level (سطوح طبقه‌بندی محرمانگی)."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"


class ArticleCategory(str, enum.Enum):
    """High-level intelligence domain category."""

    INTELLIGENCE = "intelligence"           # اطلاعات
    INFLUENCE = "influence"                 # نفوذ
    ESPIONAGE = "espionage"                 # جاسوسی
    COUNTERINTELLIGENCE = "counterintelligence" # ضد جاسوسی
    SKILLS = "skills"                       # مهارت‌ها (مثلاً مهارت‌های نفوذ)
    ANALYSIS = "analysis"                   # تحلیل
    SECURITY = "security"                   # امنیت
    POLITICS = "politics"                   # سیاست (مواضع سیاسی)
    ECONOMY = "economy"                     # اقتصاد
    MILITARY = "military"                   # نظامی
    TECHNOLOGY = "technology"               # فناوری
    CULTURE = "culture"                     # فرهنگ
    OTHER = "other"                         # سایر


# Association table for many-to-many relationship between Article and Person
article_person_association_table = Table(
    "article_person_association",
    Base.metadata,
    Column("article_id", UUID(as_uuid=True), ForeignKey("article.id"), primary_key=True),
    Column("person_id", UUID(as_uuid=True), ForeignKey("person.id"), primary_key=True),
    # Optional: Add specific metadata for the association, e.g., how relevant the person is to the article
    Column("relevance_score", Integer, default=0, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), onupdate=func.now()),
)


class Article(Base):
    """
    SQLAlchemy model for an encyclopedia article.
    """
    __tablename__ = "article"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String, index=True, nullable=False)
    
    # Raw content as initially entered by user or agent
    content_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Processed content (e.g., cleaned, normalized, structured) by LLM
    content_processed: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Summarized content by LLM for quick overview
    content_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Embedding vector for semantic search
    # Using pgvector's Vector type if available, otherwise JSONB for compatibility
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(EMBEDDING_DIM) if _HAS_PGVECTOR else JSONB, nullable=True
    )
    # Note: For efficient vector search (e.g., HNSW, IVFFLAT),
    # specific PostgreSQL indexes (not standard SQLAlchemy Index) are required,
    # usually added via Alembic migrations using raw SQL.

    status: Mapped[ContentStatus] = mapped_column(
        SAEnum(ContentStatus, name="content_status_enum", create_type=False),
        default=ContentStatus.RAW,
        nullable=False,
    )
    classification_level: Mapped[ClassificationLevel] = mapped_column(
        SAEnum(ClassificationLevel, name="classification_level_enum", create_type=False),
        default=ClassificationLevel.PUBLIC,
        nullable=False,
    )
    category: Mapped[ArticleCategory] = mapped_column(
        SAEnum(ArticleCategory, name="article_category_enum", create_type=False),
        default=ArticleCategory.OTHER,
        nullable=False,
    )

    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True, default=[])
    
    # Flexible JSONB field for additional metadata (e.g., LLM processing details, source metadata, custom attributes)
    metadata_: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default={})

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=False)
    
    # Foreign key to Source model, indicating where this article's content originated
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source.id"), nullable=True, index=True
    )
    
    # Relationship to Source model: one Source can have many Articles
    source: Mapped[Optional["Source"]] = relationship(
        "Source", back_populates="articles", lazy="joined"
    )

    # Many-to-many relationship with Person model: an Article can be related to many Persons, and a Person to many Articles
    persons: Mapped[list["Person"]] = relationship(
        "Person",
        secondary=article_person_association_table,
        back_populates="articles",
        lazy="selectin" # Eagerly load persons related to an article for common use cases
    )

    # Add an index for quick lookup by category and status
    __table_args__ = (
        Index("idx_article_category_status", category, status),
        Index("idx_article_created_at", created_at.desc()), # For chronological queries
        # Consider adding a GIN index on tags if frequently querying by tags:
        # Index("idx_article_tags", tags, postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, title='{self.title[:50]}...', status='{self.status}', category='{self.category}')>"