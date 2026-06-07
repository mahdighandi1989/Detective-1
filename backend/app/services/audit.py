"""
Audit Log Service for Detective-1

این سرویس مسئول ثبت و بازیابی تاریخچهٔ تغییرات (audit log) برای
پروفایل‌های اشخاص، ورودی‌های دانشنامه، ارزیابی‌های ریسک و سایر
موجودیت‌های سیستم است.

هر رخداد قابل ممیزی (audit event) شامل: کاربر انجام‌دهنده، نوع عمل،
موجودیت هدف، مقادیر قبل/بعد، آدرس IP، و timestamp است.

⚠️ نکتهٔ معماری (رفع باگ تداخل metadata):
این سرویس **مدل SQLAlchemy را تعریف نمی‌کند**. مدل `AuditLog` و enumهای
مرتبط به‌طور انحصاری در `app.models.audit_log` تعریف شده‌اند. تعریف مجدد
مدل در این سرویس باعث ثبت دو جدول/مدل با همان نام روی `Base.metadata` و
خطای mapper می‌شد؛ بنابراین در اینجا فقط import و استفاده می‌شوند.

این سرویس به‌صورت defensive نوشته شده تا ثبت لاگ هرگز جریان اصلی
برنامه را نشکند.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Import مدل و enumها از منبع واحد حقیقت (single source of truth).
# مدل نباید اینجا دوباره تعریف شود — رجوع به docstring بالا.
# ---------------------------------------------------------------------------
from app.models.audit_log import AuditAction, AuditEntityType, AuditLog

logger = logging.getLogger("detective1.audit")


__all__ = [
    "AuditAction",
    "AuditEntityType",
    "AuditLog",
    "AuditService",
    "record_audit_event",
    "list_audit_events",
    "count_audit_events",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _coerce_action(action: "AuditAction | str") -> AuditAction:
    """تبدیل ورودی به AuditAction به‌صورت امن."""
    if isinstance(action, AuditAction):
        return action
    try:
        return AuditAction(str(action))
    except Exception:
        # fallback امن: اگر enum مقدار OTHER را نداشت، اولین مقدار را برگردان
        try:
            return AuditAction.OTHER  # type: ignore[attr-defined]
        except Exception:
            return list(AuditAction)[0]


def _coerce_entity_type(
    entity_type: "AuditEntityType | str | None",
) -> Optional[AuditEntityType]:
    """تبدیل ورودی به AuditEntityType به‌صورت امن."""
    if entity_type is None:
        return None
    if isinstance(entity_type, AuditEntityType):
        return entity_type
    try:
        return AuditEntityType(str(entity_type))
    except Exception:
        try:
            return AuditEntityType.OTHER  # type: ignore[attr-defined]
        except Exception:
            return None


def _safe_serialize(value: Any) -> Optional[dict[str, Any]]:
    """
    تبدیل مقدار به یک dict قابل ذخیره (JSON-safe).

    اگر مقدار None باشد None برمی‌گرداند. اگر مقدار dict باشد، تلاش می‌کند
    آن را JSON-serializable کند. در صورت خطا، یک نمایش رشته‌ای امن می‌سازد.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        try:
            # round-trip برای اطمینان از JSON-safe بودن
            return json.loads(json.dumps(value, default=str, ensure_ascii=False))
        except Exception:
            return {"_repr": str(value)}
    # مقادیر غیر-dict را در یک wrapper قرار می‌دهیم
    try:
        return {"value": json.loads(json.dumps(value, default=str, ensure_ascii=False))}
    except Exception:
        return {"_repr": str(value)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Core functions (functional API)
# ---------------------------------------------------------------------------
async def record_audit_event(
    db: AsyncSession,
    *,
    action: "AuditAction | str",
    actor_id: Optional[int] = None,
    actor_username: Optional[str] = None,
    entity_type: "AuditEntityType | str | None" = None,
    entity_id: Optional[str] = None,
    before: Any = None,
    after: Any = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    commit: bool = True,
) -> Optional[AuditLog]:
    """
    ثبت یک رخداد قابل ممیزی.

    این تابع به‌صورت defensive نوشته شده: اگر ثبت لاگ به هر دلیلی شکست
    بخورد، استثنا را log می‌کند ولی جریان اصلی برنامه را نمی‌شکند
    (None برمی‌گرداند).
    """
    try:
        entry = AuditLog(
            action=_coerce_action(action),
            actor_id=actor_id,
            actor_username=actor_username,
            entity_type=_coerce_entity_type(entity_type),
            entity_id=str(entity_id) if entity_id is not None else None,
            before=_safe_serialize(before),
            after=_safe_serialize(after),
            ip_address=ip_address,
            user_agent=user_agent,
            description=description,
            extra_metadata=_safe_serialize(metadata),
            created_at=_now(),
        )
        db.add(entry)
        if commit:
            await db.commit()
            await db.refresh(entry)
        else:
            await db.flush()
        return entry
    except Exception as exc:  # noqa: BLE001 - audit must never break main flow
        logger.exception("Failed to record audit event: %s", exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to rollback after audit failure")
        return None


async def list_audit_events(
    db: AsyncSession,
    *,
    entity_type: "AuditEntityType | str | None" = None,
    entity_id: Optional[str] = None,
    actor_id: Optional[int] = None,
    action: "AuditAction | str | None" = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[AuditLog]:
    """
    بازیابی لیست رخدادهای audit با فیلترهای اختیاری.

    نتایج بر اساس زمان ایجاد به‌صورت نزولی (جدیدترین اول) مرتب می‌شوند.
    """
    stmt = select(AuditLog)

    coerced_entity = _coerce_entity_type(entity_type)
    if coerced_entity is not None:
        stmt = stmt.where(AuditLog.entity_type == coerced_entity)

    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == str(entity_id))

    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)

    if action is not None:
        stmt = stmt.where(AuditLog.action == _coerce_action(action))

    stmt = stmt.order_by(desc(AuditLog.created_at))

    # نرمال‌سازی limit/offset
    safe_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, int(offset))
    stmt = stmt.limit(safe_limit).offset(safe_offset)

    result = await db.execute(stmt)
    return result.scalars().all()


async def count_audit_events(
    db: AsyncSession,
    *,
    entity_type: "AuditEntityType | str | None" = None,
    entity_id: Optional[str] = None,
    actor_id: Optional[int] = None,
    action: "AuditAction | str | None" = None,
) -> int:
    """شمارش تعداد رخدادهای audit مطابق با فیلترهای داده‌شده."""
    stmt = select(func.count()).select_from(AuditLog)

    coerced_entity = _coerce_entity_type(entity_type)
    if coerced_entity is not None:
        stmt = stmt.where(AuditLog.entity_type == coerced_entity)

    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == str(entity_id))

    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)

    if action is not None:
        stmt = stmt.where(AuditLog.action == _coerce_action(action))

    result = await db.execute(stmt)
    return int(result.scalar_one_or_none() or 0)


# ---------------------------------------------------------------------------
# Class-based API (برای سازگاری با callerهایی که AuditService می‌خواهند)
# ---------------------------------------------------------------------------
class AuditService:
    """
    Wrapper شیء-گرا روی توابع audit.

    یک AsyncSession را نگه می‌دارد و متدهای راحت برای ثبت و بازیابی
    رخدادهای audit ارائه می‌دهد. تمام منطق واقعی به توابع ماژول‌سطح
    delegate می‌شود تا duplication نداشته باشیم.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(
        self,
        *,
        action: "AuditAction | str",
        actor_id: Optional[int] = None,
        actor_username: Optional[str] = None,
        entity_type: "AuditEntityType | str | None" = None,
        entity_id: Optional[str] = None,
        before: Any = None,
        after: Any = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        commit: bool = True,
    ) -> Optional[AuditLog]:
        return await record_audit_event(
            self.db,
            action=action,
            actor_id=actor_id,
            actor_username=actor_username,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            ip_address=ip_address,
            user_agent=user_agent,
            description=description,
            metadata=metadata,
            commit=commit,
        )

    async def list(
        self,
        *,
        entity_type: "AuditEntityType | str | None" = None,
        entity_id: Optional[str] = None,
        actor_id: Optional[int] = None,
        action: "AuditAction | str | None" = None,
        limit: int = 50,
        offset: int = 0,
    )