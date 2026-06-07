"""Pydantic schemas for Source (منابع اطلاعاتی و اعتبارسنجی).

این فایل schema های ورودی/خروجی API برای موجودیت Source را تعریف می‌کند.
Source نشان‌دهندهٔ یک منبع اطلاعاتی (URL، مقاله، سند، API search result و ...)
است که توسط Agent جستجوگر یا کاربر ثبت می‌شود و دارای امتیاز اعتبار
(credibility score) است.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class SourceType(str, Enum):
    """نوع منبع اطلاعاتی."""

    WEB = "web"  # صفحهٔ وب عمومی
    NEWS = "news"  # خبرگزاری / رسانه
    SOCIAL_MEDIA = "social_media"  # شبکهٔ اجتماعی
    OFFICIAL = "official"  # منبع رسمی / دولتی
    ACADEMIC = "academic"  # منبع آکادمیک / پژوهشی
    LLM_SEARCH = "llm_search"  # نتیجهٔ مدل جستجوگر (Perplexity / Sonar)
    DOCUMENT = "document"  # سند آپلودشده
    MANUAL = "manual"  # ورودی دستی کاربر
    OTHER = "other"


class SourceReliability(str, Enum):
    """طبقه‌بندی کیفی اعتبار منبع (الهام‌گرفته از استاندارد NATO Admiralty)."""

    A_RELIABLE = "A_reliable"  # کاملاً قابل اعتماد
    B_USUALLY_RELIABLE = "B_usually_reliable"  # معمولاً قابل اعتماد
    C_FAIRLY_RELIABLE = "C_fairly_reliable"  # نسبتاً قابل اعتماد
    D_NOT_USUALLY_RELIABLE = "D_not_usually_reliable"  # معمولاً غیرقابل اعتماد
    E_UNRELIABLE = "E_unreliable"  # غیرقابل اعتماد
    F_CANNOT_JUDGE = "F_cannot_judge"  # غیرقابل قضاوت


class SourceStatus(str, Enum):
    """وضعیت چرخهٔ حیات منبع در فرآیند اعتبارسنجی."""

    PENDING = "pending"  # در انتظار بررسی
    VALIDATED = "validated"  # اعتبارسنجی شده
    REJECTED = "rejected"  # رد شده
    ARCHIVED = "archived"  # بایگانی شده


# ---------------------------------------------------------------------------
# Base / shared fields
# ---------------------------------------------------------------------------
class SourceBase(BaseModel):
    """فیلدهای مشترک بین ساخت و نمایش Source."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        use_enum_values=True,
    )

    title: Optional[str] = Field(
        default=None,
        max_length=512,
        description="عنوان منبع",
    )
    url: Optional[AnyUrl] = Field(
        default=None,
        description="آدرس اینترنتی منبع (در صورت آنلاین بودن)",
    )
    source_type: SourceType = Field(
        default=SourceType.WEB,
        description="نوع منبع اطلاعاتی",
    )
    author: Optional[str] = Field(
        default=None,
        max_length=256,
        description="نویسنده یا ناشر منبع",
    )
    published_at: Optional[datetime] = Field(
        default=None,
        description="تاریخ انتشار منبع (در صورت وجود)",
    )
    excerpt: Optional[str] = Field(
        default=None,
        max_length=4000,
        description="گزیده یا چکیدهٔ محتوای منبع",
    )
    raw_content: Optional[str] = Field(
        default=None,
        description="محتوای خام استخراج‌شده از منبع",
    )
    language: Optional[str] = Field(
        default=None,
        max_length=16,
        description="کد زبان منبع (مثلاً fa، en)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="فراداده‌های اضافی (domain، فیلدهای استخراج‌شده و ...)",
    )

    @field_validator("language")
    @classmethod
    def _normalize_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip().lower() or None

    @model_validator(mode="after")
    def _ensure_locatable(self) -> "SourceBase":
        """منبع باید حداقل یا URL یا محتوای خام/عنوان داشته باشد."""
        if self.url is None and not (self.raw_content or self.title or self.excerpt):
            raise ValueError(
                "منبع باید حداقل یکی از url، title، excerpt یا raw_content را داشته باشد."
            )
        return self


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------
class SourceCreate(SourceBase):
    """Schema ورودی برای ساخت یک Source جدید."""

    person_id: Optional[UUID] = Field(
        default=None,
        description="شناسهٔ شخصی که این منبع برای پروفایل او ثبت می‌شود",
    )
    article_id: Optional[UUID] = Field(
        default=None,
        description="شناسهٔ مقالهٔ دانشنامه‌ای مرتبط با این منبع",
    )
    discovered_by_agent: bool = Field(
        default=False,
        description="آیا این منبع توسط Agent جستجوگر خودکار کشف شده است؟",
    )


class SourceUpdate(BaseModel):
    """Schema ورودی برای به‌روزرسانی Source (همهٔ فیلدها اختیاری)."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        use_enum_values=True,
    )

    title: Optional[str] = Field(default=None, max_length=512)
    url: Optional[AnyUrl] = None
    source_type: Optional[SourceType] = None
    author: Optional[str] = Field(default=None, max_length=256)
    published_at: Optional[datetime] = None
    excerpt: Optional[str] = Field(default=None, max_length=4000)
    raw_content: Optional[str] = None
    language: Optional[str] = Field(default=None, max_length=16)
    metadata: Optional[dict[str, Any]] = None
    status: Optional[SourceStatus] = None
    reliability: Optional[SourceReliability] = None

    @field_validator("language")
    @classmethod
    def _normalize_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip().lower() or None


# ---------------------------------------------------------------------------
# Credibility scoring
# ---------------------------------------------------------------------------
class SourceCredibilityScore(BaseModel):
    """نتیجهٔ امتیازدهی اعتبار منبع (source credibility scoring)."""

    model_config = ConfigDict(use_enum_values=True)

    credibility_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="امتیاز عددی اعتبار منبع بین ۰ تا ۱",
    )
    reliability: SourceReliability = Field(
        ...,
        description="طبقه‌بندی کیفی اعتبار منبع",
    )
    rationale: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="دلیل/توضیح امتیاز تخصیص‌یافته",
    )
    factors: dict[str, float] = Field(
        default_factory=dict,
        description="فاکتورهای جزئی امتیازدهی (domain_trust، recency، corroboration و ...)",
    )

    @field_validator("credibility_score")
    @classmethod
    def _round_score(cls, value: float) -> float:
        return round(value, 4)


class SourceValidationRequest(BaseModel):
    """درخواست اعتبارسنجی/امتیازدهی مجدد یک منبع."""

    force_recompute: bool = Field(
        default=False,
        description="در صورت true امتیاز قبلی نادیده گرفته و دوباره محاسبه می‌شود",
    )


# ---------------------------------------------------------------------------
# Output / Read
# ---------------------------------------------------------------------------
class SourceRead(SourceBase):
    """Schema خروجی کامل یک Source."""

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )

    id: UUID
    person_id: Optional[UUID] = None
    article_id: Optional[UUID] = None
    status: SourceStatus = SourceStatus.PENDING
    reliability: SourceReliability = SourceReliability.F_CANNOT_JUDGE
    credibility_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="امتیاز اعتبار منبع (در صورت محاسبه‌شدن)",
    )
    credibility_factors: dict[str, float] = Field(default_factory=dict)
    discovered_by_agent: bool = False
    created_by: Optional[UUID] = Field(
        default=None,
        description="شناسهٔ کاربری که منبع را ثبت کرده است",
    )
    created_at: datetime
    updated_at: datetime
    validated_at: Optional[datetime] = None


class SourceSummary(BaseModel):
    """نمایش خلاصه از Source برای لیست‌ها و reference های inline."""

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )

    id: UUID
    title: Optional[str] = None
    url: Optional[AnyUrl] = None
    source_type: SourceType
    reliability: SourceReliability
    credibility_score: Optional[float] = None
    status: SourceStatus


class SourceListResponse(BaseModel):
    """پاسخ صفحه‌بندی‌شدهٔ لیست منابع."""

    items: list[SourceRead]
    total: int = Field(..., ge=0, description="تعداد کل منابع منطبق با فیلتر")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


__all__ = [
    "SourceType",
    "SourceReliability",
    "SourceStatus",
    "SourceBase",
    "SourceCreate",
    "SourceUpdate",
    "SourceCredibilityScore",
    "SourceValidationRequest",
    "SourceRead",
    "SourceSummary",
    "SourceListResponse",
    "SourceCredibilityResult",
    "SourceInDB",
]


# ---------------------------------------------------------------------------
# Cross-module compatible aliases (used by app.api.routes.sources).
# ---------------------------------------------------------------------------
SourceCredibilityResult = SourceCredibilityScore
SourceInDB = SourceRead