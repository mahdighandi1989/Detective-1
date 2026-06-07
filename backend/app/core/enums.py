"""
Centralized enumerations for the Detective-1 OSINT platform.

These enums are used across models, schemas, services, and the API layer to
ensure a single source of truth for all categorical values (roles, risk
levels, classification levels, etc.).

NOTE: All enums inherit from `str` so they serialize cleanly to JSON and play
nicely with SQLAlchemy/Pydantic and FastAPI response models.
"""

from __future__ import annotations

from enum import Enum
from typing import List


class BaseStrEnum(str, Enum):
    """Base class for all string enums with shared helper methods."""

    @classmethod
    def values(cls) -> List[str]:
        """Return the list of all enum string values."""
        return [member.value for member in cls]

    @classmethod
    def names_list(cls) -> List[str]:
        """Return the list of all enum member names."""
        return [member.name for member in cls]

    @classmethod
    def has_value(cls, value: str) -> bool:
        """Return True if the given value is a valid member value."""
        return value in cls._value2member_map_

    @classmethod
    def from_value(cls, value: str) -> "BaseStrEnum":
        """Return the enum member matching `value`, raising ValueError if not found."""
        if not cls.has_value(value):
            raise ValueError(
                f"{value!r} is not a valid {cls.__name__}. "
                f"Valid values: {cls.values()}"
            )
        return cls(value)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# ---------------------------------------------------------------------------
# Authentication / Access Control
# ---------------------------------------------------------------------------
class UserRole(BaseStrEnum):
    """
    Role-based access control (RBAC) roles.

    - ADMIN:    Full system control, user management, settings.
    - ANALYST:  Can create/edit persons, articles, run analyses & agents.
    - REVIEWER: Can review/validate data and approve risk assessments.
    - VIEWER:   Read-only access to permitted resources.
    """

    ADMIN = "admin"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    # Additional roles referenced across the codebase (deps.py / models). Kept
    # here as the single source of truth so RBAC references resolve consistently.
    INVESTIGATOR = "investigator"
    OSINT_AGENT = "osint_agent"
    OPERATOR = "operator"
    VIEWER = "viewer"


class ClassificationLevel(BaseStrEnum):
    """
    Confidentiality / classification levels for sensitive data.

    Ordered from least to most restrictive (use `level_index` for ordering).
    """

    UNCLASSIFIED = "unclassified"
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"

    @property
    def level_index(self) -> int:
        """Numeric ordering of classification (higher = more restricted)."""
        order = {
            ClassificationLevel.UNCLASSIFIED: 0,
            ClassificationLevel.PUBLIC: 1,
            ClassificationLevel.INTERNAL: 2,
            ClassificationLevel.RESTRICTED: 3,
            ClassificationLevel.CONFIDENTIAL: 4,
            ClassificationLevel.SECRET: 5,
            ClassificationLevel.TOP_SECRET: 6,
        }
        return order.get(self, 0)

    def can_access(self, clearance: "ClassificationLevel") -> bool:
        """Return True if a user with `clearance` may access data at this level."""
        return clearance.level_index >= self.level_index


# ---------------------------------------------------------------------------
# Person / Profile
# ---------------------------------------------------------------------------
class RiskLevel(BaseStrEnum):
    """
    Risk classification used to color-code persons in the relationship graph.

    Maps to the categories described in the project requirements:
    پاک / مشکوک / استحاله‌یافته / اطلاعاتی / نفوذی
    """

    CLEAN = "clean"            # پاک
    LOW = "low"
    SUSPICIOUS = "suspicious"  # مشکوک
    DEGRADED = "degraded"      # استحاله‌یافته (compromised/turned)
    INTELLIGENCE = "intelligence"  # اطلاعاتی
    INFILTRATOR = "infiltrator"    # نفوذی / جاسوس
    UNKNOWN = "unknown"

    @property
    def color(self) -> str:
        """Hex color used for graph node coloring based on risk level."""
        colors = {
            RiskLevel.CLEAN: "#22c55e",          # green
            RiskLevel.LOW: "#84cc16",            # lime
            RiskLevel.SUSPICIOUS: "#f59e0b",     # amber
            RiskLevel.DEGRADED: "#f97316",       # orange
            RiskLevel.INTELLIGENCE: "#a855f7",   # purple
            RiskLevel.INFILTRATOR: "#ef4444",    # red
            RiskLevel.UNKNOWN: "#9ca3af",        # gray
        }
        return colors[self]

    @property
    def severity(self) -> int:
        """Numeric severity (higher = more dangerous). Useful for sorting."""
        severities = {
            RiskLevel.CLEAN: 0,
            RiskLevel.LOW: 1,
            RiskLevel.UNKNOWN: 2,
            RiskLevel.SUSPICIOUS: 3,
            RiskLevel.DEGRADED: 4,
            RiskLevel.INTELLIGENCE: 5,
            RiskLevel.INFILTRATOR: 6,
        }
        return severities[self]


class ProfileStatus(BaseStrEnum):
    """Lifecycle status of a person profile."""

    DRAFT = "draft"
    PENDING_RESEARCH = "pending_research"  # queued for OSINT agent
    RESEARCHING = "researching"            # agent currently gathering data
    UNDER_REVIEW = "under_review"          # awaiting reviewer validation
    VERIFIED = "verified"
    ARCHIVED = "archived"


class PositionType(BaseStrEnum):
    """Whether a position/role held by a person is current or historical."""

    CURRENT = "current"
    PREVIOUS = "previous"


class Gender(BaseStrEnum):
    """Gender of a person (kept optional/unknown by default)."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Encyclopedia / Articles
# ---------------------------------------------------------------------------
class ContentState(BaseStrEnum):
    """
    Whether encyclopedia content is raw (خام) or processed/summarized (پخته).
    """

    RAW = "raw"            # خام
    PROCESSED = "processed"  # پخته / خلاصه‌شده / دسته‌بندی‌شده
    SUMMARIZED = "summarized"


class ArticleCategory(BaseStrEnum):
    """High-level intelligence subject categories for encyclopedia articles."""

    INFILTRATION = "infiltration"            # نفوذ
    INFILTRATION_SKILLS = "infiltration_skills"  # مهارت‌های نفوذ
    INTELLIGENCE = "intelligence"            # اطلاعات
    COUNTER_INTELLIGENCE = "counter_intelligence"  # ضد جاسوسی
    ESPIONAGE = "espionage"                  # جاسوسی
    TRADECRAFT = "tradecraft"                # فنون اطلاعاتی
    PROFILE = "profile"                      # مرتبط با پروفایل اشخاص
    GENERAL = "general"
    OTHER = "other"


class ArticleStatus(BaseStrEnum):
    """Publication/processing lifecycle of an encyclopedia article."""

    DRAFT = "draft"
    PROCESSING = "processing"  # being categorized/summarized by LLM
    PUBLISHED = "published"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Sources / Credibility
# ---------------------------------------------------------------------------
class SourceType(BaseStrEnum):
    """Type of OSINT source from which information was gathered."""

    WEBSITE = "website"
    NEWS = "news"
    SOCIAL_MEDIA = "social_media"
    GOVERNMENT = "government"
    OFFICIAL_DOCUMENT = "official_document"
    ACADEMIC = "academic"
    DATABASE = "database"
    LLM_SEARCH = "llm_search"  # gathered via Perplexity/Sonar/etc.
    MANUAL = "manual"          # entered by an analyst
    OTHER = "other"


class CredibilityLevel(BaseStrEnum):
    """
    Qualitative credibility rating of a source.

    Use `score_range` for mapping to the numeric credibility score (0-100).
    """

    UNVERIFIED = "unverified"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"

    @property
    def score_range(self) -> tuple[int, int]:
        """Return the (min, max) numeric score range for this level."""
        ranges = {
            CredibilityLevel.UNVERIFIED: (0, 19),
            CredibilityLevel.LOW: (20, 39),
            CredibilityLevel.MEDIUM: (40, 64),
            CredibilityLevel.HIGH: (65, 84),
            CredibilityLevel.VERIFIED: (85, 100),
        }
        return ranges[self]

    @classmethod
    def from_score(cls, score: int) -> "CredibilityLevel":
        """Map a numeric credibility score (0-100) to a credibility level."""
        score = max(0, min(100, int(score)))
        for level in cls:
            lo, hi = level.score_range
            if lo <= score <= hi:
                return level
        return cls.UNVERIFIED


class VerificationStatus(BaseStrEnum):
    """Validation state of a piece of gathered information."""

    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"
    DISPUTED = "disputed"
    NEEDS_REVIEW = "needs_review"


# ---------------------------------------------------------------------------
# Background Jobs / OSINT Agent
# ---------------------------------------------------------------------------
class TaskStatus(BaseStrEnum):
    """Status of a background (Celery) job."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class TaskType(BaseStrEnum):
    """Type of background task processed by the worker queue."""

    OSINT_RESEARCH = "osint_research"          # gather person records
    ARTICLE_SUMMARIZE = "article_summarize"    # LLM summarize/classify
    ARTICLE_CATEGORIZE = "article_categorize"
    EMBEDDING_INDEX = "embedding_index"        # build/update embeddings
    RISK_ASSESSMENT = "risk_assessment"        # run risk engine
    SOURCE_VALIDATION = "source_validation"    # validate/score sources


class LLMProvider(BaseStrEnum):
    """Supported LLM / search providers for the integration adapter."""

    OPENAI = "openai"
    PERPLEXITY = "perplexity"
    SONAR = "sonar"
    GEMINI = "gemini"