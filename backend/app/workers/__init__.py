"""Workers package for Detective-1.

This package contains Celery background workers responsible for
asynchronous OSINT search tasks, encyclopedia content analysis,
person profile enrichment, source validation, and risk assessment.

Modules:
    celery_app: Celery application instance and configuration.
    tasks: Registered background tasks (search, analysis, enrichment).
"""

from __future__ import annotations

__all__ = ["celery_app"]


def __getattr__(name: str):
    """Lazily expose the Celery application instance.

    Importing the Celery app eagerly at package import time can create
    circular-import problems (the app pulls in settings, which may pull
    in other parts of the application). Exposing it lazily via
    ``__getattr__`` lets callers do ``from app.workers import celery_app``
    without forcing the heavy import chain at package load.
    """
    if name == "celery_app":
        from app.workers.celery_app import celery_app as _celery_app

        return _celery_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")