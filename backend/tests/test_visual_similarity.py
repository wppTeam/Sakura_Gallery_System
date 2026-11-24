"""视觉相似检索（dhash + 光谱 + 标签）测试。

覆盖：
1. 打分：同色调/同标签/同构图比例的作品排在前面，理由可读；
2. 老图缺 dhash 时仍按可用信号参与排序（权重归一化，不会整体低分）；
3. 近重复（同一张图重复上传，汉明距离 ≤ 3）不推荐；
4. 候选集只含已发布、非人像敏感作品；
5. HTTP 端点：匿名可读、返回 similarity/reasons、目标不存在或未公开时友好 404。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import photos as photos_api
from app.core import deps
from app.core.database import Base
from app.models import Photo, PhotoTag, Tag, User
from app.services.visual_similarity import (
    MIN_SCORE,
    find_similar_photos,
    photo_dhash,
    rank_similar,
    score_pair,
)

FULL_BITS = "f" * 64
ALT_BITS = "0f0f" * 16


def _photo(
    photo_id: str,
    *,
    dhash: str | None = None,
    palette: str | None = None,
    width: int = 1200,
    height: int = 800,
    season: str | None = None,
    campus: str | None = None,
    status: str = "approved",
    privacy: str = "normal",
    uploader: str = "owner",
    title: str | None = None,
) -> Photo:
    exif: dict = {}
    if dhash:
        exif["_dhash"] = dhash
    if palette:
        exif["_spectrum"] = {"palette": palette, "hex": "#e8628c", "ratio": 0.6, "coverage": 0.5}
    return Photo(
        id=photo_id,
        uploader_id=uploader,
        filename=f"{photo_id}.jpg",
        title=title or f"作品 {photo_id}",
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        width=width,
        height=height,
        file_size=200_000,
        mime_type="image/jpeg",
        season=season,
        campus=campus,
        status=status,
        privacy_level=privacy,
        processing_status="completed",
        views=0,
        exif_data=exif,
    )


def test_score_pair_prefers_same_palette_and_tags() -> None:
    target = _photo("t", dhash=FULL_BITS, palette="pink", season="Spring", campus="昌平校区")
    good = _photo("g", dhash=ALT_BITS, palette="pink", season="Spring", campus="昌平校区")
    bad = _photo("b", dhash="0" * 64 + "", palette="blue", width=900, height=1600)

    good_score, good_reasons = score_pair(target, good, ["樱花", "春天"], ["樱花", "校园"])
    bad_score, _ = score_pair(target, bad, ["樱花", "春天"], ["建筑"])

    assert good_score > bad_score
    assert good_score >= MIN_SCORE
    assert any("色调" in reason or "标签" in reason for reason in good_reasons)


def test_missing_dhash_still_scores_with_other_signals() -> None:
    target = _photo("t", dhash=FULL_BITS, palette="pink", season="Spring")
    candidate = _photo("c", dhash=None, palette="pink", season="Spring")

    score, reasons = score_pair(target, candidate, ["樱花"], ["樱花"])

    assert score >= MIN_SCORE
    assert any("色调" in reason for reason in reasons)


def test_near_duplicate_signature_is_excluded() -> None:
    target = _photo("t", dhash="1" * 64)
    same = _photo("same", dhash="1" * 64)
    useful = _photo("u", dhash="3" * 64, palette="pink", season="Spring", campus="昌平校区")

    hits = rank_similar(target, [same, useful], {}, [], limit=8)

    assert [hit.photo.id for hit in hits] == ["u"]


def test_rank_similar_sorts_by_score() -> None:
    target = _photo("t", dhash=FULL_BITS, palette="pink", season="Spring", campus="昌平校区")
    close = _photo("close", dhash=ALT_BITS, palette="pink", season="Spring", campus="昌平校区")
    far = _photo("far", dhash=("8" + "0" * 63), palette="blue", width=600, height=1600)

    hits = rank_similar(
        target,
        [far, close],
        {"close": ["樱花"], "far": []},
        ["樱花"],
        limit=8,
    )

    assert hits[0].photo.id == "close"
    assert hits[0].score >= hits[-1].score


async def _seed(session_factory) -> None:
    owner = User(
        id="owner",
        student_id="20260001",
        username="jackwpp",
        display_name="王海翔",
        full_name="真实姓名",
        hashed_password="x",
        role="user",
        is_active=True,
    )
    async with session_factory() as session:
        session.add(owner)
        session.add_all(
            [
                _photo("target", dhash=FULL_BITS, palette="pink", season="Spring"),
                _photo("similar", dhash=ALT_BITS, palette="pink", season="Spring"),
                _photo("pending", dhash=ALT_BITS, palette="pink", status="pending"),
                _photo("hidden", dhash=ALT_BITS, palette="pink", privacy="sensitive"),
                _photo("dup", dhash=FULL_BITS, palette="pink"),
            ]
        )
        tag = Tag(id=1, name="樱花", category="auto")
        session.add(tag)
        session.add_all(
            [
                PhotoTag(photo_id="target", tag_id=1),
                PhotoTag(photo_id="similar", tag_id=1),
            ]
        )
        await session.commit()


@pytest.fixture()
def similar_app(tmp_path: Path):
    db_path = tmp_path / "similar.db"
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


def test_find_similar_filters_private_and_near_duplicates(similar_app) -> None:
    _client, session_factory = similar_app

    async def _run():
        async with session_factory() as session:
            target = await session.get(Photo, "target")
            hits = await find_similar_photos(session, target, limit=8)
            return [hit.photo.id for hit in hits]

    ids = asyncio.run(_run())
    assert "similar" in ids
    assert "pending" not in ids
    assert "hidden" not in ids
    assert "dup" not in ids


def test_similar_endpoint_returns_reasons(similar_app) -> None:
    client, _ = similar_app

    response = client.get("/api/v1/photos/target/similar?limit=5")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] >= 1
    first = data["items"][0]
    assert first["id"] == "similar"
    assert 0 <= first["similarity"] <= 1
    assert isinstance(first["reasons"], list) and first["reasons"]
    assert "uploader_student_id" in first and first["uploader_student_id"] is None


def test_similar_endpoint_404_for_unpublished_target(similar_app) -> None:
    client, _ = similar_app

    assert client.get("/api/v1/photos/pending/similar").status_code == 404
    assert client.get("/api/v1/photos/missing/similar").status_code == 404
