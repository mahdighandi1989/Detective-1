"""
backend/app/api/routes/sources.py

روت‌های مدیریت و امتیازدهی منابع (Source Management & Credibility Scoring).

این ماژول endpoint های CRUD برای منابع OSINT و همچنین محاسبهٔ امتیاز
اعتبار منبع (source credibility scoring) را ارائه می‌دهد. منابع می‌توانند
به مقالات دانشنامه و پروفایل اشخاص متصل شوند تا تحلیل مبتنی بر شواهد
انجام شود.

Dependencies synced:
- upstream: Source model (models/source.py), get_db (api/deps.py),
  get_current_user / RBAC (core/security.py), Source schemas (schemas/source.py)
- downstream: osint_agent (منابع جمع‌آوری‌شده را ثبت می‌کند),
  risk_engine (از credibility_score برای وزن‌دهی شواهد استفاده می‌کند)
- cross-tier (backend → frontend): مصرف‌کنندهٔ این API صفحات مدیریت منابع
  در Next.js است؛ data shape در schemas/source.py تعریف شده.

نکته: این فایل از import مستقیم و fail-fast استفاده می‌کند. هیچ
fallback stub یا mock-based degradation در این ماژول وجود ندارد —
اگر وابستگی‌های واقعی repo موجود نباشند، import باید با خطای صریح
شکست بخورد تا مشکل ساختاری زود مشخص شود.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# import مستقیم و fail-fast (بدون try/except و بدون fallback stub).
# اگر هرکدام از این ماژول‌ها موجود نباشند، ImportError صریح رخ می‌دهد.
# ---------------------------------------------------------------------------
from app.api.deps import get_current_user, get_db, require_roles
from app.models.source import Source, SourceType
from app.schemas.source import (
    SourceCreate,
    SourceCredibilityResult,
    SourceInDB,
    SourceUpdate,
)

router = APIRouter(prefix="/sources", tags=["sources"])


# ---------------------------------------------------------------------------
# منطق امتیازدهی اعتبار منبع (Source Credibility Scoring)
# ---------------------------------------------------------------------------
def _domain_reputation_factor(url: Optional[str]) -> float:
    """
    عامل اعتبار دامنه بر اساس heuristic ساده.

    دامنه‌های رسمی/نهادی و رسانه‌های معتبر امتیاز بالاتری می‌گیرند.
    این تابع pure است و برای تست واحد قابل استفاده است.
    """
    if not url:
        return 0.4

    lowered = url.lower()

    high_trust_tlds = (".gov", ".gov.ir", ".edu", ".ac.ir", ".int", ".mil")
    medium_trust_tlds = (".org", ".ir", ".com")
    low_trust_markers = ("blogspot", "wordpress.com", "t.me", "telegram", "wixsite")

    if any(marker in lowered for marker in low_trust_markers):
        return 0.3
    if any(lowered.endswith(tld) or tld + "/" in lowered for tld in high_trust_tlds):
        return 0.95
    if any(lowered.endswith(tld) or tld + "/" in lowered for tld in medium_trust_tlds):
        return 0.6
    return 0.45


def _source_type_factor(source_type: Optional[SourceType]) -> float:
    """عامل اعتبار بر اساس نوع منبع."""
    if source_type is None:
        return 0.5

    weights = {
        SourceType.OFFICIAL: 0.95,
        SourceType.NEWS: 0.7,
        SourceType.ACADEMIC: 0.9,
        SourceType.SOCIAL_MEDIA: 0.4,
        SourceType.BLOG: 0.35,
        SourceType.FORUM: 0.3,
        SourceType.OTHER: 0.5,
    }
    # برخی deployment ها ممکن است enum value را به‌صورت مقدار خام نگه دارند.
    return weights.get(source_type, 0.5)


def compute_credibility_score(
    *,
    source_type: Optional[SourceType],
    url: Optional[str],
    corroboration_count: int = 0,
    has_author: bool = False,
    is_primary: bool = False,
) -> float:
    """
    محاسبهٔ امتیاز اعتبار منبع در بازهٔ 0.0 تا 1.0.

    ترکیب وزنی از:
    - نوع منبع (type)
    - اعتبار دامنه (domain reputation)
    - تعداد تأییدهای متقاطع (corroboration)
    - وجود نویسندهٔ مشخص
    - منبع اولیه بودن (primary source)

    این تابع pure و deterministic است (تست‌پذیر).
    """
    type_factor = _source_type_factor(source_type)
    domain_factor = _domain_reputation_factor(url)

    # تأیید متقاطع با saturation لگاریتمی تا از over-weighting جلوگیری شود.
    corroboration_factor = 1.0 - math.exp(-0.4 * max(corroboration_count, 0))

    author_factor = 1.0 if has_author else 0.0
    primary_factor = 1.0 if is_primary else 0.0

    score = (
        0.35 * type_factor
        + 0.25 * domain_factor
        + 0.20 * corroboration_factor
        + 0.10 * author_factor
        + 0.10 * primary_factor
    )

    # clamp نهایی
    return round(max(0.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "",
    response_model=SourceInDB,
    status_code=status.HTTP_201_CREATED,
    summary="ایجاد منبع جدید و محاسبهٔ امتیاز اعتبار",
)
async def create_source(
    payload: SourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SourceInDB:
    """
    ثبت یک منبع OSINT جدید.

    در صورت عدم ارسال credibility_score، امتیاز به‌صورت خودکار محاسبه
    و ذخیره می‌شود.
    """
    url_str = str(payload.url) if payload.url is not None else None

    computed_score = compute_credibility_score(
        source_type=payload.source_type,
        url=url_str,
        corroboration_count=payload.corroboration_count or 0,
        has_author=bool(payload.author),
        is_primary=bool(payload.is_primary),
    )

    source = Source(
        title=payload.title,
        url=url_str,
        source_type=payload.source_type,
        author=payload.author,
        description=payload.description,
        is_primary=bool(payload.is_primary),
        corroboration_count=payload.corroboration_count or 0,
        credibility_score=(
            payload.credibility_score
            if payload.credibility_score is not None
            else computed_score
        ),
        created_by_id=getattr(current_user, "id", None),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(source)
    await db.commit()
    await db.refresh(source)
    return SourceInDB.model_validate(source)


@router.get(
    "",
    response_model=List[SourceInDB],
    summary="فهرست منابع با فیلتر و جستجو",
)
async def list_sources(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    q: Optional[str] = Query(None, description="جستجو در عنوان/توضیح/نویسنده"),
    source_type: Optional[SourceType] = Query(None),
    min_credibility: Optional[float] = Query(None, ge=0.0, le=1.0),
    is_primary: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[SourceInDB]:
    """فهرست منابع به‌همراه فیلترهای credibility و type."""
    stmt = select(Source)

    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Source.title.ilike(like),
                Source.description.ilike(like),
                Source.author.ilike(like),
            )
        )
    if source_type is not None:
        stmt = stmt.where(Source.source_type == source_type)
    if min_credibility is not None:
        stmt = stmt.where(Source.credibility_score >= min_credibility)
    if is_primary is not None:
        stmt = stmt.where(Source.is_primary == is_primary)

    stmt = stmt.order_by(Source.credibility_score.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [SourceInDB.model_validate(row) for row in rows]


@router.get(
    "/{source_id}",
    response_model=SourceInDB,
    summary="دریافت یک منبع",
)
async def get_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SourceInDB:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="منبع یافت نشد.",
        )
    return SourceInDB.model_validate(source)


@router.patch(
    "/{source_id}",
    response_model=SourceInDB,
    summary="به‌روزرسانی منبع",
)
async def update_source(
    source_id: int,
    payload: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SourceInDB:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="منبع یافت نشد.",
        )

    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field == "url" and value is not None:
            value = str(value)
        setattr(source, field, value)

    # اگر credibility_score به‌صراحت ارسال نشده ولی فیلدهای مؤثر تغییر کرده‌اند،
    # دوباره محاسبه شود.
    if "credibility_score" not in update_data:
        source.credibility_score = compute_credibility_score(
            source_type=source.source_type,
            url=source.url,
            corroboration_count=source.corroboration_count or 0,
            has_author=bool(source.author),
            is_primary=bool(source.is_primary),
        )

    source.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(source)
    return source