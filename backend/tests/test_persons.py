"""
تست CRUD پروفایل اشخاص (Person Profiles).

این فایل رفتار endpoint های مدیریت پروفایل اشخاص را پوشش می‌دهد:
- ساخت پروفایل (با سمت فعلی/قبلی، سوابق، عملکرد)
- خواندن تکی و لیست
- به‌روزرسانی
- حذف
- کنترل دسترسی (auth/RBAC)
- اتصال به ارزیابی ریسک و رنگ‌بندی سطح خطر

طراحی شده تا با ساختار پیشنهادی پروژه (FastAPI + SQLAlchemy) سازگار باشد و
در صورت نبود برخی قابلیت‌ها به‌شکل graceful (skip) رفتار کند تا تست شکننده نشود.
"""

import os
import uuid
from typing import Generator, Any, Dict, List
from datetime import datetime
import json
import time

import pytest
from sqlalchemy import create_engine, Column, String, Boolean, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.types import TypeDecorator, TEXT

# ---------------------------------------------------------------------------
# Test environment defaults — باید قبل از import اپلیکیشن ست شوند.
# ---------------------------------------------------------------------------
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("TESTING", "1")
# Use an in-memory SQLite database for tests for speed and isolation
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-detective1")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-detective1")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "1")
os.environ.setdefault("LLM_PROVIDER", "mock")  # Use a mock LLM for tests
os.environ.setdefault("OSINT_AGENT_PROVIDER", "mock") # Use a mock OSINT agent for tests

# Custom type for handling lists as JSON in SQLite for compatibility with ARRAY type in PostgreSQL
class JSONList(TypeDecorator):
    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value

# ---------------------------------------------------------------------------
# Import application + DB plumbing با fallback های مختلف برای انعطاف‌پذیری.
# ---------------------------------------------------------------------------
try:
    from fastapi.testclient import TestClient
    from backend.app.main import app as fastapi_app
    from backend.app.core.config import settings
    from backend.app.core.security import create_access_token, get_password_hash
    from backend.app.db.session import get_db # For dependency override

    # Define a local Base for test models to ensure they are created/dropped
    Base = declarative_base()

    # Define simplified models that mirror the expected backend models
    # This avoids circular imports and ensures tests run even if full models aren't present yet
    class User(Base):
        __tablename__ = "users"
        id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
        email = Column(String, unique=True, index=True, nullable=False)
        hashed_password = Column(String, nullable=False)
        is_active = Column(Boolean, default=True)
        is_superuser = Column(Boolean, default=False)
        roles = Column(JSONList, default=[])

    class Person(Base):
        __tablename__ = "persons"
        id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
        name = Column(String, index=True, nullable=False)
        photo_url = Column(String, nullable=True)
        current_position = Column(String, nullable=True)
        previous_positions = Column(JSONList, default=[])
        actions = Column(JSONList, default=[])
        biography = Column(String, nullable=True)
        notes = Column(String, nullable=True)
        risk_score = Column(Float, default=0.0)
        risk_level = Column(String, default="unknown")
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Simplified CRUD operation for user creation, matching backend.app.crud.user.create_user
    def create_user_for_test(db_session: Any, user_in: Dict) -> User:
        hashed_password = get_password_hash(user_in["password"])
        db_user = User(
            email=user_in["email"],
            hashed_password=hashed_password,
            is_active=user_in.get("is_active", True),
            is_superuser=user_in.get("is_superuser", False),
            roles=user_in.get("roles", [])
        )
        db_session.add(db_user)
        db_session.commit()
        db_session.refresh(db_user)
        return db_user

except ImportError as exc:  # pragma: no cover
    pytest.skip(f"Application import failed: {exc}", allow_module_level=True)

# ---------------------------------------------------------------------------
# Database setup for tests
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = os.environ["DATABASE_URL"]
test_engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Override get_db dependency for tests
@pytest.fixture(name="db_session")
def db_session_fixture() -> Generator:
    """
    Provides a test database session.
    Creates tables, yields a session, then drops tables.
    """
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)

@pytest.fixture(name="client")
def client_fixture(db_session: Any) -> Generator:
    """
    Provides a FastAPI test client with a mocked database session.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides = {}

# ---------------------------------------------------------------------------
# Authentication fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(name="test_admin_user")
def test_admin_user_fixture(db_session: Any) -> User:
    """Creates and returns an admin test user."""
    user_in = {
        "email": "admin_test@example.com",
        "password": "testpassword",
        "is_active": True,
        "is_superuser": True,
        "roles": ["admin", "analyst"]
    }
    user = create_user_for_test(db_session, user_in)
    return user

@pytest.fixture(name="test_analyst_user")
def test_analyst_user_fixture(db_session: Any) -> User:
    """Creates and returns an analyst test user."""
    user_in = {
        "email": "analyst_test@example.com",
        "password": "testpassword",
        "is_active": True,
        "is_superuser": False,
        "roles": ["analyst"]
    }
    user = create_user_for_test(db_session, user_in)
    return user

@pytest.fixture(name="admin_auth_headers")
def admin_auth_headers_fixture(test_admin_user: User) -> Dict[str, str]:
    """Provides authentication headers for an admin user."""
    access_token = create_access_token(
        data={"sub": test_admin_user.email, "roles": test_admin_user.roles},
        expires_delta=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return {"Authorization": f"Bearer {access_token}"}

@pytest.fixture(name="analyst_auth_headers")
def analyst_auth_headers_fixture(test_analyst_user: User) -> Dict[str, str]:
    """Provides authentication headers for an analyst user."""
    access_token = create_access_token(
        data={"sub": test_analyst_user.email, "roles": test_analyst_user.roles},
        expires_delta=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return {"Authorization": f"Bearer {access_token}"}

# ---------------------------------------------------------------------------
# Helper function for creating a person
# ---------------------------------------------------------------------------
def create_test_person(client: TestClient, headers: Dict[str, str], person_data: Dict) -> Dict:
    """Helper to create a person and return the response data."""
    response = client.post("/api/v1/persons/", json=person_data, headers=headers)
    assert response.status_code == 201, f"Failed to create person: {response.text}"
    return response.json()

# ---------------------------------------------------------------------------
# Person CRUD Tests
# ---------------------------------------------------------------------------

class TestPersonCRUD:

    def test_create_person(self, client: TestClient, admin_auth_headers: Dict[str, str]):
        """Test creating a person profile."""
        person_data = {
            "name": "محمود احمدی",
            "photo_url": "http://example.com/mahmoud.jpg",
            "current_position": "رئیس سابق جمهور",
            "previous_positions": ["شهردار تهران", "استاندار اردبیل"],
            "actions": ["سخنرانی در سازمان ملل", "مناظره انتخاباتی"],
            "biography": "سوابق محمود احمدی‌نژاد شامل فعالیت‌های اجرایی و سیاسی...",
            "notes": "نکات مهم درباره محمود احمدی‌نژاد..."
        }
        created_person = create_test_person(client, admin_auth_headers, person_data)

        assert created_person["name"] == person_data["name"]
        assert created_person["photo_url"] == person_data["photo_url"]
        assert created_person["current_position"] == person_data["current_position"]
        assert created_person["previous_positions"] == person_data["previous_positions"]
        assert "id" in created_person
        assert created_person["risk_level"] == "unknown" # Initial risk level

    def test_create_person_unauthorized(self, client: TestClient):
        """Test creating a person profile without authentication."""
        person_data = {
            "name": "علی خامنه‌ای",
            "photo_url": "http://example.com/ali.jpg",
            "current_position": "رهبر",
            "previous_positions": ["رئیس جمهور"],
            "actions": ["سخنرانی"],
            "biography": "رهبر جمهوری اسلامی ایران",
            "notes": "نکات"
        }
        response = client.post("/api/v1/persons/", json=person_data)
        assert response.status_code == 401 # Unauthorized

    def test_read_person(self, client: TestClient, admin_auth_headers: Dict[str, str]):
        """Test reading a single person profile."""
        person_data = {
            "name": "قاسم سلیمانی",
            "photo_url": "http://example.com/qasem.jpg",
            "current_position": "فرمانده سابق سپاه قدس",
            "previous_positions": [],
            "actions": ["عملیات برون‌مرزی"],
            "biography": "زندگینامه قاسم سلیمانی...",
            "notes": "ملاحظات..."
        }
        created_person = create_test_person(client, admin_auth_headers, person_data)
        person_id = created_person["id"]

        response = client.get(f"/api/v1/persons/{person_id}", headers=admin_auth_headers)
        assert response.status_code == 200
        retrieved_person = response.json()

        assert retrieved_person["id"] == person_id
        assert retrieved_person["name"] == person_data["name"]
        assert retrieved_person["current_position"] == person_data["current_position"]
        assert retrieved_person["actions"] == person_data["actions"]

    def test_read_person_not_found(self, client: TestClient, admin_auth_headers: Dict[str, str]):
        """Test reading a non-existent person profile."""
        non_existent_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/persons/{non_existent_id}", headers=admin_auth_headers)
        assert response.status_code == 404

    def test_read_persons_list(self, client: TestClient, admin_auth_headers: Dict[str, str]):
        """Test reading a list of person profiles."""
        person_data1 = {
            "name": "حسن روحانی",
            "photo_url": "http://example.com/hassan.jpg",
            "current_position": "رئیس جمهور سابق",
            "previous_positions": [],
            "actions": [],
            "biography": "زندگینامه حسن روحانی...",
            "notes": ""
        }
        person_data2 = {
            "name": "ابراهیم رئیسی",
            "photo_url": "http://example.com/ebrahim.jpg",
            "current_position": "رئیس جمهور",
            "previous_positions": ["رئیس قوه قضائیه"],
            "actions": ["مبارزه با فساد"],
            "biography": "زندگینامه ابراهیم رئیسی...",
            "notes": ""
        }
        create_test_person(client, admin_auth_headers, person_data1)
        create_test_person(client, admin_auth_headers, person_data2)

        response = client.get("/api/v1/persons/", headers=admin_auth_headers)
        assert response.status_code == 200
        persons = response.json()

        assert len(persons) == 2
        names = {p["name"] for p in persons}
        assert person_data1["name"] in names
        assert person_data2["name"] in names

    def test_update_person(self, client: TestClient, admin_auth_headers: Dict[str, str]):
        """Test updating an existing person profile."""
        person_data = {
            "name": "محمد خاتمی",
            "photo_url": "http://example.com/khatami.jpg",
            "current_position": "رئیس جمهور سابق",
            "previous_positions": ["نماینده مجلس"],
            "actions": ["گفتگوی تمدن‌ها"],
            "biography": "زندگینامه خاتمی...",
            "notes": "نکات اولیه"
        }
        created_person = create_test_person(client, admin_auth_headers, person_data)
        person_id = created_person["id"]

        update_data = {
            "name": "سید محمد خاتمی",
            "current_position": "رئیس جمهور اسبق",
            "previous_positions": ["نماینده مجلس", "وزیر فرهنگ"], # Update list
            "notes": "اضافه شدن نکات جدید"
        }
        response = client.patch(f"/api/v1/persons/{person_id}", json=update_data, headers=admin_auth_headers)
        assert response.status_code == 200
        updated_person = response.json()

        assert updated_person["id"] == person_id
        assert updated_person["name"] == update_data["name"]
        assert updated_person["current_position"] == update_data["current_position"]
        assert updated_person["previous_positions"] == update_data["previous_positions"]
        assert updated_person["notes"] == update_data["notes"]
        # Ensure other fields remain unchanged if not in update_data
        assert updated_person["photo_url"] == person_data["photo_url"]
        assert updated_person["actions"] == person_data["actions"]

    def test_update_person_unauthorized(self, client: TestClient, analyst_auth_headers: Dict[str, str], admin_auth_headers: Dict[str, str]):
        """Test updating a person profile with insufficient permissions (e.g., analyst trying to change risk)."""
        # First, create a person with an admin user
        person_data = {
            "name": "محسن رضایی",
            "photo_url": "http://example.com/mohsen.jpg",
            "current_position": "معاون اقتصادی رئیس جمهور",
            "previous_positions": ["فرمانده سپاه"],
            "actions": ["اقتصاد مقاومتی"],
            "biography": "محسن رضایی میرقائد...",
            "notes": ""
        }
        created_person = create_test_person(client, admin_auth_headers, person_data) # Admin creates
        person_id = created_person["id"]

        # Analyst tries to update a sensitive field like risk_level, which should be forbidden for non-admins
        update_data_sensitive = {"risk_level": "نفوذی"}
        response = client.patch(f"/api/v1/persons/{person_id}", json=update_data_sensitive, headers=analyst_auth_headers)
        assert response.status_code == 403 # Forbidden (assuming RBAC prevents analysts from setting risk_level)

        # Analyst tries to update a non-sensitive field, which might be allowed
        update_data_non_sensitive = {"notes": "یادداشت‌های جدید توسط تحلیلگر"}
        response = client.patch(f"/api/v1/persons/{person_id}", json=update_data_non_sensitive, headers=analyst_auth_headers)
        assert response.status_code == 200 # Allowed (assuming analysts can edit notes)
        updated_person = response.json()
        assert updated_person["notes"] == update_data_non_sensitive["notes"]
        assert updated_person["risk_level"] == created_person["risk_level"] # Risk level should not have changed

    def test_delete_person(self, client: TestClient, admin_auth_headers: Dict[str, str]):
        """Test deleting a person profile."""
        person_data = {
            "name": "مصطفی پورمحمدی",
            "photo_url": "http://example.com/pourmohammadi.jpg",
            "current_position": "دبیرکل جامعه روحانیت مبارز",
            "previous_positions": ["وزیر دادگستری"],
            "actions": [],
            "biography": "مصطفی پورمحمدی...",
            "notes": ""
        }
        created_person = create_test_person(client, admin_auth_headers, person_data)
        person_id = created_person["id"]

        response = client.delete(f"/api/v1/persons/{person_id}", headers=admin_auth_headers)
        assert response.status_code == 204 # No content on successful deletion

        # Verify deletion
        response = client.get(f"/api/v1/persons/{person_id}", headers=admin_auth_headers)
        assert response.status_code == 404

    def test_delete_person_unauthorized(self, client: TestClient, analyst_auth_headers: Dict[str, str], admin_auth_headers: Dict[str, str]):
        """Test deleting a person profile without admin privileges."""
        # Create a person with admin
        person_data = {
            "name": "محمد باقر قالیباف",
            "photo_url": "http://example.com/ghalibaf.jpg",
            "current_position": "رئیس مجلس",
            "previous_positions": ["شهردار تهران"],
            "actions": ["نمایندگی مجلس"],
            "biography": "محمد باقر قالیباف...",
            "notes": ""
        }
        created_person = create_test_person(client, admin_auth_headers, person_data) # Admin creates
        person_id = created_person["id"]

        # Try to delete with analyst (should fail, typically delete is admin-only)
        response = client.delete(f"/api/v1/persons/{person_id}", headers=analyst_auth_headers)
        assert response.status_code == 403 # Forbidden

        # Verify it still exists
        response = client.get(f"/api/v1/persons/{person_id}", headers=analyst_auth_headers)
        assert response.status_code == 200

    def test_person_risk_assessment_update_by_admin(self, client: TestClient, admin_auth_headers: Dict[str, str]):
        """Test that risk assessment can be updated by an admin and reflected."""
        person_data = {
            "name": "محمد جواد ظریف",
            "photo_url": "http://example.com/zarif.jpg",
            "current_position": "عضو شورای راهبردی روابط خارجی",
            "previous_positions": ["وزیر امور خارجه"],
            "actions": ["مذاکرات هسته‌ای"],
            "biography": "محمد جواد ظریف...",
            "notes": ""
        }
        created_person = create_test_person(client, admin_auth_headers, person_data)
        person_id = created_person["id"]

        # Simulate a risk assessment update by admin
        update_risk_data = {
            "risk_score": 0.75,
            "risk_level": "مشکوک"
        }
        response = client.patch(f"/api/v1/persons/{person_id}", json=update_risk_data, headers=admin_auth_headers)
        assert response.status_code == 200
        updated_person = response.json()

        assert updated_person["id"] == person_id
        assert updated_person["risk_score"] == update_risk_data["risk_score"]
        assert updated_person["risk_level"] == update_risk_data["risk_level"]

        # Verify risk level is reflected in GET
        response = client.get(f"/api/v1/persons/{person_id}", headers=admin_auth_headers)
        assert response.status_code == 200
        retrieved_person = response.json()
        assert retrieved_person["risk_level"] == update_risk_data["risk_level"]

    def test_person_profile_audit_log_creation(self, client: TestClient, admin_auth_headers: Dict[str, str]):
        """
        Test that creating a person profile generates audit-related timestamps.
        A full audit log test would query a dedicated AuditLog model.
        """
        person_data = {
            "name": "سید ابراهیم رئیسی",
            "photo_url": "http://example.com/raisi_audit.jpg",
            "current_position": "رئیس جمهور",
            "previous_positions": ["رئیس قوه قضائیه"],
            "actions": ["سفر استانی"],
            "biography": "زندگینامه سید ابراهیم رئیسی...",
            "notes": ""
        }
        created_person = create_test_person(client, admin_auth_headers, person_data)

        assert "created_at" in created_person
        assert "updated_at" in created_person
        assert created_person["created_at"] is not None
        assert created_person["updated_at"] is not None
        # Verify that created_at and updated_at are valid ISO 8601 strings
        datetime.fromisoformat(created_person["created_at"].replace("Z", "+00:00"))
        datetime.fromisoformat(created_person["updated_at"].replace("Z", "+00:00"))

    def test_person_profile_audit_log_update(self, client: TestClient, admin_auth_headers: Dict[str, str]):
        """
        Test that updating a person profile updates the 'updated_at' timestamp.
        """
        person_data = {
            "name": "علی لاریجانی",
            "photo_url": "http://example.com/larijani.jpg",
            "current_position": "عضو مجمع تشخیص مصلحت نظام",
            "previous_positions": ["رئیس مجلس"],
            "actions": ["تصویب قوانین"],
            "biography": "زندگینامه علی لاریجانی...",
            "notes": "اولین یادداشت"
        }
        created_person = create_test_person(client, admin_auth_headers, person_data)
        person_id = created_person["id"]
        initial_updated_at = created_person["updated_at"]

        time.sleep(0.01) # Ensure a small time difference for updated_at to change

        update_data = {"notes": "یادداشت‌های جدید"}
        response = client.patch(f"/api/v1/persons/{person_id}", json=update_data, headers=admin_auth_headers)
        assert response.status_code == 200
        updated_person = response.json()

        assert updated_person["id"] == person_id
        assert updated_person["notes"] == update_data["notes"]
        assert datetime.fromisoformat(updated_person["updated_at"].replace("Z", "+00:00")) > \
               datetime.fromisoformat(initial_updated_at.replace("Z", "+00:00")) # updated_at should be newer
        assert updated_person["created_at"] == created_person["created_at"] # created_at should be same