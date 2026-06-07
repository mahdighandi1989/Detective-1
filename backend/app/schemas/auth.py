"""
Pydantic schemas for authentication, authorization (RBAC), and user management.

این ماژول schema های مربوط به احراز هویت (login, token, register)، مدیریت کاربر
و کنترل دسترسی نقش‌محور (RBAC) را تعریف می‌کند. سطوح طبقه‌بندی محرمانگی
(classification levels) نیز اینجا تعریف شده‌اند تا با AC پروژه Detective-1
(کنترل دسترسی نقش‌محور و سطوح طبقه‌بندی محرمانگی) همگام باشند.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# --------------------------------------------------------------------------- #
# Enums: Roles & Classification Levels
# --------------------------------------------------------------------------- #
class UserRole(str, Enum):
    """
    نقش‌های کاربری برای RBAC.

    - ADMIN: دسترسی کامل به همه چیز (مدیریت کاربران، حذف، تنظیمات سیستم)
    - ANALYST: تحلیل‌گر — ساخت/ویرایش پروفایل، اجرای agent جستجو، ارزیابی ریسک
    - EDITOR: ویرایشگر دانشنامه — افزودن/ویرایش مقالات دانشنامه
    - VIEWER: فقط مشاهده — دسترسی read-only بر اساس سطح طبقه‌بندی
    """

    ADMIN = "admin"
    ANALYST = "analyst"
    EDITOR = "editor"
    VIEWER = "viewer"


class ClassificationLevel(str, Enum):
    """
    سطوح طبقه‌بندی محرمانگی برای داده‌ها (پروفایل‌ها و مقالات دانشنامه).

    مرتب‌شده از کمترین به بیشترین حساسیت. کاربر فقط به داده‌هایی دسترسی دارد
    که سطح طبقه‌بندی آن‌ها <= سطح دسترسی (clearance) خود کاربر باشد.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"


# ترتیب عددی سطوح برای مقایسهٔ clearance
_CLASSIFICATION_ORDER: dict[ClassificationLevel, int] = {
    ClassificationLevel.PUBLIC: 0,
    ClassificationLevel.INTERNAL: 1,
    ClassificationLevel.CONFIDENTIAL: 2,
    ClassificationLevel.SECRET: 3,
    ClassificationLevel.TOP_SECRET: 4,
}


def classification_rank(level: ClassificationLevel) -> int:
    """رتبهٔ عددی یک سطح طبقه‌بندی را برمی‌گرداند (برای مقایسهٔ دسترسی)."""
    return _CLASSIFICATION_ORDER[level]


def can_access(user_clearance: ClassificationLevel, data_level: ClassificationLevel) -> bool:
    """بررسی می‌کند که آیا کاربری با clearance مشخص می‌تواند به داده‌ای با سطح
    طبقه‌بندی مشخص دسترسی داشته باشد."""
    return classification_rank(user_clearance) >= classification_rank(data_level)


# --------------------------------------------------------------------------- #
# Password validation helper
# --------------------------------------------------------------------------- #
_PASSWORD_MIN_LEN = 8
_PASSWORD_PATTERN_DIGIT = re.compile(r"\d")
_PASSWORD_PATTERN_UPPER = re.compile(r"[A-Z]")
_PASSWORD_PATTERN_LOWER = re.compile(r"[a-z]")


def _validate_password_strength(value: str) -> str:
    """اعتبارسنجی قدرت رمز عبور.

    رمز باید حداقل ۸ کاراکتر و شامل حرف بزرگ، حرف کوچک و عدد باشد.
    """
    if len(value) < _PASSWORD_MIN_LEN:
        raise ValueError(f"رمز عبور باید حداقل {_PASSWORD_MIN_LEN} کاراکتر باشد")
    if not _PASSWORD_PATTERN_UPPER.search(value):
        raise ValueError("رمز عبور باید شامل حداقل یک حرف بزرگ باشد")
    if not _PASSWORD_PATTERN_LOWER.search(value):
        raise ValueError("رمز عبور باید شامل حداقل یک حرف کوچک باشد")
    if not _PASSWORD_PATTERN_DIGIT.search(value):
        raise ValueError("رمز عبور باید شامل حداقل یک عدد باشد")
    return value


# --------------------------------------------------------------------------- #
# Token schemas
# --------------------------------------------------------------------------- #
class Token(BaseModel):
    """پاسخ موفق احراز هویت — شامل access token و refresh token."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: Optional[str] = Field(
        default=None, description="JWT refresh token برای تمدید نشست"
    )
    token_type: str = Field(default="bearer", description="نوع توکن (همیشه bearer)")
    expires_in: Optional[int] = Field(
        default=None, description="مدت اعتبار access token به ثانیه"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 1800,
            }
        }
    )


class TokenPayload(BaseModel):
    """محتوای داخل JWT (claims) — برای decode و validation استفاده می‌شود."""

    sub: Optional[str] = Field(default=None, description="subject (شناسهٔ کاربر)")
    exp: Optional[int] = Field(default=None, description="زمان انقضا (unix timestamp)")
    iat: Optional[int] = Field(default=None, description="زمان صدور (unix timestamp)")
    role: Optional[UserRole] = Field(default=None, description="نقش کاربر")
    clearance: Optional[ClassificationLevel] = Field(
        default=None, description="سطح دسترسی محرمانگی کاربر"
    )
    type: Optional[str] = Field(
        default="access", description="نوع توکن: access یا refresh"
    )


class RefreshTokenRequest(BaseModel):
    """درخواست تمدید توکن با استفاده از refresh token."""

    refresh_token: str = Field(..., description="refresh token معتبر")


# --------------------------------------------------------------------------- #
# Login schemas
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    """درخواست ورود با ایمیل/نام‌کاربری و رمز عبور."""

    username: str = Field(
        ..., min_length=3, max_length=150, description="نام کاربری یا ایمیل"
    )
    password: str = Field(..., min_length=1, max_length=128, description="رمز عبور")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"username": "analyst1", "password": "Str0ngPass"}
        }
    )


# --------------------------------------------------------------------------- #
# User schemas
# --------------------------------------------------------------------------- #
class UserBase(BaseModel):
    """فیلدهای مشترک کاربر."""

    username: str = Field(
        ...,
        min_length=3,
        max_length=150,
        description="نام کاربری یکتا",
    )
    email: EmailStr = Field(..., description="ایمیل کاربر")
    full_name: Optional[str] = Field(
        default=None, max_length=255, description="نام کامل"
    )
    role: UserRole = Field(default=UserRole.VIEWER, description="نقش کاربر در سیستم")
    clearance: ClassificationLevel = Field(
        default=ClassificationLevel.PUBLIC,
        description="بالاترین سطح طبقه‌بندی قابل دسترسی برای کاربر",
    )
    is_active: bool = Field(default=True, description="فعال بودن حساب کاربری")

    @field_validator("username")
    @classmethod
    def _username_no_spaces(cls, value: str) -> str:
        if " " in value:
            raise ValueError("نام کاربری نباید شامل فاصله باشد")
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", value):
            raise ValueError(
                "نام کاربری فقط می‌تواند شامل حروف انگلیسی، اعداد، _ . - باشد"
            )
        return value


class UserCreate(UserBase):
    """schema برای ساخت کاربر جدید (register یا توسط admin)."""

    password: str = Field(..., min_length=_PASSWORD_MIN_LEN, max_length=128)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return _validate_password_strength(value)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "analyst1",
                "email": "analyst1@detective1.local",
                "full_name": "Analyst One",
                "role": "analyst",
                "clearance": "confidential",
                "password": "Str0ngPass",
            }
        }
    )


class UserRegister(BaseModel):
    """schema برای ثبت‌نام عمومی (self-registration).

    در این حالت کاربر نمی‌تواند نقش یا سطح دسترسی خود را تعیین کند؛
    مقادیر پیش‌فرض (viewer / public) اعمال می‌شود.
    """

    username: str = Field(..., min_length=3, max_length=150)
    email: EmailStr = Field(...)
    full_name: Optional[str] = Field(default=None, max_length=255)
    password: str = Field(..., min_length=_PASSWORD_MIN_LEN, max_length=128)

    @field_validator("username")
    @classmethod
    def _username_valid(cls, value: str) -> str:
        if " " in value:
            raise ValueError("نام کاربری نباید شامل فاصله باشد")
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", value):
            raise ValueError(
                "نام کاربری فقط می‌تواند شامل حروف انگلیسی، اعداد، _ . - باشد"
            )
        return value

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class UserUpdate(BaseModel):
    """schema برای به‌روزرسانی کاربر (همهٔ فیلدها اختیاری)."""

    email: Optional[EmailStr] = Field(default=None, description="ایمیل جدید")
    full_name: Optional[str] = Field(default=None, max_length=255)
    role: Optional[UserRole] = Field(default=None, description="نقش جدید کاربر")
    clearance: Optional[ClassificationLevel] = Field(
        default=None, description="سطح دسترسی جدید"
    )
    is_active: Optional[bool] = Field(default=None, description="فعال/غیرفعال بودن حساب")
    password: Optional[str] = Field(
        default=None, min_length=_PASSWORD_MIN_LEN, max_length=128
    )

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_password_strength(value)


class UserOut(UserBase):
    """schema خروجی کاربر (پاسخ API) — بدون رمز عبور."""

    id: int = Field(..., description="شناسهٔ یکتای کاربر")
    created_at: Optional[datetime] = Field(default=None, description="زمان ایجاد حساب")
    updated_at: Optional[datetime] = Field(
        default=None, description="زمان آخرین به‌روزرسانی"
    )

    model_config = ConfigDict(from_attributes=True)


class TokenRefresh(BaseModel):
    """درخواست تمدید توکن با استفاده از refresh token (نام جایگزین معمول)."""

    refresh_token: str = Field(..., description="refresh token معتبر")