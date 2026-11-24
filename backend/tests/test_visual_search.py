"""以图搜图（上传图片找站内相似作品）测试。

覆盖：
1. 探针签名：字节 → dhash + 主色卡 + 尺寸，不落盘；
2. 拒绝：非图片、超大文件、过小图片给出可读错误；
3. HTTP 端点：匿名可上传、返回与文本检索同构的结果、带相似理由；
4. 候选过滤：pending / 人像敏感不出现，与探针近重复的作品不出现；
5. 探针图不写库（调用前后 photos 数量不变）。
"""
from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.search import limiter as search_limiter
from app.core import deps
from app.core.database import Base
from app.main import app
from app.models.photo import Photo
from app.models.tag import PhotoTag, Tag
from app.models.user import User
from app.services.visual_probe import (
    MAX_PROBE_BYTES,
    ProbeError,
    build_visual_probe,
)
from app.services.moderation_rules import dhash_from_bytes


def _png_bytes(width: int = 1200, height: int = 800, color=(240, 90, 140)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


PROBE_PNG = _png_bytes()
PROBE_DHASH = dhash_from_bytes(PROBE_PNG)
assert PROBE_DHASH is not None


def _complement(dhash: str) -> str:
    return "".join(f"{15 - int(ch, 16):x}" for ch in dhash)


def _photo(
    photo_id: str,
    *,
    dhash: str | None = None,
    palette: str | None = "pink",
    status: str = "approved",
    privacy: str = "normal",
) -> Photo:
    exif: dict = {}
    if dhash:
        exif["_dhash"] = dhash
    if palette:
        exif["_spectrum"] = {"palette": palette, "hex": "#e8628c", "ratio": 0.7}
    return Photo(
        id=photo_id,
        uploader_id="owner",
        filename=f"{photo_id}.jpg",
        title=f"作品 {photo_id}",
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        width=1200,
        height=800,
        file_size=200_000,
        mime_type="image/jpeg",
        season="Spring",
        campus="昌平校区",
        status=status,
        privacy_level=privacy,
        processing_status="completed",
        views=0,
        exif_data=exif,
        author="王海翔",
    )


@pytest.fixture()
def visual_search_env(tmp_path: Path):
    search_limiter.reset()
    db_path = tmp_path / "visual-search.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            db.add(
                User(
                    id="owner",
                    student_id="20260001",
                    username="jackwpp",
                    display_name="王海翔",
                    full_name="真实姓名",
                    hashed_password="x",
                    role="user",
                    is_active=True,
                )
            )
            db.add_all(
                [
                    _photo("similar", dhash=_complement(PROBE_DHASH)),
                    _photo("other-palette", dhash=_complement(PROBE_DHASH), palette="blue"),
                    _photo("pending", dhash=_complement(PROBE_DHASH), status="pending"),
                    _photo("hidden", dhash=_complement(PROBE_DHASH), privacy="sensitive"),
                    _photo("near-dup", dhash=PROBE_DHASH),
                ]
            )
            tag = Tag(id=1, name="樱花", category="auto")
            db.add(tag)
            db.add_all(
                [
                    PhotoTag(photo_id="similar", tag_id=1),
                    PhotoTag(photo_id="near-dup", tag_id=1),
                ]
            )
            await db.commit()

    asyncio.run(seed())

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_db
    client = TestClient(app)
    yield client, session_factory
    app.dependency_overrides.pop(deps.get_db, None)
    asyncio.run(engine.dispose())


def test_build_probe_extracts_signature() -> None:
    probe = build_visual_probe(PROBE_PNG)

    assert isinstance(probe.exif_data.get("_dhash"), str)
    assert len(probe.exif_data["_dhash"]) == 64  # type: ignore[arg-type]
    spectrum = probe.exif_data.get("_spectrum")
    assert isinstance(spectrum, dict) and spectrum.get("palette") == "pink"
    assert (probe.width, probe.height) == (1200, 800)
    assert probe.id.startswith("probe-")


def test_build_probe_rejects_invalid_and_oversized() -> None:
    with pytest.raises(ProbeError) as bad:
        build_visual_probe(b"definitely not an image")
    assert bad.value.status_code == 400

    with pytest.raises(ProbeError) as huge:
        build_visual_probe(b"x" * (MAX_PROBE_BYTES + 1))
    assert huge.value.status_code == 413

    with pytest.raises(ProbeError) as tiny:
        build_visual_probe(_png_bytes(width=48, height=48))
    assert tiny.value.status_code == 400


def test_visual_search_endpoint_returns_ranked_results(visual_search_env) -> None:
    client, _ = visual_search_env

    response = client.post(
        "/api/v1/search/visual",
        files={"file": ("probe.png", PROBE_PNG, "image/png")},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["mode"] == "visual"
    assert data["total"] == len(data["results"]) >= 1
    assert data["query"]["palette_name"] == "樱粉"
    assert data["query"]["width"] == 1200 and data["query"]["height"] == 800

    ids = [item["id"] for item in data["results"]]
    # 已发布、非敏感、非同图的作品才可被检索到
    assert "similar" in ids
    assert "pending" not in ids
    assert "hidden" not in ids
    assert "near-dup" not in ids

    first = next(item for item in data["results"] if item["id"] == "similar")
    assert 0.0 <= first["score"] <= 1.0
    assert first["match_reason"] and "色调" in first["match_reason"]
    assert first["thumb_url"] == "/api/v1/photos/similar/image/thumbnail"
    assert first["kind"] == "photo"
    assert "uploader_student_id" not in first


def test_visual_search_endpoint_rejects_bad_file(visual_search_env) -> None:
    client, _ = visual_search_env

    response = client.post(
        "/api/v1/search/visual",
        files={"file": ("broken.png", b"not-an-image", "image/png")},
    )

    assert response.status_code == 400
    assert "图片" in response.json()["detail"]


def test_visual_search_does_not_persist_probe(visual_search_env) -> None:
    client, session_factory = visual_search_env

    async def count_photos() -> int:
        async with session_factory() as session:
            return int(await session.scalar(select(func.count(Photo.id))) or 0)

    before = asyncio.run(count_photos())
    client.post(
        "/api/v1/search/visual",
        files={"file": ("probe.png", PROBE_PNG, "image/png")},
    )
    after = asyncio.run(count_photos())

    assert before == after == 5
