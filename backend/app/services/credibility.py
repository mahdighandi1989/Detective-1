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