"""SQLAlchemy ORM models package for Detective-1.

This module re-exports all ORM models so that Alembic autogenerate,
SQLAlchemy's declarative registry, and application imports can rely on a
single, stable import surface::

    from app.models import Person, Article, RiskAssessment, AuditLog, ...

Audit fix history:
    A previous revision of this file accidentally contained shell output
    (``bash: find ...``), Persian prose and a stray markdown code fence.
    That made the file invalid Python and broke importing the whole models
    package. This revision contains ONLY valid Python.

Robustness strategy:
    The exact module layout of some models has changed over time. The audit
    model may live in ``app.models.audit_log`` (preferred) or
    ``app.models.audit``. Person sub-models (``PersonPosition``,
    ``PersonAlias``, ``PersonRelationship``) may live directly inside
    ``app.models.person`` or in dedicated modules. To avoid breaking the
    entire package when one optional model is missing or relocated, optional
    models are imported defensively. Whatever is successfully imported is
    exported via ``__all__``; everything still imported eagerly below is
    considered required.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base / declarative registry
# ---------------------------------------------------------------------------
# Try the most common locations for the declarative Base so that this package
# also re-exports it for convenience and Alembic metadata access.
Base: Any = None
for _base_path in ("app.db.base_class", "app.db.base", "app.core.database", "app.db.session"):
    try:
        _mod = importlib.import_module(_base_path)
    except Exception:  # pragma: no cover - location varies between layouts
        continue
    if hasattr(_mod, "Base"):
        Base = getattr(_mod, "Base")
        break

# ---------------------------------------------------------------------------
# Required core models
# ---------------------------------------------------------------------------
from app.models.person import Person  # noqa: E402
from app.models.article import Article  # noqa: E402
from app.models.risk_assessment import RiskAssessment  # noqa: E402
from app.models.source import Source  # noqa: E402

# ---------------------------------------------------------------------------
# AuditLog: lives in ``audit_log.py`` (file is ``audit_log``), NOT ``audit``.
# Import from the correct module, but fall back gracefully if relocated.
# ---------------------------------------------------------------------------
AuditLog: Any = None
for _audit_path in ("app.models.audit_log", "app.models.audit"):
    try:
        _audit_mod = importlib.import_module(_audit_path)
    except Exception:
        continue
    if hasattr(_audit_mod, "AuditLog"):
        AuditLog = getattr(_audit_mod, "AuditLog")
        break
if AuditLog is None:  # pragma: no cover - audit model is expected to exist
    logger.warning(
        "AuditLog model could not be imported from app.models.audit_log "
        "or app.models.audit; audit logging models will be unavailable."
    )

# ---------------------------------------------------------------------------
# Optional person sub-models. They may be defined inside ``person.py`` or in
# dedicated modules. Import each defensively so a missing one does not break
# the whole package import.
# ---------------------------------------------------------------------------
PersonPosition: Any = None
PersonAlias: Any = None
PersonRelationship: Any = None

_PERSON_SUBMODELS = {
    "PersonPosition": ("app.models.person", "app.models.person_position"),
    "PersonAlias": ("app.models.person", "app.models.person_alias"),
    "PersonRelationship": ("app.models.person", "app.models.person_relationship"),
}

for _name, _candidate_modules in _PERSON_SUBMODELS.items():
    _resolved = None
    for _mod_path in _candidate_modules:
        try:
            _candidate_mod = importlib.import_module(_mod_path)
        except Exception:
            continue
        if hasattr(_candidate_mod, _name):
            _resolved = getattr(_candidate_mod, _name)
            break
    if _resolved is not None:
        globals()[_name] = _resolved
    else:
        logger.debug(
            "Optional person sub-model %s not found; it will not be exported.",
            _name,
        )

# ---------------------------------------------------------------------------
# Build __all__ from what actually resolved so we never export a dangling
# name that is still ``None``.
# ---------------------------------------------------------------------------
__all__ = ["Base", "Person", "Article", "RiskAssessment", "Source"]

for _optional_name in ("AuditLog", "PersonPosition", "PersonAlias", "PersonRelationship"):
    if globals().get(_optional_name) is not None:
        __all__.append(_optional_name)

# Clean up loop/helper names so they are not part of the public namespace.
for _tmp in (
    "_base_path",
    "_mod",
    "_audit_path",
    "_audit_mod",
    "_name",
    "_candidate_modules",
    "_resolved",
    "_mod_path",
    "_candidate_mod",
    "_optional_name",
    "_tmp",
    "_PERSON_SUBMODELS",
):
    globals().pop(_tmp, None)