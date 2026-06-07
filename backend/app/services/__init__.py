"""Services package for Detective-1 backend.

This package contains the business-logic / service layer that sits between
the API routes and the data-access (models / external integrations) layers.

Modules:
    llm_adapter   -- Unified adapter for LLM providers (OpenAI / Perplexity
                     Sonar / Gemini) used for classification, summarization
                     and search-augmented retrieval.
    osint_agent   -- Automated OSINT search agent that gathers public records
                     about persons from open internet sources.
    risk_engine   -- Risk assessment engine that classifies a person into
                     risk categories (clean / suspicious / infiltrator /
                     transformed) based on encyclopedia evidence.
    embeddings    -- Embedding generation + semantic-search helpers for the
                     intelligence encyclopedia.

These modules are imported lazily where possible to avoid pulling heavy
optional dependencies (e.g. LLM SDKs, vector clients) at package import time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "get_llm_adapter",
    "get_osint_agent",
    "get_risk_engine",
    "get_embeddings_service",
    "RiskCategory",
    "SourceCredibility",
]


# ---------------------------------------------------------------------------
# Shared enums / constants used across the service layer.
# Kept here (lightweight, no external deps) so other layers can import them
# without triggering heavy module loads.
# ---------------------------------------------------------------------------
from enum import Enum


class RiskCategory(str, Enum):
    """Risk classification buckets for a profiled person.

    Mirrors the categories described in the project requirements:
    پاک / مشکوک / نفوذی / استحاله‌یافته
    """

    CLEAN = "clean"            # آدم پاک
    SUSPICIOUS = "suspicious"  # مشکوک
    INFILTRATOR = "infiltrator"  # نفوذی / جاسوس
    TRANSFORMED = "transformed"  # دچار استحاله شده
    UNKNOWN = "unknown"

    @property
    def color(self) -> str:
        """Color used to render the node in the relationship graph."""
        return {
            RiskCategory.CLEAN: "#22c55e",        # green
            RiskCategory.SUSPICIOUS: "#eab308",   # yellow
            RiskCategory.TRANSFORMED: "#f97316",  # orange
            RiskCategory.INFILTRATOR: "#ef4444",  # red
            RiskCategory.UNKNOWN: "#6b7280",      # gray
        }[self]


class SourceCredibility(str, Enum):
    """Credibility rating for an OSINT source."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"

    @property
    def score(self) -> float:
        """Numeric weight (0.0 - 1.0) used in evidence aggregation."""
        return {
            SourceCredibility.HIGH: 1.0,
            SourceCredibility.MEDIUM: 0.66,
            SourceCredibility.LOW: 0.33,
            SourceCredibility.UNVERIFIED: 0.1,
        }[self]


if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from .llm_adapter import LLMAdapter
    from .osint_agent import OSINTAgent
    from .risk_engine import RiskEngine
    from .embeddings import EmbeddingsService


# ---------------------------------------------------------------------------
# Lazy accessors.
#
# These factory helpers defer importing the concrete service modules until
# they are actually needed. This keeps the package import cheap and avoids
# import-time failures when optional integrations are not configured.
# ---------------------------------------------------------------------------
def get_llm_adapter(*args: Any, **kwargs: Any) -> "LLMAdapter":
    """Return a configured :class:`LLMAdapter` instance."""
    from .llm_adapter import LLMAdapter

    return LLMAdapter(*args, **kwargs)


def get_osint_agent(*args: Any, **kwargs: Any) -> "OSINTAgent":
    """Return a configured :class:`OSINTAgent` instance."""
    from .osint_agent import OSINTAgent

    return OSINTAgent(*args, **kwargs)


def get_risk_engine(*args: Any, **kwargs: Any) -> "RiskEngine":
    """Return a configured :class:`RiskEngine` instance."""
    from .risk_engine import RiskEngine

    return RiskEngine(*args, **kwargs)


def get_embeddings_service(*args: Any, **kwargs: Any) -> "EmbeddingsService":
    """Return a configured :class:`EmbeddingsService` instance."""
    from .embeddings import EmbeddingsService

    return EmbeddingsService(*args, **kwargs)