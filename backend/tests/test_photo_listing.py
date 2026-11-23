"""公开列表过滤回归测试。

背景：`/photos/public` 在「未登录且肖像可见性 = LOGIN_REQUIRED」时会传
`exclude_categories=["Portrait"]`。SQL 里 `NULL != 'Portrait'` 结果是 NULL，
会把所有未分类作品从公开列表整批过滤掉（AIGC 演示图曾因此不可见）。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.crud import photo as photo_crud
from app.models import Photo


def _photo(photo_id: str, *, category: str | None) -> Photo:
    return Photo(
        id=photo_id,
        uploader_id="owner",
        filename=f"{photo_id}.jpg",
        original_path=f"originals/{photo_id}.jpg",
        width=100,
        height=100,
        file_size=100,
        mime_type="image/jpeg",
        category=category,
        status="approved",
        processing_status="completed",
        views=0,
    )


@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'listing.db').as_posix()}", future=True
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add_all(
                [
                    _photo("no-category", category=None),
                    _photo("portrait", category="Portrait"),
                    _photo("landscape", category="Landscape"),
                ]
            )
            await session.commit()

    asyncio.run(init())
    try:
        yield factory
    finally:
        asyncio.run(engine.dispose())


def test_exclude_categories_keeps_null_category_photos(session_factory):
    async def run():
        async with session_factory() as session:
            photos, total = await photo_crud.get_photos(
                session, status="approved", exclude_categories=["Portrait"]
            )
        return photos, total

    photos, total = asyncio.run(run())
    ids = {photo.id for photo in photos}

    assert total == 2
    assert ids == {"no-category", "landscape"}


def test_exclude_categories_still_filters_matching_category(session_factory):
    async def run():
        async with session_factory() as session:
            photos, _ = await photo_crud.get_photos(
                session, status="approved", category="Portrait", exclude_categories=["Portrait"]
            )
        return photos

    assert asyncio.run(run()) == []


def test_count_and_page_are_consistent(session_factory):
    async def run():
        async with session_factory() as session:
            photos, total = await photo_crud.get_photos(
                session, status="approved", exclude_categories=["Portrait"], limit=1
            )
            raw = (
                await session.execute(
                    select(func.count(Photo.id.distinct())).where(Photo.status == "approved")
                )
            ).scalar_one()
        return photos, total, raw

    photos, total, raw = asyncio.run(run())
    assert len(photos) == 1
    assert total == 2
    assert raw == 3
