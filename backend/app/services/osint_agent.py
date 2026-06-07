"""OSINT Agent - Automated open-source intelligence gathering service.

This module implements an autonomous search agent that collects, validates,
and scores public records about persons of interest from open internet
sources using search-capable LLM providers (Perplexity/Sonar, OpenAI, Gemini).

The agent is designed to be invoked from Celery background tasks but can also
be called directly (async) from API routes for synchronous lookups.

Single source of truth for the LLM adapter:
    LLMProvider, LLMResponse, and LLMAdapter are imported from
    ``app.services.llm_adapter``. This module MUST NOT redefine them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.core.config import settings
from app.services.llm_adapter import (
    LLMAdapter,
    LLMProvider,
    LLMResponse,
)

logger = logging.getLogger("detective.osint_agent")


# ---------------------------------------------------------------------------
# Risk / confidence enums shared with the risk engine
# ---------------------------------------------------------------------------

class RiskCategory(str, Enum):
    """Classification buckets derived from gathered intelligence."""

    CLEAN = "clean"                  # آدم پاک
    SUSPICIOUS = "suspicious"        # مشکوک
    INFILTRATOR = "infiltrator"      # نفوذی
    TRANSFORMED = "transformed"      # استحاله‌یافته
    UNKNOWN = "unknown"              # نامشخص / داده ناکافی


class SourceCredibility(str, Enum):
    """Qualitative credibility tiers for a discovered source."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"


# Weight used to convert a credibility tier into a numeric score (0..1).
_CREDIBILITY_WEIGHTS: Dict[SourceCredibility, float] = {
    SourceCredibility.HIGH: 0.95,
    SourceCredibility.MEDIUM: 0.65,
    SourceCredibility.LOW: 0.35,
    SourceCredibility.UNVERIFIED: 0.15,
}

# Domains that are generally considered authoritative / reputable. The list is
# intentionally small and overridable through settings; the heuristic is a
# starting point, not a definitive ranking.
_HIGH_TRUST_TLDS = (".gov", ".gov.ir", ".ac.ir", ".edu", ".int")
_MEDIUM_TRUST_HINTS = (
    "wikipedia.org",
    "irna.ir",
    "isna.ir",
    "mehrnews.com",
    "tasnimnews.com",
    "bbc.com",
    "reuters.com",
    "apnews.com",
)
_LOW_TRUST_HINTS = (
    "blogspot.",
    "wordpress.com",
    "telegram.me",
    "t.me",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredSource:
    """A single open-source reference discovered for a person."""

    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    credibility: SourceCredibility = SourceCredibility.UNVERIFIED
    credibility_score: float = 0.0
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "credibility": self.credibility.value,
            "credibility_score": round(self.credibility_score, 4),
            "retrieved_at": self.retrieved_at,
        }


@dataclass
class PersonRecord:
    """Structured intelligence record extracted for a single person."""

    full_name: str
    aliases: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    current_position: Optional[str] = None
    previous_positions: List[str] = field(default_factory=list)
    current_roles: List[str] = field(default_factory=list)
    previous_roles: List[str] = field(default_factory=list)
    activities: List[str] = field(default_factory=list)
    statements: List[str] = field(default_factory=list)
    photo_url: Optional[str] = None
    sources: List[DiscoveredSource] = field(default_factory=list)
    confidence: float = 0.0
    raw_model_text: Optional[str] = None
    gathered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "full_name": self.full_name,
            "aliases": self.aliases,
            "summary": self.summary,
            "current_position": self.current_position,
            "previous_positions": self.previous_positions,
            "current_roles": self.current_roles,
            "previous_roles": self.previous_roles,
            "activities": self.activities,
            "statements": self.statements,
            "photo_url": self.photo_url,
            "sources": [s.to_dict() for s in self.sources],
            "confidence": round(self.confidence, 4),
            "gathered_at": self.gathered_at,
        }


# ---------------------------------------------------------------------------
# Source credibility scoring
# ---------------------------------------------------------------------------

def assess_source_credibility(url: str) -> SourceCredibility:
    """Heuristically classify the credibility of a source URL.

    The heuristic combines TLD reputation with a small list of well-known
    domains. It is deterministic and side-effect free so it can be unit
    tested in isolation.
    """

    if not url:
        return SourceCredibility.UNVERIFIED

    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = (parsed.netloc or parsed.path).lower().strip()
    except Exception:  # pragma: no cover - defensive
        return SourceCredibility.UNVERIFIED

    if not host:
        return SourceCredibility.UNVERIFIED

    # Strip leading "www."
    if host.startswith("www."):
        host = host[4:]

    for tld in _HIGH_TRUST_TLDS:
        if host.endswith(tld):
            return SourceCredibility.HIGH

    for hint in _MEDIUM_TRUST_HINTS:
        if hint in host:
            return SourceCredibility.MEDIUM

    for hint in _LOW_TRUST_HINTS:
        if hint in host:
            return SourceCredibility.LOW

    return SourceCredibility.UNVERIFIED


def credibility_to_score(credibility: SourceCredibility) -> float:
    """Map a credibility tier to a numeric score in the [0, 1] range."""

    return _CREDIBILITY_WEIGHTS.get(credibility, 0.0)


def score_sources(sources: List[DiscoveredSource]) -> List[DiscoveredSource]:
    """Populate credibility tier and numeric score for each source."""

    for source in sources:
        if source.credibility == SourceCredibility.UNVERIFIED:
            source.credibility = assess_source_credibility(source.url)
        source.credibility_score = credibility_to_score(source.credibility)
    return sources


def aggregate_confidence(sources: List[DiscoveredSource]) -> float:
    """Aggregate per-source credibility into an overall confidence score.

    Uses a diminishing-returns aggregation so multiple corroborating
    sources increase confidence without ever exceeding 1.0.
    """

    if not sources:
        return 0.0

    remaining = 1.0
    for source in sources:
        remaining *= (1.0 - max(0.0, min(1.0, source.credibility_score)))
    return round(1.0 - remaining, 4)


# ---------------------------------------------------------------------------
# Prompt construction & response parsing
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an OSINT research assistant. You gather and structure ONLY "
    "publicly available, open-source information about public figures and "
    "officials. Always cite source URLs. Never fabricate facts. If a fact "
    "cannot be verified from public sources, omit it or mark it as "
    "uncertain. Respond with strict JSON only."
)

_JSON_INSTRUCTION = (
    "Return a JSON object with exactly these keys: "
    '"full_name" (string), "aliases" (string[]), "summary" (string), '
    '"current_position" (string), "previous_positions" (string[]), '
    '"current_roles" (string[]), "previous_roles" (string[]), '
    '"activities" (string[]), "statements" (string[]), '
    '"photo_url" (string|null), '
    '"sources" (array of objects with "url", "title", "snippet"). '
    "Do not include markdown fences or any commentary outside the JSON."
)


def build_lookup_prompt(
    full_name: str,
    *,
    context_hints: Optional[List[str]] = None,
    locale: str = "fa",
) -> str:
    """Build the user prompt for a person lookup request."""

    hints = ""
    if context_hints:
        joined = "; ".join(h for h in context_hints if h)
        if joined:
            hints = f"\nAdditional context to disambiguate: {joined}."

    return (
        f"Gather open-source intelligence about the person: \"{full_name}\".{hints}\n"
        f"Preferred response language: {locale}.\n"
        "Collect: current position, previous positions, current and former "
        "roles, notable activities, public statements/positions, and a "
        "representative public photo URL if available.\n\n"
        f"{_JSON_INSTRUCTION}"
    )


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort extraction of a JSON object from an LLM response."""

    if not text:
        return None

    candidate = text.strip()

    # Strip markdown code fences if present.
    fence_match = _JSON_FENCE_RE.search(candidate)
    if fence_match:
        candidate = fence_match.group(1).strip()

    # Try direct parse first.
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fall back to locating the first balanced { ... } block.
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = candidate[start : end + 1]
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None

    return None


def _as_str(value: Any) -> Optional[str]:
    """تبدیل امن یک مقدار به رشته (یا None)."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _as_str_list(value: Any) -> List[str]:
    """تبدیل امن یک مقدار به فهرستی از رشته‌ها."""
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            s = _as_str(item)
            if s:
                out.append(s)
        return out
    return []


def parse_person_record(
    full_name: str,
    payload: Dict[str, Any],
    *,
    raw_text: Optional[str] = None,
) -> PersonRecord:
    """یک payload (dict) خروجی مدل را به PersonRecord ساختاریافته تبدیل می‌کند."""
    sources: List[DiscoveredSource] = []
    for src in payload.get("sources") or []:
        if isinstance(src, dict):
            url = _as_str(src.get("url"))
            if not url:
                continue
            sources.append(
                DiscoveredSource(
                    url=url,
                    title=_as_str(src.get("title")),
                    snippet=_as_str(src.get("snippet")),
                )
            )
        else:
            url = _as_str(src)
            if url:
                sources.append(DiscoveredSource(url=url))

    sources = score_sources(sources)

    record = PersonRecord(
        full_name=_as_str(payload.get("full_name")) or full_name,
        aliases=_as_str_list(payload.get("aliases")),
        summary=_as_str(payload.get("summary")),
        current_position=_as_str(payload.get("current_position")),
        previous_positions=_as_str_list(payload.get("previous_positions")),
        current_roles=_as_str_list(payload.get("current_roles")),
        previous_roles=_as_str_list(payload.get("previous_roles")),
        activities=_as_str_list(payload.get("activities")),
        statements=_as_str_list(payload.get("statements")),
        photo_url=_as_str(payload.get("photo_url")),
        sources=sources,
        raw_model_text=raw_text,
    )
    record.confidence = aggregate_confidence(sources)
    return record


def _coerce_llm_text(result: Any) -> Optional[str]:
    """متنِ خروجی را از پاسخ مدل (با اشکال مختلف) استخراج می‌کند."""
    if result is None:
        return None
    if isinstance(result, str):
        return result
    for attr in ("text", "content", "output_text", "answer"):
        val = getattr(result, attr, None)
        if isinstance(val, str) and val:
            return val
    if isinstance(result, dict):
        for key in ("text", "content", "output", "message", "answer"):
            val = result.get(key)
            if isinstance(val, str) and val:
                return val
    return str(result)


def _invoke_llm(
    llm: Any, system_prompt: str, user_prompt: str
) -> Optional[str]:
    """فراخوانی دفاعی LLM adapter پروژه.

    چون امضای دقیق adapter ممکن است متفاوت باشد، چند شکل رایج فراخوانی را
    امتحان می‌کنیم و در صورت ناتوانی به‌صورت امن None برمی‌گردانیم. پاسخ
    coroutine نیز به‌صورت همگام اجرا می‌شود (مناسب برای task های Celery).
    """
    callables: List[Any] = []
    for method_name in ("complete", "generate", "chat", "ask", "run"):
        method = getattr(llm, method_name, None)
        if callable(method):
            callables.append(method)
    if not callables and callable(llm):
        callables.append(llm)

    for method in callables:
        for args, kwargs in (
            ((user_prompt,), {"system": system_prompt}),
            ((user_prompt,), {"system_prompt": system_prompt}),
            ((user_prompt,), {}),
            ((system_prompt, user_prompt), {}),
        ):
            try:
                res = method(*args, **kwargs)
            except TypeError:
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM invocation failed: %s", exc)
                break
            if asyncio.iscoroutine(res):
                try:
                    res = asyncio.run(res)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("LLM async invocation failed: %s", exc)
                    break
            return _coerce_llm_text(res)
    return None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
class OSINTAgent:
    """عامل خودکار جمع‌آوری اطلاعات منبع‌باز دربارهٔ یک شخص.

    از LLM adapter پروژه برای پرس‌وجو استفاده می‌کند، خروجی JSON را پارس کرده و
    یک PersonRecord ساختاریافته با منابع امتیازدهی‌شده برمی‌گرداند. اگر LLM
    پیکربندی نشده باشد، یک رکورد معتبرِ خالی (confidence=0) برمی‌گرداند تا
    جریان فراخواننده نشکند.
    """

    def __init__(self, llm: Any = None) -> None:
        self.llm = llm

    def _resolve_llm(self) -> Any:
        if self.llm is not None:
            return self.llm
        try:
            self.llm = LLMAdapter()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM adapter unavailable for OSINT agent: %s", exc)
            self.llm = None
        return self.llm

    def gather(
        self,
        full_name: str,
        *,
        context_hints: Optional[List[str]] = None,
        locale: str = "fa",
    ) -> PersonRecord:
        """اطلاعات منبع‌باز یک شخص را جمع‌آوری و ساختارمند می‌کند."""
        llm = self._resolve_llm()
        if llm is None:
            return PersonRecord(full_name=full_name, confidence=0.0)

        prompt = build_lookup_prompt(
            full_name, context_hints=context_hints, locale=locale
        )
        raw_text = _invoke_llm(llm, _SYSTEM_PROMPT, prompt)
        if not raw_text:
            return PersonRecord(full_name=full_name, confidence=0.0)

        payload = _extract_json_payload(raw_text) or {}
        return parse_person_record(full_name, payload, raw_text=raw_text)


def gather_person_intelligence(
    full_name: str,
    *,
    llm: Any = None,
    context_hints: Optional[List[str]] = None,
    locale: str = "fa",
) -> PersonRecord:
    """تابع راحت ماژول‌سطح برای جمع‌آوری اطلاعات یک شخص."""
    return OSINTAgent(llm=llm).gather(
        full_name, context_hints=context_hints, locale=locale
    )


__all__ = [
    "RiskCategory",
    "SourceCredibility",
    "DiscoveredSource",
    "PersonRecord",
    "assess_source_credibility",
    "credibility_to_score",
    "score_sources",
    "aggregate_confidence",
    "build_lookup_prompt",
    "parse_person_record",
    "OSINTAgent",
    "gather_person_intelligence",
]