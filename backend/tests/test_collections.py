"""策展专题（collections）公开接口测试。

覆盖：
1. 列表只返回 `status=published` 且 `visibility=public` 的专题；
2. `photo_count` 只统计 approved 作品，封面取专题内第一张公开作品；
3. 详情按 position 排序，且过滤掉非 approved 作品；
4. 未发布专题 404；
5. 详情给出上一/下一专题 slug，且响应不泄漏学号/真实姓名。
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
from app.models import Collection, CollectionPhoto, Photo, User


def _photo(photo_id: str, *, title: str, status: str = "approved", uploader: str = "owner") -> Photo:
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
def collections_client(tmp_path: Path):
    db_path = tmp_path / "collections.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(
                User(
                    id="owner",
                    student_id="20260001",
                    username="jackwpp",
                    display_name="王海翔",
                    full_name="真实姓名不该公开",
                    hashed_password="x",
                    role="user",
                    is_active=True,
                )
            )
            session.add_all(
                [
                    _photo("p1", title="七之一 · 生活瞬间 01"),
                    _photo("p2", title="七之一 · 生活瞬间 02"),
                    _photo("p3", title="待审照片", status="pending"),
                ]
            )
            session.add_all(
                [
                    Collection(
                        id="c1",
                        slug="2024-seven-chapters",
                        title="2024 · 七乐章",
                        subtitle="七个乐章",
                        description="一年很长。",
                        cover_photo_id=None,
                        kind="editorial",
                        status="published",
                        visibility="public",
                        sort_order=0,
                    ),
                    Collection(
                        id="c2",
                        slug="2024-campus-seasons",
                        title="校园四季",
                        kind="editorial",
                        status="published",
                        visibility="public",
                        sort_order=1,
                    ),
                    Collection(
                        id="c3",
                        slug="draft-collection",
                        title="草稿专题",
                        kind="editorial",
                        status="draft",
                        visibility="public",
                        sort_order=2,
                    ),
                ]
            )
            session.add_all(
                [
                    # p1 顺序在 p2 之后，验证 position 排序
                    CollectionPhoto(collection_id="c1", photo_id="p2", position=1),
                    CollectionPhoto(collection_id="c1", photo_id="p1", position=0),
                    # 待审作品不应出现在公开专题
                    CollectionPhoto(collection_id="c1", photo_id="p3", position=2),
                    CollectionPhoto(collection_id="c2", photo_id="p1", position=0),
                ]
            )
            await session.commit()

    asyncio.run(init_database())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    test_app = FastAPI()
    test_app.include_router(collections_api.router, prefix="/api/v1/collections")
    test_app.include_router(collections_api.photo_router, prefix="/api/v1/photos")
    test_app.dependency_overrides[deps.get_db] = override_get_db

    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_list_only_published_public(collections_client: TestClient) -> None:
    response = collections_client.get("/api/v1/collections/public")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    slugs = [item["slug"] for item in payload["items"]]
    assert slugs == ["2024-seven-chapters", "2024-campus-seasons"]
    assert "draft-collection" not in slugs


def test_list_counts_approved_and_cover(collections_client: TestClient) -> None:
    response = collections_client.get("/api/v1/collections/public")
    items = {item["slug"]: item for item in response.json()["items"]}

    seven = items["2024-seven-chapters"]
    # 三张挂载里只有 p1、p2 是 approved
    assert seven["photo_count"] == 2
    # 封面为空时取 position 最小的公开作品，即 p1
    assert seven["cover"]["id"] == "p1"
    assert seven["cover"]["thumb_path"] == "thumbnails/p1_thumb.jpg"

    seasons = items["2024-campus-seasons"]
    assert seasons["photo_count"] == 1


def test_detail_ordered_and_filtered(collections_client: TestClient) -> None:
    response = collections_client.get("/api/v1/collections/2024-seven-chapters")
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "2024 · 七乐章"
    assert payload["photo_count"] == 2
    assert [photo["id"] for photo in payload["photos"]] == ["p1", "p2"]
    assert payload["cover"]["id"] == "p1"


def test_detail_prev_next_navigation(collections_client: TestClient) -> None:
    first = collections_client.get("/api/v1/collections/2024-seven-chapters").json()
    assert first["prev_slug"] is None
    assert first["next_slug"] == "2024-campus-seasons"

    second = collections_client.get("/api/v1/collections/2024-campus-seasons").json()
    assert second["prev_slug"] == "2024-seven-chapters"
    assert second["next_slug"] is None


def test_unpublished_detail_404(collections_client: TestClient) -> None:
    response = collections_client.get("/api/v1/collections/draft-collection")
    assert response.status_code == 404


def test_public_photo_fields_do_not_leak_private_identity(collections_client: TestClient) -> None:
    payload = collections_client.get("/api/v1/collections/2024-seven-chapters").json()
    photo = payload["photos"][0]
    assert photo["uploader_name"] is None
    assert photo["uploader_student_id"] is None
    assert "20260001" not in response_text(payload)


def response_text(payload: object) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


def test_photo_collections_endpoint(collections_client: TestClient) -> None:
    response = collections_client.get("/api/v1/photos/p1/collections")
    assert response.status_code == 200
    items = response.json()["items"]
    # p1 同时收录在「七乐章」与「校园四季」，按 sort_order 排序
    assert [item["slug"] for item in items] == ["2024-seven-chapters", "2024-campus-seasons"]
    assert items[0]["title"] == "2024 · 七乐章"

    # 未审核作品不返回专题
    assert collections_client.get("/api/v1/photos/p3/collections").json()["items"] == []
