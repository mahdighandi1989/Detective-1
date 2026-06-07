"""
Source credibility scoring service for Detective-1.

این ماژول مسئول امتیازدهی اعتبار منابع (OSINT source credibility scoring) است.
بر اساس فاکتورهای متعدد (دامنه، نوع منبع، تازگی، تأییدهای متقاطع، شهرت،
سابقهٔ صحت) یک امتیاز ۰..۱ و یک سطح اعتبار (CredibilityTier) محاسبه می‌کند.

این سرویس توسط osint_agent.py برای اعتبارسنجی سوابق جمع‌آوری‌شده از منابع باز
اینترنتی استفاده می‌شود و نتیجهٔ آن روی فیلدهای مدل Source ذخیره می‌گردد.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional
from urllib.parse import urlparse

__all__ = [
    "CredibilityTier",
    "SourceType",
    "CredibilitySignal",
    "CredibilityResult",
    "CredibilityScorer",
    "score_source",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class CredibilityTier(str, Enum):
    """سطح اعتبار نهایی یک منبع."""

    UNRELIABLE = "unreliable"   # 0.00 - 0.20
    LOW = "low"                 # 0.20 - 0.40
    MEDIUM = "medium"           # 0.40 - 0.60
    HIGH = "high"               # 0.60 - 0.80
    VERIFIED = "verified"       # 0.80 - 1.00

    @classmethod
    def from_score(cls, score: float) -> "CredibilityTier":
        score = max(0.0, min(1.0, float(score)))
        if score < 0.20:
            return cls.UNRELIABLE
        if score < 0.40:
            return cls.LOW
        if score < 0.60:
            return cls.MEDIUM
        if score < 0.80:
            return cls.HIGH
        return cls.VERIFIED


class SourceType(str, Enum):
    """نوع منبع اطلاعاتی."""

    OFFICIAL = "official"           # سایت رسمی دولتی/سازمانی
    NEWS_AGENCY = "news_agency"     # خبرگزاری معتبر
    ACADEMIC = "academic"           # منبع دانشگاهی/علمی
    ENCYCLOPEDIA = "encyclopedia"   # دانشنامه (ویکی‌پدیا و ...)
    NEWS = "news"                   # سایت خبری عمومی
    BLOG = "blog"                   # وبلاگ
    SOCIAL_MEDIA = "social_media"   # شبکه‌های اجتماعی
    FORUM = "forum"                 # انجمن‌ها
    LLM_GENERATED = "llm_generated" # تولیدشده توسط مدل زبانی
    UNKNOWN = "unknown"

    @property
    def base_weight(self) -> float:
        """وزن پایهٔ اعتبار بر اساس نوع منبع (۰..۱)."""
        return {
            SourceType.OFFICIAL: 0.90,
            SourceType.ACADEMIC: 0.85,
            SourceType.NEWS_AGENCY: 0.75,
            SourceType.ENCYCLOPEDIA: 0.65,
            SourceType.NEWS: 0.55,
            SourceType.FORUM: 0.35,
            SourceType.BLOG: 0.30,
            SourceType.SOCIAL_MEDIA: 0.25,
            SourceType.LLM_GENERATED: 0.20,
            SourceType.UNKNOWN: 0.30,
        }[self]


# ---------------------------------------------------------------------------
# Domain reputation tables
# ---------------------------------------------------------------------------
# دامنه‌های شناخته‌شده با شهرت بالا/مشخص. مقادیر یک "boost" یا "penalty"
# نسبت به وزن پایهٔ نوع منبع هستند (محدودهٔ -0.5 .. +0.5).
_DOMAIN_REPUTATION: dict[str, float] = {
    # خبرگزاری‌ها / منابع بین‌المللی معتبر
    "reuters.com": 0.20,
    "apnews.com": 0.20,
    "bbc.com": 0.18,
    "bbc.co.uk": 0.18,
    "afp.com": 0.18,
    "theguardian.com": 0.12,
    "nytimes.com": 0.12,
    "washingtonpost.com": 0.12,
    "aljazeera.com": 0.10,
    # دانشنامه‌ها
    "wikipedia.org": 0.05,
    "britannica.com": 0.10,
    # دانشگاهی
    "scholar.google.com": 0.15,
    "jstor.org": 0.18,
    "arxiv.org": 0.12,
    # شبکه‌های اجتماعی (penalty)
    "twitter.com": -0.10,
    "x.com": -0.10,
    "facebook.com": -0.12,
    "instagram.com": -0.15,
    "t.me": -0.18,
    "telegram.org": -0.18,
    "tiktok.com": -0.20,
    # محتوای کاربرساخته
    "medium.com": -0.05,
    "blogspot.com": -0.10,
    "wordpress.com": -0.10,
    "reddit.com": -0.08,
    "quora.com": -0.08,
}

# پسوندهای دامنه که اعتبار را تعدیل می‌کنند.
_TLD_REPUTATION: dict[str, float] = {
    ".gov": 0.15,
    ".gov.ir": 0.15,
    ".edu": 0.12,
    ".ac.ir": 0.12,
    ".org": 0.03,
    ".mil": 0.10,
}

# الگوهای دامنه‌ای که نشان‌دهندهٔ نوع منبع هستند (heuristic).
_OFFICIAL_HINTS = re.compile(
    r"(gov|ministry|presidency|parliament|majlis|official)", re.IGNORECASE
)
_ACADEMIC_HINTS = re.compile(r"(edu|ac\.|univ|academy|scholar|research)", re.IGNORECASE)
_NEWS_AGENCY_HINTS = re.compile(
    r"(reuters|apnews|afp|irna|isna|tasnim|farsnews|mehrnews|bbc)", re.IGNORECASE
)
_SOCIAL_HINTS = re.compile(
    r"(twitter|x\.com|facebook|instagram|tiktok|t\.me|telegram|linkedin)",
    re.IGNORECASE,
)
_FORUM_HINTS = re.compile(r"(forum|reddit|quora|stackexchange)", re.IGNORECASE)
_BLOG_HINTS = re.compile(r"(blog|medium|wordpress|blogspot|substack)", re.IGNORECASE)
_WIKI_HINTS = re.compile(r"(wikipedia|britannica|wikimedia|fandom)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CredibilitySignal:
    """یک سیگنال (فاکتور) که در امتیاز نهایی نقش دارد."""

    name: str
    value: float          # سهم نرمال‌شدهٔ این سیگنال (می‌تواند منفی باشد)
    weight: float         # وزن این سیگنال در میانگین وزن‌دار
    explanation: str = ""

    @property
    def contribution(self) -> float:
        return self.value * self.weight


@dataclass
class CredibilityResult:
    """نتیجهٔ کامل امتیازدهی اعتبار یک منبع."""

    score: float
    tier: CredibilityTier
    source_type: SourceType
    signals: list[CredibilitySignal] = field(default_factory=list)
    domain: Optional[str] = None
    assessed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "tier": self.tier.value,
            "source_type": self.source_type.value,
            "domain": self.domain,
            "assessed_at": self.assessed_at.isoformat(),
            "signals": [
                {
                    "name": s.name,
                    "value": round(s.value, 4),
                    "weight": s.weight,
                    "contribution": round(s.contribution, 4),
                    "explanation": s.explanation,
                }
                for s in self.signals
            ],
        }


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------
class CredibilityScorer:
    """
    موتور امتیازدهی اعتبار منابع.

    استفاده:
        scorer = CredibilityScorer()
        result = scorer.score(
            url="https://www.reuters.com/world/...",
            source_type=SourceType.NEWS_AGENCY,
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            cross_references=3,
            historical_accuracy=0.8,
        )
    """

    # وزن هر سیگنال در میانگین وزن‌دار نهایی.
    DEFAULT_WEIGHTS: dict[str, float] = {
        "source_type": 0.30,
        "domain_reputation": 0.20,
        "recency": 0.12,
        "cross_reference": 0.18,
        "historical_accuracy": 0.12,
        "content_quality": 0.08,
    }

    # نیمه‌عمر تازگی برحسب روز (پس از این مدت اثر تازگی نصف می‌شود).
    RECENCY_HALF_LIFE_DAYS = 365.0

    def __init__(self, weights: Optional[dict[str, float]] = None) -> None:
        self.weights = dict(self.DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)

    # -- public API ---------------------------------------------------------
    def score(
        self,
        *,
        url: Optional[str] = None,
        source_type: Optional[SourceType] = None,
        published_at: Optional[datetime] = None,
        cross_references: int = 0,
        historical_accuracy: Optional[float] = None,
        content_length: Optional[int] = None,
        has_author: bool = False,
        has_citations: bool = False,
        now: Optional[datetime] = None,
    ) -> CredibilityResult:
        """امتیاز اعتبار یک منبع را بر اساس فاکتورهای متعدد محاسبه می‌کند."""
        now = now or datetime.now(timezone.utc)
        domain = self._extract_domain(url)
        resolved_type = source_type or self._infer_source_type(url, domain)

        signals: list[CredibilitySignal] = []

        # 1) نوع منبع
        signals.append(
            CredibilitySignal(
                name="source_type",
                value=resolved_type.base_weight,
                weight=self.weights.get("source_type", 0.0),
                explanation=f"نوع منبع: {resolved_type.value}",
            )
        )

        # 2) شهرت دامنه (baseline 0.5 ± تعدیل)
        rep_adj = self._domain_reputation(domain)
        signals.append(
            CredibilitySignal(
                name="domain_reputation",
                value=_clamp(0.5 + rep_adj, 0.0, 1.0),
                weight=self.weights.get("domain_reputation", 0.0),
                explanation=f"شهرت دامنه ({domain or 'نامشخص'}): adj={rep_adj:+.2f}",
            )
        )

        # 3) تازگی (decay نمایی با نیمه‌عمر)
        signals.append(
            CredibilitySignal(
                name="recency",
                value=self._recency_score(published_at, now),
                weight=self.weights.get("recency", 0.0),
                explanation="تازگی منبع بر اساس تاریخ انتشار",
            )
        )

        # 4) تأییدهای متقاطع
        signals.append(
            CredibilitySignal(
                name="cross_reference",
                value=_clamp(cross_references / 5.0, 0.0, 1.0),
                weight=self.weights.get("cross_reference", 0.0),
                explanation=f"{cross_references} تأیید متقاطع",
            )
        )

        # 5) سابقهٔ صحت تاریخی
        signals.append(
            CredibilitySignal(
                name="historical_accuracy",
                value=(
                    _clamp(historical_accuracy, 0.0, 1.0)
                    if historical_accuracy is not None
                    else 0.5
                ),
                weight=self.weights.get("historical_accuracy", 0.0),
                explanation="سابقهٔ صحت منبع/دامنه",
            )
        )

        # 6) کیفیت محتوا (طول، نویسنده، ارجاعات)
        signals.append(
            CredibilitySignal(
                name="content_quality",
                value=self._content_quality(content_length, has_author, has_citations),
                weight=self.weights.get("content_quality", 0.0),
                explanation="کیفیت محتوا (طول/نویسنده/ارجاعات)",
            )
        )

        total_weight = sum(s.weight for s in signals) or 1.0
        final_score = _clamp(
            sum(s.contribution for s in signals) / total_weight, 0.0, 1.0
        )

        return CredibilityResult(
            score=final_score,
            tier=CredibilityTier.from_score(final_score),
            source_type=resolved_type,
            signals=signals,
            domain=domain,
            assessed_at=now,
        )

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _extract_domain(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        try:
            netloc = urlparse(
                url if "://" in url else f"http://{url}"
            ).netloc.lower()
        except Exception:
            return None
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or None

    def _domain_reputation(self, domain: Optional[str]) -> float:
        if not domain:
            return 0.0
        adj = 0.0
        for known, value in _DOMAIN_REPUTATION.items():
            if domain == known or domain.endswith("." + known):
                adj += value
                break
        for tld, value in _TLD_REPUTATION.items():
            if domain.endswith(tld):
                adj += value
                break
        return _clamp(adj, -0.5, 0.5)

    @staticmethod
    def _infer_source_type(url: Optional[str], domain: Optional[str]) -> SourceType:
        hay = f"{url or ''} {domain or ''}"
        if _OFFICIAL_HINTS.search(hay):
            return SourceType.OFFICIAL
        if _NEWS_AGENCY_HINTS.search(hay):
            return SourceType.NEWS_AGENCY
        if _ACADEMIC_HINTS.search(hay):
            return SourceType.ACADEMIC
        if _WIKI_HINTS.search(hay):
            return SourceType.ENCYCLOPEDIA
        if _SOCIAL_HINTS.search(hay):
            return SourceType.SOCIAL_MEDIA
        if _FORUM_HINTS.search(hay):
            return SourceType.FORUM
        if _BLOG_HINTS.search(hay):
            return SourceType.BLOG
        return SourceType.UNKNOWN

    def _recency_score(
        self, published_at: Optional[datetime], now: datetime
    ) -> float:
        if published_at is None:
            return 0.5
        try:
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - published_at).total_seconds() / 86400.0)
        except Exception:
            return 0.5
        return _clamp(0.5 ** (age_days / self.RECENCY_HALF_LIFE_DAYS), 0.0, 1.0)

    @staticmethod
    def _content_quality(
        content_length: Optional[int], has_author: bool, has_citations: bool
    ) -> float:
        score = 0.0
        if content_length:
            score += _clamp(content_length / 4000.0, 0.0, 0.6)
        if has_author:
            score += 0.2
        if has_citations:
            score += 0.2
        return _clamp(score, 0.0, 1.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    """مقدار را در بازهٔ [lo, hi] محدود می‌کند."""
    return max(lo, min(hi, float(value)))


def score_source(
    *,
    url: Optional[str] = None,
    source_type: Optional[SourceType] = None,
    published_at: Optional[datetime] = None,
    cross_references: int = 0,
    historical_accuracy: Optional[float] = None,
    content_length: Optional[int] = None,
    has_author: bool = False,
    has_citations: bool = False,
    now: Optional[datetime] = None,
) -> CredibilityResult:
    """تابع راحت ماژول‌سطح: یک منبع را با CredibilityScorer پیش‌فرض امتیاز می‌دهد."""
    return CredibilityScorer().score(
        url=url,
        source_type=source_type,
        published_at=published_at,
        cross_references=cross_references,
        historical_accuracy=historical_accuracy,
        content_length=content_length,
        has_author=has_author,
        has_citations=has_citations,
        now=now,
    )