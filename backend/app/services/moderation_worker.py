"""AI 审核后台 worker：事务边界、幂等复用、失败重试、入队适配。

调用关系：

- 上传端点 → :func:`enqueue_moderation`（BackgroundTasks 或 Celery）；
- Celery 任务 / BackgroundTasks → :func:`run_moderation`；
- 管理端“重跑” → :func:`run_moderation`（force=True）。

设计要点：
- **绝不阻塞上传**：入队只做一次内存调用，AI 全在后台跑；
- **幂等**：同一照片已有 running / completed 的 review 时默认直接复用，避免重复扣费；
- **失败降级**：重试 ``MODERATION_RETRY`` 次仍失败则把 review 置 failed（照片保持 pending），
  管理端可再次触发；预算耗尽不再无意义重试；
- worker 自建 ``AsyncSessionLocal`` 并负责 commit，服务层只 flush。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.moderation import ModerationReview
from app.models.photo import Photo
from app.services.moderation import moderate_photo

logger = logging.getLogger(__name__)
settings = get_settings()

CELERY_TASK_NAME = "app.tasks.moderation.run_photo_moderation"


async def get_latest_review(
    db: AsyncSession, photo_id: str
) -> ModerationReview | None:
    """取某照片最新一次审核记录。"""
    stmt = (
        select(ModerationReview)
        .where(ModerationReview.photo_id == photo_id)
        .order_by(ModerationReview.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def run_moderation(
    photo_id: str,
    *,
    force: bool = False,
    review_id: str | None = None,
) -> ModerationReview | None:
    """执行一次（可重试的）审核并提交事务，返回最终 review（照片不存在返回 None）。"""
    if not settings.MODERATION_ENABLED:
        logger.info("moderation disabled, skip photo=%s", photo_id)
        return None

    async with AsyncSessionLocal() as db:
        photo = await db.get(Photo, photo_id)
        if photo is None:
            logger.warning("moderation skipped: photo %s not found", photo_id)
            return None

        review: ModerationReview | None = None
        if review_id:
            review = await db.get(ModerationReview, review_id)
        if review is None:
            review = await get_latest_review(db, photo_id)

        # 幂等：已完成的结论不重复花钱；running 说明并发 worker 正在跑
        if review is not None and not force and review.status in ("running", "completed"):
            logger.info(
                "moderation reused: photo=%s review=%s status=%s",
                photo_id,
                review.id,
                review.status,
            )
            return review

        if review is None:
            review = ModerationReview(photo_id=photo_id, status="queued")
            db.add(review)
            await db.flush()

        attempts = max(1, int(settings.MODERATION_RETRY or 0) + 1)
        result: ModerationReview | None = None
        for attempt in range(1, attempts + 1):
            result = await moderate_photo(db, photo, review)
            if result.status == "completed":
                break
            # 预算耗尽 / 渠道未配置：重试无意义，直接进人工队列
            error = result.error or ""
            if error.startswith(("AIBudgetExceeded", "AIConfigError")):
                logger.warning(
                    "moderation degraded to manual (photo=%s): %s", photo_id, error[:200]
                )
                break
            if attempt < attempts:
                logger.warning(
                    "moderation retry photo=%s attempt=%d/%d error=%s",
                    photo_id,
                    attempt,
                    attempts,
                    error[:200],
                )

        if result is not None and result.status == "failed":
            # 降级兜底：至少进人工，绝不停留在 L0；照片保持 pending 等人工终判
            if not result.tier or result.tier == "L0":
                result.tier = "L1"
            if not result.suggested_tier:
                result.suggested_tier = result.tier

        await db.commit()
        if result is not None:
            await db.refresh(result)
        return result


async def _reclaim_stale_reviews(db: AsyncSession) -> int:
    """把卡在 running 过久的记录回收为 queued（worker 崩溃 / 进程重启）。"""
    stale_seconds = int(settings.MODERATION_WORKER_STALE_SECONDS or 0)
    if stale_seconds <= 0:
        return 0
    cutoff = _utcnow() - timedelta(seconds=stale_seconds)
    stmt = (
        update(ModerationReview)
        .where(ModerationReview.status == "running")
        .where(ModerationReview.updated_at < cutoff)
        .values(status="queued", updated_at=_utcnow())
    )
    result = await db.execute(stmt)
    await db.commit()
    reclaimed = int(result.rowcount or 0)
    if reclaimed:
        logger.warning("moderation worker reclaimed %d stale running review(s)", reclaimed)
    return reclaimed


async def _claim_queued_reviews(
    db: AsyncSession, limit: int
) -> list[ModerationReview]:
    """原子领取一批 queued 记录并置 running（PG 用 SKIP LOCKED，避免多 worker 抢同一条）。"""
    stmt = (
        select(ModerationReview)
        .where(ModerationReview.status == "queued")
        .order_by(ModerationReview.created_at.asc(), ModerationReview.id.asc())
        .limit(limit)
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    reviews = list((await db.execute(stmt)).scalars().all())
    if not reviews:
        return []
    ids = [review.id for review in reviews]
    now = _utcnow()
    await db.execute(
        update(ModerationReview)
        .where(ModerationReview.id.in_(ids))
        .where(ModerationReview.status == "queued")
        .values(status="running", updated_at=now)
    )
    await db.commit()
    for review in reviews:
        review.status = "running"
    return reviews


async def process_pending_reviews(limit: int | None = None) -> int:
    """消费一批 queued 审核记录，返回成功处理的条数（供内嵌 worker / 手动 drain 使用）。"""
    if not settings.MODERATION_ENABLED:
        return 0
    batch = max(1, int(limit or settings.MODERATION_WORKER_BATCH or 1))
    async with AsyncSessionLocal() as db:
        await _reclaim_stale_reviews(db)
        claimed = await _claim_queued_reviews(db, batch)
    if not claimed:
        return 0

    processed = 0
    for review in claimed:
        try:
            await run_moderation(review.photo_id, force=True, review_id=review.id)
            processed += 1
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 单条失败不能拖垮 worker 循环
            logger.exception("moderation worker failed review=%s", review.id)
            try:
                async with AsyncSessionLocal() as db:
                    row = await db.get(ModerationReview, review.id)
                    if row is not None and row.status in ("queued", "running"):
                        row.status = "failed"
                        row.error = (row.error or "")[:2000] or "worker exception"
                        row.updated_at = _utcnow()
                        await db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("moderation worker failed to mark review failed=%s", review.id)
    return processed


async def worker_loop(stop_event: asyncio.Event | None = None) -> None:
    """常驻消费循环：定时回收 stale + 领取 queued。"""
    poll = max(0.5, float(settings.MODERATION_WORKER_POLL_SECONDS or 5.0))
    logger.info(
        "moderation worker started: poll=%.1fs batch=%s stale=%ss",
        poll,
        settings.MODERATION_WORKER_BATCH,
        settings.MODERATION_WORKER_STALE_SECONDS,
    )
    while stop_event is None or not stop_event.is_set():
        try:
            await process_pending_reviews()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 循环必须活下去
            logger.exception("moderation worker loop iteration failed")
        if stop_event is not None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll)
                return
            except asyncio.TimeoutError:
                continue
        await asyncio.sleep(poll)


def start_embedded_worker() -> asyncio.Task | None:
    """在 API 进程内启动审核队列消费任务（lifespan 调用）。"""
    if not settings.MODERATION_ENABLED or not settings.MODERATION_WORKER_EMBEDDED:
        return None
    return asyncio.create_task(worker_loop(), name="moderation-worker")


def _utcnow() -> datetime:
    """naive UTC 时间（与 DB DateTime 列一致，避免 SQLite 时区比较问题）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _ensure_queued_review(
    db: AsyncSession,
    photo_id: str,
    *,
    force: bool = False,
    review_id: str | None = None,
) -> ModerationReview | None:
    """确保该照片有一条 queued 状态的审核记录（持久化后才可能被 worker 兜底消费）。"""
    review: ModerationReview | None = None
    if review_id:
        review = await db.get(ModerationReview, review_id)
    if review is None:
        review = await get_latest_review(db, photo_id)

    if review is not None and not force:
        # 已有 queued/running/completed：复用，不重复扣费
        return review
    if review is not None and force and review.status in ("queued", "running"):
        # 重跑请求但记录还没跑：直接复用这条 queued 记录
        return review
    if review is not None and force and review.status in ("completed", "failed"):
        # 重跑语义：保留历史记录，新建一条
        review = None

    if review is None:
        review = ModerationReview(photo_id=photo_id, status="queued")
        db.add(review)
        await db.flush()
    await db.commit()
    await db.refresh(review)
    return review


async def enqueue_moderation(
    db: AsyncSession | None,
    background_tasks: object | None,
    photo_id: str,
    *,
    force: bool = False,
    review_id: str | None = None,
) -> bool:
    """持久化入队 + 尽力立即执行（Celery / BackgroundTasks / asyncio）。

    - **先落库**：``moderation_reviews`` 里的 queued 行是可靠性来源，进程重启后
      内嵌 worker 仍会把它捞起来跑（不再依赖内存中的 BackgroundTasks）。
    - **再加速**：有 BackgroundTasks 时顺带排一次快路径，保证上传后几秒内出结论。
    - 返回是否至少完成“落库或调度”之一；任何异常都被吞掉——上传接口不能因为审核入队失败而 500。
    """
    if not settings.MODERATION_ENABLED:
        return False

    queued_id = review_id
    if db is not None and (settings.MODERATION_QUEUE_MODE or "durable").lower() == "durable":
        try:
            review = await _ensure_queued_review(
                db, photo_id, force=force, review_id=review_id
            )
            if review is not None:
                queued_id = review.id
        except Exception:  # noqa: BLE001 - 落库失败仍尝试内存快路径
            logger.warning("moderation queue persist failed photo=%s", photo_id, exc_info=True)

    try:
        queue_backend = (getattr(settings, "TASK_QUEUE_BACKEND", None) or "background").lower()
        if celery_app is not None and queue_backend == "celery":
            celery_app.send_task(
                CELERY_TASK_NAME,
                kwargs={"photo_id": photo_id, "force": force, "review_id": queued_id},
            )
            logger.info("moderation enqueued to celery: photo=%s", photo_id)
            return True
    except Exception:  # noqa: BLE001 - 队列不可用时回退 BackgroundTasks
        logger.warning("celery enqueue failed, fallback to background task", exc_info=True)

    add_task = getattr(background_tasks, "add_task", None)
    if callable(add_task):
        add_task(
            run_moderation,
            photo_id,
            force=force,
            review_id=queued_id,
        )
        return True
    try:
        asyncio.create_task(run_moderation(photo_id, force=force, review_id=queued_id))
        return True
    except RuntimeError:
        logger.warning("no event loop to run moderation for photo=%s", photo_id)
        # 持久化行已经存在时，worker 会兜底，这里不算失败
        return queued_id is not None


__all__ = [
    "CELERY_TASK_NAME",
    "enqueue_moderation",
    "get_latest_review",
    "process_pending_reviews",
    "run_moderation",
    "start_embedded_worker",
    "worker_loop",
]
