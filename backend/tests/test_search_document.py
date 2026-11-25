"""补充检索语料（search_document）与 AI 画面描述公开测试。

覆盖：
1. ``build_search_document`` 的去重/限长；
2. AI 画面描述写入 search_document 后，词法检索能召回（SQLite 降级路径同样覆盖）；
3. 待审/敏感作品不会被检索到；
4. 标签变更会刷新 search_document；
5. 公开详情返回 ai_caption，脱敏视角不返回；
6. ``GET /api/v1/tags/public/popular`` 只统计公开且非敏感作品的标签。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import photos as photos_api
from app.core import deps
from app.core.database import Base
from app.main import app
from app.models.photo import Photo
from app.models.tag import PhotoTag, Tag
from app.models.user import User
from app.services import lexical_search
from app.services.search_index import (
    build_search_document,
    refresh_search_document,
)

_NOW = datetime(2026, 11, 20, 12, 0, 0)

CAPTION = "黄昏下的樱花与红砖教学楼，有人在路上骑车"


def _photo(
    photo_id: str,
    *,
    title: str,
    caption: str | None = None,
    status: str = "approved",
    privacy_level: str = "normal",
) -> Photo:
    exif = {"_ai_caption": caption} if caption else None
    return Photo(
        id=photo_id,
        uploader_id="u1",
        filename=f"{photo_id}.jpg",
        title=title,
        author="小明",
        width=1600,
        height=1067,
        description="校园日常",
        exif_data=exif,
        privacy_level=privacy_level,
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}.jpg",
        compressed_path=f"compressed/{photo_id}.jpg",
        status=status,
        processing_status="completed",
        published_at=_NOW - timedelta(minutes=5),
        created_at=_NOW - timedelta(minutes=5),
        views=0,
    )


async def _seed(session) -> None:
    session.add(
        User(
            id="u1",
            email="u1@example.com",
            hashed_password="x",
            student_id="u1",
            username="u1",
            display_name="小明",
            is_active=True,
        )
    )
    await session.flush()
    session.add_all(
        [
            _photo("p-caption", title="钟楼前的傍晚", caption=CAPTION),
            _photo("p-plain", title="没有描述的日常"),
            _photo("p-pending", title="待审作品", caption=CAPTION, status="pending"),
            _photo("p-sensitive", title="人像作品", caption=CAPTION, privacy_level="sensitive"),
            _photo("p-tag", title="骑行日志"),
        ]
    )
    session.add_all([Tag(id=1, name="共享单车", usage_count=1), Tag(id=2, name="待审标签", usage_count=1)])
    await session.flush()
    session.add_all(
        [
            PhotoTag(photo_id="p-caption", tag_id=1),
            PhotoTag(photo_id="p-pending", tag_id=2),
        ]
    )
    await session.commit()


@pytest.fixture
def search_db(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'search_document.db').as_posix()}", future=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            await _seed(session)

    asyncio.run(init())
    yield session_factory
    asyncio.run(engine.dispose())


@pytest.fixture
def client(search_db):
    async def override_get_db():
        async with search_db() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(deps.get_db, None)


def test_build_search_document_dedupes_and_limits() -> None:
    doc = build_search_document(
        caption="  " + CAPTION + "  ",
        tags=["共享单车", "共享单车", "", "钟楼", "  "],
    )
    assert doc.startswith(CAPTION)
    assert doc.count("共享单车") == 1
    assert "钟楼" in doc


def test_caption_becomes_searchable(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            photo = await session.get(Photo, "p-caption")
            await refresh_search_document(session, photo)
            await session.commit()

            hits = await lexical_search.search_photos(session, "红砖教学楼", limit=10)
            ids = [hit.photo_id for hit in hits]
            assert "p-caption" in ids
            # 待审 / 敏感作品即使描述相同也不应召回
            assert "p-pending" not in ids
            assert "p-sensitive" not in ids

            # 只出现在画面描述里的词（不在标题/标签里）也应命中，并解释为「画面描述匹配」
            caption_hits = await lexical_search.search_photos(session, "骑车", limit=10)
            assert [hit.photo_id for hit in caption_hits] == ["p-caption"]
            assert "caption" in caption_hits[0].matched_fields
            assert "画面描述匹配" in (caption_hits[0].match_reason or "")

    asyncio.run(scenario())


def test_refresh_includes_tags(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            photo = await session.get(Photo, "p-caption")
            await refresh_search_document(session, photo)
            assert "共享单车" in (photo.search_document or "")
            await session.commit()

    asyncio.run(scenario())


def test_public_detail_exposes_ai_caption(client, search_db) -> None:
    async def prepare():
        async with search_db() as session:
            photo = await session.get(Photo, "p-caption")
            await refresh_search_document(session, photo)
            await session.commit()

    asyncio.run(prepare())

    resp = client.get("/api/v1/photos/public/p-caption")
    assert resp.status_code == 200
    assert resp.json()["ai_caption"] == CAPTION

    # 匿名访问 sensitive 作品：直接 404（不暴露任何内容）
    resp = client.get("/api/v1/photos/public/p-sensitive")
    assert resp.status_code == 404


def test_serialize_redacted_hides_ai_caption(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            photo = (
                await session.execute(
                    select(Photo)
                    .where(Photo.id == "p-sensitive")
                    .options(selectinload(Photo.classifications))
                )
            ).scalar_one()
            plain = await photos_api.serialize_photo(session, photo, redact=False)
            redacted = await photos_api.serialize_photo(session, photo, redact=True)
            assert plain.ai_caption == CAPTION
            assert redacted.ai_caption is None

    asyncio.run(scenario())


def test_public_popular_tags_only_public_photos(client, search_db) -> None:
    resp = client.get("/api/v1/tags/public/popular?limit=10")
    assert resp.status_code == 200
    payload = resp.json()
    names = [item["name"] for item in payload["items"]]
    assert "共享单车" in names
    # 只挂在待审作品上的标签不应出现在公开热门里
    assert "待审标签" not in names
    counts = {item["name"]: item["count"] for item in payload["items"]}
    assert counts["共享单车"] == 1
