"""
backend/app/core/security.py

ماژول امنیتی Detective-1:
- هش و راستی‌آزمایی رمز عبور (passlib + bcrypt)
- تولید و اعتبارسنجی توکن‌های JWT (access + refresh)
- وابستگی‌های FastAPI برای احراز هویت کاربر فعلی
- کنترل دسترسی نقش‌محور (RBAC) و سطوح طبقه‌بندی محرمانگی

این ماژول به app.core.config.settings متکی است (upstream).
downstream: api/routes/auth.py، api/routes/persons.py و سایر route هایی
که نیاز به احراز هویت/RBAC دارند، توابع این فایل را مصرف می‌کنند.

نکتهٔ امنیتی مهم:
    import تنظیمات به‌صورت fail-fast انجام می‌شود. هیچ fallback ناامنی
    (مانند SECRET_KEY پیش‌فرض قابل‌حدس) وجود ندارد. اگر بارگذاری config
    شکست بخورد یا SECRET_KEY ناامن/خالی باشد، اپ هنگام راه‌اندازی با خطای
    صریح متوقف می‌شود تا هرگز توکن JWT با کلید قابل‌حدس صادر نشود.
"""

from __future__ import annotations

import enum
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Union

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, ValidationError

# ---------------------------------------------------------------------------
# بارگذاری تنظیمات (fail-fast) — بدون هیچ fallback ناامن
# ---------------------------------------------------------------------------
#
# دلیل امنیتی: نسخهٔ قبلی از try/except با یک _FallbackSettings استفاده می‌کرد
# که SECRET_KEY='CHANGE_ME_INSECURE_DEFAULT_SECRET_KEY' را تنظیم می‌کرد.
# اگر import تنظیمات به هر دلیلی شکست می‌خورد، اپ بی‌سروصدا با کلید
# قابل‌حدس JWT صادر می‌کرد. این یک آسیب‌پذیری جدی است.
#
# به‌جای آن، settings را مستقیم import می‌کنیم. اگر import شکست بخورد،
# خطا منتشر می‌شود و اپ بالا نمی‌آید (fail-fast).
from app.core.config import settings


# مقادیر ناامن شناخته‌شده که هرگز نباید به‌عنوان SECRET_KEY واقعی استفاده شوند.
_INSECURE_SECRET_KEYS = frozenset(
    {
        "",
        "CHANGE_ME_INSECURE_DEFAULT_SECRET_KEY",
        "changeme",
        "change_me",
        "secret",
        "secret_key",
        "your-secret-key",
        "your_secret_key",
        "dev",
        "development",
        "test",
        "insecure",
        "default",
    }
)

# حداقل طول قابل‌قبول برای کلید (برای HS256 توصیه می‌شود >= 32 بایت).
_MIN_SECRET_KEY_LENGTH = 32


def _validate_secret_key() -> None:
    """
    اعتبارسنجی fail-fast برای SECRET_KEY هنگام import ماژول.

    تضمین می‌کند:
    - SECRET_KEY وجود دارد و رشته است.
    - SECRET_KEY یکی از مقادیر ناامن شناخته‌شده نیست.
    - SECRET_KEY به‌اندازهٔ کافی طولانی است.

    در صورت نقض هر شرط، RuntimeError منتشر می‌شود و اپ بالا نمی‌آید.
    """
    secret_key = getattr(settings, "SECRET_KEY", None)

    # settings.SECRET_KEY is a pydantic SecretStr; unwrap it to the raw string
    # before validating (SecretStr is NOT a str subclass, so a bare isinstance
    # check would wrongly report a configured key as "not set").
    if secret_key is not None and hasattr(secret_key, "get_secret_value"):
        secret_key = secret_key.get_secret_value()

    if secret_key is None or not isinstance(secret_key, str):
        raise RuntimeError(
            "پیکربندی امنیتی نامعتبر: SECRET_KEY تنظیم نشده است. "
            "متغیر محیطی SECRET_KEY را با یک کلید تصادفی امن مقداردهی کنید "
            "(مثلاً خروجی `openssl rand -hex 32`)."
        )

    normalized = secret_key.strip()

    if normalized.lower() in _INSECURE_SECRET_KEYS or normalized in _INSECURE_SECRET_KEYS:
        raise RuntimeError(
            "پیکربندی امنیتی نامعتبر: SECRET_KEY روی یک مقدار پیش‌فرض/ناامن "
            "تنظیم شده است. هرگز از کلید قابل‌حدس استفاده نکنید. "
            "یک کلید تصادفی امن تولید کنید "
            "(مثلاً `openssl rand -hex 32`)."
        )

    if len(normalized) < _MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(
            "پیکربندی امنیتی نامعتبر: SECRET_KEY بسیار کوتاه است "
            f"(حداقل {_MIN_SECRET_KEY_LENGTH} کاراکتر لازم است، "
            f"دریافت‌شده: {len(normalized)}). "
            "یک کلید تصادفی امن تولید کنید (مثلاً `openssl rand -hex 32`)."
        )


# اجرای اعتبارسنجی در زمان import تا اپ هرگز با کلید ناامن بالا نیاید.
_validate_secret_key()


# ---------------------------------------------------------------------------
# مقادیر پیکربندی استخراج‌شده از settings (با پیش‌فرض‌های امنِ غیرحساس)
# ---------------------------------------------------------------------------

SECRET_KEY: str = (
    settings.SECRET_KEY.get_secret_value()
    if hasattr(settings.SECRET_KEY, "get_secret_value")
    else str(settings.SECRET_KEY)
)
ALGORITHM: str = getattr(settings, "ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
    getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)
)
REFRESH_TOKEN_EXPIRE_MINUTES: int = int(
    getattr(settings, "REFRESH_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7)
)
API_V1_STR: str = getattr(settings, "API_V1_STR", "/api/v1")


# ---------------------------------------------------------------------------
# نقش‌ها و سطوح طبقه‌بندی محرمانگی (RBAC)
# ---------------------------------------------------------------------------


class Role(str, enum.Enum):
    """نقش‌های کاربری برای کنترل دسترسی نقش‌محور."""

    ADMIN = "admin"
    ANALYST = "analyst"
    OPERATOR = "operator"
    VIEWER = "viewer"


class ClassificationLevel(str, enum.Enum):
    """سطوح طبقه‌بندی محرمانگی برای محتوا و پروفایل‌ها."""

    UNCLASSIFIED = "unclassified"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"


# ترتیب سطوح برای مقایسهٔ دسترسی (هرچه عدد بزرگ‌تر، محرمانه‌تر).
_CLASSIFICATION_ORDER = {
    ClassificationLevel.UNCLASSIFIED: 0,
    ClassificationLevel.CONFIDENTIAL: 1,
    ClassificationLevel.SECRET: 2,
    ClassificationLevel.TOP_SECRET: 3,
}


# ---------------------------------------------------------------------------
# مدل‌های Pydantic برای محتوای توکن
# ---------------------------------------------------------------------------


class TokenType(str, enum.Enum):
    """نوع توکن JWT."""

    ACCESS = "access"
    REFRESH = "refresh"


class TokenPayload(BaseModel):
    """ساختار payload رمزگشایی‌شدهٔ توکن JWT."""

    sub: str = Field(..., description="شناسهٔ موضوع (معمولاً ایمیل/شناسهٔ کاربر)")
    exp: int = Field(..., description="زمان انقضا (epoch seconds)")
    iat: Optional[int] = Field(default=None, description="زمان صدور (epoch seconds)")
    type: TokenType = Field(default=TokenType.ACCESS, description="نوع توکن")
    role: Optional[Role] = Field(default=None, description="نقش کاربر")
    clearance: Optional[ClassificationLevel] = Field(
        default=None, description="سطح دسترسی محرمانگی کاربر"
    )


class Token(BaseModel):
    """پاسخ بازگشتی هنگام صدور توکن."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# پیکربندی هش رمز عبور
# ---------------------------------------------------------------------------

_bcrypt_cost = int(getattr(settings, "BCRYPT_COST", 12))

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=_bcrypt_cost,
)


def hash_password(password: str) -> str:
    """هش امن رمز عبور با bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """راستی‌آزمایی رمز عبور خام در برابر هش ذخیره‌شده."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        # هش نامعتبر/خراب → عدم احراز هویت (بدون نشت اطلاعات)
        return False


def needs_rehash(hashed_password: str) -> bool:
    """تشخیص اینکه آیا هش با پارامترهای فعلی نیاز به rehash دارد."""
    try:
        return pwd_context.needs_update(hashed_password)
    except (ValueError, TypeError):
        return True


# ---------------------------------------------------------------------------
# تولید و اعتبارسنجی توکن JWT
# ---------------------------------------------------------------------------


def _create_token(
    subject: Union[str, Any],
    token_type: TokenType,
    expires_delta: timedelta,
    *,
    role: Optional[Role] = None,
    clearance: Optional[ClassificationLevel] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """تابع داخلی برای ساخت یک توکن JWT امضاشده."""
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": token_type.value,
    }
    if role is not None:
        payload["role"] = role.value if isinstance(role, enum.Enum) else str(role)
    if clearance is not None:
        payload["clearance"] = (
            clearance.value if isinstance(clearance, enum.Enum) else str(clearance)
        )
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(
    subject: Union[str, Any],
    *,
    role: Optional[Role] = None,
    clearance: Optional[ClassificationLevel] = None,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """ساخت توکن دسترسی (access) امضاشده."""
    delta = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(
        subject,
        TokenType.ACCESS,
        delta,
        role=role,
        clearance=clearance,
        extra_claims=extra_claims,
    )


def create_refresh_token(
    subject: Union[str, Any],
    *,
    role: Optional[Role] = None,
    clearance: Optional[ClassificationLevel] = None,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """ساخت توکن تازه‌سازی (refresh) امضاشده."""
    delta = expires_delta or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    return _create_token(
        subject,
        TokenType.REFRESH,
        delta,
        role=role,
        clearance=clearance,
        extra_claims=extra_claims,
    )


def decode_token(token: str) -> TokenPayload:
    """رمزگشایی و اعتبارسنجی توکن JWT و بازگرداندن payload نوع‌دار.

    در صورت نامعتبر یا منقضی‌بودن توکن، HTTPException(401) منتشر می‌شود.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="اعتبارسنجی توکن ناموفق بود",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        raw = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise credentials_exc from exc
    try:
        return TokenPayload(**raw)
    except ValidationError as exc:
        raise credentials_exc from exc


# ---------------------------------------------------------------------------
# وابستگی‌های احراز هویت / RBAC (re-export)
#
# پیاده‌سازی مرجع این‌ها در app.api.deps است تا منطق احراز هویت واحد بماند.
# چون بخشی از route ها (auth.py، persons.py، ...) این نام‌ها را از
# app.core.security وارد می‌کنند، آن‌ها را اینجا re-export می‌کنیم. توجه:
# app.api.deps ماژول app.core.security را import نمی‌کند، بنابراین این کار
# حلقهٔ import ایجاد نمی‌کند.
# ---------------------------------------------------------------------------
from app.api.deps import (  # noqa: E402
    get_current_active_user,
    get_current_user,
    require_roles,
)