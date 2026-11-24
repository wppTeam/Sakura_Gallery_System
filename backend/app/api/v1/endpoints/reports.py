"""
内容举报 / 侵权投诉端点

- 公开：`POST /api/v1/reports`（限流，匿名可提交）
- 管理：`GET /api/v1/admin/reports`、`GET /api/v1/admin/reports/stats`、
        `POST /api/v1/admin/reports/{report_id}/resolve`

受理「接受投诉」时可选择下架作品（photo.status = rejected）或撤回专题（status = draft），
同时写 audit_logs 并通知上传者。
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_auditor_user, get_db, get_optional_current_user
from app.models.collection import Collection
from app.models.photo import Photo
from app.models.report import REPORT_REASON_LABELS, Report
from app.models.user import User
from app.schemas.report import (
    ReportAdminOut,
    ReportCreate,
    ReportListResponse,
    ReportReceipt,
    ReportReporterBrief,
    ReportResolveRequest,
    ReportResolveResponse,
    ReportStats,
)
from app.services.audit import log_audit
from app.services.curation import sync_photo_curation
from app.services.notification import notify_user

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/reports", tags=["举报"])
admin_router = APIRouter(prefix="/reports", tags=["举报"])

#: 同一 IP 对同一对象 24 小时内只接受一次投诉，避免刷单
_DUPLICATE_WINDOW = timedelta(hours=24)


async def _resolve_target(db: AsyncSession, target_type: str, target_id: str):
    if target_type == "photo":
        photo = await db.get(Photo, target_id)
        if photo is None:
            raise HTTPException(status_code=404, detail="投诉对象不存在")
        return photo, photo.title or photo.filename, f"/photo/{photo.id}"
    if target_type == "collection":
        collection = await db.get(Collection, target_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="投诉对象不存在")
        return collection, collection.title, f"/collections/{collection.slug}"
    raise HTTPException(status_code=400, detail="不支持的投诉对象类型")


@router.post("", response_model=ReportReceipt, status_code=status.HTTP_201_CREATED, summary="提交举报/侵权投诉")
@limiter.limit("10/hour")
async def create_report(
    request: Request,
    payload: ReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    await _resolve_target(db, payload.target_type, payload.target_id)

    client_ip = get_remote_address(request)
    if client_ip:
        since = datetime.utcnow() - _DUPLICATE_WINDOW
        existing = await db.execute(
            select(Report.id).where(
                Report.target_type == payload.target_type,
                Report.target_id == payload.target_id,
                Report.reporter_ip == client_ip,
                Report.created_at >= since,
            )
        )
        if existing.first():
            raise HTTPException(status_code=429, detail="同一对象 24 小时内已提交过投诉，请等待处理")

    report = Report(
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason_code=payload.reason_code,
        reason_text=payload.reason_text,
        contact=(payload.contact or "").strip() or None,
        reporter_id=current_user.id if current_user else None,
        reporter_ip=client_ip,
        status="pending",
    )
    db.add(report)
    await db.flush()

    await log_audit(
        db,
        user_id=current_user.id if current_user else None,
        action="report.create",
        resource_type=payload.target_type,
        resource_id=payload.target_id,
        detail=json.dumps(
            {
                "report_id": report.id,
                "reason": payload.reason_code,
                "reason_label": REPORT_REASON_LABELS.get(payload.reason_code),
            },
            ensure_ascii=False,
        ),
        request=request,
    )
    await db.commit()
    logger.info(
        "report created id=%s target=%s:%s reason=%s", report.id, payload.target_type, payload.target_id, payload.reason_code
    )
    return ReportReceipt(id=report.id)


def _serialize_admin(
    report: Report,
    *,
    target_title: Optional[str] = None,
    target_url: Optional[str] = None,
    reporter: Optional[User] = None,
    handler: Optional[User] = None,
) -> ReportAdminOut:
    return ReportAdminOut(
        id=report.id,
        target_type=report.target_type,
        target_id=report.target_id,
        target_title=target_title,
        target_url=target_url,
        reason_code=report.reason_code,
        reason_label=REPORT_REASON_LABELS.get(report.reason_code, report.reason_code),
        reason_text=report.reason_text,
        contact=report.contact,
        reporter=ReportReporterBrief(username=reporter.username, display_name=reporter.display_name) if reporter else None,
        reporter_ip=report.reporter_ip,
        status=report.status,
        handled_by=handler.username or handler.display_name if handler else None,
        handled_at=report.handled_at,
        resolution_note=report.resolution_note,
        action_taken=report.action_taken,
        created_at=report.created_at,
    )


@admin_router.get("", response_model=ReportListResponse, summary="举报列表（管理端）")
async def list_reports(
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(pending|accepted|rejected)$"),
    target_type: Optional[str] = Query(None, pattern="^(photo|collection)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    base = select(Report)
    count_base = select(func.count()).select_from(Report)
    if status_filter:
        base = base.where(Report.status == status_filter)
        count_base = count_base.where(Report.status == status_filter)
    if target_type:
        base = base.where(Report.target_type == target_type)
        count_base = count_base.where(Report.target_type == target_type)

    total = int((await db.execute(count_base)).scalar_one() or 0)
    # 待处理优先，其次按时间倒序
    rows = (
        await db.execute(
            base.order_by(
                (Report.status == "pending").desc(),
                Report.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    # 批量取目标标题与用户，避免 N+1
    photo_ids = [r.target_id for r in rows if r.target_type == "photo"]
    collection_ids = [r.target_id for r in rows if r.target_type == "collection"]
    titles: dict[str, tuple[str, str]] = {}
    if photo_ids:
        for row in (
            await db.execute(select(Photo.id, Photo.title, Photo.filename).where(Photo.id.in_(photo_ids)))
        ).all():
            titles[row.id] = (row.title or row.filename or "未命名作品", f"/photo/{row.id}")
    if collection_ids:
        for row in (
            await db.execute(select(Collection.id, Collection.title, Collection.slug).where(Collection.id.in_(collection_ids)))
        ).all():
            titles[row.id] = (row.title or "未命名专题", f"/collections/{row.slug}")

    user_ids = {r.reporter_id for r in rows if r.reporter_id} | {r.handled_by for r in rows if r.handled_by}
    users: dict[str, User] = {}
    if user_ids:
        for row in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
            users[row.id] = row

    items = []
    for report in rows:
        title, url = titles.get(report.target_id, (None, None))
        items.append(
            _serialize_admin(
                report,
                target_title=title,
                target_url=url,
                reporter=users.get(report.reporter_id) if report.reporter_id else None,
                handler=users.get(report.handled_by) if report.handled_by else None,
            )
        )
    return ReportListResponse(items=items, total=total, limit=limit, offset=offset)


@admin_router.get("/stats", response_model=ReportStats, summary="举报概览（管理端）")
async def report_stats(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    totals = dict(
        (
            await db.execute(select(Report.status, func.count()).group_by(Report.status))
        ).all()
    )
    by_reason = dict(
        (
            await db.execute(select(Report.reason_code, func.count()).group_by(Report.reason_code))
        ).all()
    )
    since = datetime.utcnow() - timedelta(days=days)
    last = int(
        (await db.execute(select(func.count()).select_from(Report).where(Report.created_at >= since))).scalar_one()
        or 0
    )
    return ReportStats(
        total=sum(totals.values()),
        pending=totals.get("pending", 0),
        accepted=totals.get("accepted", 0),
        rejected=totals.get("rejected", 0),
        by_reason={k: int(v) for k, v in by_reason.items()},
        last_7_days=last,
    )


@admin_router.post("/{report_id}/resolve", response_model=ReportResolveResponse, summary="受理/驳回举报（管理端）")
async def resolve_report(
    report_id: str,
    payload: ReportResolveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="投诉记录不存在")
    if report.status != "pending":
        raise HTTPException(status_code=409, detail="该投诉已处理")

    action_taken: Optional[str] = None
    target = None
    if report.target_type == "photo":
        target = await db.get(Photo, report.target_id)
    elif report.target_type == "collection":
        target = await db.get(Collection, report.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="投诉对象已被删除")

    report.status = "accepted" if payload.decision == "accept" else "rejected"
    report.handled_by = current_user.id
    report.handled_at = datetime.utcnow()
    report.resolution_note = payload.note

    if payload.decision == "accept" and payload.action == "takedown":
        if report.target_type == "photo":
            target.status = "rejected"
            action_taken = "photo.takedown"
            # 下架后从「光的一日 / 樱色光谱」的自动策展里移除（数据不脏，专题页也不会留空挂）
            target_model = target
            await sync_photo_curation(db, target_model)
            await notify_user(
                db,
                user_id=target.uploader_id,
                type="photo_rejected",
                title="您的作品因举报投诉被下架",
                content=(payload.note or "作品涉及侵权或违规内容，已按投诉处理。如有异议请联系站务。")[:500],
                related_id=target.id,
            )
        else:
            target.status = "draft"
            action_taken = "collection.withdraw"
    report.action_taken = action_taken

    await log_audit(
        db,
        user_id=current_user.id,
        action=f"report.{payload.decision}",
        resource_type=report.target_type,
        resource_id=report.target_id,
        detail=json.dumps(
            {
                "report_id": report.id,
                "reason": report.reason_code,
                "action": action_taken,
                "note": payload.note,
            },
            ensure_ascii=False,
        ),
        request=request,
    )
    await db.commit()
    logger.info("report resolved id=%s decision=%s action=%s", report.id, payload.decision, action_taken)
    return ReportResolveResponse(id=report.id, status=report.status, action_taken=action_taken)
