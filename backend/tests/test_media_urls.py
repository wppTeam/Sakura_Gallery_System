"""公开响应内联媒体直链（对象存储预签名）的回归测试。

第 43 轮性能优化：公网经 Cloudflare Tunnel 时，每张图先请求一次 API 拿 307
再到对象存储，单张图要多一次 1–3 秒的隧道往返。列表/详情/检索结果里直接内联
预签名直链后，浏览器可以直连对象存储。这里锁定「对象存储模式给直链、本地模式
回退同源相对路径」的行为。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

from app.api.v1.endpoints import photos as photos_endpoint
from app.api.v1.endpoints import search as search_endpoint
from app.services import storage as storage_service

settings = storage_service.settings


class _FakePresignBackend:
    def presign_url(self, file_path: str, *, content_type=None, expires_in=None) -> str:
        return f"https://cos.example.com/{file_path}?signature=fake"


def test_public_variants_use_presigned_urls_when_available(monkeypatch) -> None:
    def fake_direct(file_path: Optional[str], *, content_type=None, expires_in=None):
        if not file_path:
            return None
        return f"https://cos.example.com/{file_path}?_sig=fake"

    monkeypatch.setattr(photos_endpoint, "direct_media_url", fake_direct)
    photo = SimpleNamespace(
        id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        exif_data={"_variants": {"640": {"width": 640, "height": 427}}},
    )

    variants = photos_endpoint._public_variants(photo)

    assert variants is not None
    entry = variants["640"]
    assert entry["webp"].startswith("https://cos.example.com/variants/")
    assert entry["webp"].endswith(".webp?_sig=fake")
    assert entry["jpeg"].startswith("https://cos.example.com/variants/")
    assert entry["width"] == 640 and entry["height"] == 427


def test_public_variants_fall_back_to_api_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        photos_endpoint, "direct_media_url", lambda *args, **kwargs: None
    )
    photo = SimpleNamespace(
        id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        exif_data={"_variants": {"640": {"width": 640, "height": 427}}},
    )

    entry = photos_endpoint._public_variants(photo)["640"]

    assert entry["webp"] == "/api/v1/photos/a1b2c3d4-e5f6-7890-abcd-ef1234567890/image/variant/640?format=webp"
    assert entry["jpeg"].endswith("/image/variant/640?format=jpeg")


def test_photo_common_dict_inlines_thumb_and_compressed_urls(monkeypatch) -> None:
    def fake_direct(file_path: Optional[str], *, content_type=None, expires_in=None):
        return f"https://cos.example.com/{file_path}" if file_path else None

    monkeypatch.setattr(photos_endpoint, "direct_media_url", fake_direct)
    photo = SimpleNamespace(
        id="p1",
        filename="p1.jpg",
        title="标题",
        author="作者",
        description="描述",
        uploader_id="u1",
        original_path="originals/p1.jpg",
        processed_path=None,
        thumb_path="thumbnails/p1_thumb.jpg",
        compressed_path="compressed/p1_comp.jpg",
        redacted_path=None,
        redacted_thumb_path=None,
        width=1200,
        height=800,
        file_size=1,
        mime_type="image/jpeg",
        season=None,
        category=None,
        campus=None,
        captured_at=None,
        status="approved",
        processing_status="completed",
        created_at=None,
        updated_at=None,
        exif_data={},
        is_aigc=False,
        kind="photo",
        aigc_label=None,
        aigc_meta=None,
        label_written=False,
        privacy_level="normal",
        views=0,
        downloads=0,
    )

    data = photos_endpoint._photo_common_dict(photo)

    assert data["thumb_url"] == "https://cos.example.com/thumbnails/p1_thumb.jpg"
    assert data["compressed_url"] == "https://cos.example.com/compressed/p1_comp.jpg"
    # 原图不内联直链：官方下载端点要写 AIGC 隐式标识，公开 JSON 不鼓励直接存原图
    assert "original_url" not in data


def test_search_thumb_url_prefers_presigned(monkeypatch) -> None:
    def fake_direct(file_path: Optional[str], *, content_type=None, expires_in=None):
        return f"https://cos.example.com/{file_path}" if file_path else None

    monkeypatch.setattr(search_endpoint, "direct_media_url", fake_direct)
    hit = SimpleNamespace(
        photo_id="p9",
        width=1200,
        height=800,
        is_aigc=False,
        tags=[],
        classifications={},
        matched_fields=["title"],
        match_reason="标题匹配",
        title="t",
        filename="f",
        author="a",
        season=None,
        category=None,
        campus=None,
        aigc_label=None,
        blurhash=None,
        created_at=None,
        published_at=None,
        score=0.9,
    )

    item = search_endpoint._to_result_item(hit)

    assert item.thumb_url == "https://cos.example.com/thumbnails/p9_thumb.jpg"


def test_direct_media_url_disabled_for_local_storage(monkeypatch) -> None:
    monkeypatch.setattr(storage_service.settings, "STORAGE_BACKEND", "local")
    assert storage_service.direct_media_url("thumbnails/p1_thumb.jpg") is None


def test_direct_media_url_presigns_for_s3(monkeypatch) -> None:
    monkeypatch.setattr(storage_service.settings, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(
        storage_service, "_direct_media_backend", lambda: _FakePresignBackend()
    )

    url = storage_service.direct_media_url("variants/p1_640.webp", content_type="image/webp")

    assert url == "https://cos.example.com/variants/p1_640.webp?signature=fake"
