# backend/app/workers/tasks.py
"""
Background tasks for Detective-1.

این ماژول تسک‌های پس‌زمینهٔ Celery را تعریف می‌کند:
  - جستجوی OSINT برای جمع‌آوری سوابق افراد از منابع باز اینترنتی
  - اعتبارسنجی و امتیازدهی منابع (source credibility scoring)
  - دسته‌بندی و خلاصه‌سازی خودکار محتوای دانشنامه توسط LLM
  - تولید embedding برای جستجوی معنایی
  - ارزیابی ریسک پروفایل اشخاص بر اساس داده‌های دانشنامه

تمام تسک‌ها به‌صورت sync اجرا می‌شوند و از `SessionLocal` (session همگام)
استفاده می‌کنند، چون worker های Celery همگام هستند.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _session_scope() -> Session:
    """یک session همگام برای استفاده درون تسک‌های Celery باز می‌کند."""
    return SessionLocal()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lazy_import_services() -> dict[str, Any]:
    """
    Lazy import سرویس‌ها تا از import چرخه‌ای (circular import) و بارگذاری
    سنگین در زمان import ماژول جلوگیری شود. اگر سرویسی هنوز وجود نداشته
    باشد، با مقدار None برمی‌گردد تا تسک به‌صورت graceful شکست بخورد.
    """
    services: dict[str, Any] = {
        "llm_adapter": None,
        "osint_agent": None,
        "risk_engine": None,
        "embeddings": None,
    }
    try:
        from app.services import llm_adapter as _llm

        services["llm_adapter"] = _llm
    except Exception:  # noqa: BLE001
        logger.warning("llm_adapter service is not available yet.")
    try:
        from app.services import osint_agent as _osint

        services["osint_agent"] = _osint
    except Exception:  # noqa: BLE001
        logger.warning("osint_agent service is not available yet.")
    try:
        from app.services import risk_engine as _risk

        services["risk_engine"] = _risk
    except Exception:  # noqa: BLE001
        logger.warning("risk_engine service is not available yet.")
    try:
        from app.services import embeddings as _emb

        services["embeddings"] = _emb
    except Exception:  # noqa: BLE001
        logger.warning("embeddings service is not available yet.")
    return services


# ---------------------------------------------------------------------------
# Encyclopedia: classification & summarization
# ---------------------------------------------------------------------------
@celery_app.task(name="app.workers.tasks.classify_and_summarize_article", bind=True)
def classify_and_summarize_article(self, article_id: int) -> dict[str, Any]:
    """
    محتوای یک مقالهٔ دانشنامه را با LLM دسته‌بندی و خلاصه می‌کند و
    embedding آن را برای جستجوی معنایی تولید می‌کند.
    """
    services = _lazy_import_services()
    llm = services["llm_adapter"]
    emb = services["embeddings"]
    session = _session_scope()
    result: dict[str, Any] = {"article_id": article_id, "status": "skipped"}
    try:
        from app.models.article import Article  # local import to avoid cycles

        article = session.get(Article, article_id)
        if article is None:
            logger.warning("Article %s not found.", article_id)
            result["status"] = "not_found"
            return result

        raw_text = getattr(article, "content", None) or getattr(article, "body", "")
        if not raw_text:
            result["status"] = "empty"
            return result

        if llm is not None:
            try:
                summary = llm.summarize(raw_text)
                categories = llm.classify(raw_text)
                if hasattr(article, "summary"):
                    article.summary = summary
                if hasattr(article, "categories"):
                    article.categories = categories
                result["summary_generated"] = True
            except Exception as exc:  # noqa: BLE001
                logger.exception("LLM summarize/classify failed: %s", exc)
                result["llm_error"] = str(exc)

        if emb is not None:
            try:
                vector = emb.embed_text(raw_text)
                if hasattr(article, "embedding"):
                    article.embedding = vector
                result["embedding_generated"] = True
            except Exception as exc:  # noqa: BLE001
                logger.exception("Embedding generation failed: %s", exc)
                result["embedding_error"] = str(exc)

        if hasattr(article, "processed_at"):
            article.processed_at = _now()
        session.commit()
        result["status"] = "done"
        return result
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("classify_and_summarize_article failed: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)
        return result
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Encyclopedia: embedding regeneration
# ---------------------------------------------------------------------------
@celery_app.task(name="app.workers.tasks.generate_embedding", bind=True)
def generate_embedding(self, article_id: int) -> dict[str, Any]:
    """تولید/به‌روزرسانی embedding یک مقاله برای جستجوی معنایی."""
    services = _lazy_import_services()
    emb = services["embeddings"]
    session = _session_scope()
    result: dict[str, Any] = {"article_id": article_id, "status": "skipped"}
    try:
        from app.models.article import Article

        article = session.get(Article, article_id)
        if article is None:
            result["status"] = "not_found"
            return result
        raw_text = getattr(article, "content", None) or getattr(article, "body", "")
        if not raw_text or emb is None:
            result["status"] = "empty_or_no_service"
            return result
        vector = emb.embed_text(raw_text)
        if hasattr(article, "embedding"):
            article.embedding = vector
        session.commit()
        result["status"] = "done"
        return result
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("generate_embedding failed: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)
        return result
    finally:
        session.close()


# ---------------------------------------------------------------------------
# OSINT: collect person history from open sources
# ---------------------------------------------------------------------------
@celery_app.task(name="app.workers.tasks.collect_person_osint", bind=True)
def collect_person_osint(self, person_id: int) -> dict[str, Any]:
    """
    با کمک agent جستجوگر (Perplexity/Sonar و ...) سوابق یک فرد را از
    منابع باز اینترنتی جمع‌آوری، اعتبارسنجی و درج می‌کند.
    """
    services = _lazy_import_services()
    osint = services["osint_agent"]
    session = _session_scope()
    result: dict[str, Any] = {"person_id": person_id, "status": "skipped"}
    try:
        from app.models.person import Person
        from app.models.source import Source

        person = session.get(Person, person_id)
        if person is None:
            result["status"] = "not_found"
            return result
        if osint is None:
            result["status"] = "no_service"
            return result

        query_name = getattr(person, "full_name", None) or getattr(person, "name", "")
        findings = osint.search_person(query_name)
        inserted_sources = 0
        for finding in findings or []:
            credibility = finding.get("credibility")
            if credibility is None and osint is not None:
                try:
                    credibility = osint.score_credibility(finding)
                except Exception:  # noqa: BLE001
                    credibility = None
            source = Source(
                person_id=person_id,
                url=finding.get("url"),
                title=finding.get("title"),
                content=finding.get("content"),
                credibility_score=credibility,
                collected_at=_now(),
            )
            session.add(source)
            inserted_sources += 1

        if hasattr(person, "last_osint_at"):
            person.last_osint_at = _now()
        session.commit()
        result["status"] = "done"
        result["sources_collected"] = inserted_sources

        # پس از جمع‌آوری، ارزیابی ریسک را زنجیره‌ای اجرا کن
        assess_person_risk.delay(person_id)
        return result
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("collect_person_osint failed: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)
        return result
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Source credibility scoring
# ---------------------------------------------------------------------------
@celery_app.task(name="app.workers.tasks.score_source_credibility", bind=True)
def score_source_credibility(self, source_id: int) -> dict[str, Any]:
    """امتیازدهی اعتبار یک منبع جمع‌آوری‌شده."""
    services = _lazy_import_services()
    osint = services["osint_agent"]
    session = _session_scope()
    result: dict[str, Any] = {"source_id": source_id, "status": "skipped"}
    try:
        from app.models.source import Source

        source = session.get(Source, source_id)
        if source is None:
            result["status"] = "not_found"
            return result
        if osint is None:
            result["status"] = "no_service"
            return result
        payload = {
            "url": getattr(source, "url", None),
            "title": getattr(source, "title", None),
            "content": getattr(source, "content", None),
        }
        score = osint.score_credibility(payload)
        if hasattr(source, "credibility_score"):
            source.credibility_score = score
        session.commit()
        result["status"] = "done"
        result["credibility_score"] = score
        return result
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("score_source_credibility failed: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)
        return result
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Risk assessment engine
# ---------------------------------------------------------------------------
@celery_app.task(name="app.workers.tasks.assess_person_risk", bind=True)
def assess_person_risk(self, person_id: int) -> dict[str, Any]:
    """
    ارزیابی ریسک یک شخص را با موتور ریسک اجرا و نتیجه را ثبت می‌کند.

    به‌صورت دفاعی نوشته شده: اگر سرویس موتور ریسک در دسترس نباشد یا API آن
    متفاوت باشد، task بدون شکستن صف، یک وضعیت معنادار برمی‌گرداند.
    """
    services = _lazy_import_services()
    risk_mod = services.get("risk_engine")
    session = _session_scope()
    result: dict[str, Any] = {"person_id": person_id, "status": "skipped"}
    try:
        if risk_mod is None:
            result["status"] = "unavailable"
            result["error"] = "risk_engine service is not available"
            return result

        engine_cls = getattr(risk_mod, "RiskEngine", None)
        if engine_cls is None:
            result["status"] = "unavailable"
            result["error"] = "RiskEngine not found in risk_engine module"
            return result

        engine = engine_cls()
        assess = getattr(engine, "assess_person", None) or getattr(
            engine, "assess", None
        )
        if not callable(assess):
            result["status"] = "noop"
            return result

        outcome = assess(person_id)
        if isinstance(outcome, dict):
            result["risk_level"] = outcome.get("risk_level")
        else:
            result["risk_level"] = getattr(outcome, "risk_level", None)
        result["status"] = "completed"
        session.commit()
        return result
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("assess_person_risk failed: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)
        return result
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Aliasهای سازگار با نام‌هایی که route ها از این ماژول import می‌کنند.
# ---------------------------------------------------------------------------
run_osint_search = collect_person_osint
run_risk_assessment = assess_person_risk
process_article = classify_and_summarize_article


__all__ = [
    "celery_app",
    "classify_and_summarize_article",
    "generate_embedding",
    "collect_person_osint",
    "score_source_credibility",
    "assess_person_risk",
    "run_osint_search",
    "run_risk_assessment",
    "process_article",
]