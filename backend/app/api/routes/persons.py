"""
backend/app/api/routes/persons.py

CRUD پروفایل اشخاص (Person Profiles) و trigger جستجوی OSINT.

این روتر بخش «ماژول پروفایل‌سازی و رهگیری اشخاص» از پلتفرم Detective-1 را
پیاده‌سازی می‌کند:
  - ایجاد/خواندن/به‌روزرسانی/حذف پروفایل اشخاص
  - مدیریت سمت‌های فعلی/قبلی، سوابق و عملکرد
  - trigger کردن Agent جستجوگر OSINT (به‌صورت Celery task پس‌زمینه)
  - دریافت ارزیابی ریسک و سطح خطر هر فرد
  - audit log برای هر تغییر
  - کنترل دسترسی نقش‌محور (RBAC) و سطوح طبقه‌بندی محرمانگی

Dependencies synced:
  - upstream: Person/PositionHistory/RiskAssessment/AuditLog models,
    Person* Pydantic schemas, get_db, get_current_user, RBAC deps,
    Celery tasks (run_osint_search, run_risk_assessment)
  - downstream: frontend persons pages/hooks, graph route (reads risk),
    encyclopedia linkage
  - cross-tier (backend → worker): trigger osint/risk Celery tasks
  - side artifacts: OpenAPI annotations (response_model/summary)

تغییر مهم (regression fix):
  الگوی try/except با fallback که RuntimeError raise می‌کرد حذف شد.
  import های حیاتی اکنون مستقیم و fail-fast هستند — مطابق همان اصلاحی که
  در main.py و celery_app.py انجام شد. اگر مسیر import اشتباه باشد، برنامه
  در زمان bootstrap به‌جای سقوط در runtime به stub، صریحاً fail می‌کند.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# ---------------------------------------------------------------------------
# وابستگی‌های حیاتی پروژه — import مستقیم و fail-fast (بدون fallback mock).
# اگر هر کدام از این‌ها قابل import نباشد، برنامه باید همان لحظه fail کند
# تا یک stub مخفی رفتار production را خراب نکند.
# ---------------------------------------------------------------------------
from app.db.session import get_db
from app.core.security import (
    get_current_user,
    require_roles,
)
from app.models.user import User
from app.models.person import (
    Person,
    PositionHistory,
    PersonStatus,
    ClassificationLevel,
)
from app.models.risk_assessment import RiskAssessment, RiskLevel
from app.models.audit_log import AuditLog, AuditAction
from app.schemas.person import (
    PersonCreate,
    PersonUpdate,
    PersonRead,
    PersonListItem,
    PositionHistoryCreate,
    PositionHistoryRead,
    RiskAssessmentRead,
    AuditLogRead,
    OsintSearchRequest,
    OsintSearchResponse,
)
from app.workers.tasks import run_osint_search, run_risk_assessment


router = APIRouter(prefix="/persons", tags=["persons"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_person_or_404(
    db: AsyncSession,
    person_id: uuid.UUID,
    *,
    with_relations: bool = False,
) -> Person:
    """واکشی Person با person_id یا 404."""
    stmt = select(Person).where(Person.id == person_id)
    if with_relations:
        stmt = stmt.options(
            selectinload(Person.positions),
            selectinload(Person.risk_assessments),
        )
    result = await db.execute(stmt)
    person = result.scalar_one_or_none()
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person {person_id} not found",
        )
    return person


def _can_access_classification(user: User, level: ClassificationLevel) -> bool:
    """بررسی اینکه آیا سطح دسترسی کاربر اجازهٔ مشاهدهٔ این طبقه‌بندی را می‌دهد."""
    user_clearance = getattr(user, "clearance_level", ClassificationLevel.PUBLIC)
    order = {
        ClassificationLevel.PUBLIC: 0,
        ClassificationLevel.RESTRICTED: 1,
        ClassificationLevel.CONFIDENTIAL: 2,
        ClassificationLevel.SECRET: 3,
        ClassificationLevel.TOP_SECRET: 4,
    }
    return order.get(user_clearance, 0) >= order.get(level, 0)


async def _record_audit(
    db: AsyncSession,
    *,
    user: User,
    action: AuditAction,
    person_id: uuid.UUID,
    detail: Optional[str] = None,
) -> None:
    """ثبت یک رکورد audit log برای تغییرات پروفایل."""
    entry = AuditLog(
        id=uuid.uuid4(),
        actor_id=user.id,
        action=action,
        entity_type="person",
        entity_id=str(person_id),
        detail=detail,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------
@router.get(
    "",
    response_model=List[PersonListItem],
    summary="فهرست پروفایل اشخاص با فیلتر/جستجو",
)
async def list_persons(
    q: Optional[str] = Query(None, description="جستجوی نام/سمت"),
    status_filter: Optional[PersonStatus] = Query(None, alias="status"),
    risk_level: Optional[RiskLevel] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[PersonListItem]:
    stmt = select(Person).options(selectinload(Person.risk_assessments))

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Person.full_name.ilike(like),
                Person.current_position.ilike(like),
            )
        )
    if status_filter is not None:
        stmt = stmt.where(Person.status == status_filter)

    stmt = stmt.order_by(desc(Person.updated_at)).limit(limit).offset(offset)
    result = await db.execute(stmt)
    persons = result.scalars().unique().all()

    items: List[PersonListItem] = []
    for p in persons:
        if not _can_access_classification(current_user, p.classification):
            continue
        latest_risk = None
        if p.risk_assessments:
            latest_risk = max(
                p.risk_assessments, key=lambda r: r.created_at
            )
        if risk_level is not None and (
            latest_risk is None or latest_risk.level != risk_level
        ):
            continue
        items.append(PersonListItem.from_person(p, latest_risk))

    return items


@router.post(
    "",
    response_model=PersonRead,
    status_code=status.HTTP_201_CREATED,
    summary="ایجاد پروفایل شخص جدید",
    dependencies=[Depends(require_roles("analyst", "admin"))],
)
async def create_person(
    payload: PersonCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonRead:
    if not _can_access_classification(current_user, payload.classification):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="سطح دسترسی کافی برای این طبقه‌بندی ندارید",
        )

    person = Person(
        id=uuid.uuid4(),
        full_name=payload.full_name,
        aliases=payload.aliases or [],
        photo_url=payload.photo_url,
        current_position=payload.current_position,
        bio=payload.bio,
        status=payload.status or PersonStatus.UNKNOWN,
        classification=payload.classification,
        created_by=current_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(person)
    await db.flush()

    for pos in payload.positions or []:
        db.add(
            PositionHistory(
                id=uuid.uuid4(),
                person_id=person.id,
                title=pos.title,
                organization=pos.organization,
                start_date=pos.start_date,
                end_date=pos.end_date,
                is_current=pos.is_current,
            )
        )

    await _record_audit(
        db,
        user=current_user,
        action=AuditAction.CREATE,
        person_id=person.id,
        detail=f"created person '{person.full_name}'",
    )
    await db.commit()

    person = await _get_person_or_404(db, person.id, with_relations=True)
    return PersonRead.from_person(person)


@router.get(
    "/{person_id}",
    response_model=PersonRead,
    summary="جزئیات کامل یک پروفایل",
)
async def get_person(
    person_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonRead:
    person = await _get_person_or_404(db, person_id, with_relations=True)
    if not _can_access_classification(current_user, person.classification):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="سطح دسترسی کافی ندارید",
        )
    return PersonRead.from_person(person)


@router.patch(
    "/{person_id}",
    response_model=PersonRead,
    summary="به‌روزرسانی پروفایل شخص",
    dependencies=[Depends(require_roles("analyst", "admin"))],
)
async def update_person(
    person_id: uuid.UUID,
    payload: PersonUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonRead:
    person = await _get_person_or_404(db, person_id, with_relations=True)
    if not _can_access_classification(current_user, person.classification):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="سطح دسترسی کافی ندارید",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(person, field, value)

    await db.commit()
    await db.refresh(person)
    return PersonRead.from_person(person)