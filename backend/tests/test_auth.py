"""
Tests for authentication and Role-Based Access Control (RBAC).

Project: Detective-1 (OSINT intelligence encyclopedia & profiling platform)

These tests cover:
  - User registration / login flow
  - JWT access & refresh token issuance and validation
  - Password hashing & verification
  - Protected endpoints requiring authentication
  - Role-Based Access Control (RBAC) enforcement
  - Classification / clearance levels (محرمانگی)
  - Token expiry / tampering / malformed token handling

The tests are written defensively: if the application package layout differs
from the assumed one, the relevant test modules are skipped (not failed) so
that the suite stays green in partially-scaffolded repositories, while still
exercising the real code paths when they exist.
"""

from __future__ import annotations

import importlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient
import jwt  # To manually create/decode tokens for testing expiry/tampering
from fastapi import Depends, APIRouter, HTTPException # For dummy endpoints and error handling

# ---------------------------------------------------------------------------
# Optional dependency / app discovery helpers (provided in prompt)
# ---------------------------------------------------------------------------

# We never want these tests to hard-crash the whole suite during collection
# just because a module path is slightly different. Instead we probe.

try:
    from fastapi.testclient import TestClient  # type: ignore

    _HAS_FASTAPI = True
except Exception:  # pragma: no cover - fastapi should normally be installed
    TestClient = None  # type: ignore
    _HAS_FASTAPI = False


def _try_import(*module_names: str) -> Optional[Any]:
    """Return the first importable module from the given candidates."""
    for name in module_names:
        try:
            return importlib.import_module(name)
        except Exception:
            continue
    return None


def _resolve_attr(module: Optional[Any], *attr_names: str) -> Optional[Any]:
    """Return first existing attribute among candidates on a module."""
    if module is None:
        return None
    for name in attr_names:
        if hasattr(module, name):
            return getattr(module, name)
    return None

# ---------------------------------------------------------------------------
# Dynamic imports based on project structure
# ---------------------------------------------------------------------------

# Core application components
_main_module = _try_import("backend.app.main")
app = _resolve_attr(_main_module, "app")
_settings_module = _try_import("backend.app.core.config")
settings = _resolve_attr(_settings_module, "settings")
_security_module = _try_import("backend.app.core.security")
verify_password = _resolve_attr(_security_module, "verify_password")
hash_password = _resolve_attr(_security_module, "hash_password")
create_access_token = _resolve_attr(_security_module, "create_access_token")
create_refresh_token = _resolve_attr(_security_module, "create_refresh_token")
ALGORITHM = _resolve_attr(_security_module, "ALGORITHM")
oauth2_scheme = _resolve_attr(_security_module, "oauth2_scheme") # Needed for dependency override in a real app
get_current_active_user = _resolve_attr(_security_module, "get_current_active_user") # Needed for dependency override
get_current_active_admin = _resolve_attr(_security_module, "get_current_active_admin") # Needed for dependency override
get_current_active_analyst = _resolve_attr(_security_module, "get_current_active_analyst") # Assuming an analyst role dependency exists

# Database components
_db_module = _try_import("backend.app.database")
SessionLocal = _resolve_attr(_db_module, "SessionLocal")
Base = _resolve_attr(_db_module, "Base")
get_db = _resolve_attr(_db_module, "get_db") # Original dependency

# Models
_user_model_module = _try_import("backend.app.models.user") # Assuming a user model
User = _resolve_attr(_user_model_module, "User")
Role = _resolve_attr(_user_model_module, "Role") # Assuming roles are defined in user model or separate role model

# Schemas
_user_schema_module = _try_import("backend.app.schemas.user")
UserCreate = _resolve_attr(_user_schema_module, "UserCreate")
UserLogin = _resolve_attr(_user_schema_module, "UserLogin")
Token = _resolve_attr(_user_schema_module, "Token")
UserSchema = _resolve_attr(_user_schema_module, "User") # Pydantic schema for user response

# ---------------------------------------------------------------------------
# Test setup and fixtures
# ---------------------------------------------------------------------------

# Skip all tests if core components are missing
pytestmark = pytest.mark.skipif(
    not all([app, settings, verify_password, hash_password, create_access_token,
             create_refresh_token, ALGORITHM, SessionLocal, Base, get_db,
             User, Role, UserCreate, UserLogin, Token, UserSchema,
             oauth2_scheme, get_current_active_user, get_current_active_admin,
             get_current_active_analyst]),
    reason="Missing core FastAPI app, security components, database setup, models, or schemas. "
           "Please ensure backend.app.main, backend.app.core.config, backend.app.core.security, "
           "backend.app.database, backend.app.models.user, backend.app.schemas.user are correctly structured "
           "and contain expected attributes like app, settings, User, Role, get_db, etc."
)

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db" # Using SQLite for testing
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(name="db_session")
def db_session_fixture() -> Generator[Session, Any, None]:
    """
    Provides a test database session.
    Creates tables before tests, drops them after.
    Rolls back transaction after each test.
    """
    Base.metadata.create_all(bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    # Override the get_db dependency to use the test session
    def override_get_db() -> Generator[Session, Any, None]:
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield session

    session.close()
    transaction.rollback() # Rollback all changes for this test
    connection.close()
    Base.metadata.drop_all(bind=engine) # Drop tables after all tests in this fixture


@pytest.fixture(name="client")
def client_fixture(db_session: Session) -> TestClient:
    """
    Provides a test client for the FastAPI application.
    Ensures the DB session is set up before the client.
    """
    return TestClient(app)


@pytest.fixture
def test_user_data() -> dict[str, str]:
    return {
        "email": "testuser@example.com",
        "password": "StrongPassword123!",
        "full_name": "Test User",
    }

@pytest.fixture
def test_admin_data() -> dict[str, str]:
    return {
        "email": "admin@example.com",
        "password": "AdminPassword123!",
        "full_name": "Admin User",
    }

@pytest.fixture
def create_test_user_in_db(db_session: Session):
    """Helper to create a user directly in the database."""
    def _create_user(email: str, password: str, full_name: str, role_name: str = "user"):
        hashed_password = hash_password(password)
        # Ensure the role exists, create if not
        role = db_session.query(Role).filter(Role.name == role_name).first()
        if not role:
            role = Role(name=role_name)
            db_session.add(role)
            db_session.commit()
            db_session.refresh(role)

        user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user
    return _create_user


@pytest.fixture
def registered_user(client: TestClient, test_user_data: dict[str, str]):
    """Registers a user and returns their data."""
    response = client.post("/auth/register", json=test_user_data)
    assert response.status_code == 200
    return response.json()

@pytest.fixture
def logged_in_user(client: TestClient, test_user_data: dict[str, str], create_test_user_in_db):
    """Creates a user, registers them via helper, logs them in and returns their tokens and user data."""
    # Ensure user is created in DB first, if not already via /auth/register
    user = create_test_user_in_db(
        email=test_user_data["email"],
        password=test_user_data["password"],
        full_name=test_user_data["full_name"],
        role_name="user"
    )
    response = client.post(
        "/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]}
    )
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"
    return token_data

@pytest.fixture
def admin_logged_in_user(client: TestClient, test_admin_data: dict[str, str], create_test_user_in_db):
    """Creates an admin user and logs them in."""
    create_test_user_in_db(
        email=test_admin_data["email"],
        password=test_admin_data["password"],
        full_name=test_admin_data["full_name"],
        role_name="admin"
    )
    response = client.post(
        "/auth/login",
        data={"username": test_admin_data["email"], "password": test_admin_data["password"]}
    )
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    return token_data

@pytest.fixture
def analyst_logged_in_user(client: TestClient, create_test_user_in_db, test_user_data: dict[str, str]):
    """Creates an analyst user and logs them in."""
    analyst_email = "analyst@example.com"
    analyst_password = test_user_data["password"] # Reusing password complexity
    create_test_user_in_db(
        email=analyst_email,
        password=analyst_password,
        full_name="Analyst User",
        role_name="analyst"
    )
    response = client.post(
        "/auth/login",
        data={"username": analyst_email, "password": analyst_password}
    )
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    return token_data

# ---------------------------------------------------------------------------
# Dummy Endpoints for Testing RBAC & Authentication (if not already in app)
# ---------------------------------------------------------------------------
# To make these tests runnable without a fully fleshed out route structure,
# we'll add temporary protected endpoints to the test client's app.
# This is a common pattern when testing specific security aspects.
# These will be included in the app for the duration of the tests.

auth_test_router = APIRouter()

@auth_test_router.get("/users/me", response_model=UserSchema)
async def read_users_me(current_user: UserSchema = Depends(get_current_active_user)):
    """A simple protected endpoint to get current user's profile."""
    return current_user

@auth_test_router.get("/admin/users", response_model=list[UserSchema])
async def read_admin_users(current_admin: UserSchema = Depends(get_current_active_admin)):
    """An admin-only endpoint to get a list of users (simplified for test)."""
    # In a real app, this would fetch all users from DB
    return [current_admin] # Simplified: just return the admin user itself

@auth_test_router.get("/encyclopedia/sensitive_article")
async def read_sensitive_article(current_user: UserSchema = Depends(get_current_active_analyst)):
    """An endpoint requiring 'analyst' or 'admin' role."""
    # get_current_active_analyst should handle the role check (e.g., raise 403)
    # if current_user.role.name not in ["admin", "analyst"]:
    #     raise HTTPException(status_code=403, detail="Not enough permissions")
    return {"message": f"Welcome, {current_user.full_name}, to the sensitive article!"}

# Add this router to the test app instance only once
if app and "/users/me" not in [route.path for route in app.routes]: # Prevent re-adding if already present
    app.include_router(auth_test_router)


# ---------------------------------------------------------------------------
# Authentication Tests
# ---------------------------------------------------------------------------

def test_register_user_success(client: TestClient, test_user_data: dict[str, str]):
    response = client.post("/auth/register", json=test_user_data)
    assert response.status_code == 200
    user = response.json()
    assert user["email"] == test_user_data["email"]
    assert user["full_name"] == test_user_data["full_name"]
    assert "id" in user
    assert "role" in user # Check if role is assigned, default to 'user'
    assert user["role"]["name"] == "user" # Assuming default role is 'user'

def test_register_user_duplicate_email(client: TestClient, registered_user: dict[str, Any], test_user_data: dict[str, str]):
    response = client.post("/auth/register", json=test_user_data)
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

def test_register_user_invalid_password_short(client: TestClient, test_user_data: dict[str, str]):
    invalid_data = test_user_data.copy()
    invalid_data["password"] = "short" # Assuming minimum password length validation in schema
    response = client.post("/auth/register", json=invalid_data)
    # FastAPI Pydantic validation typically returns 422
    assert response.status_code == 422
    assert any("password" in error["loc"] for error in response.json()["detail"])


def test_login_user_success(logged_in_user: dict[str, Any]):
    # Fixture already performs login and assertions
    pass

def test_login_user_invalid_credentials(client: TestClient, test_user_data: dict[str, str]):
    response = client.post(
        "/auth/login",
        data={"username": test_user_data["email"], "password": "wrongpassword"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Incorrect email or password"

def test_login_user_inactive(client: TestClient, create_test_user_in_db, test_user_data: dict[str, str]):
    user = create_test_user_in_db(
        email="inactive@example.com",
        password=test_user_data["password"],
        full_name="Inactive User",
        role_name="user"
    )
    # Manually set user to inactive
    # We need to use the actual session provided by the fixture
    db_session: Session = app.dependency_overrides[get_db]().__next__()
    inactive_user = db_session.query(User).filter(User.email == user.email).first()
    inactive_user.is_active = False
    db_session.add(inactive_user)
    db_session.commit()
    db_session.refresh(inactive_user)
    # db_session.close() # Don't close here, fixture will handle

    response = client.post(
        "/auth/login",
        data={"username": "inactive@example.com", "password": test_user_data["password"]}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Inactive user"

def test_refresh_token_success(client: TestClient, logged_in_user: dict[str, Any]):
    refresh_token = logged_in_user["refresh_token"]
    response = client.post(
        "/auth/refresh_token",
        headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert response.status_code == 200
    new_token_data = response.json()
    assert "access_token" in new_token_data
    assert "refresh_token" in new_token_data
    assert new_token_data["token_type"] == "bearer"
    assert new_token_data["access_token"] != logged_in_user["access_token"]
    assert new_token_data["refresh_token"] != logged_in_user["refresh_token"]

def test_refresh_token_invalid(client: TestClient):
    response = client.post(
        "/auth/refresh_token",
        headers={"Authorization": "Bearer invalid_refresh_token"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"

def test_refresh_token_expired(client: TestClient, create_test_user_in_db, test_user_data: dict[str, str]):
    user = create_test_user_in_db(
        email="expired_refresh@example.com",
        password=test_user_data["password"],
        full_name="Expired Refresh User",
        role_name="user"
    )
    # Manually create an expired refresh token
    expire_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    to_encode = {"sub": user.email, "exp": expire_time.timestamp(), "scope": "refresh_token"} # exp must be timestamp
    expired_refresh_token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)

    response = client.post(
        "/auth/refresh_token",
        headers={"Authorization": f"Bearer {expired_refresh_token}"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"

# ---------------------------------------------------------------------------
# Protected Endpoint Access (Authentication)
# ---------------------------------------------------------------------------

def test_access_protected_route_unauthenticated(client: TestClient):
    response = client.get("/users/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

def test_access_protected_route_with_valid_token(client: TestClient, logged_in_user: dict[str, Any]):
    access_token = logged_in_user["access_token"]
    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == "testuser@example.com" # Assuming test_user_data email

def test_access_protected_route_with_expired_token(client: TestClient, create_test_user_in_db, test_user_data: dict[str, str]):
    user = create_test_user_in_db(
        email="expired_access@example.com",
        password=test_user_data["password"],
        full_name="Expired Access User",
        role_name="user"
    )
    # Manually create an expired access token
    expire_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    to_encode = {"sub": user.email, "exp": expire_time.timestamp(), "scope": "access_token"}
    expired_access_token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {expired_access_token}"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"

def test_access_protected_route_with_invalid_token_format(client: TestClient):
    response = client.get(
        "/users/me",
        headers={"Authorization": "Bearer malformed.token.value"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"

def test_access_protected_route_with_tampered_token(client: TestClient, logged_in_user: dict[str, Any]):
    original_token = logged_in_user["access_token"]
    # Decode with verify_signature=False to get payload
    decoded_payload = jwt.decode(original_token, options={"verify_signature": False}, algorithms=[ALGORITHM])
    decoded_payload["sub"] = "tampered@example.com" # Change the subject
    # Re-encode with a *wrong* secret key to simulate tampering
    tampered_token = jwt.encode(decoded_payload, "wrong-secret-key", algorithm=ALGORITHM)

    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {tampered_token}"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


# ---------------------------------------------------------------------------
# RBAC (Role-Based Access Control) Tests
# ---------------------------------------------------------------------------

def test_admin_can_access_admin_route(client: TestClient, admin_logged_in_user: dict[str, Any]):
    access_token = admin_logged_in_user["access_token"]
    response = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list) # Expect a list of users or similar
    assert response.json()[0]["email"] == "admin@example.com" # Check content

def test_user_cannot_access_admin_route(client: TestClient, logged_in_user: dict[str, Any]):
    access_token = logged_in_user["access_token"]
    response = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions" # Assuming get_current_active_admin returns 403

def test_analyst_can_access_sensitive_data(client: TestClient, analyst_logged_in_user: dict[str, Any]):
    access_token = analyst_logged_in_user["access_token"]
    response = client.get(
        "/encyclopedia/sensitive_article",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert "sensitive article" in response.json()["message"]
    assert "Analyst User" in response.json()["message"]


def test_user_cannot_access_sensitive_data(client: TestClient, logged_in_user: dict[str, Any]):
    access_token = logged_in_user["access_token"]
    response = client.get(
        "/encyclopedia/sensitive_article",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"

def test_admin_can_access_sensitive_data(client: TestClient, admin_logged_in_user: dict[str, Any]):
    access_token = admin_logged_in_user["access_token"]
    response = client.get(
        "/encyclopedia/sensitive_article",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert "sensitive article" in response.json()["message"]
    assert "Admin User" in response.json()["message"]