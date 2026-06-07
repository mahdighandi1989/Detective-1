# backend/app/core/rbac.py
"""
RBAC (Role-Based Access Control) for Detective-1.

این ماژول نقش‌ها، سطوح طبقه‌بندی محرمانگی (classification levels) و
منطق بررسی دسترسی را تعریف می‌کند. به‌عنوان لایهٔ امنیتی اصلی برای
کنترل دسترسی به دانشنامهٔ اطلاعاتی، پروفایل اشخاص و نمودار ارتباطی
استفاده می‌شود.

Upstream:
    - app/core/security.py  (get_current_active_user -> current user)
    - app/core/config.py    (settings)

Downstream:
    - app/api/routes/*      (Depends(require_role(...)), Depends(require_clearance(...)))

نکتهٔ همگام‌سازی فیلد:
    نام canonical فیلد سطح محرمانگی روی مدل/اسکیمای کاربر «clearance_level»
    است. برای سازگاری عقب‌رو، تابع کمکی _get_clearance هر دو نام
    «clearance_level» و «clearance» را می‌خواند.
"""

from __future__ import annotations

from enum import IntEnum
from functools import lru_cache
from typing import Any, Iterable

from fastapi import Depends, HTTPException, status

from app.core.security import get_current_active_user


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
class Role(str):
    """نقش‌های سیستمی Detective-1 (string-based برای سازگاری با DB enum)."""

    VIEWER = "viewer"          # فقط مشاهده محتوای مجاز
    ANALYST = "analyst"        # تحلیل‌گر: ایجاد/ویرایش پروفایل و مقاله
    EDITOR = "editor"          # ویراستار دانشنامه و تأیید محتوا
    ADMIN = "admin"            # مدیریت کامل سیستم و کاربران
    SUPERADMIN = "superadmin"  # دسترسی نامحدود


# سلسله‌مراتب نقش‌ها: هر نقش، نقش‌های پایین‌تر را پوشش می‌دهد.
ROLE_HIERARCHY: dict[str, int] = {
    Role.VIEWER: 10,
    Role.ANALYST: 20,
    Role.EDITOR: 30,
    Role.ADMIN: 40,
    Role.SUPERADMIN: 50,
}

VALID_ROLES: frozenset[str] = frozenset(ROLE_HIERARCHY.keys())


# ---------------------------------------------------------------------------
# Classification / Clearance levels
# ---------------------------------------------------------------------------
class ClearanceLevel(IntEnum):
    """سطوح طبقه‌بندی محرمانگی (هرچه بزرگ‌تر، محرمانه‌تر)."""

    PUBLIC = 0          # عمومی
    RESTRICTED = 1      # محدود
    CONFIDENTIAL = 2    # محرمانه
    SECRET = 3          # سری
    TOP_SECRET = 4      # فوق سری


CLEARANCE_LABELS: dict[int, str] = {
    ClearanceLevel.PUBLIC: "public",
    ClearanceLevel.RESTRICTED: "restricted",
    ClearanceLevel.CONFIDENTIAL: "confidential",
    ClearanceLevel.SECRET: "secret",
    ClearanceLevel.TOP_SECRET: "top_secret",
}

_LABEL_TO_LEVEL: dict[str, int] = {v: k for k, v in CLEARANCE_LABELS.items()}


def normalize_clearance(value: Any) -> int:
    """
    یک مقدار clearance (int، str عددی، یا label) را به int نرمال می‌کند.

    >>> normalize_clearance("secret")
    3
    >>> normalize_clearance(2)
    2
    >>> normalize_clearance(None)
    0
    """
    if value is None:
        return int(ClearanceLevel.PUBLIC)
    if isinstance(value, ClearanceLevel):
        return int(value)
    if isinstance(value, bool):  # bool زیرکلاس int است؛ صریحاً رد شود
        return int(ClearanceLevel.PUBLIC)
    if isinstance(value, int):
        return _clamp_level(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s.isdigit():
            return _clamp_level(int(s))
        if s in _LABEL_TO_LEVEL:
            return _LABEL_TO_LEVEL[s]
    raise ValueError(f"Invalid clearance value: {value!r}")


def _clamp_level(level: int) -> int:
    lo = int(ClearanceLevel.PUBLIC)
    hi = int(ClearanceLevel.TOP_SECRET)
    return max(lo, min(hi, level))


# ---------------------------------------------------------------------------
# User attribute extraction helpers
# ---------------------------------------------------------------------------
def _get_role(user: Any) -> str:
    """نقش کاربر را استخراج می‌کند (object attr یا dict key)."""
    role = _read_attr(user, "role")
    if role is None:
        return Role.VIEWER
    if hasattr(role, "value"):  # Enum
        role = role.value
    role = str(role).strip().lower()
    return role if role in VALID_ROLES else Role.VIEWER


def _get_clearance(user: Any) -> int:
    """
    سطح محرمانگی کاربر را استخراج می‌کند.

    برای همگام‌سازی، هر دو نام فیلد «clearance_level» (canonical) و
    «clearance» (legacy) پشتیبانی می‌شوند.
    """
    raw = _read_attr(user, "clearance_level")
    if raw is None:
        raw = _read_attr(user, "clearance")
    try:
        return normalize_clearance(raw)
    except ValueError:
        return int(ClearanceLevel.PUBLIC)


def _read_attr(obj: Any, name: str) -> Any:
    """خواندن یک مقدار از object attribute یا dict key."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _is_superuser(user: Any) -> bool:
    flag = _read_attr(user, "is_superuser")
    if flag:
        return True
    return _get_role(user) == Role.SUPERADMIN


# ---------------------------------------------------------------------------
# Core permission checks
# ---------------------------------------------------------------------------
def role_rank(role: str) -> int:
    """رتبهٔ عددی یک نقش را برمی‌گرداند (نقش ناشناخته = 0)."""
    return ROLE_HIERARCHY.get(role, 0)


def has_role(user: Any, required: str) -> bool:
    """
    آیا کاربر نقش `required` یا بالاتر را دارد؟
    superuser همیشه True است.
    """
    if _is_superuser(user):
        return True
    return role_rank(_get_role(user)) >= role_rank(required)


def has_any_role(user: Any, roles: Iterable[str]) -> bool:
    """آیا کاربر حداقل یکی از نقش‌های داده‌شده (یا بالاتر) را دارد؟"""
    if _is_superuser(user):
        return True
    user_rank = role_rank(_get_role(user))
    return any(user_rank >= role_rank(r) for r in roles)


def has_clearance(user: Any, required: Any) -> bool:
    """
    آیا سطح محرمانگی کاربر >= سطح موردنیاز است؟
    superuser همیشه True است.
    """
    if _is_superuser(user):
        return True
    required_level = normalize_clearance(required)
    return _get_clearance(user) >= required_level


# ---------------------------------------------------------------------------
# FastAPI dependency factories
# ---------------------------------------------------------------------------
def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


@lru_cache(maxsize=None)
def require_role(required_role: str):
    """
    Dependency factory: مطمئن می‌شود کاربر نقش `required_role` یا بالاتر دارد.

    استفاده:
        @router.get("/admin", dependencies=[Depends(require_role(Role.ADMIN))])
    یا:
        async def handler(user = Depends(require_role(Role.EDITOR))):
            ...
    """
    if required_role not in VALID_ROLES:
        raise ValueError(f"Unknown role: {required_role!r}")

    async def _dependency(current_user: Any = Depends(get_current_active_user)) -> Any:
        if not has_role(current_user, required_role):
            raise _forbidden(
                f"Insufficient role. Required: '{required_role}' or higher."
            )
        return current_user

    return _dependency


def require_any_role(*roles: str):
    """
    Dependency factory: کاربر باید حداقل یکی از نقش‌های داده‌شده را داشته باشد.
    """
    role_tuple = tuple(roles)
    for r in role_tuple:
        if r not in VALID_ROLES:
            raise ValueError(f"Unknown role: {r!r}")

    async def _dependency(current_user: Any = Depends(get_current_active_user)) -> Any:
        if not has_any_role(current_user, role_tuple):
            raise _forbidden(
                "Insufficient role. Required one of: "
                + ", ".join(f"'{r}'" for r in role_tuple)
            )
        return current_user

    return _dependency


def require_clearance(required: Any):
    """
    Dependency factory: مطمئن می‌شود کاربر سطح محرمانگی کافی دارد.

    استفاده:
        @router.get(
            "/secret",
            dependencies=[Depends(require_clearance(ClearanceLevel.SECRET))],
        )
    """
    required_level = normalize_clearance(required)

    async def _dependency(current_user: Any = Depends(get_current_active_user)) -> Any:
        if not has_clearance(current_user, required_level):
            label = CLEARANCE_LABELS.get(required_level, str(required_level))
            raise _forbidden(
                f"Insufficient clearance. Required level: '{label}' ({required_level})."
            )
        return current_user

    return _dependency


def require_superuser():
    """Dependency factory: فقط superuser/superadmin مجاز است."""

    async def _dependency(current_user: Any = Depends(get_current_active_user)) -> Any:
        if not _is_superuser(current_user):
            raise _forbidden("Superuser privileges required.")
        return current_user

    return _dependency


__all__ = [
    "Role",
    "ClearanceLevel",
    "ROLE_HIERARCHY",
    "VALID_ROLES",
    "CLEARANCE_LABELS",
    "normalize_clearance",
    "role_rank",
    "has_role",
    "has_any_role",
    "has_clearance",
    "require_role",
    "require_any_role",
    "require_clearance",
    "require_superuser",
]