"""Celery 包装：把 AI 审核任务接到现有 Celery app 上（沿用 app/tasks/ai.py 的写法）。

Celery 未安装 / 未配置时 ``celery_app`` 为 None，本模块只保留可导入的纯函数，
由 ``moderation_worker.enqueue_moderation`` 自动回退到 BackgroundTasks。
"""
from __future__ import annotations

import asyncio

from app.core.celery_app import celery_app
from app.services.moderation_worker import run_moderation

if celery_app is not None:

    @celery_app.task(name="app.tasks.moderation.run_photo_moderation")
    def run_photo_moderation(
        photo_id: str,
        force: bool = False,
        review_id: str | None = None,
    ) -> None:
        """Celery 入口：在 worker 进程里跑一次完整审核。"""
        asyncio.run(run_moderation(photo_id, force=force, review_id=review_id))
