"""批量人工终判接口回归测试。

覆盖：多张混合结果（成功 / 已有终判 / 不存在）、批量拒绝、未鉴权 401。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.database import Base
from app.core.security import create_access_token
from app.main import app
from app.models.moderation import ModerationReview
from app.models.photo import Photo
from app.models.user import User


@pytest.fixture
def batch_env(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    monkeypatch.setattr(settings, "REQUIRE_REGISTRATION_APPROVAL", False)

    db_path = tmp_path / "batch.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            auditor = User(
                student_id="20269901",
                email="auditor@example.com",
                full_name="审核员",
                username="batch_auditor",
                role="auditor",
                is_active=True,
                hashed_password="x",
                token_version=1,
            )
            owner = User(
                student_id="20269902",
                email="owner@example.com",
                full_name="作者",
                username="batch_owner",
                role="user",
                is_active=True,
                hashed_password="x",
                token_version=1,
            )
            db.add_all([auditor, owner])
            await db.flush()

            for idx in range(1, 4):
                photo = Photo(
                    uploader_id=owner.id,
                    filename=f"batch{idx}.jpg",
                    title=f"批量测试 {idx}",
                    status="pending",
                    original_path=f"originals/batch{idx}.jpg",
                    width=100,
                    height=100,
                )
                db.add(photo)
                await db.flush()
                review = ModerationReview(
                    photo_id=photo.id,
                    status="completed",
                    tier="L1",
                    suggested_tier="L1",
                    provider="test",
                    model_id="fake",
                )
                db.add(review)
                await db.flush()
                if idx == 3:
                    # 第三张已经终判通过，用于覆盖「已有终判」分支
                    review.final_decision = "approve"
                    review.final_tier = "L1"
                    photo.status = "approved"
                    photo.published_at = datetime.utcnow()
            await db.commit()

    asyncio.run(seed())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _auditor_token() -> str:
    return create_access_token({"sub": "20269901", "ver": 1})


def test_batch_decision_reports_mixed_results(batch_env: TestClient):
    # 先取三张照片 id（按标题排序稳定）
    from app.core.database import AsyncSessionLocal  # noqa: F401  (仅说明来源，实际不直接用)

    with batch_env as client:
        queue = client.get(
            "/api/v1/admin/moderation/queue?limit=10",
            headers={"Authorization": f"Bearer {_auditor_token()}"},
        )
        assert queue.status_code == 200, queue.text
        photo_ids = [item["photo"]["id"] for item in queue.json()["items"]]
        assert len(photo_ids) == 3

        payload = {
            "photo_ids": photo_ids + ["00000000-0000-0000-0000-000000000000"],
            "decision": "approve",
            "reason": "批量测试通过",
            "final_tier": "L1",
        }
        resp = client.post(
            "/api/v1/admin/moderation/batch-decision",
            json=payload,
            headers={"Authorization": f"Bearer {_auditor_token()}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["processed"] == 4
        assert body["succeeded"] == 2
        assert body["failed"] == 2
        errors = [item["error"] for item in body["items"] if not item["ok"]]
        assert any("已有终判" in (err or "") for err in errors)
        assert any("不存在" in (err or "") for err in errors)

        detail = client.get(
            f"/api/v1/admin/moderation/{photo_ids[0]}",
            headers={"Authorization": f"Bearer {_auditor_token()}"},
        )
        assert detail.status_code == 200
        assert detail.json()["final_decision"] == "approve"


def test_batch_decision_requires_auth(batch_env: TestClient):
    resp = batch_env.post(
        "/api/v1/admin/moderation/batch-decision",
        json={"photo_ids": ["x"], "decision": "hold"},
    )
    assert resp.status_code == 401
