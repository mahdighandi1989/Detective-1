"""
backend/app/models/risk_assessment.py

مدل ارزیابی ریسک و طبقه‌بندی فرد (Risk Assessment & Classification Model).

این ماژول مدل‌های مربوط به ارزیابی خطر اشخاص نفوذی را تعریف می‌کند.
هر شخص (Person) می‌تواند چندین ارزیابی ریسک داشته باشد که هرکدام یک
طبقه‌بندی (پاک / مشکوک / نفوذی / استحاله‌یافته / اطلاعاتی / جاسوس) به‌همراه
امتیاز عددی، رنگ نمایش در نمودار، شواهد پشتیبان و سابقهٔ تغییرات دارد.

وابستگی‌ها:
    upstream:
        - app.db.base  (Base declarative)  -> در صورت نبود، fallback محلی
        - app.models.person.Person          (relationship)
    downstream:
        - app.schemas.risk_assessment       (Pydantic schemas)
        - app.services.risk_engine          (موتور ارزیابی)
        - app.api.routes.graph              (رنگ‌بندی نمودار بر اساس level)
        - alembic migrations
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ---------------------------------------------------------------------------
# پایهٔ declarative: تلاش برای استفاده از Base مشترک پروژه، در غیر این‌صورت
# یک Base محلی ساخته می‌شود تا این ماژول مستقل نیز import شود.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - مسیر اصلی پروژه
    from app.db.base_class import Base  # type: ignore
except Exception:  # pragma: no cover
    try:
        from app.db.base import Base  # type: ignore
    except Exception:
        from sqlalchemy.orm import DeclarativeBase

        class Base(DeclarativeBase):  # type: ignore[no-redef]
            """Fallback declarative base در صورت نبود Base مشترک پروژه."""

            pass


if TYPE_CHECKING:  # pragma: no cover
    from app.models.person import Person  # noqa: F401


# ---------------------------------------------------------------------------
# Enums برای طبقه‌بندی ریسک و نوع ارزیابی
# ---------------------------------------------------------------------------
class RiskLevel(str, enum.Enum):
    """
    سطوح مختلف ریسک برای یک شخص.
    """
    CLEAN = "پاک"  # آدم پاک، بدون هیچ شکی
    SUSPICIOUS = "مشکوک"  # دارای برخی رفتارهای مشکوک یا ارتباطات نامعلوم
    INFILTRATOR = "نفوذی"  # تایید شده که جزو شبکه نفوذ است
    TRANSFORMED = "استحاله_یافته"  # کسی که مواضعش تغییر کرده و مشکوک به نفوذ است
    INTELLIGENCE_AGENT = "اطلاعاتی"  # عامل سازمان‌های اطلاعاتی (ممکن است داخلی یا خارجی باشد)
    SPY = "جاسوس"  # عامل جاسوسی برای یک کشور/سازمان خارجی


class AssessmentType(str, enum.Enum):
    """
    نوع ارزیابی ریسک (خودکار، دستی، یا بازنگری/override).
    """
    AUTOMATIC = "خودکار"  # ارزیابی انجام شده توسط سیستم خودکار (LLM, OSINT agent)
    MANUAL = "دستی"  # ارزیابی انجام شده توسط کاربر انسانی
    OVERRIDE = "بازنگری"  # ارزیابی دستی که ارزیابی قبلی (خودکار یا دستی) را بازنویسی می‌کند


# ---------------------------------------------------------------------------
# مدل RiskAssessment
# ---------------------------------------------------------------------------
class RiskAssessment(Base):
    """
    مدل SQLAlchemy برای نگهداری ارزیابی ریسک یک شخص.
    """
    __tablename__ = "risk_assessment"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("person.id"), index=True, nullable=False
    )
    assessment_type: Mapped[AssessmentType] = mapped_column(
        SAEnum(AssessmentType), default=AssessmentType.AUTOMATIC, nullable=False
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel), nullable=False
    )
    score: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )  # امتیاز عددی ریسک، معمولاً بین 0.0 (کمترین) تا 1.0 (بیشترین)
    color_code: Mapped[str] = mapped_column(
        String(7), default="#CCCCCC", nullable=False
    )  # کد رنگ هگزا دسیمال برای نمایش در UI (مثلاً #FF0000 برای خطر بالا)
    summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # خلاصه‌ای از ارزیابی و دلایل آن
    evidence: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )  # شواهد پشتیبان (مثلاً لینک‌ها به منابع OSINT، نقل قول‌ها)
    assessed_by: Mapped[str] = mapped_column(
        String(255), default="system", nullable=False
    )  # شناسه کاربر یا 'system' که ارزیابی را انجام داده است
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    audit_log: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, nullable=True, default=list
    )  # تاریخچه تغییرات این ارزیابی (مثلاً چه کسی، چه زمانی، چه فیلدی را تغییر داد)

    # رابطه با مدل Person
    person: Mapped["Person"] = relationship(
        "Person", back_populates="risk_assessments"
    )

    __table_args__ = (
        # اطمینان از اینکه امتیاز ریسک در محدوده معتبر (0.0 تا 1.0) است
        CheckConstraint(score >= 0.0, name='ck_risk_assessment_score_min'),
        CheckConstraint(score <= 1.0, name='ck_risk_assessment_score_max'),
        # ایندکس ترکیبی برای جستجوهای رایج بر اساس شخص و سطح ریسک
        Index("ix_risk_assessment_person_risk_level", "person_id", "risk_level"),
    )

    def __repr__(self):
        return (
            f"<RiskAssessment(id='{self.id}', person_id='{self.person_id}', "
            f"risk_level='{self.risk_level.value}', score={self.score:.2f})>"
        )