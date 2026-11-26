"""公开主页装修测试：自助公开身份 / 头像 / 创作者页 bio 与作品筛选。"""
import asyncio
import io
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, get_password_hash
from app.models.photo import Photo
from app.models.taxonomy import PhotoClassification, TaxonomyFacet, TaxonomyNode
from app.models.user import User


def _png_bytes(size=(64, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 60, 100)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def public_profile_env(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    Session = async_sessionmaker(engine, expire_on_commit=False)

    author = User(
        student_id="20260201", username="profile_author", display_name="装修作者",
        email="profile-author@example.com", hashed_password=get_password_hash("Sakura2026!"),
        role="user", is_active=True,
    )
    other = User(
        student_id="20260202", username="taken_name", display_name="占名同学",
        hashed_password=get_password_hash("Sakura2026!"), role="user", is_active=True,
    )

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with Session() as session:
            session.add_all([author, other])
            await session.flush()
            spring = Photo(
                uploader_id=author.id, title="春樱", filename="spring.jpg",
                original_path="originals/spring.jpg", thumb_path="thumbnails/spring.jpg",
                width=1200, height=800, file_size=1000, mime_type="image/jpeg",
                processing_status="completed",
                status="approved", season="spring", views=10,
            )
            winter = Photo(
                uploader_id=author.id, title="冬雪", filename="winter.jpg",
                original_path="originals/winter.jpg", thumb_path="thumbnails/winter.jpg",
                width=1200, height=800, file_size=1000, mime_type="image/jpeg",
                processing_status="completed",
                status="approved", season="winter", views=99,
            )
            pending = Photo(
                uploader_id=author.id, title="待审", filename="pending.jpg",
                original_path="originals/pending.jpg", thumb_path="thumbnails/pending.jpg",
                width=1200, height=800, file_size=1000, mime_type="image/jpeg",
                processing_status="completed",
                status="pending", season="spring",
            )
            session.add_all([spring, winter, pending])
            await session.flush()
            facet = TaxonomyFacet(
                key="season", name="季节", selection_mode="single",
                is_system=True, is_active=True, sort_order=1,
            )
            session.add(facet)
            await session.flush()
            spring_node = TaxonomyNode(facet_id=facet.id, key="spring", name="春季", is_active=True)
            winter_node = TaxonomyNode(facet_id=facet.id, key="winter", name="冬季", is_active=True)
            session.add_all([spring_node, winter_node])
            await session.flush()
            session.add_all([
                PhotoClassification(photo_id=spring.id, facet_id=facet.id, node_id=spring_node.id),
                PhotoClassification(photo_id=winter.id, facet_id=facet.id, node_id=winter_node.id),
            ])
            await session.commit()

    asyncio.run(_init())

    async def override_get_db():
        async with Session() as session:
            yield session

    from app.main import app
    app.dependency_overrides[get_db] = override_get_db

    yield {
        "client": TestClient(app),
        "token": create_access_token({"sub": "20260201"}),
        "author_id": author.id,
        "uploads": Path(settings.UPLOAD_DIR),
    }

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_update_public_identity(public_profile_env):
    env = public_profile_env
    client = env["client"]
    resp = client.put(
        "/api/v1/user/profile",
        json={"username": "new_handle", "display_name": "  新昵称  ", "bio": "  简介  "},
        headers=_headers(env["token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["username"] == "new_handle"
    assert body["display_name"] == "新昵称"
    assert body["bio"] == "简介"

    creator = client.get("/api/v1/creators/new_handle").json()
    assert creator["profile"]["bio"] == "简介"
    assert creator["profile"]["display_name"] == "新昵称"


def test_username_conflict_and_invalid(public_profile_env):
    env = public_profile_env
    client = env["client"]
    headers = _headers(env["token"])
    assert client.put(
        "/api/v1/user/profile", json={"username": "taken_name"}, headers=headers
    ).status_code == 400
    assert client.put(
        "/api/v1/user/profile", json={"username": "bad name!"}, headers=headers
    ).status_code == 422
    assert client.put(
        "/api/v1/user/profile", json={"username": "ab"}, headers=headers
    ).status_code == 422


def test_avatar_upload_serve_and_delete(public_profile_env):
    env = public_profile_env
    client = env["client"]
    headers = _headers(env["token"])
    resp = client.post(
        "/api/v1/user/avatar",
        files={"file": ("a.png", _png_bytes(), "image/png")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["avatar_path"] == f"avatars/{env['author_id']}.webp"
    assert (env["uploads"] / "avatars" / f"{env['author_id']}.webp").is_file()

    served = client.get(f"/api/v1/user/avatar/{env['author_id']}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"
    with Image.open(io.BytesIO(served.content)) as img:
        assert img.size == (512, 512)  # 居中裁方

    creator = client.get("/api/v1/creators/profile_author").json()
    assert creator["profile"]["avatar_url"] == f"/api/v1/user/avatar/{env['author_id']}"

    assert client.delete("/api/v1/user/avatar", headers=headers).status_code == 200
    assert not (env["uploads"] / "avatars" / f"{env['author_id']}.webp").exists()
    assert client.get(f"/api/v1/user/avatar/{env['author_id']}").status_code == 404


def test_avatar_rejects_non_image_and_requires_login(public_profile_env):
    env = public_profile_env
    client = env["client"]
    assert client.post(
        "/api/v1/user/avatar", files={"file": ("a.png", _png_bytes(), "image/png")}
    ).status_code == 401
    resp = client.post(
        "/api/v1/user/avatar",
        files={"file": ("a.txt", b"not an image", "text/plain")},
        headers=_headers(env["token"]),
    )
    assert resp.status_code == 400


def test_creator_works_filters_and_sort(public_profile_env):
    client = public_profile_env["client"]
    base = "/api/v1/creators/profile_author/works"
    assert client.get(base).json()["total"] == 2  # 待审不计
    assert client.get(base, params={"season": "spring"}).json()["total"] == 1
    popular = client.get(base, params={"sort": "popular"}).json()
    assert popular["items"][0]["title"] == "冬雪"
    oldest = client.get(base, params={"sort": "oldest"}).json()
    assert oldest["items"][0]["title"] == "春樱"
    first = client.get("/api/v1/creators/profile_author", params={"season": "winter"}).json()
    assert first["works"]["total"] == 1