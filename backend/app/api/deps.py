"""
FastAPI dependency providers for Detective-1.

This module centralizes authentication and authorization (RBAC) dependencies.

IMPORTANT - role consistency:
    `UserRole` and `ClassificationLevel` are imported from the SINGLE SOURCE
    OF TRUTH module (`app.core.enums`). This file MUST NOT define its own
    local/fallback copy of `UserRole`. Previously deps.py declared a divergent
    fallback set (ADMIN/ANALYST/OSINT_AGENT/VIEWER) which made RBAC unreliable
    relative to schemas/user.py and models/user.py. That divergence is removed.
"""

from __future__ import annotations

from typing import Annotated, AsyncGenerator, Iterable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Single source of truth for roles / classification.
#
# We try the canonical central module first. If the project layout differs,
# we degrade gracefully but NEVER define a divergent local enum: we re-export
# whatever canonical definition exists so the whole app stays consistent.
# ---------------------------------------------------------------------------
try:
    # Preferred canonical location (single source of truth).
    from app.core.enums import UserRole, ClassificationLevel  # type: ignore
except Exception:  # pragma: no cover - import-path fallback only
    try:
        from app.models.enums import UserRole, ClassificationLevel  # type: ignore
    except Exception:  # pragma: no cover
        # Last-resort: import from schemas so we still share ONE definition
        # rather than minting a new, divergent fallback enum here.
        from app.schemas.user import UserRole  # type: ignore

        try:
            from app.schemas.user import ClassificationLevel  # type: ignore
        except Exception:  # pragma: no cover
            from enum import Enum

            class ClassificationLevel(str, Enum):  # type: ignore
                UNCLASSIFIED = "unclassified"
                RESTRICTED = "restricted"
                CONFIDENTIAL = "confidential"
                SECRET = "secret"
                TOP_SECRET = "top_secret"

                @classmethod
                def order(cls) -> list["ClassificationLevel"]:
                    return [
                        cls.UNCLASSIFIED,
                        cls.RESTRICTED,
                        cls.CONFIDENTIAL,
                        cls.SECRET,
                        cls.TOP_SECRET,
                    ]

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.user import User

# ---------------------------------------------------------------------------
# OAuth2 / token plumbing
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=True,
)

CredentialsException = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


# ---------------------------------------------------------------------------
# Database session dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session and ensure it is closed afterwards."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


DbSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Current-user resolution
# ---------------------------------------------------------------------------

def _decode_token(token: str) -> dict:
    """Decode and validate a JWT access token, returning its payload."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except (JWTError, ValidationError) as exc:  # pragma: no cover - thin wrapper
        raise CredentialsException from exc

    if payload.get("type") not in (None, "access"):
        # Refresh tokens (or any non-access token) must not authenticate requests.
        raise CredentialsException

    return payload


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    """Resolve the authenticated user from the bearer token."""
    payload = _decode_token(token)

    subject = payload.get("sub")
    if subject is None:
        raise CredentialsException

    # `sub` may be a user id or username depending on token issuance; support both.
    user: User | None = None
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        user_id = None

    if user_id is not None:
        user = await db.get(User, user_id)

    if user is None:
        result = await db.execute(select(User).where(User.username == str(subject)))
        user = result.scalar_one_or_none()

    if user is None:
        raise CredentialsException

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_active_user(current_user: CurrentUser) -> User:
    """Ensure the authenticated user account is active."""
    if not getattr(current_user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )
    return current_user


ActiveUser = Annotated[User, Depends(get_current_active_user)]


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------

def _user_role(user: User) -> UserRole:
    """Return the user's role as a canonical `UserRole`, normalizing strings."""
    raw = getattr(user, "role", None)
    if isinstance(raw, UserRole):
        return raw
    # Normalize a stored string into the canonical enum.
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no role assigned",
        )
    try:
        # Prefer the central parser if available (case-insensitive).
        from_str = getattr(UserRole, "from_str", None)
        if callable(from_str):
            return from_str(raw)
        return UserRole(str(raw).strip().lower())
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown user role: {raw!r}",
        ) from exc


def require_roles(*allowed_roles: UserRole):
    """Dependency factory enforcing that the current user has one of the roles.

    Usage:
        @router.get(..., dependencies=[Depends(require_roles(UserRole.ADMIN))])
        async def handler(...):
            ...
    """
    allowed: set[UserRole] = set(allowed_roles)

    async def _checker(current_user: ActiveUser) -> User:
        role = _user_role(current_user)
        if role not in allowed:
            allowed_str = ", ".join(sorted(r.value for r in allowed))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions: requires one of [{allowed_str}], "
                    f"have '{role.value}'"
                ),
            )
        return current_user

    return _checker


def require_min_role(minimum: UserRole):
    """Dependency factory enforcing a role hierarchy (privilege ordering).

    Ordering (most -> least privileged):
        ADMIN > ANALYST > INVESTIGATOR > OSINT_AGENT > VIEWER

    A user whose role is at least as privileged as `minimum` passes.
    """
    hierarchy: list[UserRole] = [
        UserRole.ADMIN,
        UserRole.ANALYST,
        UserRole.INVESTIGATOR,
        UserRole.OSINT_AGENT,
        UserRole.VIEWER,
    ]
    # Defensive: only keep roles that actually exist in the canonical enum.
    hierarchy = [r for r in hierarchy if isinstance(r, UserRole)]
    rank = {role: idx for idx, role in enumerate(hierarchy)}

    async def _checker(current_user: ActiveUser) -> User:
        role = _user_role(current_user)
        if rank.get(role, len(hierarchy)) > rank.get(minimum, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions: requires at least "
                    f"'{minimum.value}', have '{role.value}'"
                ),
            )
        return current_user

    return _checker


# Convenience pre-built role dependencies (kept as callables, not invoked here).
require_admin = require_roles(UserRole.ADMIN)
require_analyst = require_roles(UserRole.ADMIN, UserRole.ANALYST)
require_investigator = require_roles(
    UserRole.ADMIN, UserRole.ANALYST, UserRole.INVESTIGATOR
)
require_osint_agent = require_roles(
    UserRole.ADMIN, UserRole.ANALYST, UserRole.OSINT_AGENT
)


def has_role(user: User, *roles: UserRole) -> bool:
    """Pure helper (non-dependency) to check role membership in business logic."""
    try:
        return _user_role(user) in set(roles)
    except HTTPException:
        return False


# ---------------------------------------------------------------------------
# Classification-level access control
# ---------------------------------------------------------------------------

def can_access_classification(
    user: User, level: "ClassificationLevel"
) -> bool:
    """Return True if the user may access content at the given classification.

    Admins and analysts can access all levels; lower roles are bounded.
    This is intentionally conservative (default-deny on unknown roles).
    """
    try:
        role = _user_role(user)
    except HTTPException:
        return False

    if role in (UserRole.ADMIN, UserRole.ANALYST):
        return True

    # Build an ordering for classification levels if the enum exposes one.
    order_f