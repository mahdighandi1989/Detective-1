"""
Pytest fixtures for Detective-1 backend tests.

Provides:
- `db`            : isolated SQLAlchemy session backed by an in-memory SQLite DB
                    (per-test rollback for full isolation).
- `client`        : FastAPI TestClient with the DB dependency overridden.
- `auth_headers`  : Authorization headers for an authenticated regular user.
- `admin_headers` : Authorization headers for an authenticated admin user.
- `test_user`     : a persisted regular user.
- `admin_user`    : a persisted admin user.

These fixtures avoid touching the real PostgreSQL/Neo4j/Redis services so the
test suite can run hermetically in CI.
"""

from __future__ import annotations

import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Test environment must be configured *before* importing application modules so
# that pydantic Settings pick up safe, hermetic values.
# ---------------------------------------------------------------------------
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "1")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("PERPLEXITY_API_KEY", "pplx-test")
os.environ.setdefault("GEMINI_API_KEY", "gemini-test")

# ---------------------------------------------------------------------------
# Application imports. We try a few import paths so the conftest stays robust
# against small layout differences in the repo.
# ---------------------------------------------------------------------------
# Assuming the following structure based on common FastAPI patterns and provided cross-references:
# - app is in backend/app/main.py
# - Base for SQLAlchemy models is in backend/app/db/base.py
# - User model and UserRole enum are in backend/app/models/user.py
# - Security utilities are in backend/app/core/security.py
# - Database dependency is in backend/app/api/dependencies.py

from app.main import app
from app.db.base import Base
from app.models.user import User, UserRole
from app.core.security import create_access_token, pwd_context
from app.api.dependencies import get_db

# ---------------------------------------------------------------------------
# Database fixture
# ---------------------------------------------------------------------------

@pytest.fixture(name="db")
def db_session() -> Generator[Session, None, None]:
    """
    Provides an isolated SQLAlchemy session for testing.
    Uses an in-memory SQLite database and rolls back changes after each test.
    """
    engine = create_engine(
        os.environ["DATABASE_URL"],
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create all tables in the test database
    Base.metadata.create_all(bind=engine)

    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    # Event listeners for SQLite specific transaction handling
    @event.listens_for(engine, "connect")
    def do_connect(dbapi_connection, connection_record):
        # disable pysqlite's emitting of PRAGMA foreign_keys = ON which breaks
        # document and other things in tests.
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def do_begin(conn):
        conn.exec_driver_sql("BEGIN")

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    # Drop all tables after tests to ensure a clean slate, especially if engine is reused.
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# FastAPI TestClient fixture
# ---------------------------------------------------------------------------

@pytest.fixture(name="client")
def test_client(db: Session) -> Generator[TestClient, None, None]:
    """
    Provides a FastAPI TestClient instance with the database dependency overridden
    to use the test database session.
    """
    def override_get_db():
        try:
            yield db
        finally:
            # Ensure session is closed if it's not already by the fixture
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear() # Clear overrides after test to prevent interference


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(name="test_user")
def regular_test_user(db: Session) -> User:
    """
    A persisted regular user for testing authentication.
    """
    hashed_password = pwd_context.hash("testpassword")
    user = User(
        email="test@example.com",
        hashed_password=hashed_password,
        full_name="Test User",
        role=UserRole.USER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(name="admin_user")
def admin_test_user(db: Session) -> User:
    """
    A persisted admin user for testing authentication.
    """
    hashed_password = pwd_context.hash("adminpassword")
    user = User(
        email="admin@example.com",
        hashed_password=hashed_password,
        full_name="Admin User",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Authentication headers fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(name="auth_headers")
def regular_user_auth_headers(test_user: User) -> dict[str, str]:
    """
    Authorization headers for an authenticated regular user.
    """
    access_token = create_access_token(data={"sub": test_user.email})
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture(name="admin_headers")
def admin_user_auth_headers(admin_user: User) -> dict[str, str]:
    """
    Authorization headers for an authenticated admin user.
    """
    access_token = create_access_token(data={"sub": admin_user.email})
    return {"Authorization": f"Bearer {access_token}"}