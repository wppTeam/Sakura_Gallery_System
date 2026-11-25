"""公开创作者主页接口回归测试。

背景：浏览者从作品详情点作者名进入 /u/{username}，需要一次请求拿到
个人资料 + 公开作品首页 + 作者自建的作品集；「加载更多」再分页拉作品。

覆盖：
- 资料/计数只统计「已通过 + 非敏感」作品，浏览数与收藏数按同一口径聚合；
- 作品分页、排序与 `uploader_username` 回填（详情页作者可点）；
- 作品集只返回已发布 + 公开 + 至少一张公开作品的作者专辑；
- 未知/inactive 创作者 404；
- 公开响应里绝不出现学号/邮箱/真实姓名等身份字段。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.config import get_settings
from app.core.database import Base
from app.main import app
from app.models import Collection, CollectionPhoto, Favorite, Photo, User

PASSWORD = "Creators#2026"


def _make_photo(
    photo_id: str,
    uploader_id: str,
    *,
    status: str = "approved",
    privacy_level: str | None = "normal",
    views: int = 0,
) -> Photo:
    return Photo(
        id=photo_id,
        uploader_id=uploader_id,
        filename=f"{photo_id}.jpg",
        title=f"作品 {photo_id}",
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        compressed_path=f"compressed/{photo_id}_compressed.jpg",
        width=1200,
        height=800,
        file_size=123456,
        mime_type="image/jpeg",
        status=status,
        privacy_level=privacy_level,
        processing_status="completed",
        exif_data={},
        views=views,
    )


@pytest.fixture
def creators_client(tmp_path: Path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    monkeypatch.setattr(settings, "REQUIRE_REGISTRATION_APPROVAL", False)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'creators.db').as_posix()}", future=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_database())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    from app.api.v1.endpoints.auth import limiter as auth_limiter

    auth_limiter.reset()

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as client:
        yield client, session_factory
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _register_and_login(
    client: TestClient, *, username: str, student_id: str, display_name: str | None = None
) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "student_id": student_id,
            "username": username,
            "display_name": display_name if display_name is not None else username,
            "password": PASSWORD,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    login = client.post(
        "/api/v1/auth/login", json={"identifier": username, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


async def _seed(session_factory) -> dict[str, str]:
    async with session_factory() as session:
        creator = (
            await session.execute(select(User).where(User.username == "creator_lily"))
        ).scalar_one()
        fan = (
            await session.execute(select(User).where(User.username == "creator_fan"))
        ).scalar_one()
        creator.display_name = "山茶与光"
        session.add_all(
            [
                _make_photo("cp-a1", creator.id, views=120),
                _make_photo("cp-a2", creator.id, views=30),
                _make_photo("cp-a3", creator.id, views=7, status="pending"),
                _make_photo("cp-a4", creator.id, views=999, privacy_level="sensitive"),
                _make_photo("cp-fan", fan.id, views=500),
            ]
        )
        session.add_all(
            [
                Favorite(id="fav-1", user_id=fan.id, photo_id="cp-a1"),
                Favorite(id="fav-2", user_id=fan.id, photo_id="cp-a2"),
                Favorite(id="fav-3", user_id=fan.id, photo_id="cp-a4"),
            ]
        )
        session.add_all(
            [
                Collection(
                    id="col-pub",
                    slug="lily-spring",
                    title="山茶的春天",
                    subtitle="三月校园",
                    kind="user",
                    owner_id=creator.id,
                    status="published",
                    visibility="public",
                ),
                Collection(
                    id="col-draft",
                    slug="lily-draft",
                    title="草稿集",
                    kind="user",
                    owner_id=creator.id,
                    status="draft",
                    visibility="public",
                ),
                Collection(
                    id="col-empty",
                    slug="lily-empty",
                    title="空专辑",
                    kind="user",
                    owner_id=creator.id,
                    status="published",
                    visibility="public",
                ),
            ]
        )
        session.add_all(
            [
                CollectionPhoto(
                    id="ce-1", collection_id="col-pub", photo_id="cp-a1", position=0
                ),
                CollectionPhoto(
                    id="ce-2", collection_id="col-pub", photo_id="cp-a2", position=1
                ),
                CollectionPhoto(
                    id="ce-3", collection_id="col-pub", photo_id="cp-a3", position=2
                ),
                CollectionPhoto(
                    id="ce-4", collection_id="col-draft", photo_id="cp-a1", position=0
                ),
            ]
        )
        await session.commit()
        return {"creator": creator.id, "fan": fan.id}


def test_creator_profile_counts_public_works_only(creators_client):
    client, session_factory = creators_client
    _register_and_login(client, username="creator_lily", student_id="20269001")
    _register_and_login(client, username="creator_fan", student_id="20269002")
    asyncio.run(_seed(session_factory))

    resp = client.get("/api/v1/creators/creator_lily")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    profile = payload["profile"]
    assert profile["username"] == "creator_lily"
    assert profile["display_name"] == "山茶与光"
    assert profile["works_count"] == 2
    assert profile["views_total"] == 150
    assert profile["favorites_total"] == 2
    assert profile["collections_count"] == 1
    assert profile["joined_at"]

    work_payload = payload["works"]
    assert work_payload["total"] == 2
    titles = {item["id"] for item in work_payload["items"]}
    assert titles == {"cp-a1", "cp-a2"}
    # 详情页作者可点：公开作品要带上载者用户名
    assert all(item["uploader_username"] == "creator_lily" for item in work_payload["items"])


def test_creator_collections_and_privacy(creators_client):
    client, session_factory = creators_client
    _register_and_login(client, username="creator_lily", student_id="20269003")
    _register_and_login(client, username="creator_fan", student_id="20269004")
    asyncio.run(_seed(session_factory))

    payload = client.get("/api/v1/creators/creator_lily").json()
    collections = payload["collections"]
    assert [card["slug"] for card in collections] == ["lily-spring"]
    card = collections[0]
    assert card["title"] == "山茶的春天"
    assert card["subtitle"] == "三月校园"
    assert card["photo_count"] == 2  # 待审作品不计入、空专辑与草稿不出现
    assert card["cover"]["id"] == "cp-a1"

    import json

    text = json.dumps(payload, ensure_ascii=False)
    # 公开身份只有 username / display_name：学号值、邮箱、真实姓名字段都不应出现
    assert "20269003" not in text
    assert "email" not in text
    assert "full_name" not in text


def test_creator_work_pagination(creators_client):
    client, session_factory = creators_client
    _register_and_login(client, username="creator_lily", student_id="20269005")
    _register_and_login(client, username="creator_fan", student_id="20269006")
    asyncio.run(_seed(session_factory))

    first = client.get(
        "/api/v1/creators/creator_lily/works?limit=1&offset=0"
    ).json()
    assert first["total"] == 2
    assert len(first["items"]) == 1
    second = client.get(
        "/api/v1/creators/creator_lily/works?limit=1&offset=1"
    ).json()
    assert len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]


def test_unknown_and_inactive_creator_returns_404(creators_client):
    client, session_factory = creators_client
    _register_and_login(client, username="creator_lily", student_id="20269007")
    _register_and_login(client, username="creator_fan", student_id="20269008")
    asyncio.run(_seed(session_factory))

    assert client.get("/api/v1/creators/nobody-here").status_code == 404
    assert client.get("/api/v1/creators/nobody-here/works").status_code == 404

    async def deactivate() -> None:
        async with session_factory() as session:
            user = (
                await session.execute(
                    select(User).where(User.username == "creator_lily")
                )
            ).scalar_one()
            user.is_active = False
            await session.commit()

    asyncio.run(deactivate())
    assert client.get("/api/v1/creators/creator_lily").status_code == 404


def test_public_detail_exposes_uploader_username(creators_client):
    client, session_factory = creators_client
    _register_and_login(client, username="creator_lily", student_id="20269009")
    _register_and_login(client, username="creator_fan", student_id="20269010")
    asyncio.run(_seed(session_factory))

    resp = client.get("/api/v1/photos/public/cp-a1")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["uploader_username"] == "creator_lily"
    # 学号与真实姓名依旧不公开
    assert payload["uploader_student_id"] is None
    assert payload["uploader_name"] is None
