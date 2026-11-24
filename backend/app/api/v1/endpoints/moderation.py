"""AI 审核管理端 API。

给审核人员（admin / auditor）使用：

- ``GET  /moderation/queue``          人工审核队列（每张照片取最新一次 agent 结论）
- ``GET  /moderation/{photo_id}``     单张照片的最新审核详情（三层依据 + 用量）
- ``POST /moderation/{photo_id}/run`` 重新触发审核（异步，202）
- ``POST /moderation/{photo_id}/decision`` 人工终判（approve / reject / hold）
- ``GET  /moderation/stats``          近 N 天统计（级别分布、延迟、token、成本、预算）

所有响应只含 ``username`` 级别公开身份，不返回学号 / 真实姓名 / 完整 EXIF。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_auditor_user, get_db
from app.models.ai_usage import AIUsageEvent
from app.models.moderation import ModerationReview
from app.models.photo import Photo
from app.models.user import User
from app.services.audit import log_audit
from app.services.curation import sync_photo_curation
from app.services.moderation import VALID_TIERS
from app.services.moderation_worker import (
    enqueue_moderation,
    get_latest_review,
    process_pending_reviews,
)
from app.services.notification import notify_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/moderation", tags=["AI 审核"])
settings = get_settings()

MODERATION_OPERATION_PREFIX = "moderation."

# 媒体地址与 photos 路由保持一致；前端 getImageUrl 会自行补 API base
MEDIA_URL_PREFIX = "/api/v1/photos"

DecisionLiteral = Literal["approve", "reject", "hold"]
TierLiteral = Literal["L0", "L1", "L2"]


# ---------------------------------------------------------------------------
# Schemas（仅本模块使用，不新增全局 schema 文件）
# ---------------------------------------------------------------------------

class ModerationUploaderBrief(BaseModel):
    """上传者公开身份：只放 username / display_name，禁止学号与真实姓名。"""

    username: Optional[str] = None
    display_name: Optional[str] = None


class ModerationPhotoBrief(BaseModel):
    """队列里的照片摘要（公开身份字段，不含学号/真实姓名/EXIF）。"""

    id: str
    title: Optional[str] = None
    filename: Optional[str] = None
    status: Optional[str] = None
    processing_status: Optional[str] = None
    category: Optional[str] = None
    season: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    thumb_path: Optional[str] = None
    thumb_url: Optional[str] = None
    uploader: Optional[ModerationUploaderBrief] = None
    created_at: Optional[datetime] = None


class ModerationReviewOut(BaseModel):
    id: str
    photo_id: str
    status: str
    tier: Optional[str] = None
    suggested_tier: Optional[str] = None
    rules: Optional[dict[str, Any]] = None
    prefilter: Optional[dict[str, Any]] = None
    escalation: Optional[dict[str, Any]] = None
    final_decision: Optional[str] = None
    final_tier: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    provider: Optional[str] = None
    model_id: Optional[str] = None
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    photo: Optional[ModerationPhotoBrief] = None


class ModerationQueueResponse(BaseModel):
    items: list[ModerationReviewOut]
    total: int
    limit: int
    offset: int


class ModerationRunResponse(BaseModel):
    ok: bool = True
    photo_id: str
    review_id: Optional[str] = None
    status: str = "queued"
    message: str = "审核任务已入队"


class ModerationDecisionRequest(BaseModel):
    decision: DecisionLiteral
    reason: Optional[str] = Field(None, max_length=1000, description="人工判定理由（写入审计日志）")
    final_tier: Optional[TierLiteral] = Field(None, description="人工确认的发布级别")


class ModerationBatchDecisionRequest(BaseModel):
    """批量人工终判请求（一次最多 50 张）。"""

    photo_ids: list[str] = Field(..., min_length=1, max_length=50, description="照片 ID 列表")
    decision: DecisionLiteral
    reason: Optional[str] = Field(None, max_length=1000, description="统一理由（写入审计日志）")
    final_tier: Optional[TierLiteral] = Field(None, description="统一确认的发布级别")


class ModerationBatchItemResult(BaseModel):
    photo_id: str
    ok: bool
    decision: Optional[str] = None
    error: Optional[str] = None


class ModerationBatchDecisionResponse(BaseModel):
    ok: bool = True
    processed: int
    succeeded: int
    failed: int
    items: list[ModerationBatchItemResult]


class ModerationDrainResponse(BaseModel):
    ok: bool = True
    processed: int
    message: str = "已消费审核队列中的待办"


class ModerationStatsResponse(BaseModel):
    days: int
    total: int
    by_tier: dict[str, int]
    by_status: dict[str, int]
    pending_human: int
    avg_latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    today_calls: int
    daily_budget: int
    remaining_calls: Optional[int] = None


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------

def _thumb_url(photo: Photo) -> Optional[str]:
    """缩略图地址（相对路径，前端补 API base）；无缩略图时回退原图。"""
    if not (photo.thumb_path or photo.original_path):
        return None
    return f"{MEDIA_URL_PREFIX}/{photo.id}/image/thumbnail"


def _uploader_brief(user: User | None) -> Optional[ModerationUploaderBrief]:
    """上传者公开身份。User 暂无 username/display_name 列时返回空对象（不泄露学号/真名）。"""
    if user is None:
        return None
    return ModerationUploaderBrief(
        username=getattr(user, "username", None),
        display_name=getattr(user, "display_name", None),
    )


def _photo_brief(
    photo: Photo | None,
    uploader: User | None = None,
) -> Optional[ModerationPhotoBrief]:
    if photo is None:
        return None
    return ModerationPhotoBrief(
        id=photo.id,
        title=photo.title,
        filename=photo.filename,
        status=photo.status,
        processing_status=photo.processing_status,
        category=photo.category,
        season=photo.season,
        width=photo.width,
        height=photo.height,
        thumb_path=photo.thumb_path,
        thumb_url=_thumb_url(photo),
        uploader=_uploader_brief(uploader),
        created_at=photo.created_at,
    )


def _review_out(
    review: ModerationReview,
    photo: Photo | None = None,
    uploader: User | None = None,
) -> ModerationReviewOut:
    target_photo = photo if photo is not None else review.photo
    return ModerationReviewOut(
        id=review.id,
        photo_id=review.photo_id,
        status=review.status,
        tier=review.tier,
        suggested_tier=review.suggested_tier,
        rules=review.rules,
        prefilter=review.prefilter,
        escalation=review.escalation,
        final_decision=review.final_decision,
        final_tier=review.final_tier,
        reviewer_id=review.reviewer_id,
        reviewed_at=review.reviewed_at,
        provider=review.provider,
        model_id=review.model_id,
        latency_ms=review.latency_ms or 0,
        prompt_tokens=review.prompt_tokens or 0,
        completion_tokens=review.completion_tokens or 0,
        cost_usd=review.cost_usd or 0.0,
        error=review.error,
        created_at=review.created_at,
        updated_at=review.updated_at,
        photo=_photo_brief(target_photo, uploader),
    )


# ---------------------------------------------------------------------------
# 队列 / 详情
# ---------------------------------------------------------------------------

def _queue_base():
    """每张照片只保留最新 review 的查询底座（窗口函数，SQLite/PG 均支持）。"""
    ranked = select(
        ModerationReview.id.label("id"),
        func.row_number()
        .over(
            partition_by=ModerationReview.photo_id,
            order_by=(ModerationReview.created_at.desc(), ModerationReview.id.desc()),
        )
        .label("rn"),
    ).subquery()
    return (
        select(ModerationReview)
        .join(ranked, ModerationReview.id == ranked.c.id)
        .where(ranked.c.rn == 1)
    )


@router.get("/queue", response_model=ModerationQueueResponse, summary="人工审核队列")
async def get_moderation_queue(
    status_filter: Optional[str] = Query(
        None, alias="status", description="review 状态筛选：queued/running/completed/failed"
    ),
    tier: Optional[str] = Query(None, description="建议级别筛选：L0/L1/L2"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_auditor_user),
):
    """按 review.created_at 倒序返回每张照片的最新审核记录。"""
    base = _queue_base()
    if status_filter:
        base = base.where(ModerationReview.status == status_filter)
    if tier:
        base = base.where(ModerationReview.tier == tier)

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    stmt = (
        base.order_by(ModerationReview.created_at.desc())
        .offset(offset)
        .limit(min(limit, 100))
    )
    reviews = (await db.execute(stmt)).scalars().unique().all()
    uploader_ids = {review.photo.uploader_id for review in reviews if review.photo is not None}
    uploaders: dict[str, User] = {}
    if uploader_ids:
        uploaders = {
            user.id: user
            for user in (
                await db.execute(select(User).where(User.id.in_(uploader_ids)))
            ).scalars()
        }
    items = [
        _review_out(
            review,
            uploader=uploaders.get(review.photo.uploader_id) if review.photo else None,
        )
        for review in reviews
    ]
    return ModerationQueueResponse(
        items=items,
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/drain",
    response_model=ModerationDrainResponse,
    summary="手动消费审核队列",
    description=(
        "立即领取并处理一批 queued 审核记录（内嵌 worker 平时已自动轮询）。"
        "用于运维排障：重启后确认积压已清空，或在关闭内嵌 worker 时手动推进。"
    ),
)
async def drain_moderation_queue(
    limit: int = Query(5, ge=1, le=50, description="本次最多处理的条数"),
    _current_user: User = Depends(get_current_auditor_user),
):
    processed = await process_pending_reviews(limit=limit)
    return ModerationDrainResponse(processed=processed)


@router.get("/stats", response_model=ModerationStatsResponse, summary="审核统计")
async def get_moderation_stats(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_auditor_user),
):
    """近 N 天的级别 / 状态分布、平均延迟、token、成本与当日预算使用。"""
    since = datetime.utcnow() - timedelta(days=days)
    window = (ModerationReview.created_at >= since)
    total = (
        await db.execute(select(func.count()).select_from(ModerationReview).where(window))
    ).scalar_one()

    by_tier = {"L0": 0, "L1": 0, "L2": 0}
    for tier_value, count in (
        await db.execute(
            select(ModerationReview.tier, func.count())
            .where(window)
            .group_by(ModerationReview.tier)
        )
    ).all():
        if tier_value in by_tier:
            by_tier[tier_value] = int(count)

    by_status: dict[str, int] = {}
    for status_value, count in (
        await db.execute(
            select(ModerationReview.status, func.count())
            .where(window)
            .group_by(ModerationReview.status)
        )
    ).all():
        by_status[str(status_value)] = int(count)

    aggregates = (
        await db.execute(
            select(
                func.avg(ModerationReview.latency_ms),
                func.coalesce(func.sum(ModerationReview.prompt_tokens), 0),
                func.coalesce(func.sum(ModerationReview.completion_tokens), 0),
                func.coalesce(func.sum(ModerationReview.cost_usd), 0.0),
            ).where(window)
        )
    ).one()

    latest_reviews = _queue_base().subquery()
    pending_human = (
        await db.execute(
            select(func.count())
            .select_from(latest_reviews)
            .where(latest_reviews.c.final_decision.is_(None))
        )
    ).scalar_one()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_calls = (
        await db.execute(
            select(func.count())
            .select_from(AIUsageEvent)
            .where(
                AIUsageEvent.operation.like(f"{MODERATION_OPERATION_PREFIX}%"),
                AIUsageEvent.created_at >= today_start,
            )
        )
    ).scalar_one()

    budget = int(settings.MODERATION_DAILY_CALL_BUDGET or 0)
    remaining = max(0, budget - int(today_calls or 0)) if budget > 0 else None

    return ModerationStatsResponse(
        days=days,
        total=int(total or 0),
        by_tier=by_tier,
        by_status=by_status,
        pending_human=int(pending_human or 0),
        avg_latency_ms=round(float(aggregates[0] or 0.0), 1),
        prompt_tokens=int(aggregates[1] or 0),
        completion_tokens=int(aggregates[2] or 0),
        cost_usd=round(float(aggregates[3] or 0.0), 6),
        today_calls=int(today_calls or 0),
        daily_budget=budget,
        remaining_calls=remaining,
    )


@router.get("/{photo_id}", response_model=ModerationReviewOut, summary="单张照片审核详情")
async def get_moderation_detail(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_auditor_user),
):
    """返回指定照片最新一次审核记录（含规则 / 快筛 / 复核三层依据）。"""
    photo = await db.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="照片不存在")
    review = await get_latest_review(db, photo_id)
    if review is None:
        raise HTTPException(status_code=404, detail="该照片暂无审核记录，可先触发重跑")
    uploader = await db.get(User, photo.uploader_id) if photo.uploader_id else None
    return _review_out(review, photo, uploader)


# ---------------------------------------------------------------------------
# 重跑 / 人工终判
# ---------------------------------------------------------------------------

@router.post(
    "/{photo_id}/run",
    response_model=ModerationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="重新触发 AI 审核",
)
async def run_moderation_for_photo(
    photo_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    """异步重跑审核：立即返回 202，结论稍后写回 moderation_reviews。"""
    if not settings.MODERATION_ENABLED:
        raise HTTPException(status_code=409, detail="AI 审核未启用（MODERATION_ENABLED=false）")
    photo = await db.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="照片不存在")

    review = ModerationReview(photo_id=photo_id, status="queued")
    db.add(review)
    await db.flush()
    await log_audit(
        db,
        user_id=current_user.id,
        action="moderation.run",
        resource_type="photo",
        resource_id=photo_id,
        detail=json.dumps({"review_id": review.id}, ensure_ascii=False),
    )
    await db.commit()
    await db.refresh(review)

    enqueued = await enqueue_moderation(
        db, background_tasks, photo_id, force=True, review_id=review.id
    )
    if not enqueued:
        raise HTTPException(status_code=503, detail="审核任务入队失败，请稍后重试")
    return ModerationRunResponse(photo_id=photo_id, review_id=review.id)


async def _apply_decision(
    db: AsyncSession,
    photo: Photo,
    review: ModerationReview,
    *,
    decision: str,
    reason: Optional[str],
    final_tier: Optional[str],
    request: Request,
    current_user: User,
) -> None:
    """把人工终判写进 review / photo，并记审计与通知（不 commit，由调用方决定事务边界）。"""
    resolved_tier = final_tier or review.tier or "L2"
    if resolved_tier not in VALID_TIERS:  # 双保险：Pydantic 已限制
        resolved_tier = "L2"

    review.final_decision = decision
    review.final_tier = resolved_tier
    review.tier = resolved_tier
    review.reviewer_id = current_user.id
    review.reviewed_at = datetime.utcnow()
    if decision == "hold" and review.status != "completed":
        review.status = "completed"

    if decision == "approve":
        photo.status = "approved"
        photo.published_at = photo.published_at or datetime.utcnow()
    elif decision == "reject":
        photo.status = "rejected"
    # hold：照片保持 pending，等待上传者补充材料或下一轮复审

    # 策展自动归档：approve 加入「光的一日 / 樱色光谱」，reject 从这两个自动策展里移出
    await sync_photo_curation(db, photo)

    detail = {
        "decision": decision,
        "final_tier": resolved_tier,
        "review_id": review.id,
        "reason": reason,
    }
    await log_audit(
        db,
        user_id=current_user.id,
        action=f"moderation.{decision}",
        resource_type="photo",
        resource_id=photo.id,
        detail=json.dumps(detail, ensure_ascii=False),
        request=request,
    )
    if decision in ("approve", "reject"):
        await notify_user(
            db,
            user_id=photo.uploader_id,
            type="photo_approved" if decision == "approve" else "photo_rejected",
            title="您的照片已通过审核" if decision == "approve" else "您的照片未通过审核",
            content=(reason or "")[:500] or None,
            related_id=photo.id,
        )


@router.post("/{photo_id}/decision", response_model=ModerationReviewOut, summary="人工终判")
async def decide_moderation(
    photo_id: str,
    payload: ModerationDecisionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    """人工终判：approve 放行 / reject 拒绝 / hold 继续挂起等补充材料。"""
    photo = await db.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="照片不存在")

    review = await get_latest_review(db, photo_id)
    if review is None:
        review = ModerationReview(photo_id=photo_id, status="completed")
        db.add(review)
        await db.flush()

    if review.final_decision in ("approve", "reject"):
        raise HTTPException(status_code=409, detail="该照片已有终判，不能重复决策")

    await _apply_decision(
        db,
        photo,
        review,
        decision=payload.decision,
        reason=payload.reason,
        final_tier=payload.final_tier,
        request=request,
        current_user=current_user,
    )
    await db.commit()
    await db.refresh(review)
    return _review_out(review, photo)


@router.post(
    "/batch-decision",
    response_model=ModerationBatchDecisionResponse,
    summary="批量人工终判",
)
async def batch_decide_moderation(
    payload: ModerationBatchDecisionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    """批量 approve / reject / hold。

    逐条独立提交：某一张失败（不存在 / 已有终判 / 异常）不会影响其它照片，
    结果里逐条返回 ``ok`` 与 ``error``，前端据此报告。
    """
    results: list[ModerationBatchItemResult] = []
    for photo_id in payload.photo_ids:
        photo = await db.get(Photo, photo_id)
        if photo is None:
            results.append(
                ModerationBatchItemResult(photo_id=photo_id, ok=False, error="照片不存在")
            )
            continue
        try:
            review = await get_latest_review(db, photo_id)
            if review is None:
                review = ModerationReview(photo_id=photo_id, status="completed")
                db.add(review)
                await db.flush()
            if review.final_decision in ("approve", "reject"):
                results.append(
                    ModerationBatchItemResult(
                        photo_id=photo_id, ok=False, error="该照片已有终判，不能重复决策"
                    )
                )
                continue
            await _apply_decision(
                db,
                photo,
                review,
                decision=payload.decision,
                reason=payload.reason,
                final_tier=payload.final_tier,
                request=request,
                current_user=current_user,
            )
            await db.commit()
            results.append(
                ModerationBatchItemResult(
                    photo_id=photo_id, ok=True, decision=payload.decision
                )
            )
        except Exception as exc:  # noqa: BLE001 - 逐条容错，把原因带回前端
            await db.rollback()
            logger.warning("批量终判失败 photo=%s: %s", photo_id, exc)
            results.append(
                ModerationBatchItemResult(
                    photo_id=photo_id, ok=False, error="处理失败，请稍后重试"
                )
            )

    succeeded = sum(1 for item in results if item.ok)
    return ModerationBatchDecisionResponse(
        ok=True,
        processed=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        items=results,
    )


__all__ = ["router"]
