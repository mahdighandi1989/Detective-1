"""API package for Detective-1.

This package contains the FastAPI route modules and the main API router
that aggregates all versioned endpoints (auth, persons, encyclopedia,
graph, risk, sources).

Notes on routing conventions
----------------------------
Each route module defines its own ``APIRouter`` instance together with the
URL ``prefix`` and OpenAPI ``tags`` that belong to it (for example
``APIRouter(prefix="/persons", tags=["persons"])``).  Because the prefixes
are declared *inside* each route module, this aggregator must **not** add a
second prefix when calling ``include_router`` — otherwise endpoints would be
exposed under a duplicated path such as ``/persons/persons``.
"""

from fastapi import APIRouter

from app.api.routes import (
    auth,
    encyclopedia,
    graph,
    persons,
    risk,
    sources,
)

# Aggregate router for the whole API surface. The versioned prefix
# (for example ``/api/v1``) is applied where this router is mounted in
# ``app.main`` so it is intentionally omitted here.
api_router = APIRouter()

# NOTE: Do not pass ``prefix=...`` here. Every route module already declares
# its own prefix and tags, so adding another prefix would lead to a
# double-prefixed path.
api_router.include_router(auth.router)
api_router.include_router(persons.router)
api_router.include_router(encyclopedia.router)
api_router.include_router(graph.router)
api_router.include_router(risk.router)
api_router.include_router(sources.router)

__all__ = ["api_router"]