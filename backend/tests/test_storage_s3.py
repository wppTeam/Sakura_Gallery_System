"""S3 存储后端单元测试（不依赖真实对象存储）。

覆盖：上传对象的 Content-Type / Cache-Control 元数据、响应式变体 key 约定、
307 预签名跳转（而不是经 Python 转发字节）、下载语义的响应头与
ResponseContentDisposition。MinIO 全链路另见 scripts/verify_s3.py。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services import storage


class FakeClient:
    def __init__(self, presign_url: str = "http://minio.test/sakura-media/obj") -> None:
        self.presign_url = presign_url
        self.uploads: list[tuple[str, str, dict]] = []
        self.presigned: list[tuple[str, dict, int]] = []
        self.deleted: list[tuple[str, str]] = []

    def upload_file(self, filename, bucket, key, ExtraArgs=None):  # noqa: N803 - boto3 命名
        self.uploads.append((bucket, key, ExtraArgs or {}))

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803,N802
        self.presigned.append((operation, Params, ExpiresIn))
        return f"{self.presign_url}?X-Amz-Signature=fake&Key={Params.get('Key')}"

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.deleted.append((Bucket, Key))


@pytest.fixture()
def s3_backend(monkeypatch):
    fake_client = FakeClient()

    class FakeBoto3:
        @staticmethod
        def client(*args, **kwargs):
            return fake_client

    monkeypatch.setattr(storage, "boto3", FakeBoto3)
    monkeypatch.setattr(storage, "BotoConfig", lambda **kwargs: kwargs)
    s = get_settings()
    monkeypatch.setattr(s, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(s, "S3_ENDPOINT", "http://minio.test")
    monkeypatch.setattr(s, "S3_BUCKET", "sakura-media")
    monkeypatch.setattr(s, "S3_ACCESS_KEY", "test")
    monkeypatch.setattr(s, "S3_SECRET_KEY", "test")
    monkeypatch.setattr(s, "S3_REGION", "us-east-1")
    monkeypatch.setattr(s, "S3_USE_SSL", False)
    monkeypatch.setattr(s, "S3_PRESIGN_EXPIRE_SECONDS", 600)
    backend = storage.S3StorageBackend()
    return backend, fake_client


def _write(tmp_path: Path, name: str, content: bytes = b"x" * 64) -> str:
    path = tmp_path / name
    path.write_bytes(content)
    return str(path)


def test_s3_extra_args_content_type_and_cache() -> None:
    webp = storage._s3_extra_args("variants/abc_320.webp")
    assert webp["ContentType"] == "image/webp"
    assert webp["CacheControl"] == "public, max-age=31536000, immutable"

    jpeg = storage._s3_extra_args("thumbnails/abc_thumb.jpg")
    assert jpeg["ContentType"] == "image/jpeg"

    unknown = storage._s3_extra_args("originals/abc.raw")
    assert unknown["ContentType"] == "application/octet-stream"


def test_s3_persist_uploads_objects_with_metadata(s3_backend, tmp_path: Path) -> None:
    backend, fake = s3_backend
    original = _write(tmp_path, "src.jpg", b"o" * 100)
    thumb = _write(tmp_path, "thumb.jpg", b"t" * 80)
    compressed = _write(tmp_path, "compressed.jpg", b"c" * 90)
    variants = {
        320: {
            "width": 320,
            "height": 213,
            "webp": _write(tmp_path, "v320.webp"),
            "jpeg": _write(tmp_path, "v320.jpg"),
        },
    }

    media = backend.persist_photo_files(
        "photo-uuid",
        original,
        thumb,
        compressed,
        variants,
    )

    assert media.original_path == "originals/photo-uuid.jpg"
    assert media.thumb_path == "thumbnails/photo-uuid_thumb.jpg"
    assert media.compressed_path == "compressed/photo-uuid_compressed.jpg"
    assert media.variants["320"]["webp"] == "variants/photo-uuid_320.webp"
    assert media.variants["320"]["jpeg"] == "variants/photo-uuid_320.jpg"
    assert media.variants["320"]["width"] == 320

    uploaded = {key: extra for _bucket, key, extra in fake.uploads}
    assert set(uploaded) == {
        "originals/photo-uuid.jpg",
        "thumbnails/photo-uuid_thumb.jpg",
        "compressed/photo-uuid_compressed.jpg",
        "variants/photo-uuid_320.webp",
        "variants/photo-uuid_320.jpg",
    }
    assert uploaded["originals/photo-uuid.jpg"]["ContentType"] == "image/jpeg"
    assert uploaded["variants/photo-uuid_320.webp"]["ContentType"] == "image/webp"
    for extra in uploaded.values():
        assert extra["CacheControl"] == "public, max-age=31536000, immutable"


def test_s3_media_response_is_presigned_redirect(s3_backend) -> None:
    backend, fake = s3_backend

    response = backend.build_media_response("thumbnails/abc_thumb.jpg")

    assert response.status_code == 307
    location = response.headers["location"]
    assert "X-Amz-Signature=fake" in location
    assert "thumbnails/abc_thumb.jpg" in location
    # 预签名 URL 有 TTL，重定向本身只能短缓存
    assert response.headers["cache-control"] == "private, max-age=300"
    operation, params, expires = fake.presigned[0]
    assert operation == "get_object"
    assert params["Bucket"] == "sakura-media"
    assert params["Key"] == "thumbnails/abc_thumb.jpg"
    assert expires == 600
    assert "ResponseContentDisposition" not in params


def test_s3_download_presign_sets_content_disposition(s3_backend) -> None:
    backend, fake = s3_backend

    response = backend.build_media_response("originals/abc.jpg", download_name="樱花 01.jpg")

    assert response.status_code == 307
    assert response.headers["cache-control"] == "private, max-age=0, must-revalidate"
    _op, params, _expires = fake.presigned[0]
    disposition = params["ResponseContentDisposition"]
    # RFC 5987：中文文件名 URL 编码后放在 filename*
    assert disposition.startswith("attachment; filename*=UTF-8''")
    assert "%E6%A8%B1%E8%8A%B1" in disposition
