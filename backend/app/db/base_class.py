"""SQLAlchemy declarative base class for Detective-1.

This module defines the shared declarative base used by all ORM models
across the application. It provides:

- A common ``Base`` class with an auto-generated ``__tablename__``
  derived from the class name (snake_case, pluralized).
- A default integer primary key ``id`` column on every model.
- Automatic ``created_at`` / ``updated_at`` timestamp columns.
- A convenience ``to_dict`` helper for serialization.

All models in ``backend/app/models/`` should inherit from ``Base``.
Alembic autogenerate (``backend/alembic/env.py``) imports this ``Base``
metadata to detect schema changes.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Column, DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, declared_attr


def _camel_to_snake(name: str) -> str:
    """Convert a CamelCase class name to snake_case.

    Examples:
        ``RiskAssessment`` -> ``risk_assessment``
        ``OSINTSource``    -> ``osint_source``
    """
    # Insert underscore between an acronym followed by a normal word,
    # e.g. "OSINTSource" -> "OSINT_Source".
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    # Insert underscore between a lowercase/digit and an uppercase letter.
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.lower()


def _pluralize(name: str) -> str:
    """Very small, dependency-free English pluralizer for table names.

    This is intentionally simple; it handles the common cases used by
    the Detective-1 models. Models that need a custom table name can
    always override ``__tablename__`` explicitly.
    """
    if name.endswith(("s", "x", "z", "ch", "sh")):
        return name + "es"
    if name.endswith("y") and not name.endswith(("ay", "ey", "iy", "oy", "uy")):
        return name[:-1] + "ies"
    return name + "s"


class Base(DeclarativeBase):
    """Declarative base for all Detective-1 ORM models.

    Provides common columns and conventions shared by every table:

    - ``id``: integer primary key.
    - ``created_at`` / ``updated_at``: server-side timestamps.
    - ``__tablename__``: auto-generated from the class name.
    """

    # Common metadata naming convention so Alembic produces stable,
    # predictable constraint / index names across migrations.
    metadata = None  # type: ignore[assignment]  # replaced below

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805 - SQLAlchemy convention
        return _pluralize(_camel_to_snake(cls.__name__))

    id: Any = Column(Integer, primary_key=True, index=True, autoincrement=True)

    created_at: Any = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Any = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self, exclude: set[str] | None = None) -> Dict[str, Any]:
        """Return a plain ``dict`` representation of this model instance.

        Args:
            exclude: Optional set of column names to omit from the output.

        Returns:
            A dictionary mapping column names to their (JSON-friendly)
            values. ``datetime`` values are serialized to ISO 8601 strings.
        """
        exclude = exclude or set()
        result: Dict[str, Any] = {}
        for column in self.__table__.columns:  # type: ignore[attr-defined]
            if column.name in exclude:
                continue
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        identifier = getattr(self, "id", None)
        return f"<{self.__class__.__name__}(id={identifier})>"


# ---------------------------------------------------------------------------
# Naming convention for constraints / indexes.
#
# Applying a consistent naming convention keeps Alembic autogenerate
# deterministic and avoids "unnamed constraint" churn between migrations.
# We attach the convention to the metadata created by DeclarativeBase.
# ---------------------------------------------------------------------------
from sqlalchemy import MetaData  # noqa: E402

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Replace the auto-created metadata with one that carries our naming
# convention. This must happen before any model subclass is defined,
# which is guaranteed because models import ``Base`` from this module.
Base.metadata = MetaData(naming_convention=NAMING_CONVENTION)


__all__ = ["Base"]