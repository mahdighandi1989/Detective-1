"""
Detective-1 — FastAPI application entry point.

This module is the entry point of the Detective-1 backend API. It is
responsible for:
  - Creating and configuring the FastAPI application instance.
  - Registering global middleware (CORS, request logging).
  - Mounting all API routers under the configured API prefix.
  - Exposing health/readiness endpoints used by docker-compose / orchestration.
  - Wiring application lifespan events (startup/shutdown) including database
    and Neo4j connection initialization / teardown.

Detective-1 is an OSINT (Open Source Intelligence) analysis platform with two
core modules:
  1. An intelligence encyclopedia (LLM-categorized / summarized articles with
     semantic search via embeddings).
  2. A person profiling & tracking module (profiles, OSINT search agents,
     source credibility scoring, automated risk assessment, and a risk-colored
     relationship graph).

Design note (wiring philosophy):
    Imports of configuration and API routers are intentionally NOT wrapped in
    broad try/except blocks with fallback router/settings objects. A failure to
    import configuration or routers is a real wiring/configuration bug and MUST
    fail fast at process startup rather than being silently masked. Masking
    such failures produces an application that *appears* to boot but serves
    stub endpoints, which is far harder to debug.

    Connection-lifecycle helpers (database / Neo4j init & teardown) are resolved
    at import time via small, explicit optional getters. The optionality here is
    NARROW and intentional: it only covers the *presence* of lifecycle hooks so
    that the same entrypoint works while the persistence layer is being built
    out. If a lifecycle hook IS present, any error it raises at startup is
    propagated (fail-fast) — it is never swallowed.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable, Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Core imports — fail-fast. If any of these fail, the process should crash
# loudly at startup. Do NOT wrap these in try/except with a fallback.
# ---------------------------------------------------------------------------
from app.core.config import settings

from app.api.routes.auth import router as auth_router
from app.api.routes.persons import router as persons_router
from app.api.routes.encyclopedia import router as encyclopedia_router
from app.api.routes.graph import router as graph_router


logger = logging.getLogger("detective1.main")


# ---------------------------------------------------------------------------
# Connection-lifecycle resolution.
#
# These getters resolve optional startup/shutdown hooks for PostgreSQL and
# Neo4j. The import of the *module* is fail-fast; only the *presence* of a
# specific hook function is treated as optional. If a hook exists and raises
# during startup/shutdown, the exception propagates (fail-fast) and is never
# masked.
# ---------------------------------------------------------------------------
LifecycleHook = Callable[[], Awaitable[None]]


def _resolve_hook(module_path: str, attr: str) -> Optional[LifecycleHook]:
    """Resolve an optional async lifecycle hook.

    Returns the callable if both the module and the attribute exist; otherwise
    returns ``None``. A missing *module* is tolerated only for the known
    persistence packages so the API can boot while persistence wiring is being
    completed. Any other ImportError is re-raised (fail-fast).
    """
    import importlib

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        # Only tolerate the absence of the persistence package itself.
        if exc.name and (exc.name == module_path or module_path.startswith(f"{exc.name}.")):
            logger.warning(
                "Lifecycle module %r not present yet; skipping %s hook.",
                module_path,
                attr,
            )
            return None
        # A missing transitive dependency is a real bug — fail fast.
        raise

    hook = getattr(module, attr, None)
    if hook is None:
        logger.warning("Lifecycle hook %s.%s not found; skipping.", module_path, attr)
        return None
    if not callable(hook):  # pragma: no cover - defensive
        raise TypeError(f"{module_path}.{attr} is not callable")
    return hook


_DB_CONNECT = _resolve_hook("app.db.session", "connect_database")
_DB_DISCONNECT = _resolve_hook("app.db.session", "disconnect_database")
_NEO4J_CONNECT = _resolve_hook("app.db.neo4j", "connect_neo4j")
_NEO4J_DISCONNECT = _resolve_hook("app.db.neo4j", "disconnect_neo4j")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialize and tear down external connections.

    Startup order: database -> Neo4j.
    Shutdown order: Neo4j -> database (reverse of startup).

    Any error raised by an existing hook propagates so misconfiguration fails
    fast at startup rather than serving a half-initialized application.
    """
    logger.info("Detective-1 API starting up (env=%s).", getattr(settings, "ENVIRONMENT", "unknown"))

    if _DB_CONNECT is not None:
        logger.info("Initializing database connection...")
        await _DB_CONNECT()
        logger.info("Database connection initialized.")

    if _NEO4J_CONNECT is not None:
        logger.info("Initializing Neo4j connection...")
        await _NEO4J_CONNECT()
        logger.info("Neo4j connection initialized.")

    try:
        yield
    finally:
        if _NEO4J_DISCONNECT is not None:
            logger.info("Closing Neo4j connection...")
            try:
                await _NEO4J_DISCONNECT()
            except Exception:  # noqa: BLE001 - best-effort shutdown
                logger.exception("Error while closing Neo4j connection.")

        if _DB_DISCONNECT is not None:
            logger.info("Closing database connection...")
            try:
                await _DB_DISCONNECT()
            except Exception:  # noqa: BLE001 - best-effort shutdown
                logger.exception("Error while closing database connection.")

        logger.info("Detective-1 API shut down.")


def create_application() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(
        title=getattr(settings, "PROJECT_NAME", "Detective-1"),
        description=(
            "Detective-1 — OSINT intelligence encyclopedia and person "
            "profiling / risk-assessment platform."
        ),
        version=getattr(settings, "VERSION", "0.1.0"),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{getattr(settings, 'API_V1_PREFIX', '/api/v1')}/openapi.json",
        lifespan=lifespan,
    )

    # -- CORS --------------------------------------------------------------
    cors_origins = getattr(settings, "BACKEND_CORS_ORIGINS", None) or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(o) for o in cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Request logging / correlation-id middleware -----------------------
    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        start = time.perf_counter()
        logger.info(
            "request.start id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.exception(
                "request.error id=%s method=%s path=%s elapsed_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        logger.info(
            "request.end id=%s status=%s elapsed_ms=%.2f",
            request_id,
            response.status_code,
            elapsed_ms,
        )
        return response

    # -- Health / readiness endpoints --------------------------------------
    @app.get("/health", tags=["health"], summary="Liveness probe")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "detective1-api"})

    @app.get("/ready", tags=["health"], summary="Readiness probe")
    async def ready() -> JSONResponse:
        return JSONResponse(
            {
                "status": "ready",
                "database": _DB_CONNECT is not None,
                "neo4j": _NEO4J_CONNECT is not None,
            }
        )

    # -- API routers (fail-fast wiring) ------------------------------------
    api_prefix = getattr(settings, "API_V1_PREFIX", "/api/v1")
    app.include_