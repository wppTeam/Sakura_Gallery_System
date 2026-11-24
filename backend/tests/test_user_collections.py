"""作者手账（用户自建专辑）接口测试。

覆盖：
1. 新建专辑：kind=user、owner 公开身份、slug 以 u- 开头、出现在 /mine 与公开列表；
2. 编辑：标题/副标题/草稿状态；草稿不出现在公开列表，但出现在 /mine；
3. 作品列表替换：只能放本人 approved 作品（他人作品 403、待审 400），顺序保留；
4. 权限：匿名 401、非作者 403；
5. 封面只能取专辑内作品；删除后公开详情 404。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import collections as collections_api
from app.core import deps
from app.core.database import Base
from app.models import Photo, User


def _photo(photo_id: str, *, title: str, uploader: str = "owner", status: str = "approved") -> Photo:
    return Photo(
        id=photo_id,
        uploader_id=uploader,
        filename=f"{photo_id}.jpg",
        title=title,
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        width=1200,
        height=800,
        file_size=200_000,
        mime_type="image/jpeg",
        status=status,
        processing_status="completed",
        views=0,
    )


@pytest.fixture()
def author_client(tmp_path: Path):
    db_path = tmp_path / "author.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    owner = User(
        id="owner",
        student_id="20260001",
        username="jackwpp",
        display_name="王海翔",
        full_name="真实姓名不该公开",
        hashed_password="x",
        role="user",
        is_active=True,
    )
    other = User(
        id="other",
        student_id="20260002",
        username="viewer",
        display_name="路人",
        hashed_password="x",
        role="user",
        is_active=True,
    )

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add_all([owner, other])
            session.add_all(
                [
                    _photo("p1", title="春 · 樱花"),
                    _photo("p2", title="夏 · 荷塘"),
                    _photo("p3", title="待审作品", status="pending"),
                    _photo("x1", title="别人的作品", uploader="other"),
                ]
            )
            await session.commit()

    asyncio.run(init_database())

    async def override_db():
        async with session_factory() as session:
            yield session

    api = FastAPI()
    api.include_router(collections_api.router, prefix="/api/v1/collections")
    api.include_router(collections_api.photo_router, prefix="/api/v1/photos")
    api.dependency_overrides[deps.get_db] = override_db

    state = {"current": "owner"}

    async def override_current_user():
        return owner if state["current"] == "owner" else other

    api.dependency_overrides[deps.get_current_user] = override_current_user

    client = TestClient(api)
    client.owner = owner  # type: ignore[attr-defined]
    client.other = other  # type: ignore[attr-defined]
    client.state = state  # type: ignore[attr-defined]
    yield client
    asyncio.run(engine.dispose())


def _create(client: TestClient, title: str = "我的 2024") -> dict:
    response = client.post(
        "/api/v1/collections",
        json={"title": title, "subtitle": "一句话策展", "description": "写给未来的自己。"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_user_collection(author_client: TestClient) -> None:
    data = _create(author_client)
    assert data["kind"] == "user"
    assert data["status"] == "published"
    assert data["slug"].startswith("u-")
    assert data["owner"] == {"username": "jackwpp", "display_name": "王海翔"}
    assert data["photo_count"] == 0
    assert data["photos"] == []

    mine = author_client.get("/api/v1/collections/mine").json()
    assert mine["total"] == 1
    assert mine["items"][0]["title"] == "我的 2024"

    # 空专辑不进公开列表（避免首页出现空专题）；加入作品后才出现
    public = author_client.get("/api/v1/collections/public").json()
    assert public["total"] == 0
    author_client.put(
        f"/api/v1/collections/{data['id']}/photos", json={"photo_ids": ["p1"]}
    )
    public = author_client.get("/api/v1/collections/public").json()
    assert public["total"] == 1
    assert public["items"][0]["kind"] == "user"
    assert public["items"][0]["owner"] == {"username": "jackwpp", "display_name": "王海翔"}


def test_update_collection_and_draft_visibility(author_client: TestClient) -> None:
    created = _create(author_client)
    collection_id = created["id"]

    updated = author_client.patch(
        f"/api/v1/collections/{collection_id}",
        json={"title": "改名后的手账", "status": "draft"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "改名后的手账"
    assert updated.json()["status"] == "draft"

    public_slugs = [
        item["slug"] for item in author_client.get("/api/v1/collections/public").json()["items"]
    ]
    assert created["slug"] not in public_slugs

    mine = author_client.get("/api/v1/collections/mine").json()["items"]
    assert mine[0]["status"] == "draft"


def test_replace_photos_validates_ownership_and_status(author_client: TestClient) -> None:
    created = _create(author_client)
    collection_id = created["id"]

    ok = author_client.put(
        f"/api/v1/collections/{collection_id}/photos",
        json={"photo_ids": ["p2", "p1"]},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert [photo["id"] for photo in body["photos"]] == ["p2", "p1"]

    # 只能收录自己的作品
    foreign = author_client.put(
        f"/api/v1/collections/{collection_id}/photos",
        json={"photo_ids": ["x1"]},
    )
    assert foreign.status_code == 403

    # 待审作品不能收录
    pending = author_client.put(
        f"/api/v1/collections/{collection_id}/photos",
        json={"photo_ids": ["p3"]},
    )
    assert pending.status_code == 400

    # 封面必须是专辑内的作品
    bad_cover = author_client.patch(
        f"/api/v1/collections/{collection_id}",
        json={"cover_photo_id": "p3"},
    )
    assert bad_cover.status_code == 400
    good_cover = author_client.patch(
        f"/api/v1/collections/{collection_id}",
        json={"cover_photo_id": "p1"},
    )
    assert good_cover.status_code == 200
    assert good_cover.json()["cover"]["id"] == "p1"


def test_permissions(author_client: TestClient) -> None:
    created = _create(author_client)
    collection_id = created["id"]

    author_client.state["current"] = "other"
    assert author_client.patch(f"/api/v1/collections/{collection_id}", json={"title": "x"}).status_code == 403
    assert author_client.delete(f"/api/v1/collections/{collection_id}").status_code == 403
    assert author_client.get(f"/api/v1/collections/{collection_id}/manage").status_code == 403


def test_anonymous_requires_login(author_client: TestClient) -> None:
    async def anonymous():
        raise __import__("fastapi").HTTPException(status_code=401, detail="未登录")

    author_client.app.dependency_overrides[deps.get_current_user] = anonymous
    try:
        assert author_client.get("/api/v1/collections/mine").status_code == 401
        assert (
            author_client.post("/api/v1/collections", json={"title": "x"}).status_code
            == 401
        )
    finally:
        author_client.app.dependency_overrides.pop(deps.get_current_user, None)


def test_delete_collection(author_client: TestClient) -> None:
    created = _create(author_client)
    collection_id = created["id"]
    author_client.put(
        f"/api/v1/collections/{collection_id}/photos",
        json={"photo_ids": ["p1"]},
    )

    deleted = author_client.delete(f"/api/v1/collections/{collection_id}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    assert author_client.get("/api/v1/collections/mine").json()["total"] == 0
    assert author_client.get(f"/api/v1/collections/{created['slug']}").status_code == 404
