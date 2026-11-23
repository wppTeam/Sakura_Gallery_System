"""
图像管线测试（AGENTS.md §6）

覆盖:
1. 16:9 全景不被裁切（旧实现会强行裁成 3:2，损失 44% 画面）；
2. 缩略图 / 压缩图长边正确、等比、只缩小不放大；
3. 响应式变体 320/640/1080/1600/2400 + WebP 主用 + JPEG 兜底，全部可解码；
4. LQIP 为可解码的 20px 内联 data URI；
5. EXIF 脱敏：GPS / 序列号 / Artist / MakerNote 等全部剥离；
6. EXIF Orientation 校正后的显示尺寸；
7. 幂等：重复处理不重写派生文件，force=True 才重建；
8. 原图只读：处理前后原图字节不变。
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
from pathlib import Path

import pytest
from PIL import Image

from app.services import image_processing as ip


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_jpeg(
    path: Path,
    size: tuple[int, int],
    color: tuple[int, int, int] = (180, 120, 90),
    exif_bytes: bytes | None = None,
) -> Path:
    img = Image.new("RGB", size, color)
    save_kwargs: dict = {"quality": 90}
    if exif_bytes is not None:
        save_kwargs["exif"] = exif_bytes
    img.save(path, "JPEG", **save_kwargs)
    return path


def _exif_with_gps(orientation: int = 1) -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "TestMake"               # Make
    exif[0x0110] = "TestModel"              # Model
    exif[0x0112] = orientation              # Orientation
    exif[0x0131] = "TestSoftware"           # Software
    exif[0x013B] = "Secret Artist"          # Artist → 必须剥离
    exif[0x9286] = b"secret comment"        # UserComment → 必须剥离
    exif[0x8769] = {                         # Exif IFD
        36867: "2024:05:01 11:00:00",       # DateTimeOriginal
        33434: (1, 250),                    # ExposureTime = 1/250
        33437: (28, 10),                    # FNumber = 2.8
        34855: 400,                         # ISOSpeedRatings
        37386: (55, 1),                     # FocalLength
    }
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (39.0, 54.0, 0.0)
    gps[3] = "E"
    gps[4] = (116.0, 30.0, 0.0)
    return exif.tobytes()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_aspect(image_path: Path, expected_ratio: float, tol: float = 0.01) -> None:
    with Image.open(image_path) as img:
        width, height = img.size
    assert abs(width / height - expected_ratio) <= tol, (
        f"{image_path.name}: aspect {width}x{height} != {expected_ratio}"
    )


# ---------------------------------------------------------------------------
# 1. 不裁切：16:9 全景必须保持 16:9
# ---------------------------------------------------------------------------

def test_thumbnail_does_not_crop_16_9(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "pano.jpg", (1600, 900))
    thumb = tmp_path / "thumb.jpg"

    _, width, height = ip.create_thumbnail(str(source), str(thumb), max_width=640)

    assert (width, height) == (640, 360), "16:9 缩略图必须等比缩放，不能裁成 3:2"
    _assert_aspect(thumb, 16 / 9)
    assert max(width, height) == 640


def test_compressed_does_not_crop_16_9(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "pano.jpg", (1600, 900))
    compressed = tmp_path / "compressed.jpg"

    _, width, height, size = ip.create_compressed(str(source), str(compressed))

    assert max(width, height) <= ip.COMPRESSED_LONG_EDGE
    assert width / height == pytest.approx(16 / 9, rel=0.01)
    assert size > 0 and size <= ip.COMPRESSED_MAX_BYTES
    _assert_aspect(compressed, 16 / 9)


# ---------------------------------------------------------------------------
# 2. 长边 / 只缩小不放大
# ---------------------------------------------------------------------------

def test_thumbnail_long_edge_portrait_no_upscale(tmp_path: Path) -> None:
    portrait = _make_jpeg(tmp_path / "portrait.jpg", (900, 1350))
    thumb = tmp_path / "thumb.jpg"
    _, width, height = ip.create_thumbnail(str(portrait), str(thumb))
    assert height == 640
    assert width / height == pytest.approx(2 / 3, rel=0.01)
    _assert_aspect(thumb, 2 / 3)

    small = _make_jpeg(tmp_path / "small.jpg", (320, 240))
    small_thumb = tmp_path / "small_thumb.jpg"
    _, width, height = ip.create_thumbnail(str(small), str(small_thumb))
    assert (width, height) == (320, 240), "小图不能被放大"


def test_compressed_respects_long_edge_and_ratio(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "big.jpg", (4000, 3000))
    compressed = tmp_path / "compressed.jpg"
    _, width, height, size = ip.create_compressed(str(source), str(compressed))
    assert max(width, height) == ip.COMPRESSED_LONG_EDGE
    assert width / height == pytest.approx(4 / 3, rel=0.01)
    assert size <= ip.COMPRESSED_MAX_BYTES


# ---------------------------------------------------------------------------
# 3. 响应式变体：320/640/1080/1600/2400 + WebP + JPEG，全部可解码
# ---------------------------------------------------------------------------

def test_variants_ladder_webp_and_jpeg(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "pano.jpg", (1600, 900))
    out_dir = tmp_path / "variants"

    variants = ip.generate_variants(str(source), str(out_dir), photo_uuid="abc123")

    # 原图长边 1600 → 只生成 ≤1600 的档位，绝不放大
    assert sorted(variants) == [320, 640, 1080, 1600]
    for size, entry in variants.items():
        assert max(entry["width"], entry["height"]) == size
        assert entry["width"] / entry["height"] == pytest.approx(16 / 9, rel=0.01)
        for fmt in ("webp", "jpeg"):
            path = Path(entry[fmt])
            assert path.exists() and path.stat().st_size > 0
            with Image.open(path) as img:
                assert max(img.size) == size
                expected_format = "WEBP" if fmt == "webp" else "JPEG"
                assert img.format == expected_format
        assert entry["webp_bytes"] > 0 and entry["jpeg_bytes"] > 0

    # 变体文件名可预测（seed manifest 依赖）
    assert (out_dir / "abc123_320.webp").exists()
    assert (out_dir / "abc123_2400.webp").exists() is False


def test_variants_never_upscale_small_image(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "tiny.jpg", (200, 150))
    variants = ip.generate_variants(str(source), str(tmp_path / "variants"))
    assert len(variants) == 1
    (size, entry), = variants.items()
    assert size == 200
    assert (entry["width"], entry["height"]) == (200, 150)


# ---------------------------------------------------------------------------
# 4. LQIP
# ---------------------------------------------------------------------------

def test_lqip_data_uri_is_decodable(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "photo.jpg", (1200, 800))
    data_uri = ip.create_lqip(str(source))

    assert data_uri.startswith("data:image/webp;base64,")
    payload = base64.b64decode(data_uri.split(",", 1)[1])
    with Image.open(io.BytesIO(payload)) as img:
        assert img.format == "WEBP"
        assert max(img.size) <= ip.LQIP_LONG_EDGE
        assert img.width > 0 and img.height > 0

    meta = ip.create_lqip_meta(str(source))
    assert meta["lqip"] == data_uri
    assert len(meta["color"]) == 7 and meta["color"].startswith("#")


# ---------------------------------------------------------------------------
# 5. EXIF 脱敏
# ---------------------------------------------------------------------------

def test_sanitize_exif_strips_sensitive_fields() -> None:
    raw = {
        "Make": "NIKON CORPORATION",
        "Model": "NIKON Z 6_2",
        "LensModel": "NIKKOR Z 24-70mm f/2.8 S",
        "Software": "Adobe Photoshop Lightroom Classic",
        "DateTimeOriginal": "2024:05:01 11:00:00",
        "ExposureTime": (1, 250),
        "FNumber": (28, 10),
        "ISOSpeedRatings": 400,
        "FocalLength": (55, 1),
        "Orientation": 1,
        # 以下必须被剥离
        "GPSInfo": {1: "N", 2: (39.0, 54.0, 0.0), 3: "E", 4: (116.0, 30.0, 0.0)},
        "MakerNote": b"\x00\x01secret",
        "UserComment": b"private",
        "Artist": "JACK_WANG",
        "Copyright": "someone",
        "BodySerialNumber": "SN123456",
        "LensSerialNumber": "LN987654",
        "CameraOwnerName": "王海翔",
        "ImageDescription": "有 GPS 的原始描述",
        "XPAuthor": "王海翔",
    }

    cleaned = ip.sanitize_exif(raw)

    for forbidden in (
        "GPSInfo",
        "MakerNote",
        "UserComment",
        "Artist",
        "Copyright",
        "BodySerialNumber",
        "LensSerialNumber",
        "CameraOwnerName",
        "ImageDescription",
        "XPAuthor",
    ):
        assert forbidden not in cleaned, f"{forbidden} 未剥离"

    assert cleaned["Make"] == "NIKON CORPORATION"
    assert cleaned["Model"] == "NIKON Z 6_2"
    assert cleaned["DateTimeOriginal"] == "2024:05:01 11:00:00"
    assert cleaned["ISOSpeedRatings"] == 400
    # 有理数被转成 JSON 可序列化的 float
    assert cleaned["ExposureTime"] == pytest.approx(0.004)
    assert cleaned["FNumber"] == pytest.approx(2.8)
    json.dumps(cleaned)  # 必须可序列化

    # 文本中不能残留 GPS 坐标/姓名
    serialized = json.dumps(cleaned, ensure_ascii=False)
    assert "39.0" not in serialized and "116.0" not in serialized
    assert "王海翔" not in serialized


def test_extract_safe_exif_from_real_jpeg(tmp_path: Path) -> None:
    source = _make_jpeg(
        tmp_path / "with_exif.jpg",
        (1200, 800),
        exif_bytes=_exif_with_gps(),
    )

    cleaned = ip.extract_safe_exif(str(source))

    assert "GPSInfo" not in cleaned
    assert "Artist" not in cleaned
    assert "UserComment" not in cleaned
    assert cleaned["Make"] == "TestMake"
    assert cleaned["Model"] == "TestModel"
    assert cleaned["DateTimeOriginal"] == "2024:05:01 11:00:00"
    json.dumps(cleaned)

    captured_at = ip.extract_date_taken(cleaned)
    assert captured_at is not None and captured_at.year == 2024 and captured_at.month == 5

    # 原始入口保留完整 EXIF（仅用于诊断），证明脱敏发生在 sanitize 层
    raw = ip.extract_exif(str(source))
    assert "GPSInfo" in raw


# ---------------------------------------------------------------------------
# 6. Orientation 校正
# ---------------------------------------------------------------------------

def test_orientation_aware_dimensions_and_thumbnail(tmp_path: Path) -> None:
    source = _make_jpeg(
        tmp_path / "rotated.jpg",
        (800, 600),
        exif_bytes=_exif_with_gps(orientation=6),  # 顺时针旋转 90°
    )

    assert ip._display_size(str(source)) == (600, 800)

    result = ip.process_uploaded_image(
        str(source),
        "orient-uuid",
        output_dir=str(tmp_path),
        force=True,
    )
    assert (result["width"], result["height"]) == (600, 800)
    with Image.open(result["thumb_path"]) as thumb:
        assert max(thumb.size) == ip.THUMBNAIL_LONG_EDGE
        assert thumb.height > thumb.width  # 校正后是竖图


# ---------------------------------------------------------------------------
# 7. 幂等 / force / 原图只读 / 完整流程
# ---------------------------------------------------------------------------

def test_process_uploaded_image_idempotent(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "photo.jpg", (2400, 1600), exif_bytes=_exif_with_gps())
    source_hash = _sha256(source)
    output_dir = tmp_path / "derived"
    variants_dir = tmp_path / "variants"

    first = ip.process_uploaded_image(
        str(source),
        "uuid-idem",
        output_dir=str(output_dir),
        variants_dir=str(variants_dir),
        strict=True,
    )
    assert first["width"] == 2400 and first["height"] == 1600
    assert Path(first["thumb_path"]).exists()
    assert Path(first["compressed_path"]).exists()
    assert first["variants"] and sorted(first["variants"]) == [320, 640, 1080, 1600, 2400]
    assert first["exif_data"]["_lqip"].startswith("data:image/webp;base64,")
    assert "GPSInfo" not in first["exif_data"]
    assert first["captured_at"] is not None

    thumb_mtime = os.stat(first["thumb_path"]).st_mtime_ns
    compressed_mtime = os.stat(first["compressed_path"]).st_mtime_ns
    webp_mtime = os.stat(first["variants"][640]["webp"]).st_mtime_ns

    time.sleep(0.02)
    second = ip.process_uploaded_image(
        str(source),
        "uuid-idem",
        output_dir=str(output_dir),
        variants_dir=str(variants_dir),
        strict=True,
    )
    assert os.stat(second["thumb_path"]).st_mtime_ns == thumb_mtime, "幂等重跑不应重写缩略图"
    assert os.stat(second["compressed_path"]).st_mtime_ns == compressed_mtime
    assert os.stat(second["variants"][640]["webp"]).st_mtime_ns == webp_mtime

    time.sleep(0.02)
    forced = ip.process_uploaded_image(
        str(source),
        "uuid-idem",
        output_dir=str(output_dir),
        variants_dir=str(variants_dir),
        force=True,
        strict=True,
    )
    assert os.stat(forced["thumb_path"]).st_mtime_ns > thumb_mtime, "force=True 应重建"

    # 原图只读：处理前后字节完全一致
    assert _sha256(source) == source_hash


def test_process_uploaded_image_without_placeholder(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "photo.jpg", (800, 600))
    result = ip.process_uploaded_image(
        str(source),
        "uuid-nolqip",
        output_dir=str(tmp_path),
        generate_placeholder=False,
        strict=True,
    )
    assert result["lqip"] is None
    assert "_lqip" not in result["exif_data"]
    assert result["variants"] == {}


def test_rgba_png_thumbnail(tmp_path: Path) -> None:
    source = tmp_path / "alpha.png"
    Image.new("RGBA", (500, 500), (10, 20, 30, 128)).save(source)
    thumb = tmp_path / "thumb.jpg"
    _, width, height = ip.create_thumbnail(str(source), str(thumb))
    assert (width, height) == (500, 500)
    with Image.open(thumb) as img:
        assert img.format == "JPEG"
