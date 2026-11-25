"""注册开关 / 邀请码 / 欢迎通知 / 管理员审批放行 的回归测试。

覆盖：
1. GET /auth/registration-config 反映当前配置；
2. REGISTRATION_ENABLED=False 时注册返回 403；
3. 配置邀请码后，缺失/错误 403，正确 201；
4. 注册成功写入欢迎通知；
5. 开启注册审批时新用户 is_active=False，管理员放行后收到「账号已通过审批」。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.database import Base
from app.main import app
from app.models.notification import Notification
from app.models.user import User

PASSWORD = "ComposeTest#2026"


@pytest.fixture
def reg_env(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFICATION", False)
    monkeypatch.setattr(settings, "REGISTRATION_ENABLED", True)
    monkeypatch.setattr(settings, "REGISTRATION_INVITE_CODE", "")
    monkeypatch.setattr(settings, "REQUIRE_REGISTRATION_APPROVAL", False)

    db_path = tmp_path / "registration.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_database())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    from app.api.v1.endpoints.auth import limiter as auth_limiter

    auth_limiter.reset()
    app.dependency_overrides[deps.get_db] = override_get_db

    ctx = SimpleNamespace(settings=settings, session_factory=session_factory, engine=engine)
    with TestClient(app) as client:
        ctx.client = client
        yield ctx
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _register_payload(**overrides):
    payload = {
        "student_id": "20261111",
        "email": "newbie@example.com",
        "username": "sakura_newbie2",
        "display_name": "樱花新同学",
        "password": PASSWORD,
    }
    payload.update(overrides)
    return payload


def _run(session_factory, coro_factory):
    async def runner():
        async with session_factory() as session:
            return await coro_factory(session)

    return asyncio.run(runner())


def _notifications(session_factory, user_id: str):
    async def q(session):
        rows = await session.execute(
            select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at)
        )
        return list(rows.scalars().all())

    return _run(session_factory, q)


def test_registration_config_endpoint(reg_env):
    resp = reg_env.client.get("/api/v1/auth/registration-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "enabled": True,
        "invite_required": False,
        "email_verification_required": False,
        "approval_required": False,
    }

    reg_env.settings.REGISTRATION_ENABLED = False
    reg_env.settings.REGISTRATION_INVITE_CODE = "SAKURA-2026"
    reg_env.settings.REQUIRE_REGISTRATION_APPROVAL = True
    body = reg_env.client.get("/api/v1/auth/registration-config").json()
    assert body["enabled"] is False
    assert body["invite_required"] is True
    assert body["approval_required"] is True


def test_registration_disabled(reg_env):
    reg_env.settings.REGISTRATION_ENABLED = False
    resp = reg_env.client.post("/api/v1/auth/register", json=_register_payload())
    assert resp.status_code == 403
    assert "暂未开放注册" in resp.json()["detail"]


def test_invite_code_required(reg_env):
    reg_env.settings.REGISTRATION_INVITE_CODE = "SAKURA-2026"

    missing = reg_env.client.post("/api/v1/auth/register", json=_register_payload())
    assert missing.status_code == 403

    wrong = reg_env.client.post(
        "/api/v1/auth/register", json=_register_payload(invite_code="WRONG-CODE")
    )
    assert wrong.status_code == 403
    assert "邀请码不正确" in wrong.json()["detail"]

    ok = reg_env.client.post(
        "/api/v1/auth/register", json=_register_payload(invite_code="SAKURA-2026")
    )
    assert ok.status_code == 201


def test_registration_writes_welcome_notification(reg_env):
    resp = reg_env.client.post("/api/v1/auth/register", json=_register_payload())
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    notes = _notifications(reg_env.session_factory, user_id)
    assert len(notes) == 1
    assert notes[0].type == "system"
    assert "欢迎" in notes[0].title
    assert notes[0].is_read is False


def test_admin_approval_sends_notification(reg_env):
    reg_env.settings.REQUIRE_REGISTRATION_APPROVAL = True
    resp = reg_env.client.post("/api/v1/auth/register", json=_register_payload())
    assert resp.status_code == 201
    created = resp.json()
    user_id = created["id"]
    assert created["is_active"] is False

    admin_stub = SimpleNamespace(
        id="admin-stub", student_id="20260000", role="admin", is_active=True
    )
    app.dependency_overrides[deps.get_current_admin_user] = lambda: admin_stub
    try:
        upd = reg_env.client.put(f"/api/v1/admin/users/{user_id}", json={"is_active": True})
    finally:
        app.dependency_overrides.pop(deps.get_current_admin_user, None)

    assert upd.status_code == 200
    assert upd.json()["is_active"] is True

    notes = _notifications(reg_env.session_factory, user_id)
    titles = [n.title for n in notes]
    assert any("欢迎" in t for t in titles)
    assert any("通过审批" in t for t in titles)
