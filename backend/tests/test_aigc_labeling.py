"""AIGC 法定标识（《人工智能生成合成内容标识办法》）测试。

覆盖四件套中的可自动化部分：
1. 上传强制声明（缺省 400、声明 false/true 两条路径、图生图/换脸 consent 校验）；
2. 显式标识数据链路（公开响应 is_aigc/kind/aigc_label/aigc_meta，prompt 按授权公开）；
3. 下载文件隐式标识（JPEG/PNG 写 XMP、响应头、label_written 落库、非 AIGC 不变）；
4. 审核 tier 下限（声明 AIGC ≥L1，图生图/换脸 → L2）。
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
from app.core.database import Base
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import Photo, User
from app.services import aigc_labeling
from app.services.moderation import _apply_aigc_declaration_policy


def _image_bytes(fmt: str = "JPEG", color: str = "white") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buffer, format=fmt)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# 单元：XMP 构造与写入
# ---------------------------------------------------------------------------

class _FakeUploader:
    username = "jackwpp"
    display_name = "王海翔"


class _FakePhoto:
    id = "work-123"
    aigc_label = "AI 生成"
    author = "王海翔"
    uploader = _FakeUploader()
    aigc_meta = {
        "model": "qwen-image-3.0-pro",
        "provider": "阿里云百炼",
        "prompt": "樱花下的校园",
        "prompt_public": True,
        "source_work_id": None,
        "face_swap": False,
    }


def test_build_xmp_packet_contains_required_fields():
    packet = aigc_labeling.build_xmp_packet(_FakePhoto())

    assert "<sakura:IsAIGC>true</sakura:IsAIGC>" in packet
    assert "sakura:work:work-123" in packet
    assert "qwen-image-3.0-pro" in packet
    assert "樱花下的校园" in packet
    assert "王海翔" in packet
    assert "AI 生成" in packet


def test_build_xmp_packet_hides_private_prompt():
    photo = _FakePhoto()
    photo.aigc_meta = {**photo.aigc_meta, "prompt_public": False}
    packet = aigc_labeling.build_xmp_packet(photo)

    assert "<sakura:Prompt>" not in packet
    assert "樱花下的校园" not in packet


def test_embed_jpeg_inser_and_replace_is_stable():
    data = _image_bytes("JPEG")
    packet = aigc_labeling.build_xmp_packet(_FakePhoto()).encode("utf-8")

    labeled = aigc_labeling.embed_aigc_label(data, "image/jpeg", packet)
    assert labeled is not None
    assert labeled.startswith(b"\xff\xd8")
    assert aigc_labeling.has_aigc_xmp(labeled)
    assert Image.open(io.BytesIO(labeled)).size == (64, 64)

    # 二次写入（下载重复触发）不应无限膨胀：替换同一段 XMP
    labeled_twice = aigc_labeling.embed_aigc_label(labeled, "image/jpeg", packet)
    assert labeled_twice is not None
    assert aigc_labeling.has_aigc_xmp(labeled_twice)
    assert abs(len(labeled_twice) - len(labeled)) <= 8


def test_embed_png_writes_xmp_itxt():
    data = _image_bytes("PNG")
    packet = aigc_labeling.build_xmp_packet(_FakePhoto()).encode("utf-8")

    labeled = aigc_labeling.embed_aigc_label(data, "image/png", packet)
    assert labeled is not None
    assert labeled.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"XML:com.adobe.xmp" in labeled
    assert aigc_labeling.has_aigc_xmp(labeled)
    assert Image.open(io.BytesIO(labeled)).size == (64, 64)


def test_embed_webp_inserts_xmp_chunk():
    """WebP 走 RIFF `XMP ` chunk；二次写入稳定、Pillow 仍可解码。"""
    data = _image_bytes("WEBP")
    packet = aigc_labeling.build_xmp_packet(_FakePhoto()).encode("utf-8")

    labeled = aigc_labeling.embed_aigc_label(data, "image/webp", packet)
    assert labeled is not None
    assert labeled[:4] == b"RIFF"
    assert labeled[8:12] == b"WEBP"
    assert b"XMP " in labeled
    assert aigc_labeling.has_aigc_xmp(labeled)
    assert Image.open(io.BytesIO(labeled)).size == (64, 64)

    labeled_twice = aigc_labeling.embed_aigc_label(labeled, "image/webp", packet)
    assert labeled_twice is not None
    assert len(labeled_twice) == len(labeled)  # 替换而非追加
    assert labeled_twice.count(b"XMP ") >= 1


def test_embed_unsupported_format_returns_none():
    gif = _image_bytes("GIF")
    packet = aigc_labeling.build_xmp_packet(_FakePhoto()).encode("utf-8")

    assert aigc_labeling.embed_aigc_label(gif, "image/gif", packet) is None


# ---------------------------------------------------------------------------
# 单元：审核 tier 下限
# ---------------------------------------------------------------------------

def test_moderation_policy_floors_declared_aigc_to_l1():
    photo = _FakePhoto()
    photo.is_aigc = True
    photo.aigc_meta = {"face_swap": False, "source_work_id": None}

    assert _apply_aigc_declaration_policy(photo, "L0") == "L1"


def test_moderation_policy_forces_img2img_and_face_swap_to_l2():
    photo = _FakePhoto()
    photo.is_aigc = True
    photo.aigc_meta = {"source_work_id": "other-work"}
    assert _apply_aigc_declaration_policy(photo, "L0") == "L2"

    photo.aigc_meta = {"face_swap": True}
    assert _apply_aigc_declaration_policy(photo, "L1") == "L2"


def test_moderation_policy_keeps_non_aigc_untouched():
    class _PlainPhoto:
        is_aigc = False
        aigc_meta = None

    assert _apply_aigc_declaration_policy(_PlainPhoto(), "L0") == "L0"


# ---------------------------------------------------------------------------
# 集成：上传声明 / 公开序列化 / 下载隐式标识
# ---------------------------------------------------------------------------

@pytest.fixture
def aigc_client(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(get_settings(), "AI_ENABLED", False)
    # 上传后 enqueue_moderation 会用全局 session/engine 跑后台审核，与 fixture 的临时库不一致；
    # 审核链路本身由 test_moderation_* 覆盖，这里只测 AIGC 标识。
    monkeypatch.setattr(get_settings(), "MODERATION_ENABLED", False)

    db_path = tmp_path / "aigc.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    uploads_dir = tmp_path / "uploads"
    originals = uploads_dir / "originals"
    thumbnails = uploads_dir / "thumbnails"
    compressed = uploads_dir / "compressed"
    for directory in (originals, thumbnails, compressed):
        directory.mkdir(parents=True, exist_ok=True)

    aigc_original = originals / "aigc-work.jpg"
    plain_original = originals / "plain-work.jpg"
    aigc_original.write_bytes(_image_bytes("JPEG", "pink"))
    plain_original.write_bytes(_image_bytes("JPEG", "white"))
    (thumbnails / "aigc-work.jpg").write_bytes(_image_bytes("JPEG", "pink"))
    (thumbnails / "plain-work.jpg").write_bytes(_image_bytes("JPEG", "white"))

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            owner = User(
                id="aigc-owner",
                student_id="20260011",
                email="aigc@buct.edu.cn",
                username="jackwpp",
                display_name="王海翔",
                hashed_password=get_password_hash("password123"),
                full_name="王海翔",
                role="user",
                is_active=True,
            )
            session.add(owner)
            session.add_all([
                Photo(
                    id="aigc-work",
                    uploader_id=owner.id,
                    filename="aigc-work.jpg",
                    original_path="originals/aigc-work.jpg",
                    thumb_path="thumbnails/aigc-work.jpg",
                    width=64,
                    height=64,
                    file_size=aigc_original.stat().st_size,
                    mime_type="image/jpeg",
                    status="approved",
                    processing_status="completed",
                    is_aigc=True,
                    aigc_label="AI 生成",
                    aigc_meta={
                        "model": "qwen-image-3.0-pro",
                        "provider": "阿里云百炼",
                        "prompt": "樱花下的校园",
                        "prompt_public": False,
                        "face_swap": False,
                    },
                    views=0,
                ),
                Photo(
                    id="plain-work",
                    uploader_id=owner.id,
                    filename="plain-work.jpg",
                    original_path="originals/plain-work.jpg",
                    thumb_path="thumbnails/plain-work.jpg",
                    width=64,
                    height=64,
                    file_size=plain_original.stat().st_size,
                    mime_type="image/jpeg",
                    status="approved",
                    processing_status="completed",
                    is_aigc=False,
                    views=0,
                ),
            ])
            await session.commit()

    asyncio.run(init_database())

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    token = create_access_token({"sub": "20260011"})

    with TestClient(app) as client:
        yield client, {"token": token, "session_factory": session_factory}

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_upload_requires_aigc_declaration(aigc_client):
    client, data = aigc_client
    files = {"file": ("new.jpg", _image_bytes(), "image/jpeg")}

    response = client.post("/api/v1/photos/upload", files=files, headers=_auth(data["token"]))

    assert response.status_code == 400
    assert "声明" in response.json()["detail"]


def test_upload_plain_photo_declaration_false(aigc_client):
    client, data = aigc_client
    files = {"file": ("plain-new.jpg", _image_bytes(), "image/jpeg")}

    response = client.post(
        "/api/v1/photos/upload",
        files=files,
        data={"aigc_declared": "false"},
        headers=_auth(data["token"]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["is_aigc"] is False
    assert body["aigc_label"] is None


def test_upload_aigc_declaration_records_meta(aigc_client):
    client, data = aigc_client
    files = {"file": ("aigc-new.jpg", _image_bytes("JPEG", "pink"), "image/jpeg")}

    response = client.post(
        "/api/v1/photos/upload",
        files=files,
        data={
            "aigc_declared": "true",
            "aigc_model": "qwen-image-3.0-pro",
            "aigc_provider": "阿里云百炼",
            "aigc_prompt": "樱花下的校园少女",
            "aigc_prompt_public": "true",
        },
        headers=_auth(data["token"]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["is_aigc"] is True
    assert body["aigc_label"] == "AI 生成"

    photo = client.get(f"/api/v1/photos/{body['id']}", headers=_auth(data["token"])).json()
    assert photo["is_aigc"] is True
    assert photo["kind"] == "aigc"
    assert photo["aigc_meta"]["model"] == "qwen-image-3.0-pro"
    assert photo["aigc_meta"]["prompt"] == "樱花下的校园少女"


def test_upload_img2img_requires_consent(aigc_client):
    client, data = aigc_client
    files = {"file": ("img2img.jpg", _image_bytes("JPEG", "blue"), "image/jpeg")}

    rejected = client.post(
        "/api/v1/photos/upload",
        files=files,
        data={"aigc_declared": "true", "aigc_source_work_id": "other-work"},
        headers=_auth(data["token"]),
    )
    assert rejected.status_code == 400
    assert "同意" in rejected.json()["detail"]

    files = {"file": ("img2img2.jpg", _image_bytes("JPEG", "blue"), "image/jpeg")}
    accepted = client.post(
        "/api/v1/photos/upload",
        files=files,
        data={
            "aigc_declared": "true",
            "aigc_source_work_id": "other-work",
            "consent_confirmed": "true",
        },
        headers=_auth(data["token"]),
    )
    assert accepted.status_code == 201, accepted.text


def test_upload_false_declaration_rejects_ai_fields(aigc_client):
    client, data = aigc_client
    files = {"file": ("conflict.jpg", _image_bytes("JPEG", "green"), "image/jpeg")}

    response = client.post(
        "/api/v1/photos/upload",
        files=files,
        data={"aigc_declared": "false", "aigc_model": "qwen-image-3.0-pro"},
        headers=_auth(data["token"]),
    )

    assert response.status_code == 400


def test_public_detail_exposes_aigc_label_but_not_private_prompt(aigc_client):
    client, _ = aigc_client

    payload = client.get("/api/v1/photos/public/aigc-work").json()

    assert payload["is_aigc"] is True
    assert payload["kind"] == "aigc"
    assert payload["aigc_label"] == "AI 生成"
    assert payload["aigc_meta"]["model"] == "qwen-image-3.0-pro"
    # prompt_public=False → 公开响应不含提示词
    assert "prompt" not in payload["aigc_meta"]


def test_download_writes_xmp_implicit_label(aigc_client):
    client, data = aigc_client

    response = client.get("/api/v1/photos/aigc-work/download")

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-aigc-label"] == "AIGC"
    assert response.headers["x-aigc-implicit-label"] == "xmp"
    assert aigc_labeling.has_aigc_xmp(response.content)
    assert b"sakura:work:aigc-work" in response.content

    async def check_flag() -> bool:
        async with data["session_factory"]() as session:
            photo = (await session.execute(select(Photo).where(Photo.id == "aigc-work"))).scalar_one()
            return bool(photo.label_written)

    assert asyncio.run(check_flag()) is True


def test_download_non_aigc_has_no_label(aigc_client):
    client, _ = aigc_client

    response = client.get("/api/v1/photos/plain-work/download")

    assert response.status_code == 200
    assert "x-aigc-implicit-label" not in {key.lower() for key in response.headers}
    assert not aigc_labeling.has_aigc_xmp(response.content)
