"""robots.txt / sitemap.xml 回归测试。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.database import Base
from app.main import app
from app.models.collection import Collection, CollectionPhoto
from app.models.photo import Photo
from app.models.user import User


@pytest.fixture
def seo_env(tmp_path: Path, monkeypatch):
    import app.main as main_module

    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    monkeypatch.setattr(settings, "SITE_BASE_URL", "https://example.test")

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'seo.db').as_posix()}", future=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main_module, "AsyncSessionLocal", session_factory)

    async def seed() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            owner = User(
                student_id="20267701",
                email="seo@example.com",
                full_name="作者",
                username="seo_owner",
                role="user",
                is_active=True,
                hashed_password="x",
            )
            db.add(owner)
            await db.flush()
            photos = [
                Photo(
                    id="11111111-1111-1111-1111-111111111111",
                    uploader_id=owner.id,
                    filename="public.jpg",
                    title="公开作品",
                    status="approved",
                    privacy_level="normal",
                    original_path="originals/public.jpg",
                    width=100,
                    height=100,
                ),
                Photo(
                    id="22222222-2222-2222-2222-222222222222",
                    uploader_id=owner.id,
                    filename="sensitive.jpg",
                    title="敏感作品",
                    status="approved",
                    privacy_level="sensitive",
                    original_path="originals/sensitive.jpg",
                    width=100,
                    height=100,
                ),
                Photo(
                    id="33333333-3333-3333-3333-333333333333",
                    uploader_id=owner.id,
                    filename="pending.jpg",
                    title="待审作品",
                    status="pending",
                    privacy_level="normal",
                    original_path="originals/pending.jpg",
                    width=100,
                    height=100,
                ),
            ]
            db.add_all(photos)
            await db.flush()
            published = Collection(slug="seo-published", title="公开专题", status="published", visibility="public")
            draft = Collection(slug="seo-draft", title="草稿专题", status="draft", visibility="public")
            db.add_all([published, draft])
            await db.flush()
            db.add(CollectionPhoto(collection_id=published.id, photo_id=photos[0].id, position=0))
            await db.commit()

    asyncio.run(seed())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_robots_points_to_sitemap(seo_env: TestClient):
    resp = seo_env.get("/robots.txt")
    assert resp.status_code == 200
    text = resp.text
    assert "Disallow: /admin" in text
    assert "Sitemap: https://example.test/sitemap.xml" in text


def test_sitemap_filters_private_and_pending(seo_env: TestClient):
    resp = seo_env.get("/sitemap.xml")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    body = resp.text
    assert "https://example.test/" in body
    assert "https://example.test/explore" in body
    assert "11111111-1111-1111-1111-111111111111" in body
    assert "22222222-2222-2222-2222-222222222222" not in body  # 敏感作品不收录
    assert "33333333-3333-3333-3333-333333333333" not in body  # 待审不收录
    assert "seo-published" in body
    assert "seo-draft" not in body
    # 创作者主页：有公开作品的账号被收录
    assert "https://example.test/u/seo_owner" in body


def test_sitemap_includes_image_entries(seo_env: TestClient):
    """图片 sitemap 扩展：公开作品带 image:loc/title，敏感作品不出现。"""
    body = seo_env.get("/sitemap.xml").text
    assert 'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"' in body
    assert "<image:image>" in body
    assert "<image:loc>https://example.test/api/v1/photos/11111111-1111-1111-1111-111111111111/image/compressed</image:loc>" in body
    assert "<image:title>公开作品</image:title>" in body
    assert "22222222-2222-2222-2222-222222222222" not in body


# ---------------------------------------------------------------------------
# 分享卡（og 标签）：nginx 按 UA 把 /photo/{id}、/collections/{slug} 转发到这里
# ---------------------------------------------------------------------------

def test_share_photo_page_has_og_tags(seo_env: TestClient):
    resp = seo_env.get("/api/v1/share/photo/11111111-1111-1111-1111-111111111111")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert '<meta property="og:title" content="公开作品">' in body
    assert (
        '<meta property="og:image" '
        'content="https://example.test/api/v1/photos/11111111-1111-1111-1111-111111111111/image/compressed">'
    ) in body
    assert '<meta property="og:url" content="https://example.test/photo/11111111-1111-1111-1111-111111111111">' in body
    assert '<meta name="twitter:card" content="summary_large_image">' in body
    assert "cache-control" in {k.lower() for k in resp.headers}


def test_share_photo_page_hides_sensitive_pending_and_unknown(seo_env: TestClient):
    for photo_id in (
        "22222222-2222-2222-2222-222222222222",  # sensitive
        "33333333-3333-3333-3333-333333333333",  # pending
        "99999999-9999-9999-9999-999999999999",  # 不存在
    ):
        resp = seo_env.get(f"/api/v1/share/photo/{photo_id}")
        assert resp.status_code == 404, photo_id
        assert "og:image" not in resp.text  # 404 页不泄露图片


def test_share_collection_page(seo_env: TestClient):
    resp = seo_env.get("/api/v1/share/collection/seo-published")
    assert resp.status_code == 200
    body = resp.text
    assert '<meta property="og:title" content="公开专题">' in body
    assert (
        '<meta property="og:image" '
        'content="https://example.test/api/v1/photos/11111111-1111-1111-1111-111111111111/image/compressed">'
    ) in body
    assert "/collections/seo-published" in body

    draft = seo_env.get("/api/v1/share/collection/seo-draft")
    assert draft.status_code == 404

    unknown = seo_env.get("/api/v1/share/collection/does-not-exist")
    assert unknown.status_code == 404
