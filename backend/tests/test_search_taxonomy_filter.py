"""结构化 taxonomy facet 过滤的回归测试。

线上（asyncpg）曾出现：planner 把「图书馆」解析成 ``filters={"building": "图书馆"}``
后，词法检索把 facet key 列表绑到单个占位符（``tff.key IN :fk``），asyncpg 生成
``tff.key IN $19`` 语法非法 → 整个检索降级为空结果。这里在 SQLite 上覆盖同一条
SQL 构造路径，保证 facet key 是逐个绑定的。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.photo import Photo
from app.models.user import User
from app.models.taxonomy import PhotoClassification
from app.services import lexical_search
from app.services.taxonomy import ensure_default_taxonomy, resolve_taxonomy_node

_NOW = datetime(2026, 11, 20, 12, 0, 0)


def _photo(photo_id: str, title: str) -> Photo:
    return Photo(
        id=photo_id,
        uploader_id="u1",
        filename=f"{photo_id}.jpg",
        title=title,
        author="小明",
        width=1600,
        height=1067,
        captured_at=datetime(2026, 5, 1, 12, 0),
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}.jpg",
        compressed_path=f"compressed/{photo_id}.jpg",
        status="approved",
        processing_status="completed",
        published_at=_NOW - timedelta(minutes=5),
        created_at=_NOW - timedelta(minutes=5),
        views=0,
    )


@pytest.fixture
def taxonomy_db(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'taxonomy.db').as_posix()}", future=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
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
                    _photo("p-library", "图书馆的午后"),
                    _photo("p-lake", "湖边散步"),
                    _photo("p-other", "教学楼前的樱花"),
                ]
            )
            await ensure_default_taxonomy(session)

            node = await resolve_taxonomy_node(session, "building", "图书馆")
            assert node is not None
            session.add(
                PhotoClassification(
                    photo_id="p-library",
                    facet_id=node.facet_id,
                    node_id=node.id,
                )
            )
            await session.commit()

    asyncio.run(init())
    yield session_factory
    asyncio.run(engine.dispose())


def test_taxonomy_filter_matches_classified_photo(taxonomy_db) -> None:
    async def run():
        async with taxonomy_db() as session:
            hits = await lexical_search.search_photos(
                session,
                query="图书馆",
                keywords=["图书馆"],
                filters={"building": "图书馆"},
                limit=10,
            )
            return [hit.photo_id for hit in hits]

    assert asyncio.run(run()) == ["p-library"]


def test_taxonomy_filter_without_match_returns_empty(taxonomy_db) -> None:
    async def run():
        async with taxonomy_db() as session:
            hits = await lexical_search.search_photos(
                session,
                query="食堂",
                keywords=["食堂"],
                filters={"building": "食堂"},
                limit=10,
            )
            return [hit.photo_id for hit in hits]

    assert asyncio.run(run()) == []


def test_landmark_filter_expands_to_building_and_landscape(taxonomy_db) -> None:
    """landmark 是个合成 key：SQL 里要同时匹配 building 与 landscape 两个 facet。"""

    async def run():
        async with taxonomy_db() as session:
            filters = lexical_search.normalize_filters({"landmark": "图书馆"})
            caps = await lexical_search.get_dialect_caps(session)
            params: dict[str, object] = {}
            conditions = lexical_search._build_filter_sql(filters, params, caps)  # noqa: SLF001
            return "\n".join(conditions), params

    sql, params = asyncio.run(run())
    assert "tff.key IN (" in sql
    assert "IN :" not in sql  # 列表不允许再绑到单个占位符
    assert {"building", "landscape"} <= set(params.values())
