"""人像隐私分级（sensitive + 脱敏图）测试。

覆盖：
1. 公共列表默认排除 sensitive 作品；``include_sensitive=true`` 时登录用户才可见；
2. 匿名访问 sensitive 详情 → 404；登录用户看到脱敏图；作者/管理员看到原图；
3. 媒体端点：非作者/非审核员的 thumbnail 给脱敏图、original 403；作者正常；
4. ``privacy.mark_photo_sensitive`` 会生成并落盘脱敏图（真实 Pillow 处理）。
"""
from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.config import get_settings
from app.core.database import Base
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import Photo, User
from app.services import privacy


def _jpeg_bytes(width: int = 240, height: int = 160, color: str = "pink") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _write_jpeg(path: Path, color: str = "pink") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_jpeg_bytes(color=color))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def privacy_env(tmp_path: Path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)

    uploads = tmp_path / "uploads"
    for sub in ("originals", "thumbnails", "compressed", "variants", "redacted"):
        (uploads / sub).mkdir(parents=True, exist_ok=True)
    _write_jpeg(uploads / "originals" / "normal-orig.jpg", "pink")
    _write_jpeg(uploads / "thumbnails" / "normal-thumb.jpg", "pink")
    _write_jpeg(uploads / "originals" / "sens-orig.jpg", "pink")
    _write_jpeg(uploads / "thumbnails" / "sens-thumb.jpg", "pink")
    _write_jpeg(uploads / "redacted" / "sens_redacted.jpg", "gray")
    _write_jpeg(uploads / "redacted" / "sens_redacted_thumb.jpg", "gray")

    db_path = tmp_path / "privacy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            owner = User(
                id="privacy-owner",
                student_id="20260011",
                email="owner@buct.edu.cn",
                username="privacy_owner",
                display_name="作者",
                hashed_password=get_password_hash("password123"),
                full_name="作者",
                role="user",
                is_active=True,
            )
            viewer = User(
                id="privacy-viewer",
                student_id="20260012",
                email="viewer@buct.edu.cn",
                username="privacy_viewer",
                display_name="访客",
                hashed_password=get_password_hash("password123"),
                full_name="访客",
                role="user",
                is_active=True,
            )
            admin = User(
                id="privacy-admin",
                student_id="20260013",
                email="admin@buct.edu.cn",
                username="privacy_admin",
                display_name="管理员",
                hashed_password=get_password_hash("password123"),
                full_name="管理员",
                role="admin",
                is_active=True,
            )
            session.add_all([owner, viewer, admin])
            session.add_all(
                [
                    Photo(
                        id="normal-photo",
                        uploader_id=owner.id,
                        filename="normal.jpg",
                        title="普通风景",
                        original_path="originals/normal-orig.jpg",
                        thumb_path="thumbnails/normal-thumb.jpg",
                        compressed_path="thumbnails/normal-thumb.jpg",
                        status="approved",
                        privacy_level="normal",
                        width=240,
                        height=160,
                    ),
                    Photo(
                        id="sensitive-photo",
                        uploader_id=owner.id,
                        filename="portrait.jpg",
                        title="人像作品",
                        original_path="originals/sens-orig.jpg",
                        thumb_path="thumbnails/sens-thumb.jpg",
                        compressed_path="thumbnails/sens-thumb.jpg",
                        status="approved",
                        privacy_level="sensitive",
                        redacted_path="redacted/sens_redacted.jpg",
                        redacted_thumb_path="redacted/sens_redacted_thumb.jpg",
                        width=240,
                        height=160,
                    ),
                ]
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
    with TestClient(app) as client:
        yield {
            "client": client,
            "owner_token": create_access_token({"sub": "20260011"}),
            "viewer_token": create_access_token({"sub": "20260012"}),
            "admin_token": create_access_token({"sub": "20260013"}),
            "session_factory": session_factory,
            "uploads": uploads,
        }
    app.dependency_overrides.clear()


def test_public_list_excludes_sensitive_by_default(privacy_env):
    client = privacy_env["client"]
    resp = client.get("/api/v1/photos/public?limit=20")
    assert resp.status_code == 200
    data = resp.json()
    ids = [item["id"] for item in data["items"]]
    assert "normal-photo" in ids
    assert "sensitive-photo" not in ids


def test_include_sensitive_requires_login(privacy_env):
    client = privacy_env["client"]
    anonymous = client.get("/api/v1/photos/public?limit=20&include_sensitive=true")
    assert anonymous.status_code == 200
    assert "sensitive-photo" not in [item["id"] for item in anonymous.json()["items"]]

    logged_in = client.get(
        "/api/v1/photos/public?limit=20&include_sensitive=true",
        headers=_auth(privacy_env["viewer_token"]),
    )
    assert logged_in.status_code == 200
    item = next(i for i in logged_in.json()["items"] if i["id"] == "sensitive-photo")
    assert item["privacy_level"] == "sensitive"
    assert item["is_redacted"] is True
    assert item["thumb_path"] == "redacted/sens_redacted_thumb.jpg"
    assert item["variants"] is None


def test_sensitive_detail_anonymous_404_and_viewer_redacted(privacy_env):
    client = privacy_env["client"]
    assert client.get("/api/v1/photos/public/sensitive-photo").status_code == 404

    viewer = client.get(
        "/api/v1/photos/public/sensitive-photo",
        headers=_auth(privacy_env["viewer_token"]),
    )
    assert viewer.status_code == 200
    payload = viewer.json()
    assert payload["is_redacted"] is True
    assert payload["thumb_path"] == "redacted/sens_redacted_thumb.jpg"

    owner = client.get(
        "/api/v1/photos/public/sensitive-photo",
        headers=_auth(privacy_env["owner_token"]),
    )
    assert owner.status_code == 200
    assert owner.json()["is_redacted"] is False
    assert owner.json()["thumb_path"] == "thumbnails/sens-thumb.jpg"

    admin = client.get(
        "/api/v1/photos/public/sensitive-photo",
        headers=_auth(privacy_env["admin_token"]),
    )
    assert admin.status_code == 200
    assert admin.json()["is_redacted"] is False


def test_sensitive_media_serves_redacted_and_blocks_original(privacy_env):
    client = privacy_env["client"]
    viewer_headers = _auth(privacy_env["viewer_token"])

    thumb = client.get(
        "/api/v1/photos/sensitive-photo/image/thumbnail", headers=viewer_headers
    )
    assert thumb.status_code == 200
    assert thumb.headers["content-type"].startswith("image/")

    original = client.get(
        "/api/v1/photos/sensitive-photo/image/original", headers=viewer_headers
    )
    assert original.status_code == 403

    owner_original = client.get(
        "/api/v1/photos/sensitive-photo/image/original",
        headers=_auth(privacy_env["owner_token"]),
    )
    assert owner_original.status_code == 200


def test_mark_photo_sensitive_generates_redacted_files(privacy_env):
    session_factory = privacy_env["session_factory"]
    uploads = privacy_env["uploads"]

    async def run() -> dict[str, str | None]:
        async with session_factory() as session:
            photo = (
                await session.execute(select(Photo).where(Photo.id == "normal-photo"))
            ).scalar_one()
            ok = await privacy.mark_photo_sensitive(
                session, photo, reason="test.person"
            )
            assert ok is True
            await session.commit()
            return {
                "privacy_level": photo.privacy_level,
                "redacted_path": photo.redacted_path,
                "redacted_thumb_path": photo.redacted_thumb_path,
            }

    result = asyncio.run(run())
    assert result["privacy_level"] == "sensitive"
    assert result["redacted_path"] and result["redacted_thumb_path"]
    assert (uploads / result["redacted_path"]).exists()
    assert (uploads / result["redacted_thumb_path"]).exists()
