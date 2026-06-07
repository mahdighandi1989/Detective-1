"""
backend/app/models/source.py

مدل Source — نمایندهٔ یک منبع اطلاعاتی (URL، سند، خبرگزاری، شبکهٔ اجتماعی و …)
که داده‌های مرتبط با پروفایل اشخاص یا ورودی‌های دانشنامه از آن استخراج شده است.

این مدل شامل امتیاز اعتبارسنجی منبع (source credibility scoring) است که توسط
موتور OSINT/LLM محاسبه می‌شود و در ارزیابی ریسک (risk_engine) به‌عنوان وزن شواهد
استفاده می‌شود.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    Column,  # برای تعریف جداول ارتباطی (association tables)
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Table,  # برای تعریف جداول ارتباطی (association tables)
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    # الگوی رایج این پروژه: Base مشترک در app.db.base یا app.models.base
    from app.db.base_class import Base  # type: ignore
except Exception:  # pragma: no cover - fallback برای ساختارهای جایگزین
    try:
        from app.models.base import Base  # type: ignore
    except Exception:
        from sqlalchemy.orm import DeclarativeBase

        class Base(DeclarativeBase):  # type: ignore
            """Fallback declarative base در صورت نبودن Base مشترک."""

            pass


if TYPE_CHECKING:
    # برای جلوگیری از circular import؛ این مدل‌ها در سایر فایل‌ها تعریف شده‌اند.
    from app.models.person import Person  # noqa: F401
    from app.models.article import Article  # noqa: F401


class SourceType(str, enum.Enum):
    """نوع منبع اطلاعاتی."""

    NEWS = "news"               # خبرگزاری / سایت خبری
    OFFICIAL = "official"       # سایت رسمی / دولتی / سازمانی
    SOCIAL_MEDIA = "social_media"  # شبکهٔ اجتماعی (توییتر، اینستاگرام، تلگرام و ...)
    BLOG = "blog"              # وبلاگ / یادداشت شخصی
    FORUM = "forum"            # انجمن / تالار گفتگو
    ACADEMIC = "academic"      # مقاله / منبع آکادمیک (ژورنال، کنفرانس)
    LEAK = "leak"              # داده‌های افشاشده / leak
    DATABASE = "database"      # پایگاه دادهٔ عمومی / Open Data
    REPORT = "report"          # گزارش تحلیلی / پژوهشی / سازمان‌های غیردولتی
    ARCHIVE = "archive"        # آرشیو اینترنت (Wayback Machine) / اسناد تاریخی
    OTHER = "other"            # سایر موارد نامشخص یا خاص


# جداول ارتباطی برای روابط چند به چند (Many-to-Many)
# این جداول به صورت مستقیم در دیتابیس ایجاد می‌شوند و فقط شامل کلیدهای خارجی هستند.
# فرض بر این است که `Base.metadata` در `Base` تعریف شده است.
article_source_association = Table(
    "article_source_association",
    Base.metadata,
    Column("article_id", UUID(as_uuid=True), ForeignKey("article.id", ondelete="CASCADE"), primary_key=True),
    Column("source_id", UUID(as_uuid=True), ForeignKey("source.id", ondelete="CASCADE"), primary_key=True),
    # افزودن ایندکس برای جستجوهای کارآمد
    Index("ix_article_source_article_id", "article_id"),
    Index("ix_article_source_source_id", "source_id"),
    UniqueConstraint("article_id", "source_id", name="uq_article_source"),
)

person_source_association = Table(
    "person_source_association",
    Base.metadata,
    Column("person_id", UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE"), primary_key=True),
    Column("source_id", UUID(as_uuid=True), ForeignKey("source.id", ondelete="CASCADE"), primary_key=True),
    # افزودن ایندکس برای جستجوهای کارآمد
    Index("ix_person_source_person_id", "person_id"),
    Index("ix_person_source_source_id", "source_id"),
    UniqueConstraint("person_id", "source_id", name="uq_person_source"),
)


class Source(Base):
    """
    مدل SQLAlchemy برای نگهداری اطلاعات منابع داده.

    این منابع می‌توانند شامل URLها، اسناد، خبرگزاری‌ها، شبکه‌های اجتماعی و غیره باشند.
    هر منبع دارای یک امتیاز اعتبارسنجی (credibility_score) است که میزان قابل اعتماد بودن
    خود منبع را نشان می‌دهد و یک امتیاز قابلیت اطمینان (reliability_score) که مربوط به
    داده‌های استخراج شده از آن منبع در یک مورد خاص است.
    """

    __tablename__ = "source"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(
        String(255), index=True, nullable=False, comment="نام منبع (مثلاً 'BBC News', 'Twitter')"
    )
    url: Mapped[str] = mapped_column(
        Text, unique=True, index=True, nullable=False, comment="آدرس URL دقیق منبع"
    )
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType),
        nullable=False,
        default=SourceType.OTHER,
        comment="نوع منبع اطلاعاتی",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="توضیحات کوتاه درباره منبع"
    )
    credibility_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
        comment="امتیاز اعتبارسنجی کلی منبع (۰.۰ تا ۱.۰)، توسط موتور OSINT/LLM محاسبه می‌شود.",
    )
    reliability_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
        comment="امتیاز قابلیت اطمینان داده‌های استخراج شده از این منبع برای یک مورد خاص (۰.۰ تا ۱.۰).",
    )
    last_accessed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="آخرین باری که منبع بررسی یا دسترسی شده است",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="آیا این منبع هنوز فعال و قابل استفاده است",
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="متادیتای اضافی و ساختارنیافته مربوط به منبع (مثلاً پارامترهای API، تنظیمات scraping)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )

    # Relationships
    # یک منبع می‌تواند به چندین مقاله (Article) مرتبط باشد.
    articles: Mapped[List["Article"]] = relationship(
        secondary=article_source_association,
        back_populates="sources",
        lazy="selectin",  # بارگذاری بهینه برای روابط چند به چند
    )

    # یک منبع می‌تواند به چندین شخص (Person) مرتبط باشد.
    persons: Mapped[List["Person"]] = relationship(
        secondary=person_source_association,
        back_populates="sources",
        lazy="selectin",  # بارگذاری بهینه برای روابط چند به چند
    )

    def __repr__(self) -> str:
        return f"<Source(id='{self.id}', name='{self.name}', type='{self.source_type.value}')>"