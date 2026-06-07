"""
Database session management for Detective-1.

Provides both synchronous and asynchronous SQLAlchemy engines, session
factories, and FastAPI dependency callables.

Exports:
    - engine            : synchronous SQLAlchemy Engine
    - async_engine      : asynchronous SQLAlchemy AsyncEngine
    - SessionLocal      : synchronous sessionmaker
    - AsyncSessionLocal : async_sessionmaker (also aliased as async_sessionmaker)
    - get_db            : FastAPI dependency yielding a sync Session
    - get_async_db      : FastAPI dependency yielding an AsyncSession
    - Base              : declarative base (re-exported for convenience)
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_sync_url() -> str:
    """Resolve the synchronous SQLAlchemy database URL from settings."""
    # Prefer an explicit sync URL if provided.
    sync_url = getattr(settings, "DATABASE_URL_SYNC", None)
    if sync_url:
        return str(sync_url)

    # Fall back to SQLALCHEMY_DATABASE_URI and normalise the driver to a
    # synchronous one (e.g. strip +asyncpg / +aiosqlite).
    uri = getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
    if uri is None:
        raise RuntimeError(
            "No database URL configured. Set DATABASE_URL_SYNC or "
            "SQLALCHEMY_DATABASE_URI in settings."
        )
    uri = str(uri)
    uri = uri.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    uri = uri.replace("postgresql+asyncpg", "postgresql+psycopg2")
    uri = uri.replace("sqlite+aiosqlite://", "sqlite://")
    return uri


def _build_async_url() -> str:
    """Resolve the asynchronous SQLAlchemy database URL from settings."""
    # Prefer SQLALCHEMY_DATABASE_URI (the canonical app URI).
    uri = getattr(settings, "SQLALCHEMY_DATABASE_URI", None)
    if uri is None:
        # Derive from the sync URL if only that is present.
        uri = _build_sync_url()
    uri = str(uri)

    # Normalise to an async driver.
    if uri.startswith("postgresql+psycopg2://"):
        uri = uri.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    elif uri.startswith("postgresql://"):
        uri = uri.replace("postgresql://", "postgresql+asyncpg://")
    elif uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql+asyncpg://")
    elif uri.startswith("sqlite://") and "+aiosqlite" not in uri:
        uri = uri.replace("sqlite://", "sqlite+aiosqlite://")
    return uri


# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------

_SYNC_URL = _build_sync_url()
_ASYNC_URL = _build_async_url()

_is_sqlite = _SYNC_URL.startswith("sqlite")

_pool_kwargs: dict = {}
if not _is_sqlite:
    _pool_kwargs = {
        "pool_pre_ping": True,
        "pool_size": getattr(settings, "DB_POOL_SIZE", 10),
        "max_overflow": getattr(settings, "DB_MAX_OVERFLOW", 20),
        "pool_recycle": getattr(settings, "DB_POOL_RECYCLE", 1800),
    }

_sync_connect_args: dict = {}
_async_connect_args: dict = {}
if _is_sqlite:
    _sync_connect_args = {"check_same_thread": False}

_echo = bool(getattr(settings, "DB_ECHO", False))

# Synchronous engine (used by Alembic, Celery tasks, scripts, etc.)
engine: Engine = create_engine(
    _SYNC_URL,
    echo=_echo,
    future=True,
    connect_args=_sync_connect_args,
    **_pool_kwargs,
)

# Asynchronous engine (used by the FastAPI request lifecycle).
async_engine: AsyncEngine = create_async_engine(
    _ASYNC_URL,
    echo=_echo,
    future=True,
    connect_args=_async_connect_args,
    **_pool_kwargs,
)


# ---------------------------------------------------------------------------
# Session factories
# ---------------------------------------------------------------------------

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
    future=True,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Backwards-compatible alias: some modules import `async_sessionmaker`
# from this module expecting the configured factory.
async_session_maker = AsyncSessionLocal


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a synchronous SQLAlchemy session.

    Usage:
        @router.get("/")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an asynchronous SQLAlchemy session.

    Usage:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_async_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Re-export Base if available so callers can do
# `from app.db.session import Base` without breaking older imports.
try:  # pragma: no cover - optional convenience re-export
    from app.db.base_class import Base  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover
    try:
        from app.db.base import Base  # type: ignore  # noqa: F401
    except Exception:
        Base = None  # type: ignore


__all__ = [
    "engine",
    "async_engine",
    "SessionLocal",
    "AsyncSessionLocal",
    "async_session_maker",
    "get_db",
    "get_async_db",
    "Base",
]