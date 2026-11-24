"""邮箱验证码 / 登录注册增强 / 管理员用户管理 测试"""
import asyncio
import os
import tempfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.deps import get_db
from app.core.database import Base
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture()
def email_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="sakura-email-")
    db_path = os.path.join(tmpdir, "test.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())

    settings = get_settings()
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "console")
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFICATION", True)
    monkeypatch.setattr(settings, "ALLOW_PASSWORDLESS_EMAIL_LOGIN", True)
    monkeypatch.setattr(settings, "REQUIRE_REGISTRATION_APPROVAL", False)
    monkeypatch.setattr(settings, "EMAIL_CODE_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(settings, "EMAIL_CODE_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "EMAIL_CODE_TTL_SECONDS", 600)
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-key-for-email")

    async def override_get_db():
        async with Session() as session:
            yield session

    from app.main import app

    app.dependency_overrides[get_db] = override_get_db

    # slowapi 的限流是进程级，测试里重置，避免用例间相互影响
    from app.api.v1.endpoints.auth import limiter as auth_limiter

    auth_limiter.reset()

    yield {"client": TestClient(app), "Session": Session, "settings": settings}

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _register_payload(code: str, email: str = "student@example.com", student_id: str = "20260001"):
    return {
        "student_id": student_id,
        "email": email,
        "email_code": code,
        "username": f"user{student_id[-4:]}",
        "display_name": "测试同学",
        "password": "Sakura2026!",
    }


def test_register_requires_email_code(email_env):
    client = email_env["client"]
    payload = _register_payload("")
    payload.pop("email_code")
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 400
    assert "验证码" in resp.json()["detail"]


def test_email_code_then_register_verifies_email(email_env):
    client = email_env["client"]
    resp = client.post(
        "/api/v1/auth/email-code",
        json={"email": "student@example.com", "purpose": "register"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["delivered"] is False
    assert body["dev_code"], "本地开发应返回 dev_code"

    resp = client.post("/api/v1/auth/register", json=_register_payload(body["dev_code"]))
    assert resp.status_code == 201, resp.text
    user = resp.json()
    assert user["email_verified"] is True
    assert user["email"] == "student@example.com"


def test_register_rejects_wrong_code(email_env):
    client = email_env["client"]
    client.post(
        "/api/v1/auth/email-code",
        json={"email": "student@example.com", "purpose": "register"},
    )
    resp = client.post("/api/v1/auth/register", json=_register_payload("000000"))
    assert resp.status_code == 400
    assert "验证码" in resp.json()["detail"]


def test_email_code_login(email_env):
    client = email_env["client"]
    code = client.post(
        "/api/v1/auth/email-code",
        json={"email": "student@example.com", "purpose": "register"},
    ).json()["dev_code"]
    assert client.post("/api/v1/auth/register", json=_register_payload(code)).status_code == 201

    login_code = client.post(
        "/api/v1/auth/email-code",
        json={"email": "student@example.com", "purpose": "login"},
    ).json()["dev_code"]
    resp = client.post(
        "/api/v1/auth/login-with-code",
        json={"email": "student@example.com", "code": login_code},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["access_token"]
    assert data["user"]["student_id"] == "20260001"


def test_forgot_and_reset_password(email_env):
    client = email_env["client"]
    code = client.post(
        "/api/v1/auth/email-code",
        json={"email": "student@example.com", "purpose": "register"},
    ).json()["dev_code"]
    assert client.post("/api/v1/auth/register", json=_register_payload(code)).status_code == 201

    forgot = client.post(
        "/api/v1/auth/password/forgot", json={"identifier": "student@example.com"}
    )
    assert forgot.status_code == 200, forgot.text
    reset_code = forgot.json()["dev_code"]
    assert reset_code

    reset = client.post(
        "/api/v1/auth/password/reset",
        json={
            "identifier": "student@example.com",
            "code": reset_code,
            "new_password": "NewSakura2026!",
        },
    )
    assert reset.status_code == 200, reset.text

    ok = client.post(
        "/api/v1/auth/login",
        json={"identifier": "student@example.com", "password": "NewSakura2026!"},
    )
    assert ok.status_code == 200


def test_email_code_cooldown(email_env):
    settings = email_env["settings"]
    settings.EMAIL_CODE_COOLDOWN_SECONDS = 60
    client = email_env["client"]
    first = client.post(
        "/api/v1/auth/email-code",
        json={"email": "student@example.com", "purpose": "register"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/auth/email-code",
        json={"email": "student@example.com", "purpose": "register"},
    )
    assert second.status_code == 429
    assert "Retry-After" in second.headers


def test_verify_own_email(email_env):
    client = email_env["client"]
    code = client.post(
        "/api/v1/auth/email-code",
        json={"email": "student@example.com", "purpose": "register"},
    ).json()["dev_code"]
    assert client.post("/api/v1/auth/register", json=_register_payload(code)).status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "student@example.com", "password": "Sakura2026!"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 手动把邮箱置为未验证，模拟历史账号
    async def _unverify():
        async with email_env["Session"]() as session:
            from sqlalchemy import select

            user = (
                await session.execute(select(User).where(User.student_id == "20260001"))
            ).scalar_one()
            user.email_verified = False
            await session.commit()

    asyncio.run(_unverify())

    sent = client.post("/api/v1/auth/email/send-verification", headers=headers)
    assert sent.status_code == 200, sent.text
    verify_code = sent.json()["dev_code"]
    verified = client.post(
        "/api/v1/auth/email/verify", headers=headers, json={"code": verify_code}
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["email_verified"] is True


def test_email_code_unavailable_when_not_configured_in_prod(email_env):
    settings = email_env["settings"]
    settings.DEBUG = False
    settings.EMAIL_ENABLED = False
    client = email_env["client"]
    resp = client.post(
        "/api/v1/auth/email-code",
        json={"email": "student@example.com", "purpose": "register"},
    )
    assert resp.status_code == 503
    assert "邮件" in resp.json()["detail"]


def test_admin_user_stats_and_filters(email_env):
    Session = email_env["Session"]

    async def _seed():
        async with Session() as session:
            session.add(
                User(
                    id="admin-1",
                    student_id="20260000",
                    email="admin@example.com",
                    hashed_password=get_password_hash("Admin2026!"),
                    role="admin",
                    is_active=True,
                    email_verified=True,
                    username="admin1",
                )
            )
            session.add(
                User(
                    id="user-1",
                    student_id="20260002",
                    email="pending@example.com",
                    hashed_password=get_password_hash("User2026!!"),
                    role="user",
                    is_active=False,
                    email_verified=False,
                    username="pending1",
                )
            )
            await session.commit()

    asyncio.run(_seed())
    client = email_env["client"]
    token = create_access_token({"sub": "20260000", "ver": 1})
    headers = {"Authorization": f"Bearer {token}"}

    stats = client.get("/api/v1/admin/users/stats", headers=headers)
    assert stats.status_code == 200, stats.text
    data = stats.json()
    assert data["total"] == 2
    assert data["admins"] == 1
    assert data["pending_approval"] >= 1
    assert isinstance(data["recent_logins"], list)

    listed = client.get("/api/v1/admin/users?search=pending&is_active=false", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["users"][0]["student_id"] == "20260002"

    verified = client.post("/api/v1/admin/users/user-1/verify-email", headers=headers)
    assert verified.status_code == 200, verified.text
    assert verified.json()["email_verified"] is True
