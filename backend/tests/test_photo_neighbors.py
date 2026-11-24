"""详情页「上一张 / 下一张」导航测试。

覆盖：
1. 全站最新流：位置、前后邻接、窗口边界（第一张没有上一张）；
2. 候选集只含已发布 + 非人像敏感作品，待审 / 敏感作品不出现；
3. 专题上下文：按 collection_photos.position 排序，位置与前后邻接来自专题；
4. 上下文不可用（专题不存在 / 作品不在专题里）时退回全站最新流；
5. HTTP 端点：紧凑字段（无学号、有缩略图 URL 与宽高比），目标不可访问时 404。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import photos as photos_api
from app.core import deps
from app.core.database import Base
from app.models import Collection, CollectionPhoto, Photo, User

BASE_TIME = datetime(2026, 5, 1, 8, 0, 0)


def _photo(
    photo_id: str,
    *,
    published_at: datetime,
    status: str = "approved",
    privacy: str = "normal",
    width: int = 1200,
    height: int = 800,
    title: str | None = None,
) -> Photo:
    return Photo(
        id=photo_id,
        uploader_id="owner",
        filename=f"{photo_id}.jpg",
        title=title or f"作品 {photo_id}",
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        width=width,
        height=height,
        file_size=200_000,
        mime_type="image/jpeg",
        status=status,
        privacy_level=privacy,
        processing_status="completed",
        views=0,
        published_at=published_at,
        exif_data={"_lqip_color": "#e8628c"},
    )


async def _seed(session_factory) -> None:
    async with session_factory() as session:
        session.add(
            User(
                id="owner",
                student_id="owner01",
                email="owner@example.com",
                username="owner",
                display_name="作者",
                hashed_password="x",
                role="user",
                is_active=True,
            )
        )
        # 最新 → 最旧：p1 p2 p3 p4 p5；p6 待审、p7 人像敏感
        session.add_all(
            [
                _photo("p1", published_at=BASE_TIME + timedelta(days=4)),
                _photo("p2", published_at=BASE_TIME + timedelta(days=3)),
                _photo("p3", published_at=BASE_TIME + timedelta(days=2)),
                _photo("p4", published_at=BASE_TIME + timedelta(days=1)),
                _photo("p5", published_at=BASE_TIME),
                _photo("p6", published_at=BASE_TIME + timedelta(days=5), status="pending"),
                _photo(
                    "p7",
                    published_at=BASE_TIME + timedelta(days=6),
                    privacy="sensitive",
                ),
            ]
        )
        session.add(
            Collection(
                id="c1",
                slug="light-dusk",
                title="暮 · 一日将尽",
                kind="editorial",
                status="published",
                visibility="public",
                sort_order=22,
            )
        )
        session.add(
            Collection(
                id="c2",
                slug="secret",
                title="未发布",
                kind="editorial",
                status="draft",
                visibility="public",
                sort_order=90,
            )
        )
        # 专题顺序：p4 → p2 → p5
        for position, photo_id in enumerate(["p4", "p2", "p5"]):
            session.add(
                CollectionPhoto(
                    id=f"cp-{photo_id}",
                    collection_id="c1",
                    photo_id=photo_id,
                    position=position,
                )
            )
        await session.commit()


@pytest.fixture()
def neighbors_app(tmp_path: Path):
    db_path = tmp_path / "neighbors.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _seed(session_factory)

    asyncio.run(init_database())

    async def override_db():
        async with session_factory() as session:
            yield session

    api = FastAPI()
    api.include_router(photos_api.router, prefix="/api/v1/photos")
    api.dependency_overrides[deps.get_db] = override_db
    client = TestClient(api)
    yield client, session_factory
    asyncio.run(engine.dispose())


def test_latest_neighbors_position_and_adjacency(neighbors_app) -> None:
    client, _ = neighbors_app

    data = client.get("/api/v1/photos/p3/neighbors").json()

    assert data["context"]["kind"] == "latest"
    # 公开作品 5 张，p3 是第 3 张
    assert data["context"]["total"] == 5
    assert data["context"]["position"] == 3
    ids = [item["id"] for item in data["items"]]
    assert ids == ["p1", "p2", "p3", "p4", "p5"]
    assert data["index"] == 2
    assert data["prev"] == "p2"
    assert data["next"] == "p4"


def test_latest_neighbors_edges(neighbors_app) -> None:
    client, _ = neighbors_app

    newest = client.get("/api/v1/photos/p1/neighbors").json()
    assert newest["context"]["position"] == 1
    assert newest["prev"] is None
    assert newest["next"] == "p2"

    oldest = client.get("/api/v1/photos/p5/neighbors").json()
    assert oldest["context"]["position"] == 5
    assert oldest["prev"] == "p4"
    assert oldest["next"] is None


def test_neighbors_exclude_pending_and_sensitive(neighbors_app) -> None:
    client, _ = neighbors_app

    ids = [item["id"] for item in client.get("/api/v1/photos/p3/neighbors").json()["items"]]
    assert "p6" not in ids and "p7" not in ids
    # 待审 / 敏感作品本身不可公开访问
    assert client.get("/api/v1/photos/p6/neighbors").status_code == 404
    assert client.get("/api/v1/photos/p7/neighbors").status_code == 404


def test_collection_context_uses_curated_order(neighbors_app) -> None:
    client, _ = neighbors_app

    data = client.get(
        "/api/v1/photos/p2/neighbors", params={"context": "collection:light-dusk"}
    ).json()

    assert data["context"]["kind"] == "collection"
    assert data["context"]["slug"] == "light-dusk"
    assert data["context"]["title"] == "暮 · 一日将尽"
    assert data["context"]["total"] == 3
    assert data["context"]["position"] == 2
    assert [item["id"] for item in data["items"]] == ["p4", "p2", "p5"]
    assert data["index"] == 1
    assert data["prev"] == "p4"
    assert data["next"] == "p5"


def test_collection_context_falls_back_to_latest(neighbors_app) -> None:
    client, _ = neighbors_app

    # 未发布专题
    draft = client.get(
        "/api/v1/photos/p2/neighbors", params={"context": "collection:secret"}
    ).json()
    assert draft["context"]["kind"] == "latest"

    # 作品不在专题里
    outside = client.get(
        "/api/v1/photos/p1/neighbors", params={"context": "collection:light-dusk"}
    ).json()
    assert outside["context"]["kind"] == "latest"


def test_neighbors_respect_window_limits(neighbors_app) -> None:
    client, _ = neighbors_app

    data = client.get("/api/v1/photos/p3/neighbors", params={"before": 1, "after": 1}).json()
    assert [item["id"] for item in data["items"]] == ["p2", "p3", "p4"]
    assert data["index"] == 1


def test_neighbors_items_are_compact_and_public(neighbors_app) -> None:
    client, _ = neighbors_app

    item = client.get("/api/v1/photos/p3/neighbors").json()["items"][0]

    assert item["thumb_url"] == f"/api/v1/photos/{item['id']}/image/thumbnail"
    assert item["aspect_ratio"] == pytest.approx(1.5)
    assert item["lqip_color"] == "#e8628c"
    assert "uploader_student_id" not in item
    assert "exif_data" not in item
