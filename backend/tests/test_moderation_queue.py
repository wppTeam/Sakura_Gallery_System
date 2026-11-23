"""审核队列持久化（durable queue）与内嵌 worker 测试。

覆盖：

1. 入队即落库：上传/重跑只调一次 ``enqueue_moderation``，``moderation_reviews``
   里就有 queued 行——进程重启后不会丢任务（不再依赖内存里的 BackgroundTasks）；
2. worker 兜底消费：没有快路径时 ``process_pending_reviews`` 也能把 queued 跑成 completed；
3. 幂等：已 completed 的记录再入队不会重新花钱；
4. 崩溃恢复：卡在 running 超过 ``MODERATION_WORKER_STALE_SECONDS`` 的记录会被回收重跑。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import Base
from app.models import Photo, User
from app.models.moderation import ModerationReview
from app.services import moderation_worker as mw


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FakeBackgroundTasks:
    """记录 add_task 调用，但不执行——模拟“快路径还没跑”的状态。"""

    def __init__(self) -> None:
        self.tasks: list[tuple] = []
        self.kwargs: list[dict] = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, *args))
        self.kwargs.append(kwargs)


async def _fake_moderate_photo(db, photo, review):
    """替代真实 AI 链路：直接给一个 L0 完成结论，避免测试花钱/联网。"""
    review.status = "completed"
    review.tier = "L0"
    review.suggested_tier = "L0"
    review.final_decision = "approve"
    review.provider = "fake"
    review.model_id = "fake-model"
    await db.flush()
    return review


@dataclass
class QueueEnv:
    db_path: Path
    engine: object
    factory: async_sessionmaker
    photo_id: str = "queue-photo-1"
    background: FakeBackgroundTasks = field(default_factory=FakeBackgroundTasks)


@pytest.fixture
def queue_env(tmp_path: Path, monkeypatch) -> QueueEnv:
    settings = get_settings()
    monkeypatch.setattr(settings, "MODERATION_ENABLED", True)
    monkeypatch.setattr(settings, "MODERATION_QUEUE_MODE", "durable")
    monkeypatch.setattr(settings, "MODERATION_WORKER_EMBEDDED", False)
    monkeypatch.setattr(settings, "MODERATION_WORKER_BATCH", 5)
    monkeypatch.setattr(settings, "MODERATION_WORKER_POLL_SECONDS", 0.5)
    monkeypatch.setattr(settings, "MODERATION_WORKER_STALE_SECONDS", 900)
    monkeypatch.setattr(settings, "MODERATION_RETRY", 0)
    monkeypatch.setattr(settings, "AI_ENABLED", False)

    db_path = tmp_path / "queue.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _init() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add(
                User(
                    id="queue-user-1",
                    student_id="20261234",
                    username="queueuser",
                    display_name="队列测试",
                    full_name="队列测试",
                    role="user",
                )
            )
            session.add(
                Photo(
                    id="queue-photo-1",
                    uploader_id="queue-user-1",
                    filename="queue.jpg",
                    title="队列测试图",
                    status="pending",
                    processing_status="completed",
                )
            )
            await session.commit()

    asyncio.run(_init())
    monkeypatch.setattr(mw, "AsyncSessionLocal", factory)
    monkeypatch.setattr(mw, "moderate_photo", _fake_moderate_photo)

    return QueueEnv(db_path=db_path, engine=engine, factory=factory)


async def _get_review(env: QueueEnv) -> ModerationReview | None:
    async with env.factory() as session:
        stmt = (
            select(ModerationReview)
            .where(ModerationReview.photo_id == env.photo_id)
            .order_by(ModerationReview.created_at.desc())
        )
        return (await session.execute(stmt)).scalars().first()


def test_enqueue_persists_queued_review_before_any_ai_call(queue_env: QueueEnv):
    async def _run() -> None:
        async with queue_env.factory() as session:
            ok = await mw.enqueue_moderation(
                session, queue_env.background, queue_env.photo_id
            )
            assert ok is True
            assert len(queue_env.background.tasks) == 1  # 快路径已排，但尚未执行

        review = await _get_review(queue_env)
        assert review is not None
        assert review.status == "queued"
        assert review.tier is None  # 还没花模型钱

    asyncio.run(_run())


def test_worker_processes_queued_review_without_fast_path(queue_env: QueueEnv):
    """快路径丢失（进程重启）时，内嵌 worker 仍能把 queued 跑完——本次不再调用快路径。"""

    async def _run() -> int:
        async with queue_env.factory() as session:
            await mw.enqueue_moderation(session, None, queue_env.photo_id)
        return await mw.process_pending_reviews(limit=5)

    processed = asyncio.run(_run())
    assert processed == 1

    review = asyncio.run(_get_review(queue_env))
    assert review is not None
    assert review.status == "completed"
    assert review.tier == "L0"


def test_completed_review_is_not_charged_again(queue_env: QueueEnv):
    async def _run_first() -> None:
        async with queue_env.factory() as session:
            await mw.enqueue_moderation(session, queue_env.background, queue_env.photo_id)
        await mw.process_pending_reviews(limit=5)

    asyncio.run(_run_first())
    review = asyncio.run(_get_review(queue_env))
    assert review is not None and review.status == "completed"
    review_id = review.id

    async def _run_second() -> bool:
        async with queue_env.factory() as session:
            return await mw.enqueue_moderation(
                session, queue_env.background, queue_env.photo_id
            )

    ok = asyncio.run(_run_second())
    assert ok is True  # 幂等复用：会调度一次快路径，但 run_moderation 内部直接复用 completed
    assert asyncio.run(_get_review(queue_env)).id == review_id
    assert asyncio.run(mw.process_pending_reviews(limit=5)) == 0


def test_stale_running_review_is_reclaimed_and_processed(queue_env: QueueEnv):
    async def _seed_stale() -> str:
        async with queue_env.factory() as session:
            review = ModerationReview(
                photo_id=queue_env.photo_id,
                status="running",
                tier="L1",
                updated_at=_utcnow_naive() - timedelta(hours=2),
                created_at=_utcnow_naive() - timedelta(hours=2),
            )
            session.add(review)
            await session.commit()
            await session.refresh(review)
            return review.id

    review_id = asyncio.run(_seed_stale())
    processed = asyncio.run(mw.process_pending_reviews(limit=5))

    assert processed == 1
    review = asyncio.run(_get_review(queue_env))
    assert review is not None
    assert review.id == review_id
    assert review.status == "completed"


def test_enqueue_disabled_returns_false(queue_env: QueueEnv, monkeypatch):
    monkeypatch.setattr(get_settings(), "MODERATION_ENABLED", False)

    async def _run() -> bool:
        async with queue_env.factory() as session:
            return await mw.enqueue_moderation(
                session, queue_env.background, queue_env.photo_id
            )

    assert asyncio.run(_run()) is False
    assert asyncio.run(_get_review(queue_env)) is None
    assert queue_env.background.tasks == []
