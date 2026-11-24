"""举报 / 侵权投诉接口回归测试。

覆盖：匿名提交、字段校验、目标不存在、同 IP 重复提交限流、管理端列表/统计、
受理下架（照片 rejected + 通知上传者）、重复受理 409、驳回。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.reports import limiter as report_limiter
from app.core import deps
from app.core.database import Base
from app.core.security import create_access_token
from app.main import app
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.photo import Photo
from app.models.report import Report
from app.models.user import User


@pytest.fixture
def report_env(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    report_limiter.reset()

    db_path = tmp_path / "reports.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            owner = User(
                student_id="20269801",
                email="report-owner@example.com",
                full_name="被投诉作者",
                username="report_owner",
                role="user",
                is_active=True,
                hashed_password="x",
                token_version=1,
            )
            auditor = User(
                student_id="20269802",
                email="report-auditor@example.com",
                full_name="举报处理员",
                username="report_auditor",
                role="auditor",
                is_active=True,
                hashed_password="x",
                token_version=1,
            )
            db.add_all([owner, auditor])
            await db.flush()
            photo = Photo(
                uploader_id=owner.id,
                filename="reported.jpg",
                title="被投诉的作品",
                status="approved",
                original_path="originals/reported.jpg",
                width=800,
                height=600,
            )
            db.add(photo)
            await db.commit()

    asyncio.run(seed())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as client:
        yield client, session_factory
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _auditor_headers() -> dict:
    token = create_access_token({"sub": "20269802", "ver": 1})
    return {"Authorization": f"Bearer {token}"}


async def _photo_id(session_factory) -> str:
    async with session_factory() as db:
        return (await db.execute(select(Photo.id))).scalar_one()


def test_anonymous_can_report_photo(report_env):
    client, session_factory = report_env
    photo_id = asyncio.run(_photo_id(session_factory))
    resp = client.post(
        "/api/v1/reports",
        json={
            "target_type": "photo",
            "target_id": photo_id,
            "reason_code": "copyright",
            "reason_text": "这张图与我的作品高度相似，且未获授权。",
            "contact": "reporter@example.com",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ok"] is True and body["status"] == "pending"
    assert body["id"]

    async def check():
        async with session_factory() as db:
            report = (await db.execute(select(Report))).scalar_one()
            assert report.target_type == "photo"
            assert report.target_id == photo_id
            assert report.status == "pending"
            assert report.reporter_id is None
            audit = (await db.execute(select(AuditLog).where(AuditLog.action == "report.create"))).scalars().all()
            assert audit, "应写入审计日志"

    asyncio.run(check())


def test_report_validation_and_missing_target(report_env):
    client, session_factory = report_env
    photo_id = asyncio.run(_photo_id(session_factory))

    too_short = client.post(
        "/api/v1/reports",
        json={"target_type": "photo", "target_id": photo_id, "reason_code": "other", "reason_text": "短"},
    )
    assert too_short.status_code == 422

    missing = client.post(
        "/api/v1/reports",
        json={
            "target_type": "photo",
            "target_id": "00000000-0000-0000-0000-000000000000",
            "reason_code": "copyright",
            "reason_text": "目标不存在的情况",
        },
    )
    assert missing.status_code == 404

    bad_reason = client.post(
        "/api/v1/reports",
        json={"target_type": "photo", "target_id": photo_id, "reason_code": "unknown", "reason_text": "原因码非法"},
    )
    assert bad_reason.status_code == 422


def test_duplicate_report_same_ip_blocked(report_env):
    client, session_factory = report_env
    photo_id = asyncio.run(_photo_id(session_factory))
    payload = {
        "target_type": "photo",
        "target_id": photo_id,
        "reason_code": "portrait",
        "reason_text": "照片中有我本人，未获同意。",
    }
    assert client.post("/api/v1/reports", json=payload).status_code == 201
    duplicate = client.post("/api/v1/reports", json=payload)
    assert duplicate.status_code == 429


def test_admin_list_and_stats(report_env):
    client, session_factory = report_env
    photo_id = asyncio.run(_photo_id(session_factory))
    assert (
        client.post(
            "/api/v1/reports",
            json={
                "target_type": "photo",
                "target_id": photo_id,
                "reason_code": "copyright",
                "reason_text": "列表接口的样本投诉内容",
            },
        ).status_code
        == 201
    )

    assert client.get("/api/v1/admin/reports").status_code == 401
    listing = client.get("/api/v1/admin/reports", headers=_auditor_headers())
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["reason_label"]
    assert item["target_title"] == "被投诉的作品"
    assert item["target_url"].startswith("/photo/")

    stats = client.get("/api/v1/admin/reports/stats", headers=_auditor_headers())
    assert stats.status_code == 200
    assert stats.json()["pending"] == 1
    assert stats.json()["by_reason"].get("copyright") == 1


def test_resolve_accept_takedown_and_repeat(report_env):
    client, session_factory = report_env
    photo_id = asyncio.run(_photo_id(session_factory))
    created = client.post(
        "/api/v1/reports",
        json={
            "target_type": "photo",
            "target_id": photo_id,
            "reason_code": "illegal",
            "reason_text": "该作品包含违规内容，请核实处理。",
        },
    ).json()
    report_id = created["id"]

    resp = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"decision": "accept", "action": "takedown", "note": "核实后下架"},
        headers=_auditor_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    assert resp.json()["action_taken"] == "photo.takedown"

    async def check():
        async with session_factory() as db:
            photo = await db.get(Photo, photo_id)
            assert photo.status == "rejected"
            note = (await db.execute(select(Notification))).scalars().all()
            assert note and note[0].type == "photo_rejected"

    asyncio.run(check())

    repeat = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"decision": "accept", "action": "takedown"},
        headers=_auditor_headers(),
    )
    assert repeat.status_code == 409


def test_resolve_reject_keeps_photo(report_env):
    client, session_factory = report_env
    photo_id = asyncio.run(_photo_id(session_factory))
    report_id = client.post(
        "/api/v1/reports",
        json={
            "target_type": "photo",
            "target_id": photo_id,
            "reason_code": "spam",
            "reason_text": "看起来像广告推广内容",
        },
    ).json()["id"]

    resp = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"decision": "reject", "note": "不构成违规"},
        headers=_auditor_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    async def check():
        async with session_factory() as db:
            photo = await db.get(Photo, photo_id)
            assert photo.status == "approved"

    asyncio.run(check())
