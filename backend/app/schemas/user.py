"""Pydantic schemas for User, authentication tokens, and RBAC roles.

These schemas back the auth flow (JWT + RBAC) and user management endpoints
in Detective-1 (see backend/app/api/routes/auth.py and
backend/app/core/security.py).

NOTE ON ROLE ENUM CONSOLIDATION
-------------------------------
RBAC roles (``UserRole``) and confidentiality levels (``ClassificationLevel``)
are now defined in a *single* canonical location: ``app.core.enums``.

Previously, three diverging definitions existed:
    * this module (ADMIN, ANALYST, INVESTIGATOR, VIEWER)
    * app/schemas/auth.py (ADMIN, ANALYST, EDITOR, VIEWER)
    * app/api/deps.py (importing from app.core.enums)

That divergence caused authorization bugs because different layers disagreed
about which roles existed. To prevent regression, this module now re-exports
the canonical enums from ``app.core.enums`` instead of declaring its own.
Do NOT redefine these enums here or elsewhere.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Canonical RBAC roles + classification levels.
#
# These are imported (not redefined) from the single source of truth in
# app.core.enums so that schemas/user.py, schemas/auth.py and api/deps.py all
# agree on exactly the same set of roles/levels.
# ---------------------------------------------------------------------------
from app.core.enums import ClassificationLevel, UserRole

__all__ = [
    "UserRole",
    "ClassificationLevel",
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserInDBBase",
    "User",
    "UserInDB",
    "UserPublic",
]


# ---------------------------------------------------------------------------
# Base / shared user schemas
# ---------------------------------------------------------------------------
class UserBase(BaseModel):
    """Fields shared across user representations."""

    email: EmailStr = Field(..., description="Unique login email")
    username: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Unique username",
    )
    full_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Display name",
    )
    role: UserRole = Field(
        default=UserRole.VIEWER,
        description="RBAC role assigned to the user",
    )
    clearance: ClassificationLevel = Field(
        default=ClassificationLevel.UNCLASSIFIED,
        description="Confidentiality level the user is cleared for",
    )
    is_active: bool = Field(
        default=True,
        description="Whether the account is enabled",
    )

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("username must not be blank")
        if " " in v:
            raise ValueError("username must not contain spaces")
        return v


# ---------------------------------------------------------------------------
# Create / update payloads
# ---------------------------------------------------------------------------
class UserCreate(UserBase):
    """Payload for creating a new user (registration / admin-create)."""

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plaintext password (hashed server-side before storage)",
    )

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        has_letter = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_letter and has_digit):
            raise ValueError("password must contain both letters and digits")
        return v


class UserUpdate(BaseModel):
    """Partial update payload. All fields optional."""

    email: Optional[EmailStr] = Field(default=None)
    username: Optional[str] = Field(default=None, min_length=3, max_length=64)
    full_name: Optional[str] = Field(default=None, max_length=255)
    role: Optional[UserRole] = Field(default=None)
    clearance: Optional[ClassificationLevel] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("username must not be blank")
        if " " in v:
            raise ValueError("username must not contain spaces")
        return v

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        has_letter = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_letter and has_digit):
            raise ValueError("password must contain both letters and digits")
        return v


# ---------------------------------------------------------------------------
# DB-backed / response schemas
# ---------------------------------------------------------------------------
class UserInDBBase(UserBase):
    """Shared fields for any user loaded from the database."""

    id: int = Field(..., description="Primary key")
    created_at: datetime = Field(..., description="Row creation timestamp")
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Last modification timestamp",
    )

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class User(UserInDBBase):
    """User as returned to authorized API consumers (no secrets)."""


class UserInDB(UserInDBBase):
    """Internal representation including the password hash."""

    hashed_password: str = Field(..., description="Server-side password hash")


class UserPublic(BaseModel):
    """Minimal public-facing user representation."""

    id: int
    username: str
    full_name: Optional[str] = None
    role: UserRole

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
