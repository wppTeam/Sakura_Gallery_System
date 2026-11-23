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

from sqlalchemy import select
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


def enqueue_moderation(
    background_tasks: object | None,
    photo_id: str,
    *,
    force: bool = False,
    review_id: str | None = None,
) -> bool:
    """把审核任务排到后台（Celery 优先，否则 BackgroundTasks / asyncio）。

    返回是否成功入队。任何异常都被吞掉——上传接口不能因为审核入队失败而 500。
    """
    if not settings.MODERATION_ENABLED:
        return False
    try:
        queue_backend = (getattr(settings, "TASK_QUEUE_BACKEND", None) or "background").lower()
        if celery_app is not None and queue_backend == "celery":
            celery_app.send_task(
                CELERY_TASK_NAME,
                kwargs={"photo_id": photo_id, "force": force, "review_id": review_id},
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
            review_id=review_id,
        )
        return True
    try:
        asyncio.create_task(run_moderation(photo_id, force=force, review_id=review_id))
        return True
    except RuntimeError:
        logger.warning("no event loop to run moderation for photo=%s", photo_id)
        return False


__all__ = [
    "CELERY_TASK_NAME",
    "get_latest_review",
    "run_moderation",
    "enqueue_moderation",
]
