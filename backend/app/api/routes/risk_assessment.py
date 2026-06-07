"""
Risk Assessment API routes for Detective-1 OSINT platform.

Endpoints for creating, listing, retrieving, updating and recomputing
risk assessments that classify a person (target) into one of the risk
categories: clean / suspicious / infiltrator / transformed.

The risk classification leverages encyclopedia evidence and the
configured risk engine service.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Compatibility imports — the rest of the codebase wires these up.
# We import defensively so this module is usable even before every helper
# exists, while still preferring the real implementations when present.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - prefer the real dependency
    from app.core.deps import get_db, get_current_user, require_roles
except Exception:  # pragma: no cover - fallback for partial scaffolding
    try:
        from app.api.deps import get_db, get_current_user, require_roles
    except Exception:
        from app.core.database import get_db  # type: ignore

        async def get_current_user():  # type: ignore
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication dependency not configured",
            )

        def require_roles(*_roles):  # type: ignore
            async def _checker(current_user=Depends(get_current_user)):
                return current_user

            return _checker


try:  # pragma: no cover
    from app.models.risk_assessment import RiskAssessment
except Exception:  # pragma: no cover
    RiskAssessment = None  # type: ignore

try:  # pragma: no cover
    from app.models.person import Person
except Exception:  # pragma: no cover
    Person = None  # type: ignore

try:  # pragma: no cover
    from app.services.risk_engine import RiskEngine
except Exception:  # pragma: no cover
    RiskEngine = None  # type: ignore

try:  # pragma: no cover
    from app.workers.tasks import recompute_risk_assessment_task
except Exception:  # pragma: no cover
    recompute_risk_assessment_task = None  # type: ignore


router = APIRouter(prefix="/risk-assessments", tags=["risk-assessment"])


# ---------------------------------------------------------------------------
# Enums & Schemas
# ---------------------------------------------------------------------------
class RiskCategory(str, enum.Enum):
    """Risk classification buckets for a target person."""

    CLEAN = "clean"               # پاک
    SUSPICIOUS = "suspicious"     # مشکوک
    INFILTRATOR = "infiltrator"   # نفوذی
    TRANSFORMED = "transformed"   # استحاله‌یافته
    UNKNOWN = "unknown"


class RiskLevel(str, enum.Enum):
    """Severity buckets used for chart color coding."""

    LOW = "low"          # green
    MEDIUM = "medium"    # yellow
    HIGH = "high"        # orange
    CRITICAL = "critical"  # red
    UNKNOWN = "unknown"  # gray


# Map a numeric score (0..100) to a level for graph color coding.
def score_to_level(score: float) -> RiskLevel:
    if score is None:
        return RiskLevel.UNKNOWN
    if score < 25:
        return RiskLevel.LOW
    if score < 50:
        return RiskLevel.MEDIUM
    if score < 75:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


# Color hints (consumed by frontend graph for node coloring).
LEVEL_COLORS = {
    RiskLevel.LOW: "#22c55e",
    RiskLevel.MEDIUM: "#eab308",
    RiskLevel.HIGH: "#f97316",
    RiskLevel.CRITICAL: "#ef4444",
    RiskLevel.UNKNOWN: "#9ca3af",
}


class EvidenceItem(BaseModel):
    """A single piece of evidence backing a risk assessment."""

    article_id: Optional[int] = None
    source_id: Optional[int] = None
    excerpt: Optional[str] = None
    weight: float = Field(default=1.0, ge=0.0)
    credibility: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RiskAssessmentBase(BaseModel):
    person_id: int
    category: RiskCategory = RiskCategory.UNKNOWN
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    rationale: Optional[str] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)


class RiskAssessmentCreate(RiskAssessmentBase):
    pass


class RiskAssessmentUpdate(BaseModel):
    category: Optional[RiskCategory] = None
    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    rationale: Optional[str] = None
    evidence: Optional[List[EvidenceItem]] = None


class RiskAssessmentOut(RiskAssessmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: RiskLevel = RiskLevel.UNKNOWN
    color: str = LEVEL_COLORS[RiskLevel.UNKNOWN]
    assessed_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RiskAssessmentListOut(BaseModel):
    total: int
    items: List[RiskAssessmentOut]


class RecomputeRequest(BaseModel):
    person_id: int
    async_mode: bool = Field(
        default=True,
        description="If true, enqueue a background Celery task; "
        "otherwise compute synchronously.",
    )


class RecomputeResponse(BaseModel):
    person_id: int
    enqueued: bool
    task_id: Optional[str] = None
    assessment: Optional[RiskAssessmentOut] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_out(obj) -> RiskAssessmentOut:
    """Serialize an ORM RiskAssessment (or compatible dict) to the output schema."""
    if isinstance(obj, dict):
        data = dict(obj)
        score = data.get("score", 0.0) or 0.0
        level = score_to_level(score)
        data.setdefault("evidence", [])
        out = RiskAssessmentOut(level=level, color=LEVEL_COLORS[level], **{
            k: v for k, v in data.items() if k not in {"level", "color"}
        })
        return out

    score = getattr(obj, "score", 0.0) or 0.0
    level = score_to_level(score)
    raw_evidence = getattr(obj, "evidence", None) or []
    evidence: List[EvidenceItem] = []
    for e in raw_evidence:
        if isinstance(e, EvidenceItem):
            evidence.append(e)
        elif isinstance(e, dict):
            evidence.append(EvidenceItem(**e))

    return RiskAssessmentOut(
        id=getattr(obj, "id"),
        person_id=getattr(obj, "person_id"),
        category=getattr(obj, "category", RiskCategory.UNKNOWN),
        score=score,
        rationale=getattr(obj, "rationale", None),
        evidence=evidence,
        level=level,
        color=LEVEL_COLORS[level],
        assessed_by=getattr(obj, "assessed_by", None),
        created_at=getattr(obj, "created_at", None),
        updated_at=getattr(obj, "updated_at", None),
    )


async def _ensure_person_exists(db: AsyncSession, person_id: int) -> None:
    if Person is None:
        return
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person {person_id} not found",
        )


async def _get_assessment_or_404(db: AsyncSession, assessment_id: int):
    if RiskAssessment is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RiskAssessment model is not available",
        )
    result = await db.execute(
        select(RiskAssessment).where(RiskAssessment.id == assessment_id)
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk assessment {assessment_id} not found",
        )
    return obj


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("", response_model=RiskAssessmentListOut)
async def list_risk_assessments(
    person_id: Optional[int] = Query(default=None, ge=1),
    category: Optional[RiskCategory] = Query(default=None),
    min_score: Optional[float] = Query(default=None, ge=0.0, le=100.0),
    max_score: Optional[float] = Query(default=None, ge=0.0, le=100.0),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List risk assessments with optional filtering by person / category / score."""
    if RiskAssessment is None:
        return RiskAssessmentListOut(total=0, items=[])

    stmt = select(RiskAssessment)
    count_stmt = select(func.count()).select_from(RiskAssessment)

    if person_id is not None:
        stmt = stmt.where(RiskAssessment.person_id == person_id)
        count_stmt = count_stmt.where(RiskAssessment.person_id == person_id)
    if category is not None:
        stmt = stmt.where(RiskAssessment.category == category.value)
        count_stmt = count_stmt.where(RiskAssessment.category == category.value)
    if min_score is not None:
        stmt = stmt.where(RiskAssessment.score >= min_score)
        count_stmt = count_stmt.where(RiskAssessment.score >= min_score)
    if max_score is not None:
        stmt = stmt.where(RiskAssessment.score <= max_score)
        count_stmt = count_stmt.where(RiskAssessment.score <= max_score)

    total_result = await db.execute(count_stmt)
    total = int(total_result.scalar_one() or 0)

    stmt = stmt.order_by(RiskAssessment.score.desc()).offset