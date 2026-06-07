"""
Person model — پروفایل اشخاص هدف در پلتفرم Detective-1.

این مدل اطلاعات هویتی, سمت‌های فعلی/قبلی, سوابق و عملکرد هر شخص را
نگه می‌دارد و به ارزیابی‌های ریسک, منابع و گراف ارتباطی متصل می‌شود.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    # ساختار پروژه: backend/app/models/base.py یا backend/app/db/base_class.py
    from app.db.base_class import Base  # type: ignore
except Exception:  # pragma: no cover - fallback اگر مسیر متفاوت بود
    try:
        from app.models.base import Base  # type: ignore
    except Exception:
        from sqlalchemy.orm import DeclarativeBase

        class Base(DeclarativeBase):  # type: ignore
            """Fallback declarative base اگر base مشترک یافت نشد."""

            pass


if TYPE_CHECKING:
    from app.models.risk_assessment import RiskAssessment
    from app.models.source import Source
    from app.models.article import Article


class RiskCategory(str, enum.Enum):
    """دسته‌بندی سطح خطر فرد (مطابق AC موتور ارزیابی ریسک)."""

    CLEAN = "clean"  # پاک
    SUSPECT = "suspect"  # مشکوک
    INFILTRATOR = "infiltrator"  # نفوذی
    TRANSFORMED = "transformed"  # استحاله‌یافته
    UNKNOWN = "unknown"  # ارزیابی‌نشده


class RiskLevel(str, enum.Enum):
    """سطح عددی/رنگی خطر برای رنگ‌بندی در نمودار ارتباطی."""

    NONE = "none"  # خاکستری
    LOW = "low"  # سبز
    MEDIUM = "medium"  # زرد
    HIGH = "high"  # نارنجی
    CRITICAL = "critical"  # قرمز


class VerificationStatus(str, enum.Enum):
    """وضعیت اعتبارسنجی داده‌های پروفایل."""

    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    DISPUTED = "disputed"


class Person(Base):
    """
    مدل SQLAlchemy برای نگهداری پروفایل اشخاص.
    """

    __tablename__ = "persons"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    full_name: Mapped[str] = mapped_column(String, index=True)
    photo_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    current_position_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    place_of_birth: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    nationality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    social_media_links: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, name="metadata"
    )  # برای داده‌های اضافی غیرساختاریافته

    # فیلدهای مربوط به ارزیابی ریسک و وضعیت
    risk_category: Mapped[RiskCategory] = mapped_column(
        SAEnum(RiskCategory), default=RiskCategory.UNKNOWN, index=True
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel), default=RiskLevel.NONE, index=True
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus), default=VerificationStatus.UNVERIFIED, index=True
    )

    # فیلدهای زمانی
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    # روابط
    # یک شخص می‌تواند سوابق شغلی متعددی داشته باشد
    position_history: Mapped[List["PositionHistory"]] = relationship(
        "PositionHistory", back_populates="person", cascade="all, delete-orphan"
    )
    # یک شخص می‌تواند ارزیابی‌های ریسک متعددی داشته باشد
    risk_assessments: Mapped[List["RiskAssessment"]] = relationship(
        "RiskAssessment", back_populates="person", cascade="all, delete-orphan"
    )
    # منابعی که اطلاعات این شخص از آن‌ها جمع‌آوری شده
    sources: Mapped[List["Source"]] = relationship(
        "Source", back_populates="person", cascade="all, delete-orphan"
    )
    # مقالاتی که به این شخص مرتبط هستند (مثلاً در دانشنامه)
    articles: Mapped[List["Article"]] = relationship(
        "Article", back_populates="person", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_persons_full_name_trgm", full_name, postgresql_ops={"full_name": "gin_trgm_ops"}, postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return (
            f"<Person(id='{self.id}', full_name='{self.full_name}', "
            f"risk_category='{self.risk_category.value}')>"
        )


class PositionHistory(Base):
    """
    مدل SQLAlchemy برای نگهداری سوابق شغلی/سمت‌های یک شخص.
    """

    __tablename__ = "position_history"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    person_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id"), index=True
    )
    title: Mapped[str] = mapped_column(String)
    organization: Mapped[str] = mapped_column(String)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, name="metadata"
    )

    # رابطه با مدل Person
    person: Mapped["Person"] = relationship("Person", back_populates="position_history")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<PositionHistory(id='{self.id}', person_id='{self.person_id}', "
            f"title='{self.title}', organization='{self.organization}')>"
        )

# Note: The `Classification` enum was incomplete in the prompt.
# If it's intended to be used, its definition should be completed.
# For now, I've removed it to avoid incomplete code.