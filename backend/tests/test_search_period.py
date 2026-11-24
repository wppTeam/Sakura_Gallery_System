"""按光找图：拍摄时段（晨/昼/暮/夜）过滤测试。

覆盖：
1. 时段写法的规范化（中文口语 / 英文 key / 无法识别）；
2. 词法检索层 ``filters={"period": ...}`` 的 SQL 语义（含夜跨零点、无拍摄时间排除）；
3. 公共列表 CRUD 的 period 过滤；
4. planner 解析结果只保留合法时段；
5. HTTP 端点透传（/photos/public 与 /search?mode=fast）。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.database import Base
from app.main import app
from app.models.photo import Photo
from app.models.user import User
from app.services import lexical_search
from app.services.agent_search.planner import parse_planner_data
from app.services.light_of_day import PERIOD_HOUR_RANGES, normalize_period, period_for_hour

_NOW = datetime(2026, 11, 20, 12, 0, 0)


def _photo(photo_id: str, *, captured_at: datetime | None, status: str = "approved") -> Photo:
    return Photo(
        id=photo_id,
        uploader_id="u1",
        filename=f"{photo_id}.jpg",
        title=f"作品 {photo_id}",
        author="小明",
        width=1600,
        height=1067,
        captured_at=captured_at,
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
            _photo("p-dawn", captured_at=datetime(2026, 5, 1, 6, 30)),
            _photo("p-noon", captured_at=datetime(2026, 5, 1, 12, 0)),
            _photo("p-dusk", captured_at=datetime(2026, 5, 1, 17, 45)),
            _photo("p-night", captured_at=datetime(2026, 5, 1, 22, 10)),
            _photo("p-late-night", captured_at=datetime(2026, 5, 1, 2, 0)),
            _photo("p-no-captured", captured_at=None),
            _photo("p-pending", captured_at=datetime(2026, 5, 1, 17, 30), status="pending"),
        ]
    )
    await session.commit()


@pytest.fixture
def period_db(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'period.db').as_posix()}", future=True
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
def client(period_db):
    async def override_get_db():
        async with period_db() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(deps.get_db, None)


# ---------------------------------------------------------------------------
# 1. 时段写法规范化
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("黄昏", "dusk"),
        ("傍晚", "dusk"),
        ("日落", "dusk"),
        ("清晨", "dawn"),
        ("早上", "dawn"),
        ("中午", "noon"),
        ("夜晚", "night"),
        ("晚上", "night"),
        ("night", "night"),
        ("DUSK", "dusk"),
        ("下午", None),  # 跨 noon/dusk，宁可不过滤
        ("", None),
        (None, None),
    ],
)
def test_normalize_period(raw, expected) -> None:
    assert normalize_period(raw) == expected


def test_period_hour_ranges_match_period_for_hour() -> None:
    for key, (start, end) in PERIOD_HOUR_RANGES.items():
        if start <= end:
            assert period_for_hour(start).key == key
            assert period_for_hour(end - 1).key == key
        else:
            assert period_for_hour(start).key == key
            assert period_for_hour(0).key == key
            assert period_for_hour(end - 1).key == key


# ---------------------------------------------------------------------------
# 2. 词法检索层
# ---------------------------------------------------------------------------

def test_lexical_search_period_filter(period_db) -> None:
    async def scenario():
        async with period_db() as session:
            dusk = await lexical_search.search_photos(
                session, None, filters={"period": "黄昏"}, limit=10
            )
            night = await lexical_search.search_photos(
                session, None, filters={"period": "night"}, limit=10
            )
            noon = await lexical_search.search_photos(
                session, None, filters={"period": "中午"}, limit=10
            )
            total_night = await lexical_search.count_matched(
                session, None, filters={"period": "night"}
            )
            unknown = await lexical_search.search_photos(
                session, None, filters={"period": "下午"}, limit=10
            )
        assert [hit.photo_id for hit in dusk] == ["p-dusk"]
        # 夜跨零点：22:10 与 02:00 都属于夜；pending 不出现
        assert {hit.photo_id for hit in night} == {"p-night", "p-late-night"}
        assert [hit.photo_id for hit in noon] == ["p-noon"]
        assert total_night == 2
        # 无法识别的时段不过滤（也不报错）
        assert len(unknown) == 6

    asyncio.run(scenario())


def test_crud_period_filter(period_db) -> None:
    from app.crud.photo import get_photos

    async def scenario():
        async with period_db() as session:
            photos, total = await get_photos(
                session, status="approved", period="暮", limit=10
            )
            dawn_photos, dawn_total = await get_photos(
                session, status="approved", period="dawn", limit=10
            )
        assert [photo.id for photo in photos] == ["p-dusk"]
        assert total == 1
        assert [photo.id for photo in dawn_photos] == ["p-dawn"]
        assert dawn_total == 1

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 3. planner 只保留合法时段
# ---------------------------------------------------------------------------

def test_planner_keeps_canonical_period() -> None:
    intent = parse_planner_data(
        {"keywords": ["黄昏", "校园"], "filters": {"period": "傍晚", "season": "秋季"}},
        "黄昏的校园",
    )
    assert intent is not None
    assert intent.filters["period"] == "dusk"
    assert intent.filters["season"] == "秋季"


def test_planner_drops_invalid_period() -> None:
    intent = parse_planner_data(
        {"keywords": ["照片"], "filters": {"period": "下午"}},
        "下午的照片",
    )
    assert intent is not None
    assert "period" not in intent.filters


# ---------------------------------------------------------------------------
# 4. HTTP 端点透传
# ---------------------------------------------------------------------------

def test_public_photos_period_param(client) -> None:
    response = client.get("/api/v1/photos/public", params={"period": "night", "limit": 20})
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {"p-night", "p-late-night"}


def test_search_fast_period_param(client) -> None:
    response = client.get(
        "/api/v1/search",
        params={"q": "作品", "mode": "fast", "period": "dusk", "limit": 10},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    ids = {item["photo_id"] for item in body.get("results", [])}
    # fast 模式没有关键词命中时也会返回按筛选条件的结果
    assert "p-dusk" in ids
    assert "p-noon" not in ids
