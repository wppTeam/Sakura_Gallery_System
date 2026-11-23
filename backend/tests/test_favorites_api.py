"""收藏列表 API 回归测试。

背景：「我的收藏」此前只返回 `photo_ids`，前端需要再逐个请求作品详情（N+1），
无法直接渲染收藏页；同时作品下架后仍会出现在收藏列表里。

覆盖：
1. 列表直接返回公开安全序列化的作品（items），并保留 photo_ids 兼容字段；
2. 只包含 approved 作品，pending 作品既不出现在 items 也不计入 total；
3. 未登录访问返回 401；
4. 收藏/取消收藏切换后列表与计数同步。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.database import Base
from app.main import app
from app.models import Photo, User

PASSWORD = "Favorites#2026"


def _make_photo(photo_id: str, uploader_id: str, *, status: str) -> Photo:
    return Photo(
        id=photo_id,
        uploader_id=uploader_id,
        filename=f"{photo_id}.jpg",
        title=f"作品 {photo_id}",
        original_path=f"originals/{photo_id}.jpg",
        width=1200,
        height=800,
        file_size=123456,
        mime_type="image/jpeg",
        status=status,
        processing_status="completed",
        views=0,
    )


@pytest.fixture
def favorites_client(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    monkeypatch.setattr(settings, "REQUIRE_REGISTRATION_APPROVAL", False)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'favorites.db').as_posix()}", future=True
    )
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
    with TestClient(app) as client:
        yield client, session_factory
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _register_and_login(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "student_id": "20267777",
            "username": "fav_user",
            "display_name": "收藏同学",
            "password": PASSWORD,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "fav_user", "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


async def _seed_photos(session_factory, uploader_id: str) -> None:
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.username == "fav_user"))
        user = result.scalar_one_or_none()
        assert user is not None
        session.add_all(
            [
                _make_photo("fav-approved", user.id, status="approved"),
                _make_photo("fav-pending", user.id, status="pending"),
            ]
        )
        await session.commit()


def test_my_favorites_returns_serialized_approved_items(
    favorites_client: tuple[TestClient, object],
):
    client, session_factory = favorites_client
    token = _register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}

    asyncio.run(_seed_photos(session_factory, ""))

    # 收藏一张已发布 + 一张待审作品
    for photo_id in ("fav-approved", "fav-pending"):
        resp = client.post(f"/api/v1/photos/{photo_id}/favorite", headers=headers)
        assert resp.status_code == 200, resp.text

    listed = client.get("/api/v1/photos/favorites/my", headers=headers)
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["total"] == 1, payload  # 待审不计入
    assert payload["returned"] == 1
    assert payload["photo_ids"] == ["fav-approved"]
    item = payload["items"][0]
    assert item["id"] == "fav-approved"
    assert item["title"] == "作品 fav-approved"
    assert item["status"] == "approved"
    # 公开安全：不得泄露学号/真实姓名
    assert item["uploader_student_id"] is None
    assert item["uploader_name"] is None

    # 取消收藏后列表为空
    un = client.post("/api/v1/photos/fav-approved/favorite", headers=headers)
    assert un.status_code == 200
    empty = client.get("/api/v1/photos/favorites/my", headers=headers).json()
    assert empty["total"] == 0
    assert empty["items"] == []


def test_my_favorites_requires_auth(favorites_client: tuple[TestClient, object]):
    client, _ = favorites_client
    resp = client.get("/api/v1/photos/favorites/my")
    assert resp.status_code == 401
