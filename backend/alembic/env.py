"""Alembic environment configuration for Detective-1.

This module configures the Alembic migration environment, wiring it to the
application's SQLAlchemy metadata and settings so that autogenerate works
against the live model definitions (Person, Article, RiskAssessment, Source,
audit logs, RBAC, etc.).

It supports both "offline" (emit SQL) and "online" (run against a live
database) migration modes, and reads the database URL from the application
settings / environment rather than hard-coding it in alembic.ini.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Make the application package importable.
#
# This file typically lives at: backend/alembic/env.py
# The application package lives at: backend/app/...
# So we add the "backend" directory (parent of "alembic") to sys.path.
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Application imports
#
# We import settings for the DB URL and the declarative Base (with its
# metadata) for autogenerate support. All models MUST be imported (directly
# or transitively) so their tables are registered on Base.metadata.
# ---------------------------------------------------------------------------
try:
    from app.core.config import settings
    from app.db.base import Base  # Assuming Base is defined here

    # Import all models to ensure they are registered with Base.metadata.
    # This is crucial for Alembic's 'autogenerate' to detect changes in your models.
    # Add any new models here as they are created.
    from app.models import article, person, risk_assessment, source, audit_log, rbac
    # Note: If 'audit_log' or 'rbac' are not separate files but part of other models,
    # adjust imports accordingly. This assumes they are distinct modules in app.models.

except ImportError as e:
    # This block allows Alembic to run even if the app dependencies are not fully
    # set up (e.g., during initial project setup or in environments where
    # `app` package is not yet fully functional for some reason).
    # However, 'autogenerate' will not work correctly without Base.metadata.
    print(f"Warning: Could not import application models or settings: {e}", file=sys.stderr)
    settings = None
    Base = None
    # If Base is not imported, target_metadata will be None or an empty MetaData object.
    # This means autogenerate will not detect any models.
    # For a functional setup, Base must be available.

# ---------------------------------------------------------------------------
# Alembic configuration
# ---------------------------------------------------------------------------

# this is the Alembic Config object, which provides
# access to values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
if Base:
    target_metadata = Base.metadata
else:
    # If Base could not be imported, autogenerate won't work correctly.
    # Provide an empty metadata object to prevent errors but indicate issue.
    print("Error: Base.metadata not available. Autogenerate will not function.", file=sys.stderr)
    from sqlalchemy.schema import MetaData
    target_metadata = MetaData()


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is additionally needed
    for SQL execution options.  Calls to context.execute() here
    emit the given string to the script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    if url is None and settings and settings.DATABASE_URL:
        url = settings.DATABASE_URL
    
    if url is None:
        raise Exception("Database URL not found for offline migration. "
                        "Set 'sqlalchemy.url' in alembic.ini or DATABASE_URL in settings.")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = None
    if settings and settings.DATABASE_URL:
        connectable = engine_from_config(
            {"sqlalchemy.url": settings.DATABASE_URL},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
    else:
        # Fallback to alembic.ini if settings.DATABASE_URL is not available
        # This might be less reliable if settings are expected to provide the URL.
        print("Warning: settings.DATABASE_URL not found. Falling back to alembic.ini for DB URL.", file=sys.stderr)
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
    
    if connectable is None:
        raise Exception("Connectable engine could not be created for online migration. "
                        "Ensure DATABASE_URL is set in environment or settings, "
                        "or 'sqlalchemy.url' in alembic.ini.")

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()