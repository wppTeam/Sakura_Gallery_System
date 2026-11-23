"""响应式图变体（320/640/1080/1600/2400，WebP+JPEG）与 username 登录测试。

覆盖：
1. 本地存储后端把上传期生成的变体落盘到 ``uploads/variants/{id}_{size}.{ext}``；
2. 真实上传端点生成变体，公开响应 ``variants`` 给出各档 URL；
3. ``GET /photos/{id}/image/variant/{size}`` 返回变体并带长缓存头；
4. 老图（无 ``_variants`` 元信息）走 thumbnail 兜底，不 404；
5. 登录支持 ``users.username``（AIGC 演示账号 jackwpp 之类）。
"""
from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.database import Base
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import User
from app.services import storage as storage_module


def _jpeg_bytes(width: int = 900, height: int = 600, color: str = "pink") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def variants_client(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    monkeypatch.setattr(settings, "UPLOAD_GENERATE_VARIANTS", True)

    uploads = tmp_path / "uploads"
    for sub in ("originals", "thumbnails", "compressed", "variants"):
        (uploads / sub).mkdir(parents=True, exist_ok=True)

    db_path = tmp_path / "variants.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(
                User(
                    id="variants-owner",
                    student_id="20260099",
                    email="variants@buct.edu.cn",
                    username="variants_owner",
                    display_name="变体测试",
                    hashed_password=get_password_hash("password123"),
                    full_name="变体测试",
                    role="user",
                    is_active=True,
                )
            )
            await session.commit()

    asyncio.run(init_database())

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    token = create_access_token({"sub": "20260099"})

    with TestClient(app) as client:
        yield client, {"token": token, "uploads": uploads, "session_factory": session_factory}

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 存储后端
# ---------------------------------------------------------------------------

def test_persist_photo_files_moves_variants(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "UPLOAD_DIR", str(tmp_path / "uploads"))
    for sub in ("originals", "thumbnails", "compressed", "variants"):
        (tmp_path / "uploads" / sub).mkdir(parents=True, exist_ok=True)

    staged = tmp_path / "staged"
    staged.mkdir()
    original = staged / "abc.jpg"
    original.write_bytes(_jpeg_bytes())
    thumb = staged / "abc_thumb.jpg"
    thumb.write_bytes(_jpeg_bytes(320, 213))
    compressed = staged / "abc_compressed.jpg"
    compressed.write_bytes(_jpeg_bytes(640, 427))

    variants_src = {}
    for size in (320, 640):
        webp = staged / f"abc_{size}.webp"
        jpg = staged / f"abc_{size}.jpg"
        webp.write_bytes(b"RIFFxxxxWEBP")
        jpg.write_bytes(_jpeg_bytes(size, int(size * 2 / 3)))
        variants_src[size] = {
            "width": size,
            "height": int(size * 2 / 3),
            "webp": str(webp),
            "jpeg": str(jpg),
        }

    backend = storage_module.LocalStorageBackend()
    media = backend.persist_photo_files(
        "abc", str(original), str(thumb), str(compressed), variants_src
    )

    assert set(media.variants) == {"320", "640"}
    for size in ("320", "640"):
        entry = media.variants[size]
        assert Path(tmp_path / "uploads" / entry["webp"]).exists()
        assert Path(tmp_path / "uploads" / entry["jpeg"]).exists()
        assert entry["width"] == int(size)
    assert Path(tmp_path / "uploads" / media.thumb_path).exists()


# ---------------------------------------------------------------------------
# 上传端点 → 公开响应 → 变体媒体端点
# ---------------------------------------------------------------------------

def test_upload_creates_variants_and_exposes_urls(variants_client):
    client, data = variants_client
    token = data["token"]
    response = client.post(
        "/api/v1/photos/upload",
        headers=_auth(token),
        files={"file": ("variant-test.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"title": "变体测试图", "enable_ai": "false", "aigc_declared": "false"},
    )
    assert response.status_code == 201, response.text
    photo_id = response.json()["id"]

    detail = client.get(f"/api/v1/photos/{photo_id}", headers=_auth(token))
    assert detail.status_code == 200, detail.text
    variants = detail.json().get("variants")
    assert variants, "公开响应应带 variants 各档 URL"
    # 900px 原图：只应有 <= 900 的档位（320/640），绝不放大
    assert set(variants) == {"320", "640"}
    assert variants["320"]["width"] == 320
    assert variants["320"]["webp"].startswith(f"/api/v1/photos/{photo_id}/image/variant/320")

    # 变体端点返回真实 WebP，并保留长缓存头
    media = client.get(variants["320"]["webp"], headers=_auth(token))
    assert media.status_code == 200
    assert media.headers.get("cache-control") == "public, max-age=31536000, immutable"
    assert media.headers.get("content-type", "").startswith("image/webp")

    jpeg_media = client.get(variants["320"]["jpeg"], headers=_auth(token))
    assert jpeg_media.status_code == 200
    assert jpeg_media.headers.get("content-type", "").startswith("image/jpeg")


def test_variant_endpoint_falls_back_for_legacy_photo(variants_client):
    client, data = variants_client
    token = data["token"]
    uploads = data["uploads"]

    # 模拟历史数据：有 thumb 但没有 _variants 元信息
    (uploads / "originals" / "legacy.jpg").write_bytes(_jpeg_bytes())
    (uploads / "thumbnails" / "legacy_thumb.jpg").write_bytes(_jpeg_bytes(320, 213))

    from app.models import Photo

    async def insert_photo() -> None:
        async with data["session_factory"]() as session:
            session.add(
                Photo(
                    id="legacy-work",
                    uploader_id="variants-owner",
                    filename="legacy.jpg",
                    original_path="originals/legacy.jpg",
                    thumb_path="thumbnails/legacy_thumb.jpg",
                    width=900,
                    height=600,
                    status="approved",
                    processing_status="completed",
                    views=0,
                )
            )
            await session.commit()

    asyncio.run(insert_photo())

    fallback = client.get("/api/v1/photos/legacy-work/image/variant/1080")
    assert fallback.status_code == 200, fallback.text
    assert fallback.headers.get("cache-control") == "public, max-age=31536000, immutable"


# ---------------------------------------------------------------------------
# username 登录
# ---------------------------------------------------------------------------

def test_login_with_username(variants_client):
    client, _data = variants_client
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "variants_owner", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["user"]["username"] == "variants_owner"


def test_login_with_unknown_identifier_fails(variants_client):
    client, _data = variants_client
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "no-such-user", "password": "password123"},
    )
    assert response.status_code == 401
    assert "用户名" in response.json()["detail"]


def test_upload_semaphore_per_loop() -> None:
    """上传处理信号量按事件循环隔离、取 settings 的并发上限。"""
    import asyncio

    from app.api.v1.endpoints import photos as photos_module

    async def check() -> None:
        sem_one = photos_module._get_upload_semaphore()
        sem_two = photos_module._get_upload_semaphore()
        assert sem_one is sem_two
        assert sem_one._value == max(1, photos_module.settings.UPLOAD_PROCESS_CONCURRENCY)

    asyncio.run(check())
    # 新事件循环拿到新的信号量（不会复用已绑定的旧实例）
    asyncio.run(check())
