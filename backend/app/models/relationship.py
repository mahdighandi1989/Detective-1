"""Relationship model for the person connection graph.

This model represents a directed/undirected relationship (edge) between two
persons in the OSINT relation graph. It is used both by the PostgreSQL
relational store and as the canonical source for synchronizing edges into
Neo4j for interactive graph visualization.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    # Preferred: project-wide declarative base.
    from app.db.base_class import Base  # type: ignore
except Exception:  # pragma: no cover - fallback for differing layouts
    try:
        from app.models.base import Base  # type: ignore
    except Exception:
        from sqlalchemy.orm import DeclarativeBase

        class Base(DeclarativeBase):  # type: ignore
            pass


if TYPE_CHECKING:
    from app.models.person import Person  # noqa: F401


class RelationshipType(str, enum.Enum):
    """Semantic type of the relationship between two persons."""

    COLLEAGUE = "colleague"            # هم‌کار / هم‌رده
    SUPERIOR = "superior"             # مافوق (source بالادست target)
    SUBORDINATE = "subordinate"       # زیردست (source زیردست target)
    FAMILY = "family"                 # خانوادگی
    FINANCIAL = "financial"           # ارتباط مالی
    POLITICAL = "political"           # ارتباط سیاسی
    EDUCATIONAL = "educational"       # هم‌دانشگاهی / استاد-شاگرد
    MEETING = "meeting"               # ملاقات / دیدار
    COMMUNICATION = "communication"   # ارتباط مخابراتی / پیام
    AFFILIATION = "affiliation"       # وابستگی سازمانی
    HANDLER = "handler"               # رابط / گرداننده (intelligence context)
    ASSOCIATE = "associate"           # همکار / شریک (general association)
    MENTOR = "mentor"                 # مرشد / راهنما
    PROTÉGÉ = "protégé"               # شاگرد / تحت حمایت
    ADVISOR = "advisor"               # مشاور
    ADVERSARY = "adversary"           # دشمن / رقیب
    WITNESS = "witness"               # شاهد
    VICTIM = "victim"                 # قربانی
    OTHER = "other"                   # سایر


class Relationship(Base):
    """Represents a relationship (edge) between two persons in the OSINT graph.

    This model stores directed or undirected relationships, their types, and associated
    metadata for risk assessment and graph visualization.
    """

    __tablename__ = "relationships"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    source_person_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("persons.id"), index=True, nullable=False
    )
    target_person_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("persons.id"), index=True, nullable=False
    )

    relationship_type: Mapped[RelationshipType] = mapped_column(
        SAEnum(RelationshipType, name="relationship_types", create_type=True),
        nullable=False,
        index=True,
    )

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True) # URL to source of information
    strength: Mapped[Optional[float]] = mapped_column(Float, nullable=True) # e.g., 0.0 to 1.0, higher is stronger
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Risk assessment specific to this relationship
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True) # e.g., 0.0 to 1.0, higher is riskier
    risk_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships to Person model
    source_person: Mapped["Person"] = relationship(
        "Person", foreign_keys=[source_person_id], back_populates="outgoing_relationships"
    )
    target_person: Mapped["Person"] = relationship(
        "Person", foreign_keys=[target_person_id], back_populates="incoming_relationships"
    )

    __table_args__ = (
        UniqueConstraint(
            "source_person_id",
            "target_person_id",
            "relationship_type",
            name="uq_relationship_source_target_type",
        ),
        # Ensure source_person_id and target_person_id are different for self-relationships
        CheckConstraint("source_person_id != target_person_id", name="ck_self_relationship_no_loop"),
        Index("ix_relationships_risk_score", risk_score),
        Index("ix_relationships_type", relationship_type),
    )

    def __repr__(self) -> str:
        return (
            f"<Relationship(id={self.id}, "
            f"source_id={self.source_person_id}, "
            f"target_id={self.target_person_id}, "
            f"type='{self.relationship_type.value}', "
            f"risk_score={self.risk_score})>"
        )