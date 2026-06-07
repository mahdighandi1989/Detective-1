"""User model with role-based access control (RBAC) and classification clearance levels.

This module defines the User SQLAlchemy model for the Detective-1 platform.
Users authenticate via JWT and are authorized through a role + clearance system:

- ``role``        : coarse-grained RBAC role (admin / analyst / operator / viewer)
- ``clearance``   : confidentiality clearance level controlling which classified
                    encyclopedia entries / person profiles a user may read.

The model is intentionally framework-light so it can be reused by:
  * FastAPI dependency ``get_current_user`` (backend/app/core/security.py)
  * Pydantic schemas (backend/app/schemas/user.py)
  * Alembic migrations (backend/alembic/)
  * Audit-log writers (records ``actor_id`` referencing User.id)

Important:
    ``Base`` is imported *directly* from ``app.db.base_class`` with **no
    try/except fallback**. A previous implementation wrapped this import in a
    fallback that created a *local* ``DeclarativeBase`` if the shared module
    could not be found. That fallback was dangerous: when triggered, ``User``
    would be mapped onto a *separate* metadata registry, so the ``users`` table
    would silently disappear from Alembic autogenerate output. ``Base`` MUST be
    the single, shared source of truth for the entire backend.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

# Single, shared declarative Base for the whole backend.
# NOTE: do NOT wrap this in try/except with a local fallback Base. Every model
# (user, person, source, risk_assessment, relationship, audit_log) must map
# onto this exact Base so that a single MetaData registry powers Alembic
# autogenerate and avoids "missing table" migration bugs.
from app.db.base_class import Base


class UserRole(str, enum.Enum):
    """Coarse-grained RBAC roles.

    Ordered from most to least privileged. Permission helpers below treat the
    ordering as a hierarchy: a higher-privileged role implicitly satisfies the
    requirement for any lower-privileged role.
    """

    ADMIN = "admin"
    ANALYST = "analyst"
    OPERATOR = "operator"
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        """Numeric privilege rank (higher == more privileged)."""
        return _ROLE_RANK[self]

    def satisfies(self, required: "UserRole") -> bool:
        """Return True if this role is at least as privileged as ``required``."""
        return self.rank >= required.rank


# Privilege ordering (higher number == more privileged).
_ROLE_RANK: dict[UserRole, int] = {
    UserRole.VIEWER: 0,
    UserRole.OPERATOR: 1,
    UserRole.ANALYST: 2,
    UserRole.ADMIN: 3,
}


class ClearanceLevel(str, enum.Enum):
    """Confidentiality clearance levels.

    Controls which classified encyclopedia entries / person profiles a user may
    read. Ordered from lowest to highest clearance. A user can read content
    whose required classification is **less than or equal to** their clearance.
    """

    UNCLASSIFIED = "unclassified"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"

    @property
    def rank(self) -> int:
        """Numeric clearance rank (higher == more access)."""
        return _CLEARANCE_RANK[self]

    def can_access(self, required: "ClearanceLevel") -> bool:
        """Return True if this clearance can access ``required`` classification."""
        return self.rank >= required.rank


# Clearance ordering (higher number == more access).
_CLEARANCE_RANK: dict[ClearanceLevel, int] = {
    ClearanceLevel.UNCLASSIFIED: 0,
    ClearanceLevel.RESTRICTED: 1,
    ClearanceLevel.CONFIDENTIAL: 2,
    ClearanceLevel.SECRET: 3,
    ClearanceLevel.TOP_SECRET: 4,
}


class User(Base):
    """Authenticated platform user with RBAC role and clearance level."""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_username", "username", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    username: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    # Hashed password (never store plaintext). Hashing handled in
    # backend/app/core/security.py via passlib.
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=False, length=32),
        nullable=False,
        default=UserRole.VIEWER,
        server_default=UserRole.VIEWER.value,
    )

    clearance: Mapped[ClearanceLevel] = mapped_column(
        SAEnum(
            ClearanceLevel,
            name="clearance_level",
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=ClearanceLevel.UNCLASSIFIED,
        server_default=ClearanceLevel.UNCLASSIFIED.value,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ----- Authorization helpers -------------------------------------------

    def has_role(self, required: UserRole) -> bool:
        """Return True if the user's role satisfies ``required`` (hierarchical)."""
        if self.is_superuser:
            return True
        return self.role.satisfies(required)

    def has_clearance(self, required: ClearanceLevel) -> bool:
        """Return True if the user's clearance can access ``required`` classification."""
        if self.is_superuser:
            return True
        return self.clearance.can_access(required)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<User id={self.id!s} username={self.username!r} "
            f"role={self.role.value!r} clearance={self.clearance.value!r}>"
        )