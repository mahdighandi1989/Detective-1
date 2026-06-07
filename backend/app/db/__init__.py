"""
Database package for Detective-1.

This package centralizes all database-related infrastructure for the
backend, including the SQLAlchemy engine, session factory, declarative
base, and the dependency used by FastAPI routes to obtain a DB session.

Exposing these objects at the package level allows the rest of the
application (models, services, workers, alembic) to import a single,
consistent source of truth:

    from app.db import Base, engine, SessionLocal, get_db

Modules in this package:
    - base_class : Declarative ``Base`` for ORM models.
    - session    : Engine, ``SessionLocal`` factory and ``get_db`` dep.
"""

from app.db.base_class import Base
from app.db.session import (
    SessionLocal,
    engine,
    get_db,
)

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
]