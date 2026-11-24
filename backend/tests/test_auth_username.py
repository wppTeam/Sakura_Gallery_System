"""注册/登录的公开身份（username / display_name）回归测试。

覆盖：
1. 注册时传入的 username / display_name 真正入库，并可用于登录；
2. 用户名重复注册返回 409；
3. 非法用户名返回 422；
4. 学号登录保持可用。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.database import Base
from app.main import app

PASSWORD = "ComposeTest#2026"


@pytest.fixture
def auth_client(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    monkeypatch.setattr(settings, "REQUIRE_REGISTRATION_APPROVAL", False)

    db_path = tmp_path / "auth.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_database())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    # 注册端点有 5/minute 的 slowapi 限流；多个用例共用同一 TestClient IP，
    # 不重置的话第 4 个注册请求就会返回 429（与业务逻辑无关）。
    from app.api.v1.endpoints.auth import limiter as auth_limiter

    auth_limiter.reset()

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_register_persists_public_identity_and_allows_username_login(auth_client: TestClient):
    resp = auth_client.post(
        "/api/v1/auth/register",
        json={
            "student_id": "20268888",
            "username": "sakura_newbie",
            "display_name": "樱花新同学",
            "password": PASSWORD,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["username"] == "sakura_newbie"
    assert body["display_name"] == "樱花新同学"

    resp = auth_client.post(
        "/api/v1/auth/login",
        json={"identifier": "sakura_newbie", "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    assert resp.json()["user"]["username"] == "sakura_newbie"

    # 学号登录保持可用
    resp = auth_client.post(
        "/api/v1/auth/login",
        json={"identifier": "20268888", "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text


def test_duplicate_username_rejected(auth_client: TestClient):
    payload = {
        "student_id": "20267777",
        "username": "sakura_dup",
        "display_name": "重名测试",
        "password": PASSWORD,
    }
    assert auth_client.post("/api/v1/auth/register", json=payload).status_code == 201
    payload["student_id"] = "20267778"
    resp = auth_client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409
    assert "用户名" in resp.json()["detail"]


def test_invalid_username_rejected(auth_client: TestClient):
    for bad in ("ab", "带中文的名字", "has space", "a" * 33):
        resp = auth_client.post(
            "/api/v1/auth/register",
            json={
                "student_id": "2026666" + str(len(bad)),
                "username": bad,
                "password": PASSWORD,
            },
        )
        assert resp.status_code == 422, (bad, resp.text)



def test_user_response_tolerates_invalid_email():
    """响应模型对 email 放宽：历史/导入的非法邮箱不应让序列化直接炸。"""
    from datetime import datetime

    from app.schemas.user import User as UserSchema

    user = UserSchema.model_validate(
        {
            "id": "u-invalid-email",
            "student_id": "20260001",
            "email": "broken@example.invalid",
            "full_name": "历史用户",
            "role": "user",
            "is_active": True,
            "created_at": datetime.utcnow(),
        }
    )
    assert user.email == "broken@example.invalid"


def test_me_returns_200_for_invalid_stored_email():
    """/auth/me 不因 DB 里非法邮箱 500（回归：曾触发 ResponseValidationError）。"""
    from datetime import datetime
    from types import SimpleNamespace

    from app.core.deps import get_current_active_user

    stub = SimpleNamespace(
        id="u-invalid-email",
        student_id="20260001",
        email="broken@example.invalid",
        full_name="历史用户",
        username=None,
        display_name=None,
        role="user",
        is_active=True,
        created_at=datetime.utcnow(),
        last_login_at=None,
        login_count=0,
        failed_login_attempts=0,
        locked_until=None,
        token_version=1,
        email_verified=False,
    )
    app.dependency_overrides[get_current_active_user] = lambda: stub
    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200, resp.text
        assert resp.json()["email"] == "broken@example.invalid"
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
