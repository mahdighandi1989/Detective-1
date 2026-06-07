"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

Detective-1: OSINT intelligence platform initial database schema.

Creates core relational tables: users, roles, user_roles, persons,
person_positions, articles, article_categories, article_category_links,
sources, risk_assessments, profile_article_links, and audit_logs.
Includes an optional pgvector embedding column for semantic search when
the ``vector`` extension is available.

Enum alignment note
-------------------
The ``risk_category`` enum is the single source of truth for risk
classification across the platform. Its values are kept consistent with
both the SQLAlchemy models and the Pydantic schemas
(``schemas/person.py`` and ``schemas/risk_assessment.py``):

    clean | suspicious | infiltrator | transformed | intelligence | unknown

Mapping to the product acceptance criteria
(پاک / مشکوک / نفوذی / استحاله‌یافته):
    clean        -> پاک (clean)
    suspicious   -> مشکوک (suspect/suspicious)
    infiltrator  -> نفوذی (infiltrator)
    transformed  -> استحاله‌یافته (transformed/co-opted)
    intelligence -> اطلاعاتی (intelligence officer)
    unknown      -> نامشخص (not yet assessed)

Enum types are created explicitly via ``enum.create(bind, checkfirst=True)``
so that re-running the migration (or running on a database where the type
already exists) does not raise a duplicate-type error.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Enum definitions (single source of truth for this migration).
# ---------------------------------------------------------------------------
RISK_CATEGORY_VALUES = (
    "clean",
    "suspicious",
    "infiltrator",
    "transformed",
    "intelligence",
    "unknown",
)

RISK_LEVEL_VALUES = (
    "low",
    "medium",
    "high",
    "critical",
    "unknown",
)

CLASSIFICATION_VALUES = (
    "unclassified",
    "restricted",
    "confidential",
    "secret",
    "top_secret",
)

CONTENT_STATUS_VALUES = (
    "raw",
    "processing",
    "processed",
    "archived",
)

SOURCE_TYPE_VALUES = (
    "web",
    "social_media",
    "news",
    "official",
    "leak",
    "manual",
    "other",
)

AUDIT_ACTION_VALUES = (
    "create",
    "update",
    "delete",
    "view",
    "assess",
    "link",
    "unlink",
)


risk_category_enum = postgresql.ENUM(
    *RISK_CATEGORY_VALUES, name="risk_category", create_type=False
)
risk_level_enum = postgresql.ENUM(
    *RISK_LEVEL_VALUES, name="risk_level", create_type=False
)
classification_enum = postgresql.ENUM(
    *CLASSIFICATION_VALUES, name="classification_level", create_type=False
)
content_status_enum = postgresql.ENUM(
    *CONTENT_STATUS_VALUES, name="content_status", create_type=False
)
source_type_enum = postgresql.ENUM(
    *SOURCE_TYPE_VALUES, name="source_type", create_type=False
)
audit_action_enum = postgresql.ENUM(
    *AUDIT_ACTION_VALUES, name="audit_action", create_type=False
)

_ALL_ENUMS = (
    risk_category_enum,
    risk_level_enum,
    classification_enum,
    content_status_enum,
    source_type_enum,
    audit_action_enum,
)


def _has_pgvector(bind) -> bool:
    """Return True when the ``vector`` extension is installed/available."""
    try:
        result = bind.execute(
            sa.text(
                "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
            )
        ).first()
        return result is not None
    except Exception:  # pragma: no cover - non-postgres backends
        return False


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ------------------------------------------------------------------
    # Create enum types up-front so columns can reference them safely.
    # ------------------------------------------------------------------
    if is_postgres:
        for enum in _ALL_ENUMS:
            enum.create(bind, checkfirst=True)

    pgvector_available = is_postgres and _has_pgvector(bind)
    if pgvector_available:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # roles
    # ------------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "clearance_level",
            classification_enum,
            server_default="unclassified",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    # ------------------------------------------------------------------
    # user_roles (many-to-many)
    # ------------------------------------------------------------------
    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ------------------------------------------------------------------
    # sources
    # ------------------------------------------------------------------
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column(
            "source_type",
            source_type_enum,
            server_default="other",
            nullable=False,
        ),
        sa.Column(
            "credibility_score",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_sources_source_type", "sources", ["source_type"])

    # ------------------------------------------------------------------
    # article_categories
    # ------------------------------------------------------------------
    op.create_table(
        "article_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("article_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("slug", name="uq_article_categories_slug"),
    )

    # ------------------------------------------------------------------
    # articles (encyclopedia entries)
    # ------------------------------------------------------------------
    article_columns = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("slug", sa.String(length=560), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("processed_content", sa.Text(), nullable=True),
        sa.Column(
            "status",
            content_status_enum,
            server_default="raw",
            nullable=False,
        ),
        sa.Column(
            "classification",
            classification_enum,
            server_default="unclassified",
            nullable=False,
        ),
        sa.Column