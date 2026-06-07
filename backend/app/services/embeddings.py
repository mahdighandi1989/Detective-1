"""
embeddings.py — تولید embedding و جستجوی معنایی روی دانشنامهٔ اطلاعاتی.

این ماژول مسئول:
  1. تولید بردارهای embedding از متن مقالات/محتوای دانشنامه با استفاده از
     یک provider قابل‌تعویض (OpenAI / Gemini / مدل محلی) از طریق abstraction.
  2. ذخیره و جستجوی این بردارها در PostgreSQL با افزونهٔ pgvector.
  3. ارائهٔ جستجوی معنایی (semantic search) با cosine similarity.

اصلاح مهم نسبت به نسخهٔ قبلی:
  - این ماژول دیگر یک `declarative_base` محلی یا موتور SQLAlchemy مستقل
    نمی‌سازد و در fallback مدل `Article` ساختگی تعریف نمی‌کند.
  - تمام دسترسی‌های دیتابیس از طریق session factory پروژه
    (`app.db.session`) و مدل واقعی `app.models.article.Article` انجام
    می‌شود تا از تعریف موازی schema جلوگیری شود.
  - اگر این وابستگی‌ها در محیط در دسترس نباشند (مثلاً در حین unit-test
    ایزوله)، عملیات‌های مربوط به دیتابیس به‌صورت امن غیرفعال می‌شوند و
    تنها بخش تولید embedding (با fallback قطعی) فعال می‌ماند — بدون ساخت
    Base یا engine موازی.

اصلاح این نسخه (رفع یافتهٔ audit):
  - مشکل قبلی: وقتی pgvector در دسترس نبود، مدل `Article` به JSONB
    fallback می‌کرد و مسیر جستجوی معنایی به‌صورت «خاموش» (silent) عملاً
    غیرفعال می‌شد بدون هیچ هشدار، طوریکه ستون semantic search
    غیرقابل‌جستجو می‌ماند.
  - رفع: pgvector اکنون به‌عنوان مسیر اصلی و توصیه‌شده در نظر گرفته شده
    (در docker از image `pgvector/pgvector` استفاده می‌شود). اگر pgvector
    در دسترس نبود:
      * یک‌بار هشدار صریح (`logger.warning`) ثبت می‌شود تا fallback
        دیگر «خاموش» نباشد.
      * به‌جای غیرفعال‌کردن جستجو، یک مسیر fallback **فعال** برای
        جستجوی معنایی پیاده‌سازی شده است که بردارها را از ستون JSONB
        می‌خواند و cosine similarity را در سطح Python محاسبه می‌کند.
        این مسیر کندتر است ولی جستجو را عملاً کار می‌اندازد (نه خاموش).

طراحی به‌گونه‌ای است که اگر API key واقعی provider در محیط تنظیم نشده باشد،
یک fallback قطعی (deterministic local hashing embedding) فعال می‌شود تا
توسعه/تست بدون نیاز به سرویس خارجی ممکن باشد.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# ابعاد پیش‌فرض بردار embedding. با text-embedding-3-small (OpenAI) سازگار است.
DEFAULT_EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

# آستانهٔ پیش‌فرض شباهت برای فیلتر نتایج جستجو.
DEFAULT_SIMILARITY_THRESHOLD = float(os.getenv("EMBEDDING_SIMILARITY_THRESHOLD", "0.0"))


# ---------------------------------------------------------------------------
# تلاش برای import وابستگی‌های واقعی پروژه به‌صورت امن.
# اگر در محیط ایزولهٔ تست در دسترس نباشند، None باقی می‌مانند و عملیات‌های
# دیتابیس به‌صورت no-op امن رفتار می‌کنند (بدون ساخت Base/engine موازی).
# ---------------------------------------------------------------------------
try:  # session factory واقعی پروژه
    from app.db.session import SessionLocal  # type: ignore
except Exception:  # pragma: no cover - محیط ایزوله
    SessionLocal = None  # type: ignore

try:  # مدل واقعی Article
    from app.models.article import Article  # type: ignore
except Exception:  # pragma: no cover - محیط ایزوله
    Article = None  # type: ignore

try:  # تنظیمات پروژه (اختیاری)
    from app.core.config import settings  # type: ignore
except Exception:  # pragma: no cover - محیط ایزوله
    settings = None  # type: ignore


def _get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    """خواندن مقدار تنظیمات از settings پروژه یا متغیر محیطی به‌صورت امن."""
    if settings is not None:
        value = getattr(settings, name, None)
        if value is not None:
            return str(value)
    return os.getenv(name, default)


# ---------------------------------------------------------------------------
# تشخیص در دسترس بودن pgvector.
# ---------------------------------------------------------------------------
def _pgvector_available() -> bool:
    """آیا کتابخانهٔ pgvector برای استفاده در ORM در دسترس است؟"""
    try:
        import pgvector  # noqa: F401  # type: ignore

        return True
    except Exception:
        return False


_PGVECTOR_AVAILABLE = _pgvector_available()
_PGVECTOR_WARNING_EMITTED = False


def _warn_pgvector_fallback_once() -> None:
    """فقط یک‌بار هشدار صریح می‌دهد که fallback جستجوی Python فعال است."""
    global _PGVECTOR_WARNING_EMITTED
    if not _PGVECTOR_WARNING_EMITTED:
        logger.warning(
            "pgvector در دسترس نیست؛ جستجوی معنایی از مسیر fallback فعال "
            "(محاسبهٔ cosine similarity در سطح Python روی ستون JSONB) استفاده "
            "می‌کند. این مسیر کندتر است ولی جستجو خاموش نمی‌شود. برای "
            "عملکرد بهتر، افزونهٔ pgvector را نصب/فعال کنید "
            "(image: pgvector/pgvector)."
        )
        _PGVECTOR_WARNING_EMITTED = True


# ---------------------------------------------------------------------------
# Embedding providers (abstraction قابل‌تعویض)
# ---------------------------------------------------------------------------
@dataclass
class EmbeddingResult:
    """نتیجهٔ تولید embedding برای یک متن."""

    vector: List[float]
    model: str
    dim: int


class BaseEmbeddingProvider:
    """رابط پایه برای provider های embedding."""

    name: str = "base"

    def embed(self, text: str) -> EmbeddingResult:  # pragma: no cover - abstract
        raise NotImplementedError

    def embed_batch(self, texts: Sequence[str]) -> List[EmbeddingResult]:
        return [self.embed(t) for t in texts]


class DeterministicLocalProvider(BaseEmbeddingProvider):
    """
    fallback قطعی (deterministic) بدون نیاز به سرویس خارجی.

    از hashing روی توکن‌ها برای تولید یک بردار پایدار و قابل‌تکرار استفاده
    می‌کند. مناسب برای توسعه/تست؛ کیفیت معنایی واقعی ندارد ولی پایدار است.
    """

    name = "local-deterministic"

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        self.dim = dim

    def embed(self, text: str) -> EmbeddingResult:
        vector = [0.0] * self.dim
        normalized = (text or "").strip().lower()
        if not normalized:
            return EmbeddingResult(vector=vector, model=self.name, dim=self.dim)

        tokens = normalized.split()
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            # از چند بایت برای انتخاب index و علامت استفاده می‌کنیم.
            for i in range(0, len(digest), 4):
                chunk = digest[i : i + 4]
                if len(chunk) < 4:
                    break
                idx = int.from_bytes(chunk[:2], "big") % self.dim
                sign = 1.0 if chunk[2] % 2 == 0 else -1.0
                magnitude = (chunk[3] / 255.0)
                vector[idx] += sign * magnitude

        return EmbeddingResult(
            vector=_normalize_vector(vector), model=self.name, dim=self.dim
        )


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """provider مبتنی بر OpenAI embeddings."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dim: int = DEFAULT_EMBEDDING_DIM,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # type: ignore

            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def embed(self, text: str) -> EmbeddingResult:
        client = self._get_client()
        response = client.embeddings.create(
            model=self.model,
            input=text or " ",
        )
        vector = list(response.data[0].embedding)
        return EmbeddingResult(vector=vector, model=self.model, dim=len(vector))

    def embed_batch(self, texts: Sequence[str]) -> List[EmbeddingResult]:
        if not texts:
            return []
        client = self._get_client()
        response = client.embeddings.create(
            model=self.model,
            input=[t or " "