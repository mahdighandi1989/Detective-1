"""
backend/app/models/audit_log.py

مدل تاریخچهٔ تغییرات (audit log) برای پلتفرم Detective-1.

این مدل هر اقدام قابل‌توجه روی موجودیت‌ها (پروفایل اشخاص، ورودی‌های
دانشنامه، ارزیابی ریسک، منابع و ...) را ثبت می‌کند تا یک رد ممیزی
(audit trail) کامل، تغییرناپذیر و قابل پیگیری فراهم شود.

طراحی به‌گونه‌ای است که:
  - برای هر رکورد، شناسهٔ کاربر انجام‌دهنده، نوع عمل، نوع و شناسهٔ
    موجودیت هدف، مقادیر قبل و بعد (به‌صورت JSON)، و متادیتای درخواست
    (IP، user-agent) نگه‌داری می‌شود.
  - سطح طبقه‌بندی محرمانگی (classification) هر رویداد ثبت می‌شود تا با
    سیاست‌های RBAC و دسترسی محرمانه هماهنگ باشد.
  - رکوردها فقط افزودنی (append-only) هستند؛ ویرایش/حذف منطقی پشتیبانی
    نمی‌شود (در لایهٔ سرویس enforce می‌شود).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    # مسیر استاندارد پروژه طبق ساختار پیشنهادی AI
    from app.db.base_class import Base  # type: ignore
except Exception:  # pragma: no cover - fallback برای ساختارهای جایگزین
    try:
        from app.models.base import Base  # type: ignore
    except Exception:  # pragma: no cover
        from app.database import Base  # type: ignore


def _utcnow() -> datetime:
    """زمان فعلی با timezone آگاه (UTC)."""
    return datetime.now(timezone.utc)


class AuditAction(str, enum.Enum):
    """نوع عمل ثبت‌شده در audit log."""

    # General entity actions
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    READ = "read"
    CLASSIFY = "classify" # Change confidentiality classification

    # User/Authentication related actions
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    USER_REGISTER = "user_register"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    CHANGE_PASSWORD = "change_password"
    RESET_PASSWORD = "reset_password"
    PERMISSION_CHANGE = "permission_change" # User role/permission changes

    # Person Profile related actions
    ADD_PERSON = "add_person"
    EDIT_PERSON = "edit_person"
    DELETE_PERSON = "delete_person"
    VIEW_PERSON_PROFILE = "view_person_profile"
    ASSESS_RISK = "assess_risk" # Running or updating risk assessment

    # Encyclopedia/Article related actions
    ADD_ARTICLE = "add_article"
    EDIT_ARTICLE = "edit_article"
    DELETE_ARTICLE = "delete_article"
    SEARCH_ENCYCLOPEDIA = "search_encyclopedia"

    # OSINT/Source related actions
    RUN_OSINT = "run_osint" # Initiating an OSINT data collection task
    VALIDATE_SOURCE = "validate_source" # Marking a source as validated/invalidated
    ADD_SOURCE = "add_source"
    EDIT_SOURCE = "edit_source"
    DELETE_SOURCE = "delete_source"

    # Graph/Relationship related actions
    GRAPH_QUERY = "graph_query" # Querying the graph database
    ADD_RELATIONSHIP = "add_relationship"
    EDIT_RELATIONSHIP = "edit_relationship"
    DELETE_RELATIONSHIP = "delete_relationship"

    # System/Configuration actions
    SYSTEM_CONFIG_UPDATE = "system_config_update"
    EXPORT = "export" # Exporting data
    IMPORT = "import" # Importing data


class ConfidentialityClassification(str, enum.Enum):
    """سطح طبقه‌بندی محرمانگی برای رویدادهای audit log."""
    PUBLIC = "public" # Accessible to all users
    INTERNAL = "internal" # Accessible to authenticated internal users
    CONFIDENTIAL = "confidential" # Accessible to specific roles/groups
    SECRET = "secret" # Highly restricted access
    TOP_SECRET = "top_secret" # Extremely restricted access


class AuditLog(Base):
    """
    مدل SQLAlchemy برای نگهداری تاریخچهٔ تغییرات (Audit Log).
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"), # Assuming a 'users' table
        index=True,
        nullable=True, # Nullable for system-initiated actions or anonymous actions
    )
    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction), nullable=False, index=True
    )
    entity_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    ) # e.g., "Person", "Article", "RiskAssessment", "User", "Source"
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    ) # ID of the entity that was acted upon

    old_value: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    ) # JSON representation of the entity state BEFORE the action
    new_value: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    ) # JSON representation of the entity state AFTER the action

    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    classification: Mapped[ConfidentialityClassification] = mapped_column(
        SAEnum(ConfidentialityClassification),
        default=ConfidentialityClassification.INTERNAL,
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    ) # Optional human-readable description of the event

    # Relationship to the User model (assuming User model exists and has 'audit_logs' back_populates)
    # user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")

    __table_args__ = (
        # Index for quickly retrieving all audit logs for a specific entity
        Index("idx_audit_logs_entity", "entity_type", "entity_id"),
        # Index for quickly retrieving all actions by a specific user
        Index("idx_audit_logs_user_id", "user_id"),
        # Index for specific actions, useful for security monitoring
        Index("idx_audit_logs_action", "action"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, user_id={self.user_id}, action='{self.action}', "
            f"entity_type='{self.entity_type}', entity_id={self.entity_id}, "
            f"timestamp='{self.timestamp}', classification='{self.classification}')>"
        )