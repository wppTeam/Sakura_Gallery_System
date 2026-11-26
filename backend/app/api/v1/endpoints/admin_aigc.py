"""AI 生图（创作台）后台管理 API。

给管理员三件事：
- 看生成量 / 成功率 / 成本 / 活跃作者（``GET /admin/aigc/overview``）；
- 查任意作者的生成记录与额度（``GET /admin/aigc/generations``、``/users/{id}/quota``）；
- 赠送额外额度（``POST /admin/aigc/users/{id}/grants``，写审计 + 站内通知），
  以及撤销某笔赠送（``DELETE /admin/aigc/grants/{id}``）。

额度口径与作者端一致：每日基础额度 + 赠送池，失败不计（见 ``services/aigc_quota.py``）。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin_user, get_db
from app.models.aigc_generation import AIGCGeneration
from app.models.aigc_quota import AigcQuotaGrant
from app.models.user import User
from app.schemas.aigc_generation import AigcQuotaResponse
from app.services import aigc_quota
from app.services.audit import log_audit
from app.services.notification import notify_user

router = APIRouter(prefix="/aigc", tags=["AI 生图管理"])

MAX_GRANT_AMOUNT = 1000


class AigcUserBrief(BaseModel):
    id: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    student_id: Optional[str] = None


class AigcTotals(BaseModel):
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    pending: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    success_rate: float = 0.0


class AigcDayBucket(BaseModel):
    day: str
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    cost_usd: float = 0.0


class AigcTopUser(BaseModel):
    user: AigcUserBrief
    total: int = 0
    succeeded: int = 0
    cost_usd: float = 0.0


class AigcQuotaSummary(BaseModel):
    grant_count: int = 0
    recipients: int = 0
    granted_total: int = 0
    bonus_used: int = 0
    bonus_remaining: int = 0


class AigcOverviewResponse(BaseModel):
    days: int
    base_daily_limit: int
    totals: AigcTotals
    today: AigcTotals
    by_day: List[AigcDayBucket]
    top_users: List[AigcTopUser]
    quota: AigcQuotaSummary


class AigcGenerationAdminItem(BaseModel):
    id: str
    user: AigcUserBrief
    prompt: str
    size_key: str
    status: str
    quota_source: str
    model_id: str
    width: Optional[int] = None
    height: Optional[int] = None
    latency_ms: Optional[int] = None
    cost_usd: float = 0.0
    error: Optional[str] = None
    image_url: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class AigcGenerationAdminList(BaseModel):
    items: List[AigcGenerationAdminItem]
    total: int
    skip: int
    limit: int


class AigcGrantItem(BaseModel):
    id: str
    user: AigcUserBrief
    amount: int
    reason: Optional[str] = None
    granted_by: Optional[str] = None
    granted_by_name: Optional[str] = None
    created_at: datetime


class AigcGrantList(BaseModel):
    items: List[AigcGrantItem]
    total: int
    skip: int
    limit: int


class AigcGrantCreate(BaseModel):
    amount: int = Field(..., ge=1, le=MAX_GRANT_AMOUNT, description="赠送张数")
    reason: Optional[str] = Field(None, max_length=200, description="赠送理由，会展示给作者")


class AigcUserQuotaResponse(BaseModel):
    user: AigcUserBrief
    quota: AigcQuotaResponse
    grants: List[AigcGrantItem]
    recent: List[AigcGenerationAdminItem]


def _brief(user: Optional[User]) -> AigcUserBrief:
    if user is None:
        return AigcUserBrief(id="")
    return AigcUserBrief(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        student_id=user.student_id,
    )


def _totals(rows) -> AigcTotals:
    """rows = (total, succeeded, failed, pending, cost, avg_latency)。"""
    total, succeeded, failed, pending, cost, avg_latency = rows
    total = int(total or 0)
    succeeded = int(succeeded or 0)
    failed = int(failed or 0)
    finished = succeeded + failed
    return AigcTotals(
        total=total,
        succeeded=succeeded,
        failed=failed,
        pending=int(pending or 0),
        cost_usd=round(float(cost or 0.0), 6),
        avg_latency_ms=round(float(avg_latency or 0.0), 1),
        success_rate=round(succeeded / finished, 4) if finished else 0.0,
    )


_AGG_COLUMNS = (
    func.count(AIGCGeneration.id),
    func.coalesce(func.sum(case((AIGCGeneration.status == "succeeded", 1), else_=0)), 0),
    func.coalesce(func.sum(case((AIGCGeneration.status == "failed", 1), else_=0)), 0),
    func.coalesce(
        func.sum(case((AIGCGeneration.status.in_(("queued", "running")), 1), else_=0)), 0
    ),
    func.coalesce(func.sum(AIGCGeneration.cost_usd), 0.0),
    func.coalesce(func.avg(AIGCGeneration.latency_ms), 0.0),
)


async def _totals_since(db: AsyncSession, since: Optional[datetime]) -> AigcTotals:
    stmt = select(*_AGG_COLUMNS)
    if since is not None:
        stmt = stmt.where(AIGCGeneration.created_at >= since)
    return _totals((await db.execute(stmt)).one())


def _image_url(generation: AIGCGeneration) -> Optional[str]:
    if generation.status != "succeeded" or not generation.image_path:
        return None
    return f"/api/v1/aigc/generations/{generation.id}/image"


def _generation_item(generation: AIGCGeneration, user: Optional[User]) -> AigcGenerationAdminItem:
    return AigcGenerationAdminItem(
        id=generation.id,
        user=_brief(user),
        prompt=generation.prompt,
        size_key=generation.size_key,
        status=generation.status,
        quota_source=generation.quota_source or "daily",
        model_id=generation.model_id,
        width=generation.width,
        height=generation.height,
        latency_ms=generation.latency_ms,
        cost_usd=float(generation.cost_usd or 0.0),
        error=generation.error,
        image_url=_image_url(generation),
        created_at=generation.created_at,
        finished_at=generation.finished_at,
    )


async def _users_map(db: AsyncSession, user_ids) -> dict[str, User]:
    ids = {uid for uid in user_ids if uid}
    if not ids:
        return {}
    rows = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {user.id: user for user in rows}


async def _grant_items(db: AsyncSession, grants: List[AigcQuotaGrant]) -> List[AigcGrantItem]:
    users = await _users_map(
        db, [g.user_id for g in grants] + [g.granted_by for g in grants if g.granted_by]
    )
    items = []
    for grant in grants:
        operator = users.get(grant.granted_by) if grant.granted_by else None
        items.append(
            AigcGrantItem(
                id=grant.id,
                user=_brief(users.get(grant.user_id)),
                amount=int(grant.amount),
                reason=grant.reason,
                granted_by=grant.granted_by,
                granted_by_name=(operator.display_name or operator.username) if operator else None,
                created_at=grant.created_at,
            )
        )
    return items


@router.get("/overview", response_model=AigcOverviewResponse, summary="生图总览")
async def get_overview(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> AigcOverviewResponse:
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    today_start = datetime(now.year, now.month, now.day)

    totals = await _totals_since(db, since)
    today = await _totals_since(db, today_start)

    day_rows = (
        await db.execute(
            select(
                func.date(AIGCGeneration.created_at).label("day"),
                func.count(AIGCGeneration.id),
                func.coalesce(
                    func.sum(case((AIGCGeneration.status == "succeeded", 1), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case((AIGCGeneration.status == "failed", 1), else_=0)), 0
                ),
                func.coalesce(func.sum(AIGCGeneration.cost_usd), 0.0),
            )
            .where(AIGCGeneration.created_at >= since)
            .group_by("day")
            .order_by("day")
        )
    ).all()
    by_day = [
        AigcDayBucket(
            day=str(row[0])[:10],
            total=int(row[1] or 0),
            succeeded=int(row[2] or 0),
            failed=int(row[3] or 0),
            cost_usd=round(float(row[4] or 0.0), 6),
        )
        for row in day_rows
    ]

    user_rows = (
        await db.execute(
            select(
                AIGCGeneration.user_id,
                func.count(AIGCGeneration.id),
                func.coalesce(
                    func.sum(case((AIGCGeneration.status == "succeeded", 1), else_=0)), 0
                ),
                func.coalesce(func.sum(AIGCGeneration.cost_usd), 0.0),
            )
            .where(AIGCGeneration.created_at >= since)
            .group_by(AIGCGeneration.user_id)
            .order_by(func.count(AIGCGeneration.id).desc())
            .limit(8)
        )
    ).all()
    users = await _users_map(db, [row[0] for row in user_rows])
    top_users = [
        AigcTopUser(
            user=_brief(users.get(row[0])),
            total=int(row[1] or 0),
            succeeded=int(row[2] or 0),
            cost_usd=round(float(row[3] or 0.0), 6),
        )
        for row in user_rows
    ]

    granted_total = int(
        (await db.execute(select(func.coalesce(func.sum(AigcQuotaGrant.amount), 0)))).scalar_one()
        or 0
    )
    grant_count = int(
        (await db.execute(select(func.count()).select_from(AigcQuotaGrant))).scalar_one() or 0
    )
    recipients = int(
        (
            await db.execute(
                select(func.count(func.distinct(AigcQuotaGrant.user_id)))
            )
        ).scalar_one()
        or 0
    )
    bonus_used = int(
        (
            await db.execute(
                select(func.count())
                .select_from(AIGCGeneration)
                .where(
                    AIGCGeneration.quota_source == "bonus",
                    AIGCGeneration.status != "failed",
                )
            )
        ).scalar_one()
        or 0
    )

    return AigcOverviewResponse(
        days=days,
        base_daily_limit=aigc_quota.base_daily_limit(),
        totals=totals,
        today=today,
        by_day=by_day,
        top_users=top_users,
        quota=AigcQuotaSummary(
            grant_count=grant_count,
            recipients=recipients,
            granted_total=granted_total,
            bonus_used=bonus_used,
            bonus_remaining=max(0, granted_total - bonus_used),
        ),
    )


@router.get("/generations", response_model=AigcGenerationAdminList, summary="生成记录")
async def list_generations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[Literal["queued", "running", "succeeded", "failed"]] = Query(
        None, alias="status"
    ),
    quota_source: Optional[Literal["daily", "bonus", "unlimited"]] = Query(None),
    user_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=100, description="提示词关键词"),
    days: Optional[int] = Query(None, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> AigcGenerationAdminList:
    filters = []
    if status_filter:
        filters.append(AIGCGeneration.status == status_filter)
    if quota_source:
        filters.append(AIGCGeneration.quota_source == quota_source)
    if user_id:
        filters.append(AIGCGeneration.user_id == user_id)
    if search and search.strip():
        filters.append(AIGCGeneration.prompt.ilike(f"%{search.strip()}%"))
    if days:
        filters.append(AIGCGeneration.created_at >= datetime.utcnow() - timedelta(days=days))

    total = int(
        (
            await db.execute(select(func.count()).select_from(AIGCGeneration).where(*filters))
        ).scalar_one()
        or 0
    )
    rows = (
        (
            await db.execute(
                select(AIGCGeneration)
                .where(*filters)
                .order_by(AIGCGeneration.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    users = await _users_map(db, [row.user_id for row in rows])
    return AigcGenerationAdminList(
        items=[_generation_item(row, users.get(row.user_id)) for row in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/grants", response_model=AigcGrantList, summary="额度赠送台账")
async def list_grants(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> AigcGrantList:
    filters = [AigcQuotaGrant.user_id == user_id] if user_id else []
    total = int(
        (
            await db.execute(select(func.count()).select_from(AigcQuotaGrant).where(*filters))
        ).scalar_one()
        or 0
    )
    grants = list(
        (
            await db.execute(
                select(AigcQuotaGrant)
                .where(*filters)
                .order_by(AigcQuotaGrant.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return AigcGrantList(
        items=await _grant_items(db, grants), total=total, skip=skip, limit=limit
    )


@router.get("/users/{user_id}/quota", response_model=AigcUserQuotaResponse, summary="某位作者的额度")
async def get_user_quota(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
) -> AigcUserQuotaResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    state = await aigc_quota.get_quota(db, user)
    grants = list(
        (
            await db.execute(
                select(AigcQuotaGrant)
                .where(AigcQuotaGrant.user_id == user_id)
                .order_by(AigcQuotaGrant.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    recent = list(
        (
            await db.execute(
                select(AIGCGeneration)
                .where(AIGCGeneration.user_id == user_id)
                .order_by(AIGCGeneration.created_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    return AigcUserQuotaResponse(
        user=_brief(user),
        quota=AigcQuotaResponse(
            unlimited=state.unlimited,
            daily_limit=state.daily_limit,
            daily_used=state.daily_used,
            daily_remaining=state.daily_remaining,
            bonus_total=state.bonus_total,
            bonus_used=state.bonus_used,
            bonus_remaining=state.bonus_remaining,
            total_remaining=state.total_remaining,
        ),
        grants=await _grant_items(db, grants),
        recent=[_generation_item(row, user) for row in recent],
    )


@router.post(
    "/users/{user_id}/grants",
    response_model=AigcGrantItem,
    status_code=status.HTTP_201_CREATED,
    summary="赠送生图额度",
)
async def create_grant(
    user_id: str,
    payload: AigcGrantCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> AigcGrantItem:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    reason = (payload.reason or "").strip() or None
    grant = AigcQuotaGrant(
        user_id=user_id, amount=int(payload.amount), reason=reason, granted_by=admin.id
    )
    db.add(grant)
    await db.flush()
    await log_audit(
        db,
        user_id=admin.id,
        action="aigc.quota_grant",
        resource_type="user",
        resource_id=user_id,
        detail=f"赠送生图额度 {payload.amount} 张给 {user.username or user.email}"
        + (f"（{reason}）" if reason else ""),
        request=request,
    )
    await notify_user(
        db,
        user_id=user_id,
        type="system",
        title=f"收到 {payload.amount} 张 AI 生图额度 🎁",
        content=(
            f"{reason or '管理员赠送'}。赠送额度不会随日重置，"
            "每日基础额度用完后会自动消耗它。去 AI 创作台看看吧。"
        ),
    )
    await db.commit()
    await db.refresh(grant)
    items = await _grant_items(db, [grant])
    return items[0]


@router.delete("/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT, summary="撤销一笔赠送")
async def revoke_grant(
    grant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> None:
    grant = await db.get(AigcQuotaGrant, grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="赠送记录不存在")
    user = await db.get(User, grant.user_id)
    target = (user.username or user.email) if user else grant.user_id
    await log_audit(
        db,
        user_id=admin.id,
        action="aigc.quota_revoke",
        resource_type="user",
        resource_id=grant.user_id,
        detail=f"撤销生图额度赠送 {grant.amount} 张（{target}）",
        request=request,
    )
    await db.delete(grant)
    await db.commit()
    return None