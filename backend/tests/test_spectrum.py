"""樱色光谱：颜色分类与 /collections/spectrum 接口测试。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import collections as collections_api
from app.core import deps
from app.core.database import Base
from app.models import Collection, CollectionPhoto, Photo
from app.services.spectrum import PALETTES, classify_image, palette_slug, spectrum_meta

_COLORS = {
    "pink": (232, 120, 160),
    "gold": (222, 168, 60),
    "green": (60, 140, 80),
    "blue": (70, 130, 200),
    "ink": (24, 22, 28),
}


@pytest.mark.parametrize("expected, rgb", list(_COLORS.items()))
def test_classify_solid_colors(tmp_path: Path, expected: str, rgb: tuple[int, int, int]) -> None:
    path = tmp_path / f"{expected}.png"
    Image.new("RGB", (32, 32), rgb).save(path)

    meta = classify_image(path)

    assert meta is not None
    assert meta["palette"] == expected
    assert meta["hex"].startswith("#") and len(meta["hex"]) == 7
    assert 0 < meta["ratio"] <= 1.0


def test_palette_lookup_and_meta_helper() -> None:
    assert palette_slug("pink") == "spectrum-pink"
    assert palette_slug("nope") is None

    class _FakePhoto:
        exif_data = {"_spectrum": {"palette": "blue", "hex": "#5b8fc0", "ratio": 0.6}}

    assert spectrum_meta(_FakePhoto()) == {
        "palette": "blue",
        "hex": "#5b8fc0",
        "ratio": 0.6,
    }

    class _BadPhoto:
        exif_data = {"_spectrum": {"palette": "unknown"}}

    assert spectrum_meta(_BadPhoto()) is None


@pytest.mark.parametrize("palette", PALETTES)
def test_palettes_are_well_formed(palette) -> None:
    assert palette.slug.startswith("spectrum-")
    assert palette.name and palette.description
    assert palette.hex.startswith("#") and len(palette.hex) == 7


def _photo(photo_id: str, *, palette: str, ratio: float) -> Photo:
    return Photo(
        id=photo_id,
        uploader_id="owner",
        filename=f"{photo_id}.jpg",
        title=f"{palette} photo",
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        width=1200,
        height=800,
        file_size=200_000,
        mime_type="image/jpeg",
        status="approved",
        processing_status="completed",
        exif_data={"_spectrum": {"palette": palette, "hex": "#ffffff", "ratio": ratio}},
        views=0,
    )


@pytest.fixture()
def spectrum_client(tmp_path: Path):
    db_path = tmp_path / "spectrum.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add_all(
                [
                    _photo("p-pink", palette="pink", ratio=0.62),
                    _photo("p-gold", palette="gold", ratio=0.55),
                    _photo("p-blue", palette="blue", ratio=0.48),
                ]
            )
            session.add_all(
                [
                    Collection(
                        id="col-pink",
                        slug="spectrum-pink",
                        title="樱粉光谱",
                        kind="editorial",
                        status="published",
                        visibility="public",
                        sort_order=30,
                    ),
                    Collection(
                        id="col-blue",
                        slug="spectrum-blue",
                        title="蓝色光谱",
                        kind="editorial",
                        status="published",
                        visibility="public",
                        sort_order=33,
                    ),
                ]
            )
            session.add_all(
                [
                    CollectionPhoto(collection_id="col-pink", photo_id="p-pink", position=0),
                    CollectionPhoto(collection_id="col-blue", photo_id="p-blue", position=0),
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


def test_spectrum_endpoint(spectrum_client: TestClient) -> None:
    response = spectrum_client.get("/api/v1/collections/spectrum")
    assert response.status_code == 200, response.text
    body = response.json()

    palettes = {item["key"]: item for item in body["palettes"]}
    assert set(palettes) == {"pink", "gold", "green", "blue", "ink"}
    assert palettes["pink"]["photo_count"] == 1
    assert palettes["pink"]["cover"]["id"] == "p-pink"
    assert palettes["blue"]["photo_count"] == 1
    # 没有对应专题的色卡也返回，但不给 slug/封面
    assert palettes["green"]["slug"] is None
    assert palettes["green"]["cover"] is None
    assert body["total"] == 2
