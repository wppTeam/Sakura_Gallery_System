"""后台仪表盘聚合接口（admin + auditor）。

把「现在需要人处理的事」放在一屏：待审作品 / 待人工复核 / 待处理举报 / 待处理申诉，
再加上作品、用户、生图与 AI 成本的概览。auditor 也能访问（只返回计数与公开作品信息，
不返回学号 / 邮箱等身份字段）；``recent_logins`` 仅 admin 可见。

图表数据（近 30 天上传 / 热门标签）仍走 ``GET /api/v1/stats/dashboard``。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_auditor_user, get_db
from app.models.ai_usage import AIUsageEvent
from app.models.aigc_generation import AIGCGeneration
from app.models.aigc_quota import AigcQuotaGrant
from app.models.appeal import PhotoAppeal
from app.models.moderation import ModerationReview
from app.models.photo import Photo
from app.models.report import Report
from app.models.user import User

router = APIRouter(tags=["后台概览"])


class TodoCounts(BaseModel):
    review_pending: int = 0
    moderation_pending_human: int = 0
    reports_pending: int = 0
    appeals_pending: int = 0


class PhotoCounts(BaseModel):
    total: int = 0
    approved: int = 0
    pending: int = 0
    rejected: int = 0
    views: int = 0
    storage_bytes: int = 0


class UserCounts(BaseModel):
    total: int = 0
    active: int = 0
    new_7_days: int = 0
    email_unverified: int = 0


class RecentLogin(BaseModel):
    id: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    role: str
    last_login_at: Optional[datetime] = None
    login_count: int = 0


class AigcSummary(BaseModel):
    today_total: int = 0
    today_succeeded: int = 0
    today_failed: int = 0
    cost_7d: float = 0.0
    bonus_remaining: int = 0


class TopPhoto(BaseModel):
    id: str
    title: Optional[str] = None
    views: int = 0
    thumb_url: str


class OverviewResponse(BaseModel):
    role: str
    todos: TodoCounts
    photos: PhotoCounts
    users: UserCounts
    recent_logins: List[RecentLogin]
    aigc: AigcSummary
    ai_cost_7d: float
    top_photos: List[TopPhoto]


async def _count(db: AsyncSession, model, *filters) -> int:
    stmt = select(func.count()).select_from(model)
    if filters:
        stmt = stmt.where(*filters)
    return int((await db.execute(stmt)).scalar_one() or 0)


@router.get("/overview", response_model=OverviewResponse, summary="后台一屏概览")
async def get_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
) -> OverviewResponse:
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    today_start = datetime(now.year, now.month, now.day)
    is_admin = current_user.role == "admin"

    photo_status = dict(
        (await db.execute(select(Photo.status, func.count()).group_by(Photo.status))).all()
    )
    photo_agg = (
        await db.execute(
            select(
                func.coalesce(func.sum(Photo.views), 0),
                func.coalesce(func.sum(Photo.file_size), 0),
            ).where(Photo.status != "deleted")
        )
    ).one()

    latest_reviews = (
        select(
            ModerationReview.id,
            func.row_number()
            .over(
                partition_by=ModerationReview.photo_id,
                order_by=(ModerationReview.created_at.desc(), ModerationReview.id.desc()),
            )
            .label("rn"),
            ModerationReview.final_decision.label("final_decision"),
        )
        .subquery()
    )
    pending_human = int(
        (
            await db.execute(
                select(func.count())
                .select_from(latest_reviews)
                .where(latest_reviews.c.rn == 1, latest_reviews.c.final_decision.is_(None))
            )
        ).scalar_one()
        or 0
    )

    aigc_today = dict(
        (
            await db.execute(
                select(AIGCGeneration.status, func.count())
                .where(AIGCGeneration.created_at >= today_start)
                .group_by(AIGCGeneration.status)
            )
        ).all()
    )
    aigc_cost_7d = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(AIGCGeneration.cost_usd), 0.0)).where(
                    AIGCGeneration.created_at >= week_ago
                )
            )
        ).scalar_one()
        or 0.0
    )
    granted_total = int(
        (await db.execute(select(func.coalesce(func.sum(AigcQuotaGrant.amount), 0)))).scalar_one()
        or 0
    )
    bonus_used = await _count(
        db, AIGCGeneration, AIGCGeneration.quota_source == "bonus", AIGCGeneration.status != "failed"
    )
    ai_cost_7d = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(AIUsageEvent.cost_usd), 0.0)).where(
                    AIUsageEvent.created_at >= week_ago
                )
            )
        ).scalar_one()
        or 0.0
    )

    recent_logins: List[RecentLogin] = []
    if is_admin:
        rows = (
            (
                await db.execute(
                    select(User)
                    .where(User.last_login_at.is_not(None))
                    .order_by(User.last_login_at.desc())
                    .limit(8)
                )
            )
            .scalars()
            .all()
        )
        recent_logins = [
            RecentLogin(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                role=user.role,
                last_login_at=user.last_login_at,
                login_count=user.login_count or 0,
            )
            for user in rows
        ]

    top_rows = (
        (
            await db.execute(
                select(Photo)
                .where(Photo.status == "approved")
                .order_by(Photo.views.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    return OverviewResponse(
        role=current_user.role,
        todos=TodoCounts(
            review_pending=int(photo_status.get("pending", 0)),
            moderation_pending_human=pending_human,
            reports_pending=await _count(db, Report, Report.status == "pending"),
            appeals_pending=await _count(db, PhotoAppeal, PhotoAppeal.status == "pending"),
        ),
        photos=PhotoCounts(
            total=sum(int(v) for k, v in photo_status.items() if k != "deleted"),
            approved=int(photo_status.get("approved", 0)),
            pending=int(photo_status.get("pending", 0)),
            rejected=int(photo_status.get("rejected", 0)),
            views=int(photo_agg[0] or 0),
            storage_bytes=int(photo_agg[1] or 0),
        ),
        users=UserCounts(
            total=await _count(db, User),
            active=await _count(db, User, User.is_active.is_(True)),
            new_7_days=await _count(db, User, User.created_at >= week_ago),
            email_unverified=await _count(db, User, User.email_verified.is_(False)),
        ),
        recent_logins=recent_logins,
        aigc=AigcSummary(
            today_total=sum(int(v) for v in aigc_today.values()),
            today_succeeded=int(aigc_today.get("succeeded", 0)),
            today_failed=int(aigc_today.get("failed", 0)),
            cost_7d=round(aigc_cost_7d, 6),
            bonus_remaining=max(0, granted_total - bonus_used),
        ),
        ai_cost_7d=round(ai_cost_7d, 6),
        top_photos=[
            TopPhoto(
                id=photo.id,
                title=photo.title,
                views=photo.views or 0,
                thumb_url=f"/api/v1/photos/{photo.id}/image/thumbnail",
            )
            for photo in top_rows
        ],
    )