"""策展自动归档（curation sync）测试。

覆盖：

1. 审核通过的作品按拍摄时段 / 主色卡自动加入对应专题（成员追加到末尾）；
2. 重复同步幂等（不重复加关联、不新增空专题）；
3. 作品被驳回 / 下架时自动从自动策展中移除；
4. 待审作品不归档；缺少 captured_at / 光谱元数据时安静跳过；
5. 时段边界与 `/collections/light` 使用同一套定义（05/09/15/19 点）；
6. `sync_all_photos` 能一次性回填存量作品。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import Collection, CollectionPhoto, Photo
from app.services import curation


def _photo(
    photo_id: str,
    *,
    status: str = "approved",
    captured_at: datetime | None = None,
    palette: str | None = None,
) -> Photo:
    exif: dict = {}
    if palette:
        exif["_spectrum"] = {"palette": palette, "hex": "#ffffff", "ratio": 0.9, "coverage": 0.5}
    return Photo(
        id=photo_id,
        uploader_id="owner",
        filename=f"{photo_id}.jpg",
        title=f"photo {photo_id}",
        author="王海翔",
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        width=1200,
        height=800,
        file_size=200_000,
        mime_type="image/jpeg",
        status=status,
        processing_status="completed",
        privacy_level="normal",
        captured_at=captured_at,
        exif_data=exif,
        views=0,
    )


@pytest.fixture()
def curation_db(tmp_path: Path):
    database_path = tmp_path / "curation.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _bootstrap() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_bootstrap())
    try:
        yield session_factory
    finally:
        asyncio.run(engine.dispose())


def _run(coro):
    return asyncio.run(coro)


def _memberships(session_factory) -> list[tuple[str, str, int]]:
    async def _query():
        async with session_factory() as db:
            rows = (
                await db.execute(
                    select(Collection.slug, CollectionPhoto.photo_id, CollectionPhoto.position)
                    .join(Collection, Collection.id == CollectionPhoto.collection_id)
                    .order_by(Collection.slug, CollectionPhoto.position)
                )
            ).all()
            return [(slug, photo_id, position) for slug, photo_id, position in rows]

    return _run(_query())


def test_sync_adds_light_and_spectrum(curation_db):
    async def _flow():
        async with curation_db() as db:
            photo = _photo(
                "p-dawn",
                captured_at=datetime(2025, 3, 20, 6, 30),
                palette="pink",
            )
            db.add(photo)
            await db.flush()
            result = await curation.sync_photo_curation(db, photo)
            await db.commit()
            return result

    result = _run(_flow())
    assert result["added"] == ["light-dawn", "spectrum-pink"]
    assert result["removed"] == []
    assert _memberships(curation_db) == [
        ("light-dawn", "p-dawn", 0),
        ("spectrum-pink", "p-dawn", 0),
    ]

    async def _collection_meta():
        async with curation_db() as db:
            collection = (
                await db.execute(select(Collection).where(Collection.slug == "light-dawn"))
            ).scalars().one()
            return collection

    dawn = _run(_collection_meta())
    assert dawn.kind == "editorial"
    assert dawn.visibility == "public"
    assert dawn.status == "published"
    assert dawn.title.startswith("晨")


def test_sync_is_idempotent_and_appends_position(curation_db):
    async def _seed():
        async with curation_db() as db:
            first = _photo("p-a", captured_at=datetime(2025, 3, 20, 17, 0), palette="gold")
            second = _photo("p-b", captured_at=datetime(2025, 3, 21, 18, 0), palette="gold")
            db.add_all([first, second])
            await db.flush()
            await curation.sync_photo_curation(db, first)
            await curation.sync_photo_curation(db, second)
            again = await curation.sync_photo_curation(db, first)
            await db.commit()
            return again

    result = _run(_seed())
    assert result == {"added": [], "removed": []}
    memberships = _memberships(curation_db)
    assert memberships == [
        ("light-dusk", "p-a", 0),
        ("light-dusk", "p-b", 1),
        ("spectrum-gold", "p-a", 0),
        ("spectrum-gold", "p-b", 1),
    ]


def test_sync_removes_membership_when_photo_rejected(curation_db):
    async def _flow():
        async with curation_db() as db:
            photo = _photo("p-x", captured_at=datetime(2025, 3, 20, 11, 0), palette="blue")
            db.add(photo)
            await db.flush()
            await curation.sync_photo_curation(db, photo)
            photo.status = "rejected"
            result = await curation.sync_photo_curation(db, photo)
            await db.commit()
            return result

    result = _run(_flow())
    assert sorted(result["removed"]) == ["light-noon", "spectrum-blue"]
    assert result["added"] == []
    assert _memberships(curation_db) == []


def test_sync_removes_membership_when_marked_sensitive(curation_db):
    async def _flow():
        async with curation_db() as db:
            photo = _photo("p-portrait", captured_at=datetime(2025, 3, 20, 10, 0), palette="pink")
            db.add(photo)
            await db.flush()
            await curation.sync_photo_curation(db, photo)
            photo.privacy_level = "sensitive"
            result = await curation.sync_photo_curation(db, photo)
            await db.commit()
            return result

    result = _run(_flow())
    assert sorted(result["removed"]) == ["light-noon", "spectrum-pink"]
    assert result["added"] == []
    assert _memberships(curation_db) == []


def test_sync_skips_pending_and_incomplete_photos(curation_db):
    async def _flow():
        async with curation_db() as db:
            pending = _photo("p-pending", status="pending", captured_at=datetime(2025, 3, 20, 6, 30))
            neither = _photo("p-neither")
            unknown_palette = _photo("p-unknown", palette="chartreuse")
            db.add_all([pending, neither, unknown_palette])
            await db.flush()
            results = {}
            for photo in (pending, neither, unknown_palette):
                results[photo.id] = await curation.sync_photo_curation(db, photo)
            await db.commit()
            return results

    results = _run(_flow())
    assert results == {
        "p-pending": {"added": [], "removed": []},
        "p-neither": {"added": [], "removed": []},
        "p-unknown": {"added": [], "removed": []},
    }
    assert _memberships(curation_db) == []


@pytest.mark.parametrize(
    ("hour", "expected"),
    [(4, "light-night"), (5, "light-dawn"), (8, "light-dawn"), (9, "light-noon"),
     (14, "light-noon"), (15, "light-dusk"), (18, "light-dusk"), (19, "light-night")],
)
def test_light_slug_boundaries(hour: int, expected: str):
    photo = _photo("p", captured_at=datetime(2025, 3, 20, hour, 0))
    assert curation.light_slug_for(photo) == expected


def test_sync_all_photos_backfills(curation_db):
    async def _flow():
        async with curation_db() as db:
            db.add_all(
                [
                    _photo("p1", captured_at=datetime(2025, 3, 20, 6, 0), palette="green"),
                    _photo("p2", captured_at=datetime(2025, 3, 20, 12, 0), palette="ink"),
                    _photo("p3", status="pending", captured_at=datetime(2025, 3, 20, 16, 0)),
                ]
            )
            await db.commit()
            summary = await curation.sync_all_photos(db, commit_every=2)
            return summary

    summary = _run(_flow())
    assert summary == {"scanned": 2, "added": 4, "removed": 0}
    assert len(_memberships(curation_db)) == 4

    async def _collection_count():
        async with curation_db() as db:
            return (await db.execute(select(func.count()).select_from(Collection))).scalar()

    # 两段光 + 两个色卡，共 4 个专题
    assert _run(_collection_count()) == 4
