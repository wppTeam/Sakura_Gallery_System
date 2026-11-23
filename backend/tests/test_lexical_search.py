"""词法检索层测试（SQLite 降级路径）。

真实生产路径是 PostgreSQL（pg_trgm + tsvector），这里用临时 SQLite 验证：
查询/过滤/分页/facet/补全的语义与 SQL 正确性、状态白名单、同义词展开、
limit 硬上限，以及不依赖 N+1 的批量返回结构。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.photo import Photo
from app.models.tag import PhotoTag, Tag
from app.services import lexical_search

_NOW = datetime(2026, 11, 20, 12, 0, 0)


async def _seed(session) -> None:
    session.add_all(
        [
            Photo(
                id="photo-cherry",
                uploader_id="u1",
                filename="cherry.jpg",
                title="秋季樱花大道",
                author="小明",
                description="昌平校区的樱花开了",
                season="秋季",
                category="风光",
                campus="昌平校区",
                width=1600,
                height=1067,
                status="approved",
                processing_status="completed",
                published_at=_NOW - timedelta(hours=1),
                created_at=_NOW - timedelta(hours=1),
                views=0,
            ),
            Photo(
                id="photo-ginkgo",
                uploader_id="u2",
                filename="ginkgo.jpg",
                title="金色银杏",
                description="校园里的银杏叶",
                season="秋季",
                category="风光",
                campus="昌平校区",
                width=1200,
                height=1600,
                status="approved",
                processing_status="completed",
                published_at=_NOW - timedelta(hours=2),
                created_at=_NOW - timedelta(hours=2),
                views=0,
            ),
            Photo(
                id="photo-snow",
                uploader_id="u3",
                filename="snow.jpg",
                title="冬季初雪",
                description="朝阳校区的第一场雪",
                season="冬季",
                category="风光",
                campus="朝阳校区",
                width=1920,
                height=1080,
                status="approved",
                processing_status="completed",
                published_at=_NOW - timedelta(hours=3),
                created_at=_NOW - timedelta(hours=3),
                views=0,
            ),
            Photo(
                id="photo-pending",
                uploader_id="u1",
                filename="pending.jpg",
                title="秋季樱花大道（待审）",
                description="不应出现在检索结果里",
                season="秋季",
                category="风光",
                campus="昌平校区",
                status="pending",
                processing_status="completed",
                published_at=_NOW,
                created_at=_NOW,
                views=0,
            ),
        ]
    )
    await session.flush()

    cherry = Tag(name="樱花", category="object", usage_count=10)
    ginkgo = Tag(name="银杏", category="object", usage_count=5)
    snow = Tag(name="雪", category="scene", usage_count=2)
    session.add_all([cherry, ginkgo, snow])
    await session.flush()
    session.add_all(
        [
            PhotoTag(photo_id="photo-cherry", tag_id=cherry.id),
            PhotoTag(photo_id="photo-ginkgo", tag_id=ginkgo.id),
            PhotoTag(photo_id="photo-snow", tag_id=snow.id),
        ]
    )
    await session.commit()


@pytest.fixture
def search_db(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'lexical.db').as_posix()}", future=True
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


def test_query_matches_title_and_returns_summary_fields(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            hits = await lexical_search.search_photos(session, "樱花", limit=10)
        assert [hit.photo_id for hit in hits] == ["photo-cherry"]
        hit = hits[0]
        assert hit.score > 0
        assert hit.title == "秋季樱花大道"
        assert hit.author == "小明"
        assert (hit.width, hit.height) == (1600, 1067)
        assert "樱花" in hit.tags
        assert "title" in hit.matched_fields
        assert "樱花" in (hit.match_reason or "")

    asyncio.run(scenario())


def test_pending_photos_are_never_exposed(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            hits = await lexical_search.search_photos(session, "樱花", limit=10)
            total = await lexical_search.count_matched(session, "樱花")
        assert all(hit.photo_id != "photo-pending" for hit in hits)
        assert total == 1

    asyncio.run(scenario())


def test_tag_filter(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            hits = await lexical_search.search_photos(
                session, None, filters={"tag": "银杏"}, limit=10
            )
        assert [hit.photo_id for hit in hits] == ["photo-ginkgo"]
        assert "银杏" in hits[0].tags

    asyncio.run(scenario())


def test_season_and_campus_synonyms(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            autumn = await lexical_search.search_photos(
                session, None, filters={"season": "秋"}, limit=10
            )
            campus = await lexical_search.search_photos(
                session, None, filters={"season": "秋天", "campus": "昌平"}, limit=10
            )
            winter = await lexical_search.search_photos(
                session, None, filters={"season": "Winter"}, limit=10
            )
        assert {hit.photo_id for hit in autumn} == {"photo-cherry", "photo-ginkgo"}
        assert {hit.photo_id for hit in campus} == {"photo-cherry", "photo-ginkgo"}
        assert [hit.photo_id for hit in winter] == ["photo-snow"]

    asyncio.run(scenario())


def test_pagination_and_hard_limit(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            first = await lexical_search.search_photos(session, None, limit=1, offset=0)
            second = await lexical_search.search_photos(session, None, limit=1, offset=1)
            capped = await lexical_search.search_photos(session, None, limit=500)
            total = await lexical_search.count_matched(session, None)
        assert len(first) == 1 and len(second) == 1
        assert first[0].photo_id != second[0].photo_id
        assert total == 3
        assert len(capped) <= lexical_search.LIMIT_MAX

    asyncio.run(scenario())


def test_empty_query_returns_recent_approved(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            hits = await lexical_search.search_photos(session, None, limit=10)
        # 无关键词时按 published_at 倒序（最近发布的在前）
        assert [hit.photo_id for hit in hits] == [
            "photo-cherry",
            "photo-ginkgo",
            "photo-snow",
        ]
        assert all(hit.score == 0 for hit in hits)

    asyncio.run(scenario())


def test_facets_single_aggregate_sql(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            facets = await lexical_search.compute_facets(session, None)
        assert facets.total == 3
        seasons = {value.value: value.count for value in facets.seasons}
        assert seasons["秋季"] == 2 and seasons["冬季"] == 1
        campuses = {value.value: value.count for value in facets.campuses}
        assert campuses["昌平校区"] == 2 and campuses["朝阳校区"] == 1
        tags = {value.value: value.count for value in facets.tags}
        assert tags["樱花"] == 1 and tags["银杏"] == 1
        payload = facets.to_dict()
        assert set(payload) >= {"season", "category", "campus", "tag", "total"}
        assert payload["total"] == 3
        assert {"value", "label", "count"} <= set(payload["season"][0])

    asyncio.run(scenario())


def test_facets_respect_query(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            facets = await lexical_search.compute_facets(session, "樱花")
        assert facets.total == 1
        assert [value.value for value in facets.tags] == ["樱花"]

    asyncio.run(scenario())


def test_suggest_returns_typed_items(search_db) -> None:
    async def scenario():
        async with search_db() as session:
            items = await lexical_search.suggest(session, "樱", limit=5)
            empty = await lexical_search.suggest(session, "  ", limit=5)
        assert items and items[0]["text"] == "樱花"
        assert items[0]["type"] == "tag"
        assert empty == []

    asyncio.run(scenario())


def test_normalize_filters_and_terms() -> None:
    normalized = lexical_search.normalize_filters(
        {
            "season": "秋季",
            "tag": "樱花",
            "campus": "昌平",
            "uploader": "user-1",
            "captured_from": "2026-01-01",
            "unknown_facet": "x",
            "kind": "photo",
            "mode": "fast",
        }
    )
    assert normalized["season"] == ["秋季", "Autumn", "秋"]
    assert normalized["campus"] == ["昌平校区", "昌平"]
    assert normalized["tag"] == "樱花"
    assert normalized["uploader_id"] == "user-1"
    # 未识别的 key 视作 taxonomy facet 原样保留；明确忽略的键才丢弃
    assert normalized["unknown_facet"] == "x"
    assert "kind" not in normalized and "mode" not in normalized
    assert "秋季" in lexical_search.build_search_terms("秋季校园樱花")
