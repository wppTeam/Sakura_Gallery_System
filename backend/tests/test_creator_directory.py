"""公开创作者名录（GET /api/v1/creators）回归测试。

覆盖：
- 只列出「启用 + 至少一张公开作品（approved 且非敏感）」的创作者；
- 排序：默认按公开作品数降序、再按浏览数；sort=views 按浏览数优先；
- 分页 total 正确；
- 每位创作者最多 3 张封面，且封面只来自公开作品；
- 响应不含学号 / 邮箱 / 真实姓名；
- /creators 不会被 /creators/{username} 抢占（前者返回名录）。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.config import get_settings
from app.core.database import Base
from app.main import app
from app.models import Photo, User


def _make_user(user_id: str, username: str, *, active: bool = True, student_id: str | None = None) -> User:
    return User(
        id=user_id,
        student_id=student_id or f"S{user_id}",
        username=username,
        display_name=f"{username} 的昵称",
        full_name=f"{username} 真名",
        email=f"{username}@example.com",
        hashed_password="x",
        is_active=active,
    )


def _make_photo(
    photo_id: str,
    uploader_id: str,
    *,
    status: str = "approved",
    privacy_level: str | None = "normal",
    views: int = 0,
    published_at=None,
) -> Photo:
    return Photo(
        id=photo_id,
        uploader_id=uploader_id,
        filename=f"{photo_id}.jpg",
        title=f"作品 {photo_id}",
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        compressed_path=f"compressed/{photo_id}_compressed.jpg",
        width=1200,
        height=800,
        file_size=123456,
        mime_type="image/jpeg",
        status=status,
        privacy_level=privacy_level,
        processing_status="completed",
        exif_data={"_lqip_color": "#e8628c"},
        views=views,
        published_at=published_at,
    )


@pytest.fixture
def directory_client(tmp_path: Path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    monkeypatch.setattr(settings, "REQUIRE_REGISTRATION_APPROVAL", False)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'directory.db').as_posix()}", future=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def seed() -> None:
        async with session_factory() as session:
            session.add_all(
                [
                    _make_user("u-lily", "lily"),
                    _make_user("u-fan", "fan"),
                    _make_user("u-quiet", "quiet"),          # 无公开作品
                    _make_user("u-off", "off", active=False),  # 停用账号
                ]
            )
            session.add_all(
                [
                    # lily：3 张公开（其中一张 999 次浏览）+ 1 张待审 + 1 张敏感
                    _make_photo("lily-1", "u-lily", views=120, published_at=datetime(2026, 1, 3)),
                    _make_photo("lily-2", "u-lily", views=30, published_at=datetime(2026, 1, 2)),
                    _make_photo("lily-3", "u-lily", views=7, published_at=datetime(2026, 1, 1)),
                    _make_photo("lily-p", "u-lily", status="pending", views=100),
                    _make_photo("lily-s", "u-lily", privacy_level="sensitive", views=500),
                    # fan：2 张公开，浏览数很高
                    _make_photo("fan-1", "u-fan", views=900, published_at=datetime(2026, 2, 2)),
                    _make_photo("fan-2", "u-fan", views=800, published_at=datetime(2026, 2, 1)),
                    # quiet / off：已通过但无公开作品 / 停用账号
                    _make_photo("off-1", "u-off", views=50),
                ]
            )
            await session.commit()

    asyncio.run(init_database())
    asyncio.run(seed())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as client:
        yield client, session_factory
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_directory_lists_only_active_with_public_works(directory_client):
    client, _ = directory_client
    resp = client.get("/api/v1/creators")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    usernames = [item["username"] for item in body["items"]]
    assert usernames == ["lily", "fan"]
    assert body["total"] == 2
    assert body["limit"] == 12 and body["offset"] == 0


def test_directory_ordering_and_sort_param(directory_client):
    client, _ = directory_client
    by_works = client.get("/api/v1/creators").json()["items"]
    assert [item["works_count"] for item in by_works] == [3, 2]
    assert [item["views_total"] for item in by_works] == [157, 1700]

    by_views = client.get("/api/v1/creators", params={"sort": "views"}).json()["items"]
    assert [item["username"] for item in by_views] == ["fan", "lily"]
    assert by_views[0]["views_total"] == 1700


def test_directory_pagination(directory_client):
    client, _ = directory_client
    first = client.get("/api/v1/creators", params={"limit": 1}).json()
    assert first["total"] == 2
    assert [item["username"] for item in first["items"]] == ["lily"]
    second = client.get("/api/v1/creators", params={"limit": 1, "offset": 1}).json()
    assert [item["username"] for item in second["items"]] == ["fan"]


def test_directory_covers_only_public_and_capped(directory_client):
    client, _ = directory_client
    items = client.get("/api/v1/creators").json()["items"]
    lily = next(item for item in items if item["username"] == "lily")
    assert len(lily["covers"]) == 3
    cover_ids = [cover["id"] for cover in lily["covers"]]
    assert cover_ids == ["lily-1", "lily-2", "lily-3"]
    assert all(cover["thumb_url"].startswith("/api/v1/photos/") for cover in lily["covers"])
    assert all(cover["thumb_url"].endswith("/image/thumbnail") for cover in lily["covers"])
    fan = next(item for item in items if item["username"] == "fan")
    assert [cover["id"] for cover in fan["covers"]] == ["fan-1", "fan-2"]


def test_directory_does_not_leak_identity(directory_client):
    client, _ = directory_client
    raw = client.get("/api/v1/creators").text
    assert "真名" not in raw
    assert "@example.com" not in raw
    for item in client.get("/api/v1/creators").json()["items"]:
        assert set(item) == {
            "username",
            "display_name",
            "joined_at",
            "works_count",
            "views_total",
            "covers",
        }


def test_directory_creator_path_not_shadowed(directory_client):
    """/creators 必须返回名录，而不是被 /creators/{username} 当成 username='' 捕获。"""
    client, _ = directory_client
    resp = client.get("/api/v1/creators")
    assert resp.status_code == 200
    assert "items" in resp.json()
    detail = client.get("/api/v1/creators/lily")
    assert detail.status_code == 200
    assert detail.json()["profile"]["username"] == "lily"
    assert client.get("/api/v1/creators/nobody").status_code == 404
