"""Aggregation of all Pydantic schemas for the Detective-1 platform.

This module re-exports every request/response schema so other parts of the
application (API routes, services, workers, tests) can import from a single
location:

    from app.schemas import PersonCreate, ArticleRead, RiskAssessmentRead

The individual schema modules (``person``, ``article``, ``risk_assessment``,
``source``, ``auth``, ``graph``, ``common``, ``user``) are expected to live next to this
file. To stay resilient while the codebase is still being built, imports are
guarded so that a missing sibling module does not break the whole package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# Public API ----------------------------------------------------------------
# ---------------------------------------------------------------------------
# Every name listed here is guaranteed to be importable from ``app.schemas``
# as long as the corresponding sibling module exists. The lists are kept
# explicit (rather than ``*``) so that static type checkers / linters can
# verify the surface area.
# ---------------------------------------------------------------------------

__all__: list[str] = []


def _extend(*names: str) -> None:
    """Append exported names to ``__all__`` without duplicates."""
    for name in names:
        if name not in __all__:
            __all__.append(name)


# ---------------------------------------------------------------------------
# common — shared base models / enums / pagination --------------------------
# ---------------------------------------------------------------------------
try:  # pragma: no cover - defensive import
    from .common import (  # noqa: F401
        ORMBase,
        PaginatedResponse,
        PaginationParams,
        Timestamped,
        ClassificationLevel,
    )
except ImportError:  # pragma: no cover
    pass
else:
    _extend(
        "ORMBase",
        "PaginatedResponse",
        "PaginationParams",
        "Timestamped",
        "ClassificationLevel",
    )


# ---------------------------------------------------------------------------
# user — user authentication and authorization schemas ----------------------
# ---------------------------------------------------------------------------
try:  # pragma: no cover - defensive import
    from .user import (  # noqa: F401
        User,
        UserCreate,
        UserRead,
        UserUpdate,
        UserInDB,
        Token,
        TokenPayload,
    )
except ImportError:  # pragma: no cover
    pass
else:
    _extend(
        "User",
        "UserCreate",
        "UserRead",
        "UserUpdate",
        "UserInDB",
        "Token",
        "TokenPayload",
    )


# ---------------------------------------------------------------------------
# person — schemas for persons/targets --------------------------------------
# ---------------------------------------------------------------------------
try:  # pragma: no cover - defensive import
    from .person import (  # noqa: F401
        Person,
        PersonCreate,
        PersonRead,
        PersonUpdate,
        PersonInDB,
        PersonWithRiskAssessment,
    )
except ImportError:  # pragma: no cover
    pass
else:
    _extend(
        "Person",
        "PersonCreate",
        "PersonRead",
        "PersonUpdate",
        "PersonInDB",
        "PersonWithRiskAssessment",
    )


# ---------------------------------------------------------------------------
# article — schemas for encyclopedia articles -------------------------------
# ---------------------------------------------------------------------------
try:  # pragma: no cover - defensive import
    from .article import (  # noqa: F401
        Article,
        ArticleCreate,
        ArticleRead,
        ArticleUpdate,
        ArticleInDB,
    )
except ImportError:  # pragma: no cover
    pass
else:
    _extend(
        "Article",
        "ArticleCreate",
        "ArticleRead",
        "ArticleUpdate",
        "ArticleInDB",
    )


# ---------------------------------------------------------------------------
# risk_assessment — schemas for risk assessments ----------------------------
# ---------------------------------------------------------------------------
try:  # pragma: no cover - defensive import
    from .risk_assessment import (  # noqa: F401
        RiskAssessment,
        RiskAssessmentCreate,
        RiskAssessmentRead,
        RiskAssessmentUpdate,
        RiskAssessmentInDB,
        RiskCategory,
    )
except ImportError:  # pragma: no cover
    pass
else:
    _extend(
        "RiskAssessment",
        "RiskAssessmentCreate",
        "RiskAssessmentRead",
        "RiskAssessmentUpdate",
        "RiskAssessmentInDB",
        "RiskCategory",
    )


# ---------------------------------------------------------------------------
# source — schemas for data sources -----------------------------------------
# ---------------------------------------------------------------------------
try:  # pragma: no cover - defensive import
    from .source import (  # noqa: F401
        Source,
        SourceCreate,
        SourceRead,
        SourceUpdate,
        SourceInDB,
        SourceCredibility,
    )
except ImportError:  # pragma: no cover
    pass
else:
    _extend(
        "Source",
        "SourceCreate",
        "SourceRead",
        "SourceUpdate",
        "SourceInDB",
        "SourceCredibility",
    )


# ---------------------------------------------------------------------------
# graph — schemas for graph data structures ---------------------------------
# ---------------------------------------------------------------------------
try:  # pragma: no cover - defensive import
    from .graph import (  # noqa: F401
        GraphNode,
        GraphEdge,
        GraphData,
        GraphQuery,
    )
except ImportError:  # pragma: no cover
    pass
else:
    _extend(
        "GraphNode",
        "GraphEdge",
        "GraphData",
        "GraphQuery",
    )