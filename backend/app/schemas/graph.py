"""
Pydantic schemas for the relationship graph (nodes and edges).

این ماژول قراردادهای داده‌ای (data contracts) برای نمودار ارتباطی اشخاص را
تعریف می‌کند. گره‌ها (nodes) معمولاً پروفایل اشخاص یا موجودیت‌های مرتبط (سازمان،
مکان، رویداد) هستند و یال‌ها (edges) روابط میان آن‌ها را نشان می‌دهند.

رنگ‌بندی گره‌ها بر اساس سطح ریسک (RiskLevel) انجام می‌شود — مطابق خواستهٔ
پروژه که میزان خطر هر فرد با رنگ‌های مختلف در چارت/دیاگرام مشخص شود.

این schemaها توسط backend/app/api/routes/graph.py مصرف می‌شوند و خروجی آن‌ها
در frontend توسط React Flow / Cytoscape.js رندر می‌شود؛ بنابراین فیلدها به‌گونه‌ای
طراحی شده‌اند که مستقیماً قابل نگاشت به فرمت آن کتابخانه‌ها باشند.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class RiskLevel(str, Enum):
    """سطح ریسک هر گره — مبنای رنگ‌بندی در نمودار.

    این مقادیر باید با مقادیر مدل RiskAssessment (backend/app/models/risk_assessment.py)
    و موتور ریسک (backend/app/services/risk_engine.py) هماهنگ بمانند.
    دسته‌بندی‌ها مطابق یادداشت پروژه: پاک / مشکوک / نفوذی / استحاله‌یافته.
    """

    CLEAN = "clean"  # پاک
    SUSPECT = "suspect"  # مشکوک
    INFILTRATOR = "infiltrator"  # نفوذی
    TRANSFORMED = "transformed"  # استحاله‌یافته (دچار استحاله شده)
    UNKNOWN = "unknown"  # هنوز ارزیابی نشده

    @property
    def color(self) -> str:
        """رنگ پیشنهادی (hex) متناظر با سطح ریسک برای رندر در نمودار."""
        return _RISK_COLOR_MAP[self]


# نگاشت سطح ریسک به رنگ — کلید واحد برای frontend و backend تا رنگ‌بندی همگام بماند.
_RISK_COLOR_MAP: dict[RiskLevel, str] = {
    RiskLevel.CLEAN: "#16a34a",  # سبز
    RiskLevel.SUSPECT: "#f59e0b",  # کهربایی
    RiskLevel.INFILTRATOR: "#dc2626",  # قرمز
    RiskLevel.TRANSFORMED: "#9333ea",  # بنفش
    RiskLevel.UNKNOWN: "#6b7280",  # خاکستری
}


class NodeType(str, Enum):
    """نوع گره در نمودار ارتباطی."""

    PERSON = "person"  # شخص (مسئول/فرد نفوذی)
    ORGANIZATION = "organization"  # سازمان/نهاد
    POSITION = "position"  # سمت/جایگاه
    LOCATION = "location"  # مکان
    EVENT = "event"  # رویداد
    ARTICLE = "article"  # ورودی دانشنامه مرتبط
    SOURCE = "source"  # منبع اطلاعاتی


class EdgeType(str, Enum):
    """نوع رابطه (یال) میان دو گره."""

    KNOWS = "knows"  # آشنایی
    REPORTS_TO = "reports_to"  # گزارش‌دهی/زیرمجموعه
    MEMBER_OF = "member_of"  # عضویت
    HOLDS_POSITION = "holds_position"  # تصدی سمت فعلی
    HELD_POSITION = "held_position"  # تصدی سمت قبلی
    ASSOCIATED_WITH = "associated_with"  # ارتباط عمومی
    FAMILY = "family"  # خویشاوندی
    FINANCIAL = "financial"  # ارتباط مالی
    LOCATED_AT = "located_at"  # موقعیت مکانی
    REFERENCED_IN = "referenced_in"  # ارجاع‌شده در دانشنامه/منبع
    MENTORED_BY = "mentored_by"  # هدایت/آموزش
    OTHER = "other"  # سایر


class LayoutAlgorithm(str, Enum):
    """الگوریتم چیدمان پیشنهادی برای رندر نمودار در frontend."""

    FORCE = "force"
    HIERARCHICAL = "hierarchical"
    RADIAL = "radial"
    GRID = "grid"
    CONCENTRIC = "concentric"


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------
class NodePosition(BaseModel):
    """مختصات گره در صفحهٔ نمودار (در صورت ذخیرهٔ چیدمان دستی کاربر)."""

    model_config = ConfigDict(extra="forbid")

    x: float = 0.0
    y: float = 0.0


# ---------------------------------------------------------------------------
# Node schemas
# ---------------------------------------------------------------------------
class GraphNodeBase(BaseModel):
    """فیلدهای مشترک یک گره نمودار."""

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        populate_by_name=True,
    )

    label: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="برچسب نمایشی گره (مثلاً نام شخص یا سازمان).",
    )
    type: NodeType = Field(
        default=NodeType.PERSON,
        description="نوع موجودیت گره.",
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.UNKNOWN,
        description="سطح ریسک گره؛ مبنای رنگ‌بندی در نمودار.",
    )
    risk_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="امتیاز عددی ریسک (۰ تا ۱۰۰) در صورت وجود ارزیابی.",
    )
    image_url: Optional[str] = Field(
        default=None,
        max_length=2048,
        description="آدرس عکس/آواتار گره (مثلاً عکس شخص).",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="توضیح کوتاه دربارهٔ گره.",
    )
    position: Optional[NodePosition] = Field(
        default=None,
        description="مختصات چیدمان دستی در صورت وجود.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="فراداده‌های دلخواه (سمت فعلی، سازمان، شهر و ...).",
    )

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("label نمی‌تواند خالی باشد")
        return stripped


class GraphNodeCreate(GraphNodeBase):
    """ورودی ساخت گره جدید (برای افزودن دستی به نمودار)."""

    person_id: Optional[int] = Field(
        default=None,
        description="شناسهٔ پروفایل شخص مرتبط در صورت وجود (FK به Person).",
    )
    entity_id: Optional[int] = Field(
        default=None,
        description="شناسهٔ موجودیت مرتبط (سازمان/مقاله/منبع) در صورت وجود.",
    )


class GraphNodeUpdate(BaseModel):
    """ورودی به‌روزرسانی جزئی یک گره."""

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    label: Optional[str] = Field(default=None, min_length=1, max_length=255)
    type: Optional[NodeType] = None
    risk_level: Optional[RiskLevel] = None
    risk_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    image_url: Optional[str] = Field(default=None, max_length=2048)
    description: Optional[str] = Field(default=None, max_length=2000)
    position: Optional[NodePosition] = None
    metadata: Optional[dict[str, Any]] = None


class GraphNode(GraphNodeBase):
    """گرهٔ کامل با شناسه و فیلدهای مشتق‌شده — خروجی API."""

    id: str = Field(
        ...,
        description="شناسهٔ یکتای گره در نمودار (string برای سازگاری با Cytoscape/React Flow).",
    )
    person_id: Optional[int] = Field(
        default=None,
        description="شناسهٔ پروفایل شخص مرتبط در صورت وجود.",
    )
    entity_id: Optional[int] = Field(
        default=None,
        description="شناسهٔ موجودیت مرتبط در صورت وجود.",
    )
    color: Optional[str] = Field(
        default=None,
        description="رنگ محاسبه‌شده بر اساس risk_level (hex). در صورت None توسط API پر می‌شود.",
    )
    degree: Optional[int] = Field(
        default=None,
        ge=0,
        description="درجهٔ گره (تعداد یال‌های متصل) برای تنظیم اندازه در نمودار.",
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, value: Any) -> str:
        return str(value)

    def with_resolved_color(self) -> "GraphNode":
        """رنگ گره را در صورت خالی‌بودن از روی risk_level استخراج می‌کند."""
        if self.color is None:
            level = self.risk_level
            if not isinstance(level, RiskLevel):
                level = RiskLevel(level)
            self.color = _RISK_COLOR_MAP.get(level, _RISK_COLOR_MAP