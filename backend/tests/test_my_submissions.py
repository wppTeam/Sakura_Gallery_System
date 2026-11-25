"""「我的投稿」工作台接口回归测试。

背景：公共端「我的投稿」页要重做成作者工作台，需要：
1. 一次请求拿到按状态分组的计数（避免前端为统计卡拉 4 次列表）；
2. 删除未通过/待审作品时清理全部派生文件（原图、缩略图、压缩图、响应式
   变体、脱敏图），旧实现只删前三项会在磁盘上留下孤儿文件。

覆盖：
- `GET /my-submissions/stats` 的计数与待受理复核数；
- 列表按状态过滤仍走原接口；
- `DELETE /{photo_id}` 清掉全部关联文件，且非作者不能删。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.config import get_settings
from app.core.database import Base
from app.main import app
from app.models import Photo, PhotoAppeal, User

PASSWORD = "Submissions#2026"


def _make_photo(
    photo_id: str,
    uploader_id: str,
    *,
    status: str,
    exif_data: dict | None = None,
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
        processing_status="completed",
        exif_data=exif_data or {},
        views=0,
    )


@pytest.fixture
def submissions_client(tmp_path: Path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    monkeypatch.setattr(settings, "REQUIRE_REGISTRATION_APPROVAL", False)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'submissions.db').as_posix()}", future=True
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
        yield client, session_factory, tmp_path / "uploads"
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _register_and_login(client: TestClient, *, username: str, student_id: str) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "student_id": student_id,
            "username": username,
            "display_name": username,
            "password": PASSWORD,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": username, "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return token, resp.json().get("id", "")


async def _seed(session_factory) -> tuple[str, str]:
    async with session_factory() as session:
        owner = (await session.execute(select(User).where(User.username == "sub_owner"))).scalar_one()
        other = (await session.execute(select(User).where(User.username == "sub_other"))).scalar_one()
        session.add_all(
            [
                _make_photo("sub-a1", owner.id, status="approved"),
                _make_photo("sub-a2", owner.id, status="approved"),
                _make_photo("sub-p1", owner.id, status="pending"),
                _make_photo("sub-r1", owner.id, status="rejected"),
                _make_photo("sub-other", other.id, status="approved"),
            ]
        )
        session.add(
            PhotoAppeal(
                id="appeal-1",
                photo_id="sub-r1",
                user_id=owner.id,
                reason="这张照片是我自己拍的，希望能再复核一次。",
                status="pending",
            )
        )
        await session.commit()
        return owner.id, other.id


def test_stats_counts_by_status_and_pending_appeals(
    submissions_client: tuple[TestClient, object, Path],
):
    client, session_factory, _uploads = submissions_client
    token, _ = _register_and_login(client, username="sub_owner", student_id="20268001")
    _register_and_login(client, username="sub_other", student_id="20268002")
    asyncio.run(_seed(session_factory))
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/photos/my-submissions/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["total"] == 4
    assert payload["approved"] == 2
    assert payload["pending"] == 1
    assert payload["rejected"] == 1
    assert payload["pending_appeal"] == 1

    # 未登录不可见
    assert client.get("/api/v1/photos/my-submissions/stats").status_code == 401


def test_list_filters_by_status_still_works(
    submissions_client: tuple[TestClient, object, Path],
):
    client, session_factory, _uploads = submissions_client
    token, _ = _register_and_login(client, username="sub_owner", student_id="20268003")
    _register_and_login(client, username="sub_other", student_id="20268004")
    asyncio.run(_seed(session_factory))
    headers = {"Authorization": f"Bearer {token}"}

    approved = client.get(
        "/api/v1/photos/my-submissions?status=approved", headers=headers
    ).json()
    assert approved["total"] == 2
    assert {item["status"] for item in approved["items"]} == {"approved"}

    rejected = client.get("/api/v1/photos/my-submissions?status=rejected", headers=headers).json()
    assert rejected["total"] == 1
    assert rejected["items"][0]["id"] == "sub-r1"


def test_delete_photo_removes_all_assets(
    submissions_client: tuple[TestClient, object, Path],
):
    client, session_factory, upload_dir = submissions_client
    token, _ = _register_and_login(client, username="sub_owner", student_id="20268005")
    _register_and_login(client, username="sub_other", student_id="20268006")
    owner_id, _ = asyncio.run(_seed(session_factory))
    headers = {"Authorization": f"Bearer {token}"}

    # 造齐磁盘文件：原图 / 缩略图 / 压缩图 / 变体 / 脱敏图
    photo_id = "sub-p1"
    files = {
        f"originals/{photo_id}.jpg": b"original",
        f"thumbnails/{photo_id}_thumb.jpg": b"thumb",
        f"compressed/{photo_id}_compressed.jpg": b"compressed",
        f"variants/{photo_id}_640.webp": b"webp",
        f"variants/{photo_id}_640.jpg": b"jpeg",
        f"redacted/{photo_id}_redacted.jpg": b"redacted",
        f"redacted/{photo_id}_redacted_thumb.jpg": b"redacted-thumb",
    }
    for rel, content in files.items():
        target = upload_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    async def _mark_redacted() -> None:
        async with session_factory() as session:
            photo = await session.get(Photo, photo_id)
            assert photo is not None
            photo.exif_data = {"_variants": {"640": {"width": 640, "height": 480}}}
            photo.redacted_path = f"redacted/{photo_id}_redacted.jpg"
            photo.redacted_thumb_path = f"redacted/{photo_id}_redacted_thumb.jpg"
            await session.commit()

    asyncio.run(_mark_redacted())

    resp = client.delete(f"/api/v1/photos/{photo_id}", headers=headers)
    assert resp.status_code == 204, resp.text
    for rel in files:
        assert not (upload_dir / rel).exists(), f"{rel} 应被清理"

    async def _assert_gone() -> None:
        async with session_factory() as session:
            assert await session.get(Photo, photo_id) is None
            remaining = await session.execute(
                select(Photo).where(Photo.uploader_id == owner_id)
            )
            assert len(remaining.scalars().all()) == 3

    asyncio.run(_assert_gone())


def test_delete_photo_forbidden_for_other_user(
    submissions_client: tuple[TestClient, object, Path],
):
    client, session_factory, _uploads = submissions_client
    _register_and_login(client, username="sub_owner", student_id="20268007")
    other_token, _ = _register_and_login(client, username="sub_other", student_id="20268008")
    asyncio.run(_seed(session_factory))
    headers = {"Authorization": f"Bearer {other_token}"}

    resp = client.delete("/api/v1/photos/sub-a1", headers=headers)
    assert resp.status_code == 403, resp.text

    async def _still_there() -> None:
        async with session_factory() as session:
            assert await session.get(Photo, "sub-a1") is not None

    asyncio.run(_still_there())
