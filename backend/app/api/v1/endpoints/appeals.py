"""
审核复核（申诉）管理端端点

- `GET  /api/v1/admin/appeals`：复核申请列表（待处理优先）
- `GET  /api/v1/admin/appeals/stats`：概览
- `POST /api/v1/admin/appeals/{id}/resolve`：受理
    accept → 作品回到 pending 并重新入审核队列，通知作者
    reject → 保持 rejected，通知作者结论
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_auditor_user, get_db
from app.models.appeal import PhotoAppeal
from app.models.photo import Photo
from app.models.user import User
from app.schemas.appeal import (
    AppealAdminOut,
    AppealListResponse,
    AppealResolveRequest,
    AppealResolveResponse,
    AppealStats,
)
from app.services.audit import log_audit
from app.services.moderation_worker import enqueue_moderation
from app.services.notification import notify_user

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/appeals", tags=["审核复核"])


async def _to_item(db: AsyncSession, appeal: PhotoAppeal) -> AppealAdminOut:
    photo = await db.get(Photo, appeal.photo_id)
    uploader = await db.get(User, appeal.user_id) if appeal.user_id else None
    return AppealAdminOut(
        id=appeal.id,
        photo_id=appeal.photo_id,
        photo_title=(photo.title or photo.filename) if photo else None,
        thumb_url=f"/api/v1/photos/{appeal.photo_id}/image/thumbnail" if photo else None,
        uploader_username=uploader.username if uploader else None,
        uploader_display_name=uploader.display_name if uploader else None,
        reason=appeal.reason,
        status=appeal.status,
        note=appeal.note,
        created_at=appeal.created_at,
        handled_at=appeal.handled_at,
    )


@admin_router.get("", response_model=AppealListResponse, summary="复核申请列表")
async def list_appeals(
    appeal_status: Optional[str] = Query(None, alias="status", description="pending|accepted|rejected"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    """待处理优先，其次按提交时间倒序。"""
    query = select(PhotoAppeal)
    count_query = select(func.count(PhotoAppeal.id))
    if appeal_status:
        query = query.where(PhotoAppeal.status == appeal_status)
        count_query = count_query.where(PhotoAppeal.status == appeal_status)
    total = (await db.execute(count_query)).scalar() or 0
    status_order = {"pending": 0, "accepted": 1, "rejected": 2}
    rows = (
        await db.execute(
            query.order_by(PhotoAppeal.status != "pending", PhotoAppeal.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    items = [await _to_item(db, row) for row in rows]
    return AppealListResponse(items=items, total=int(total))


@admin_router.get("/stats", response_model=AppealStats, summary="复核申请概览")
async def appeal_stats(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    since = datetime.utcnow() - timedelta(days=days)

    async def _count(where):
        q = select(func.count(PhotoAppeal.id))
        if where is not None:
            q = q.where(where)
        return int((await db.execute(q)).scalar() or 0)

    return AppealStats(
        total=await _count(None),
        pending=await _count(PhotoAppeal.status == "pending"),
        accepted=await _count(PhotoAppeal.status == "accepted"),
        rejected=await _count(PhotoAppeal.status == "rejected"),
        last_7_days=await _count(PhotoAppeal.created_at >= since),
    )


@admin_router.post(
    "/{appeal_id}/resolve", response_model=AppealResolveResponse, summary="受理复核申请"
)
async def resolve_appeal(
    appeal_id: str,
    payload: AppealResolveRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    appeal = await db.get(PhotoAppeal, appeal_id)
    if appeal is None:
        raise HTTPException(status_code=404, detail="复核申请不存在")
    if appeal.status != "pending":
        raise HTTPException(status_code=409, detail="该复核申请已经处理过了")

    photo = await db.get(Photo, appeal.photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="作品不存在")

    note = (payload.note or "").strip()
    appeal.handled_by = current_user.id
    appeal.handled_at = datetime.utcnow()

    if payload.decision == "accept":
        appeal.status = "accepted"
        appeal.note = note or "复核通过，作品已重新进入审核流程"
        photo.status = "pending"
        await enqueue_moderation(db, background_tasks, photo.id, force=True)
        await notify_user(
            db,
            user_id=appeal.user_id,
            type="photo_appeal_accepted",
            title="复核申请已受理，作品重新进入审核",
            content=appeal.note[:500],
            related_id=photo.id,
        )
        action = "appeal.accept"
        message = "已受理：作品已退回审核队列，会按最新审核结果通知你"
    else:
        appeal.status = "rejected"
        appeal.note = note or "复核结论：维持原审核结果"
        await notify_user(
            db,
            user_id=appeal.user_id,
            type="photo_appeal_rejected",
            title="复核申请未通过",
            content=appeal.note[:500],
            related_id=photo.id,
        )
        action = "appeal.reject"
        message = "已驳回复核申请，结论已通知作者"

    await log_audit(
        db,
        user_id=current_user.id,
        action=action,
        resource_type="photo_appeal",
        resource_id=appeal.id,
        detail=json.dumps(
            {
                "photo_id": photo.id,
                "decision": payload.decision,
                "note": appeal.note,
            },
            ensure_ascii=False,
        ),
        request=request,
    )
    await db.commit()

    return AppealResolveResponse(ok=True, status=appeal.status, message=message)
