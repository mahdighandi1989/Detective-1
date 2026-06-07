"""
Authentication routes for Detective-1 OSINT platform.

Endpoints:
    POST /auth/register  -> register a new user
    POST /auth/login     -> obtain an access + refresh token pair
    POST /auth/refresh   -> refresh an access token
    GET  /auth/me        -> current authenticated user profile

Depends on:
    - app.core.config.settings        (JWT secret / expiry / algorithm)
    - app.core.security               (hashing + JWT helpers + RBAC deps)
    - app.db.session.get_async_db     (async SQLAlchemy session dependency)
    - app.models.user.User            (ORM user model)
    - app.schemas.auth.*              (Pydantic request/response models)

IMPORTANT (cross-tier sync — backend <-> db):
    These routes use ``AsyncSession``. The session dependency injected here MUST
    yield an ``AsyncSession`` (created via ``create_async_engine`` + an
    ``async_sessionmaker``). ``app.db.session`` therefore exposes
    ``get_async_db`` for async routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.session import get_async_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    Token,
    TokenRefresh,
    UserCreate,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_async_db),
) -> User:
    """Create a new user account.

    Fails with 409 if the username or email is already taken.
    """
    result = await db.execute(
        select(User).where(
            or_(User.username == payload.username, User.email == payload.email)
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this username or email already exists.",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=getattr(payload, "role", None) or "analyst",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="Obtain an access + refresh token pair",
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_async_db),
) -> Token:
    """Authenticate a user and return access + refresh tokens."""
    result = await db.execute(
        select(User).where(
            or_(
                User.username == payload.username,
                User.email == payload.username,
            )
        )
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is disabled.",
        )

    access_token = create_access_token(subject=str(user.id), role=user.role)
    refresh_token = create_refresh_token(subject=str(user.id))

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post(
    "/refresh",
    response_model=Token,
    summary="Refresh an access token",
)
async def refresh(
    payload: TokenRefresh,
    db: AsyncSession = Depends(get_async_db),
) -> Token:
    """Issue a new access token (and rotated refresh token) from a refresh token."""
    try:
        claims = decode_token(payload.refresh_token)
    except Exception as exc:  # noqa: BLE001 - normalize all decode errors to 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if claims.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provided token is not a refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    subject = claims.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing a subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == subject))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists or is disabled.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=str(user.id), role=user.role)
    new_refresh_token = create_refresh_token(subject=str(user.id))

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.get(
    "/me",
    response_model=UserOut,
    summary="Current authenticated user profile",
)
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return the profile of the currently authenticated user."""
    return current_user