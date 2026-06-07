"""
backend/app/api/routes/risk.py

روت‌های ارزیابی ریسک و طبقه‌بندی اشخاص (Risk Assessment & Classification).

این ماژول endpoint های زیر را فراهم می‌کند:
- اجرای ارزیابی ریسک خودکار روی یک پروفایل شخص (با اتکا به داده‌های دانشنامه)
- بازیابی آخرین ارزیابی ریسک یک شخص
- بازیابی تاریخچهٔ ارزیابی‌های ریسک (audit trail)
- override دستی طبقه‌بندی توسط کاربر مجاز
- لیست/فیلتر اشخاص بر اساس دستهٔ ریسک (پاک / مشکوک / نفوذی / استحاله‌یافته)

طبقه‌بندی‌ها (RiskCategory):
    clean        — پاک
    suspicious   — مشکوک
    infiltrator  — نفوذی
    degenerated  — استحاله‌یافته (دچار استحاله شده)

رنگ‌بندی نمودار بر اساس همین دسته‌ها در پاسخ بازگردانده می‌شود تا frontend
(React Flow / Cytoscape.js) بتواند گره‌ها را رنگ‌آمیزی کند.

importها fail-fast هستند؛ اگر ماژول‌های upstream (get_db / require_roles)
موجود نباشند، خطا در زمان import رخ می‌دهد، نه با fallbackی که کنترل
دسترسی (RBAC) را دور بزند.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

# Fail-fast imports: نبود این dependencyها باید در زمان import خطا بدهد،
# نه با fallback که می‌تواند RBAC را دور بزند.
from app.api.deps import get_db, require_roles
from app.models.person import Person
from app.models.risk_assessment import RiskAssessment
from app.services.risk_engine import RiskEngine

router = APIRouter(prefix="/risk", tags=["risk"])


# ---------------------------------------------------------------------------
# Enums و ثابت‌ها
# ---------------------------------------------------------------------------

class RiskCategory(str, enum.Enum):
    """دسته‌بندی ریسک یک شخص."""

    CLEAN = "clean"               # پاک
    SUSPICIOUS = "suspicious"     # مشکوک
    INFILTRATOR = "infiltrator"   # نفوذی
    DEGENERATED = "degenerated"   # استحاله‌یافته


# رنگ‌بندی نمودار بر اساس دستهٔ ریسک (برای React Flow / Cytoscape.js)
RISK_COLOR_MAP: dict[str, str] = {
    RiskCategory.CLEAN.value: "#22c55e",        # سبز
    RiskCategory.SUSPICIOUS.value: "#eab308",   # زرد
    RiskCategory.INFILTRATOR.value: "#ef4444",  # قرمز
    RiskCategory.DEGENERATED.value: "#f97316",  # نارنجی
}

# نقش‌های مجاز برای عملیات نوشتن/override روی ارزیابی ریسک
_ANALYST_ROLES = ("admin", "analyst")
_VIEWER_ROLES = ("admin", "analyst", "viewer")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RiskAssessmentBase(BaseModel):
    category: RiskCategory = Field(..., description="دستهٔ ریسک")
    score: float = Field(..., ge=0.0, le=1.0, description="امتیاز ریسک ۰..۱")
    rationale: Optional[str] = Field(
        None, description="توضیح/استدلال پشت طبقه‌بندی"
    )


class RiskAssessmentRead(RiskAssessmentBase):
    id: UUID
    person_id: UUID
    color: str = Field(..., description="رنگ نمودار متناظر با دسته")
    is_manual_override: bool = False
    created_at: datetime
    created_by: Optional[UUID] = None

    model_config = {"from_attributes": True}


class RiskOverrideRequest(RiskAssessmentBase):
    """درخواست override دستی طبقه‌بندی توسط کاربر مجاز."""


class RiskEvaluateResponse(RiskAssessmentRead):
    """پاسخ اجرای ارزیابی خودکار."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_read_model(assessment: RiskAssessment) -> RiskAssessmentRead:
    """تبدیل model دیتابیس به schema خواندنی با رنگ نمودار."""
    category_value = (
        assessment.category.value
        if isinstance(assessment.category, enum.Enum)
        else str(assessment.category)
    )
    return RiskAssessmentRead(
        id=assessment.id,
        person_id=assessment.person_id,
        category=RiskCategory(category_value),
        score=assessment.score,
        rationale=assessment.rationale,
        color=RISK_COLOR_MAP.get(category_value, "#9ca3af"),
        is_manual_override=bool(getattr(assessment, "is_manual_override", False)),
        created_at=assessment.created_at,
        created_by=getattr(assessment, "created_by", None),
    )


async def _get_person_or_404(db: AsyncSession, person_id: UUID) -> Person:
    person = await db.get(Person, person_id)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="شخص یافت نشد",
        )
    return person


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/persons/{person_id}/evaluate",
    response_model=RiskEvaluateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="اجرای ارزیابی ریسک خودکار روی یک شخص",
)
async def evaluate_person_risk(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles(*_ANALYST_ROLES)),
):
    """
    ارزیابی ریسک خودکار را روی پروفایل یک شخص اجرا می‌کند.

    موتور ریسک با اتکا به سوابق، عملکرد، مواضع و داده‌های مرتبط دانشنامه،
    دستهٔ ریسک و امتیاز را محاسبه و یک رکورد جدید RiskAssessment ثبت می‌کند.
    """
    person = await _get_person_or_404(db, person_id)

    engine = RiskEngine(db)
    result = await engine.assess(person)

    assessment = RiskAssessment(
        person_id=person.id,
        category=result.category,
        score=result.score,
        rationale=result.rationale,
        is_manual_override=False,
        created_by=getattr(current_user, "id", None),
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)

    return _to_read_model(assessment)


@router.get(
    "/persons/{person_id}/latest",
    response_model=RiskAssessmentRead,
    summary="آخرین ارزیابی ریسک یک شخص",
)
async def get_latest_risk(
    person_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles(*_VIEWER_ROLES)),
):
    """آخرین ارزیابی ریسک ثبت‌شده برای یک شخص را بازمی‌گرداند."""
    await _get_person_or_404(db, person_id)

    stmt = (
        select(RiskAssessment)
        .where(RiskAssessment.person_id == person_id)
        .order_by(desc(RiskAssessment.created_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ارزیابی ریسکی برای این شخص ثبت نشده است",
        )
    return _to_read_model(assessment)


@router.get(
    "/persons/{person_id}/history",
    response_model=List[RiskAssessmentRead],
    summary="تاریخچهٔ ارزیابی‌های ریسک یک شخص (audit trail)",
)
async def get_risk_history(
    person_id: UUID,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles(*_VIEWER_ROLES)),
):
    """تاریخچهٔ کامل ارزیابی‌های ریسک یک شخص را به‌ترتیب نزولی زمان بازمی‌گرداند."""
    await _get_person_or_404(db, person_id)

    stmt = (
        select(RiskAssessment)
        .where(RiskAssessment.person_id == person_id)
        .order_by(desc(RiskAssessment.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    assessments = result.scalars().all()
    return [_to_read_model(a) for a in assessments]


@router.post(
    "/persons/{person_id}/override",
    response_model=RiskAssessmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="override دستی طبقه‌بندی ریسک توسط کاربر مجاز",
)
async def override_risk(
    person_id: UUID,
    payload: RiskOverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles(*_ANALYST_ROLES)),
):
    """
    یک طبقه‌بندی ریسک دستی برای شخص ثبت می‌کند.

    رکورد قبلی پاک نمی‌شود؛ یک رکورد جدید با پرچم is_manual_override ثبت
    می‌شود تا audit trail حفظ بماند.
    """
    await _get_person_or_404(db, person_id)

    assessment = RiskAssessment(
        person_id=person_id,
        category=payload.category.value,
        score=payload.score,
        rationale=payload.rationale,
        is_manual_override=True,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return _to_read_model(assessment)