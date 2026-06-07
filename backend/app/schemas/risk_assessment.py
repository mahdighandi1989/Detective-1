"""Pydantic schemas for risk assessment.

These schemas validate and serialize the data exchanged through the
risk-assessment API. They are intentionally kept in sync with the
SQLAlchemy model in ``backend/app/models/risk_assessment.py``.

Risk categories (per project spec):
    - clean        (پاک)
    - suspicious   (مشکوک)
    - infiltrator  (نفوذی)
    - transformed  (استحاله‌یافته)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskCategory(str, Enum):
    """Classification buckets for a profiled person."""

    CLEAN = "clean"  # پاک
    SUSPICIOUS = "suspicious"  # مشکوک
    INFILTRATOR = "infiltrator"  # نفوذی
    TRANSFORMED = "transformed"  # استحاله‌یافته
    INTELLIGENCE = "intelligence"  # اطلاعاتی / جاسوس
    UNKNOWN = "unknown"  # نامشخص / در حال بررسی


class RiskLevel(str, Enum):
    """Coarse risk severity used for chart colour coding."""

    NONE = "none"  # بدون خطر
    LOW = "low"  # کم
    MEDIUM = "medium"  # متوسط
    HIGH = "high"  # زیاد
    CRITICAL = "critical"  # بحرانی


# Mapping used by the frontend graph to colour nodes by risk level.
RISK_LEVEL_COLORS: dict[str, str] = {
    RiskLevel.NONE.value: "#22c55e",  # green
    RiskLevel.LOW.value: "#84cc16",  # lime
    RiskLevel.MEDIUM.value: "#eab308",  # yellow
    RiskLevel.HIGH.value: "#f97316",  # orange
    RiskLevel.CRITICAL.value: "#ef4444",  # red
}


class RiskFactor(BaseModel):
    """A single weighted signal that contributed to the assessment."""

    model_config = ConfigDict(from_attributes=True)

    key: str = Field(..., description="Identifier of the factor, e.g. 'past_position'")
    label: str = Field(..., description="Human-readable description of the factor")
    weight: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Signed contribution to the score in range [-1, 1]",
    )
    evidence: Optional[str] = Field(
        default=None, description="Short justification / cited evidence for this factor"
    )
    source_id: Optional[UUID] = Field(
        default=None, description="Optional reference to a credibility-scored source"
    )


class RiskAssessmentBase(BaseModel):
    """Shared fields for creating / reading a risk assessment."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    person_id: UUID = Field(..., description="Person this assessment belongs to")
    category: RiskCategory = Field(
        default=RiskCategory.UNKNOWN, description="Classification bucket"
    )
    level: RiskLevel = Field(
        default=RiskLevel.NONE, description="Coarse severity for chart colouring"
    )
    score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Normalised risk score in range [0, 100]",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model/analyst confidence in this assessment, [0, 1]",
    )
    summary: Optional[str] = Field(
        default=None, description="Narrative summary of why this category was assigned"
    )
    factors: list[RiskFactor] = Field(
        default_factory=list, description="Weighted factors used in the computation"
    )
    evidence_article_ids: list[UUID] = Field(
        default_factory=list,
        description="Encyclopedia article IDs that support this assessment",
    )
    assessed_by_model: Optional[str] = Field(
        default=None,
        description="Name of the LLM/agent that produced the assessment (if automated)",
    )

    @field_validator("score")
    @classmethod
    def _round_score(cls, v: float) -> float:
        return round(v, 2)

    @field_validator("confidence")
    @classmethod
    def _round_confidence(cls, v: float) -> float:
        return round(v, 4)


class RiskAssessmentCreate(RiskAssessmentBase):
    """Payload for creating a new risk assessment."""

    pass


class RiskAssessmentUpdate(BaseModel):
    """Partial update payload — every field is optional."""

    model_config = ConfigDict(use_enum_values=True)

    category: Optional[RiskCategory] = None
    level: Optional[RiskLevel] = None
    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    summary: Optional[str] = None
    factors: Optional[list[RiskFactor]] = None
    evidence_article_ids: Optional[list[UUID]] = None
    assessed_by_model: Optional[str] = None

    @field_validator("score")
    @classmethod
    def _round_score(cls, v: Optional[float]) -> Optional[float]:
        return round(v, 2) if v is not None else v

    @field_validator("confidence")
    @classmethod
    def _round_confidence(cls, v: Optional[float]) -> Optional[float]:
        return round(v, 4) if v is not None else v


class RiskAssessmentRead(RiskAssessmentBase):
    """Full representation returned by the API."""

    id: UUID
    color: Optional[str] = Field(
        default=None, description="Hex colour derived from the risk level"
    )
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("color", mode="before")
    @classmethod
    def _derive_color(cls, v: Optional[str], info: Any) -> Optional[str]:
        if v:
            return v
        level = info.data.get("level")
        if level is None:
            return None
        level_value = level.value if isinstance(level, RiskLevel) else str(level)
        return RISK_LEVEL_COLORS.get(level_value)


class RiskAssessmentList(BaseModel):
    """Paginated list wrapper."""

    model_config = ConfigDict(from_attributes=True)

    total: int = Field(..., ge=0)
    items: list[RiskAssessmentRead] = Field(default_factory=list)


__all__ = [
    "RiskCategory",
    "RiskLevel",
    "RISK_LEVEL_COLORS",
    "RiskFactor",
    "RiskAssessmentBase",
    "RiskAssessmentCreate",
    "RiskAssessmentUpdate",
    "RiskAssessmentRead",
    "RiskAssessmentList",
]