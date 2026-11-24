"""光的一日（/collections/light）接口测试。"""
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
from app.models import Collection, CollectionPhoto, Photo
from app.services.light_of_day import LIGHT_PERIODS, period_for_hour


def _photo(photo_id: str, *, status: str = "approved", privacy: str = "normal") -> Photo:
    return Photo(
        id=photo_id,
        uploader_id="owner",
        filename=f"{photo_id}.jpg",
        title=f"photo {photo_id}",
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        width=1200,
        height=800,
        file_size=200_000,
        mime_type="image/jpeg",
        status=status,
        processing_status="completed",
        privacy_level=privacy,
        exif_data={},
        views=0,
    )


@pytest.fixture()
def light_client(tmp_path: Path):
    db_path = tmp_path / "light.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add_all(
                [
                    _photo("n-1"),
                    _photo("n-2"),
                    _photo("n-3"),
                    _photo("n-pending", status="pending"),
                    _photo("n-sensitive", privacy="sensitive"),
                    _photo("d-1"),
                ]
            )
            session.add_all(
                [
                    Collection(
                        id="col-noon",
                        slug="light-noon",
                        title="昼 · 光在正上方",
                        subtitle="十点到十五点，影子最短的时刻",
                        description="正午的光最诚实。",
                        kind="editorial",
                        status="published",
                        visibility="public",
                        sort_order=21,
                    ),
                    Collection(
                        id="col-dusk",
                        slug="light-dusk",
                        title="暮 · 一日将尽",
                        kind="editorial",
                        status="draft",  # 草稿不应出现在公开接口
                        visibility="public",
                        sort_order=22,
                    ),
                ]
            )
            session.add_all(
                [
                    CollectionPhoto(collection_id="col-noon", photo_id="n-1", position=0),
                    CollectionPhoto(collection_id="col-noon", photo_id="n-2", position=1),
                    CollectionPhoto(collection_id="col-noon", photo_id="n-3", position=2),
                    CollectionPhoto(collection_id="col-noon", photo_id="n-pending", position=3),
                    CollectionPhoto(collection_id="col-noon", photo_id="n-sensitive", position=4),
                    CollectionPhoto(collection_id="col-dusk", photo_id="d-1", position=0),
                ]
            )
            await session.commit()

    asyncio.run(init_database())

    async def override_db():
        async with session_factory() as session:
            yield session

    api = FastAPI()
    api.include_router(collections_api.router, prefix="/api/v1/collections")
    api.dependency_overrides[deps.get_db] = override_db
    client = TestClient(api)
    yield client
    asyncio.run(engine.dispose())


def test_period_for_hour_boundaries() -> None:
    assert period_for_hour(5).key == "dawn"
    assert period_for_hour(8).key == "dawn"
    assert period_for_hour(9).key == "noon"
    assert period_for_hour(14).key == "noon"
    assert period_for_hour(15).key == "dusk"
    assert period_for_hour(18).key == "dusk"
    assert period_for_hour(19).key == "night"
    assert period_for_hour(4).key == "night"


def test_light_periods_shape(light_client: TestClient) -> None:
    response = light_client.get("/api/v1/collections/light")
    assert response.status_code == 200, response.text
    body = response.json()

    assert [p["key"] for p in body["periods"]] == [p.key for p in LIGHT_PERIODS]
    assert [p["slug"] for p in body["periods"]] == [p.slug for p in LIGHT_PERIODS]
    labels = {p["key"]: p for p in body["periods"]}
    assert labels["dawn"]["label"] == "晨"
    assert labels["dusk"]["time_range"] == "15:00–19:00"
    assert labels["noon"]["title"] == "昼 · 光在正上方"
    assert labels["noon"]["intro"] == "正午的光最诚实。"


def test_light_periods_only_public_photos(light_client: TestClient) -> None:
    body = light_client.get("/api/v1/collections/light").json()
    noon = next(p for p in body["periods"] if p["key"] == "noon")

    ids = [item["id"] for item in noon["photos"]]
    assert ids == ["n-1", "n-2", "n-3"]  # position 顺序，pending / sensitive 不出现
    assert noon["photo_count"] == 3


def test_light_periods_per_period_limit(light_client: TestClient) -> None:
    body = light_client.get("/api/v1/collections/light?per_period=2").json()
    noon = next(p for p in body["periods"] if p["key"] == "noon")
    assert [item["id"] for item in noon["photos"]] == ["n-1", "n-2"]
    assert noon["photo_count"] == 3  # 计数仍是整册公开数量


def test_light_periods_empty_and_draft_periods(light_client: TestClient) -> None:
    body = light_client.get("/api/v1/collections/light").json()
    periods = {p["key"]: p for p in body["periods"]}

    # 晨间没有专题、夜专题缺失 => 空态但不报错
    assert periods["dawn"]["photos"] == []
    assert periods["dawn"]["photo_count"] == 0
    assert "整理中" in periods["night"]["title"]
    # 暮专题存在但为 draft，不得公开
    assert periods["dusk"]["photos"] == []
    assert periods["dusk"]["photo_count"] == 0
    assert body["total"] == 1


def test_light_periods_photos_are_public_serialization(light_client: TestClient) -> None:
    body = light_client.get("/api/v1/collections/light").json()
    photo = next(
        item for p in body["periods"] for item in p["photos"] if item["id"] == "n-1"
    )
    assert photo.get("uploader_student_id") is None
    assert photo.get("uploader_name") is None
    assert photo["privacy_level"] in (None, "normal")
