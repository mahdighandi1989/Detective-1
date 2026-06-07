"""
Celery application configuration for Detective-1.

This module configures the Celery distributed task queue with a Redis
broker and result backend. It is responsible for:
  - Bootstrapping the Celery app instance.
  - Wiring broker / result-backend URLs from application settings.
  - Registering task modules (autodiscovery).
  - Configuring serialization, timeouts, retries, and beat schedules.

Used by background OSINT search agents, LLM analysis pipelines, embedding
generation, and periodic credibility re-scoring jobs.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from celery import Celery
from celery.signals import setup_logging

# --- FIX: Removed try/except for importing settings.
# --- As per the prompt, 'settings' is a critical dependency, and its
# --- absence should be a hard error, not a silently handled fallback.
from app.core.config import settings


logger = logging.getLogger(__name__)

# Task modules that contain @celery_app.task definitions.
# This list can be extended or dynamically loaded.
# We attempt to fetch it from settings, providing a default if not explicitly set.
TASK_MODULES: list[str] = getattr(settings, "CELERY_TASK_MODULES", ["app.workers.tasks"])


# ---------------------------------------------------------------------------
# Celery application instance
# ---------------------------------------------------------------------------
celery_app = Celery(
    "detective_1_worker",
    broker=settings.CELERY_BROKER_URL,  # Broker URL is critical, must be in settings
    backend=settings.CELERY_RESULT_BACKEND,  # Result backend is critical, must be in settings
    include=TASK_MODULES,
)

# ---------------------------------------------------------------------------
# Celery configuration
# ---------------------------------------------------------------------------
celery_app.conf.update(
    # Serialization settings
    task_serializer=getattr(settings, "CELERY_TASK_SERIALIZER", "json"),
    result_serializer=getattr(settings, "CELERY_RESULT_SERIALIZER", "json"),
    accept_content=getattr(settings, "CELERY_ACCEPT_CONTENT", ["json"]),

    # Timezone settings
    timezone=getattr(settings, "CELERY_TIMEZONE", "UTC"),
    enable_utc=getattr(settings, "CELERY_ENABLE_UTC", True),

    # Broker connection settings
    broker_connection_retry_on_startup=getattr(settings, "CELERY_BROKER_RETRY_ON_STARTUP", True),

    # Task time limits (in seconds) to prevent tasks from running indefinitely
    # Soft limit: raises SoftTimeLimitExceeded, allowing task to clean up
    # Hard limit: sends SIGKILL, terminating the task abruptly
    task_soft_time_limit=getattr(settings, "CELERY_TASK_SOFT_TIME_LIMIT", 300),  # 5 minutes
    task_time_limit=getattr(settings, "CELERY_TASK_TIME_LIMIT", 600),  # 10 minutes

    # Result expiration (in seconds) - how long task results are stored in the backend
    result_expires=getattr(settings, "CELERY_RESULT_EXPIRES", 3600),  # 1 hour

    # Worker concurrency: number of concurrent processes/threads
    # Default to CPU count or 2 if not set in settings
    worker_concurrency=getattr(settings, "CELERY_WORKER_CONCURRENCY", os.cpu_count() or 2),

    # Task acknowledgment: Acknowledge tasks after they complete, not before (more robust)
    task_acks_late=getattr(settings, "CELERY_TASK_ACKS_LATE", True),
    # Pre-fetch multiplier: number of tasks a worker prefetches. Set to 1 for better load distribution.
    worker_prefetch_multiplier=getattr(settings, "CELERY_WORKER_PREFETCH_MULTIPLIER", 1),

    # Optional: Default retry configuration for tasks
    # task_default_retry_delay=getattr(settings, "CELERY_DEFAULT_RETRY_DELAY", 3 * 60), # 3 minutes
    # task_max_retries=getattr(settings, "CELERY_MAX_RETRIES", 3),
)


# ---------------------------------------------------------------------------
# Logging configuration for Celery worker
# ---------------------------------------------------------------------------
@setup_logging.connect
def config_loggers(*args: Any, **kwargs: Any) -> None:
    """
    Configures logging for Celery workers.
    This ensures that Celery's logging uses a consistent configuration with the main application.
    It attempts to use the LOG_LEVEL from application settings, falling back to INFO.
    """
    log_level = getattr(settings, "LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    # Set levels for specific potentially noisy loggers to match the overall log_level
    logging.getLogger("celery").setLevel(log_level)
    logging.getLogger("kombu").setLevel(log_level)
    logging.getLogger("amqp").setLevel(log_level)
    logging.getLogger("redis").setLevel(log_level)
    logger.info(f"Celery worker logging configured with level: {log_level}")


# ---------------------------------------------------------------------------
# Celery Beat Schedule (for periodic tasks)
# ---------------------------------------------------------------------------
# Periodic tasks can be defined here or dynamically loaded via settings.
# For now, this section is commented out as specific periodic tasks are not
# part of this file's direct scope, but the structure is provided for future expansion.
#
# from celery.schedules import crontab
# celery_app.conf.beat_schedule = {
#     "perform-periodic-osint-scan": {
#         "task": "app.workers.tasks.perform_periodic_osint_scan",
#         "schedule": crontab(hour=3, minute=0), # Example: Every day at 3:00 AM UTC
#         "args": (),
#     },
#     "re-evaluate-risk-scores": {
#         "task": "app.workers.tasks.re_evaluate_all_risk_scores",
#         "schedule": crontab(day_of_week='monday', hour=4, minute=0), # Every Monday at 4:00 AM UTC
#         "args": (),
#     },
# }
# Ensure timezone is consistent for Celery Beat, typically matching the main app's timezone.
# celery_app.conf.timezone = getattr(settings, "CELERY_BEAT_TIMEZONE", "UTC")