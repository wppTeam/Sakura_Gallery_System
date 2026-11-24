"""审核复核（申诉）接口回归测试。

覆盖：作者对自己的驳回作品提交申诉、非作者 403、非 rejected 400、重复 pending 409、
查看申诉、管理端列表/概览、受理接受（作品回到 pending + 通知 + 审计）、
受理驳回（保持 rejected + 通知）、重复受理 409。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.photos import _appeal_limiter
from app.core import deps
from app.core.database import Base
from app.core.security import create_access_token
from app.main import app
from app.models.appeal import PhotoAppeal
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.photo import Photo
from app.models.user import User


@pytest.fixture
def appeal_env(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    _appeal_limiter.reset()

    db_path = tmp_path / "appeals.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    ids: dict[str, str] = {}

    async def seed() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            owner = User(
                student_id="20269901",
                email="appeal-owner@example.com",
                full_name="申诉作者",
                username="appeal_owner",
                role="user",
                is_active=True,
                hashed_password="x",
                token_version=1,
            )
            other = User(
                student_id="20269902",
                email="appeal-other@example.com",
                full_name="路人",
                username="appeal_other",
                role="user",
                is_active=True,
                hashed_password="x",
                token_version=1,
            )
            auditor = User(
                student_id="20269903",
                email="appeal-auditor@example.com",
                full_name="审核员",
                username="appeal_auditor",
                role="auditor",
                is_active=True,
                hashed_password="x",
                token_version=1,
            )
            db.add_all([owner, other, auditor])
            await db.flush()
            rejected = Photo(
                uploader_id=owner.id,
                filename="rejected.jpg",
                title="被驳回的作品",
                status="rejected",
                original_path="originals/rejected.jpg",
                width=800,
                height=600,
            )
            approved = Photo(
                uploader_id=owner.id,
                filename="approved.jpg",
                title="已发布的作品",
                status="approved",
                original_path="originals/approved.jpg",
                width=800,
                height=600,
            )
            db.add_all([rejected, approved])
            await db.commit()
            ids.update(
                owner=owner.id,
                other=other.id,
                auditor=auditor.id,
                rejected=rejected.id,
                approved=approved.id,
            )

    asyncio.run(seed())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as client:
        yield client, session_factory, ids
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _headers(student_id: str) -> dict:
    token = create_access_token({"sub": student_id, "ver": 1})
    return {"Authorization": f"Bearer {token}"}


def _owner_headers() -> dict:
    return _headers("20269901")


def _other_headers() -> dict:
    return _headers("20269902")


def _auditor_headers() -> dict:
    return _headers("20269903")


def test_author_appeals_rejected_photo(appeal_env):
    client, session_factory, ids = appeal_env
    resp = client.post(
        f"/api/v1/photos/{ids['rejected']}/appeal",
        json={"reason": "这张照片是我自己拍摄的校园樱花，驳回理由可能有误。"},
        headers=_owner_headers(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "pending"

    async def count() -> int:
        async with session_factory() as db:
            return len((await db.execute(select(PhotoAppeal))).scalars().all())

    assert asyncio.run(count()) == 1


def test_appeal_requires_ownership_and_login(appeal_env):
    client, _session_factory, ids = appeal_env
    resp = client.post(
        f"/api/v1/photos/{ids['rejected']}/appeal",
        json={"reason": "这不是我的作品，我只是试试能不能申诉。"},
        headers=_other_headers(),
    )
    assert resp.status_code == 403

    resp = client.post(
        f"/api/v1/photos/{ids['rejected']}/appeal",
        json={"reason": "未登录也应该被挡住，不能提交申诉。"},
    )
    assert resp.status_code == 401


def test_appeal_only_for_rejected_photos(appeal_env):
    client, _session_factory, ids = appeal_env
    resp = client.post(
        f"/api/v1/photos/{ids['approved']}/appeal",
        json={"reason": "已发布的作品不应该能提交申诉吧？"},
        headers=_owner_headers(),
    )
    assert resp.status_code == 400
    assert "驳回" in resp.json()["detail"]


def test_duplicate_pending_appeal_is_conflict(appeal_env):
    client, _session_factory, ids = appeal_env
    payload = {"reason": "第一次申诉：请复核这张照片的驳回理由。"}
    first = client.post(
        f"/api/v1/photos/{ids['rejected']}/appeal",
        json=payload,
        headers=_owner_headers(),
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/photos/{ids['rejected']}/appeal",
        json=payload,
        headers=_owner_headers(),
    )
    assert second.status_code == 409


def test_get_own_appeal(appeal_env):
    client, _session_factory, ids = appeal_env
    resp = client.get(f"/api/v1/photos/{ids['rejected']}/appeal", headers=_owner_headers())
    assert resp.status_code == 200
    assert resp.json() is None

    client.post(
        f"/api/v1/photos/{ids['rejected']}/appeal",
        json={"reason": "请复核，这张作品是原创拍摄。"},
        headers=_owner_headers(),
    )
    resp = client.get(f"/api/v1/photos/{ids['rejected']}/appeal", headers=_owner_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    # 其他普通用户看不到
    resp = client.get(f"/api/v1/photos/{ids['rejected']}/appeal", headers=_other_headers())
    assert resp.status_code == 403
    # 审核员可以看
    resp = client.get(f"/api/v1/photos/{ids['rejected']}/appeal", headers=_auditor_headers())
    assert resp.status_code == 200


def test_admin_list_and_stats(appeal_env):
    client, _session_factory, ids = appeal_env
    client.post(
        f"/api/v1/photos/{ids['rejected']}/appeal",
        json={"reason": "这是第一条申诉，用来测试管理端列表。"},
        headers=_owner_headers(),
    )
    resp = client.get("/api/v1/admin/appeals", headers=_auditor_headers())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["status"] == "pending"
    assert item["photo_title"] == "被驳回的作品"
    assert item["uploader_username"] == "appeal_owner"

    resp = client.get("/api/v1/admin/appeals/stats", headers=_auditor_headers())
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total"] == 1
    assert stats["pending"] == 1

    # 普通用户无权访问管理端
    resp = client.get("/api/v1/admin/appeals", headers=_owner_headers())
    assert resp.status_code == 403


def test_resolve_accept_requeues_photo(appeal_env):
    client, session_factory, ids = appeal_env
    created = client.post(
        f"/api/v1/photos/{ids['rejected']}/appeal",
        json={"reason": "这张是本人原创拍摄，请复核恢复。"},
        headers=_owner_headers(),
    ).json()

    resp = client.post(
        f"/api/v1/admin/appeals/{created['id']}/resolve",
        json={"decision": "accept", "note": "确认是原创，重新审核"},
        headers=_auditor_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"

    async def check():
        async with session_factory() as db:
            photo = await db.get(Photo, ids["rejected"])
            appeal = await db.get(PhotoAppeal, created["id"])
            notes = (
                await db.execute(
                    select(Notification).where(Notification.user_id == ids["owner"])
                )
            ).scalars().all()
            audits = (
                await db.execute(
                    select(AuditLog).where(AuditLog.action == "appeal.accept")
                )
            ).scalars().all()
            return photo.status, appeal.status, appeal.note, notes, audits

    status, appeal_status, note, notes, audits = asyncio.run(check())
    assert status == "pending"
    assert appeal_status == "accepted"
    assert note == "确认是原创，重新审核"
    assert any(n.type == "photo_appeal_accepted" for n in notes)
    assert len(audits) == 1


def test_resolve_reject_keeps_photo_rejected(appeal_env):
    client, session_factory, ids = appeal_env
    created = client.post(
        f"/api/v1/photos/{ids['rejected']}/appeal",
        json={"reason": "我觉得这张照片被误判了，请再看一次。"},
        headers=_owner_headers(),
    ).json()

    resp = client.post(
        f"/api/v1/admin/appeals/{created['id']}/resolve",
        json={"decision": "reject", "note": "复核后维持原结论"},
        headers=_auditor_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"

    async def check():
        async with session_factory() as db:
            photo = await db.get(Photo, ids["rejected"])
            notes = (
                await db.execute(
                    select(Notification).where(Notification.user_id == ids["owner"])
                )
            ).scalars().all()
            return photo.status, notes

    status, notes = asyncio.run(check())
    assert status == "rejected"
    assert any(n.type == "photo_appeal_rejected" for n in notes)

    # 重复受理 409
    resp = client.post(
        f"/api/v1/admin/appeals/{created['id']}/resolve",
        json={"decision": "accept"},
        headers=_auditor_headers(),
    )
    assert resp.status_code == 409
