"""规则前置层单元测试：纯函数为主，不依赖数据库 / AI / 网络。"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from PIL import Image, ImageDraw

from app.services import moderation_rules as rules
from app.services.moderation_rules import (
    RuleHit,
    RuleResult,
    detect_aigc_hits,
    detect_exif_privacy_hits,
    dhash_from_image,
    dhash_from_path,
    hamming_distance_hex,
    hashes_within,
    inspect_image_file,
)

JPEG_MIME = "image/jpeg"


# ---------------------------------------------------------------------------
# 测试图片
# ---------------------------------------------------------------------------

def _gradient_image(size: tuple[int, int] = (400, 300)) -> Image.Image:
    image = Image.new("L", size)
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 4):
        shade = (x * 5) % 256
        draw.rectangle([x, 0, x + 3, size[1]], fill=shade)
    return image.convert("RGB")


def _save_image(path, size=(400, 300), fmt="JPEG", color=None) -> str:
    image = _gradient_image(size)
    if color is not None:
        image = Image.new("RGB", size, color)
    image.save(path, format=fmt)
    return str(path)


# ---------------------------------------------------------------------------
# dhash
# ---------------------------------------------------------------------------

def test_dhash_is_stable_and_well_formed(tmp_path):
    image = _gradient_image()
    first = dhash_from_image(image)
    second = dhash_from_image(image.copy())

    assert len(first) == 64
    assert int(first, 16) >= 0
    assert hamming_distance_hex(first, second) == 0
    assert hashes_within(first, second, 0)


def test_dhash_distinguishes_different_images(tmp_path):
    gradient = dhash_from_image(_gradient_image())
    solid = dhash_from_image(Image.new("RGB", (400, 300), (0, 0, 0)))

    assert gradient != solid
    assert hamming_distance_hex(gradient, solid) > 5
    assert not hashes_within(gradient, solid, 5)


def test_dhash_from_path_reads_file(tmp_path):
    path = _save_image(tmp_path / "a.jpg")

    assert dhash_from_path(path) == dhash_from_path(path)
    assert dhash_from_path(tmp_path / "missing.jpg") is None


def test_hamming_rejects_invalid_hex():
    assert hamming_distance_hex("not-hex", "ffff") == 1024
    assert hamming_distance_hex(None, "ffff") == 1024  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 文件层
# ---------------------------------------------------------------------------

def test_inspect_image_file_accepts_normal_photo(tmp_path):
    path = _save_image(tmp_path / "normal.jpg")

    result = inspect_image_file(path, filename="normal.jpg")

    assert result.checked is True
    assert result.blocked is False
    assert result.width == 400
    assert result.height == 300
    assert result.image_format == "JPEG"
    assert result.file_size and result.file_size > 0
    assert result.dhash


def test_inspect_image_file_warns_on_tiny_dimensions(tmp_path):
    path = _save_image(tmp_path / "tiny.png", size=(120, 80), fmt="PNG")

    result = inspect_image_file(path)

    assert result.blocked is False
    assert "image_too_small" in {hit.code for hit in result.hits}


def test_inspect_image_file_blocks_missing_file(tmp_path):
    result = inspect_image_file(tmp_path / "nope.jpg")

    assert result.blocked is True
    assert result.hits[0].code == "file_missing"


def test_inspect_image_file_blocks_undecodable_file(tmp_path):
    path = tmp_path / "fake.jpg"
    path.write_bytes(b"this is definitely not an image" * 50)

    result = inspect_image_file(path)

    assert result.blocked is True
    assert "file_undecodable" in {hit.code for hit in result.hits}


def test_inspect_image_file_warns_on_extreme_aspect(tmp_path):
    path = _save_image(tmp_path / "panorama.png", size=(2000, 200), fmt="PNG")

    result = inspect_image_file(path)

    assert result.blocked is False
    assert "image_extreme_aspect" in {hit.code for hit in result.hits}


# ---------------------------------------------------------------------------
# EXIF 隐私
# ---------------------------------------------------------------------------

def test_exif_gps_is_blocked():
    hits = detect_exif_privacy_hits(
        {"GPSInfo": {"GPSLatitude": [39, 56, 0], "GPSLongitude": [116, 17, 0]}}
    )
    assert any(hit.code == "exif_gps_present" and hit.severity == "block" for hit in hits)


def test_exif_top_level_gps_is_blocked():
    hits = detect_exif_privacy_hits({"GPSLatitude": 39.5, "Make": "Canon"})
    assert any(hit.code == "exif_gps_present" for hit in hits)


def test_exif_personal_fields_warn():
    hits = detect_exif_privacy_hits(
        {"Artist": "张三", "Copyright": "© 张三", "Make": "Canon"}
    )
    assert any(hit.code == "exif_personal_fields" and hit.severity == "warn" for hit in hits)
    assert all(hit.severity != "block" for hit in hits)


def test_exif_clean_metadata_has_no_hits():
    hits = detect_exif_privacy_hits({"Make": "Canon", "Model": "EOS R6", "ISO": 100})
    assert hits == []


# ---------------------------------------------------------------------------
# AIGC 元数据探测
# ---------------------------------------------------------------------------

def test_aigc_software_metadata_warns():
    hits = detect_aigc_hits(
        {"Software": "Stable Diffusion v1.5", "UserComment": "prompt: a cat, negative prompt: blur"}
    )
    assert any(hit.code == "aigc_metadata" and hit.severity == "warn" for hit in hits)


def test_aigc_filename_and_editor_hint():
    hits = detect_aigc_hits({"Software": "Adobe Photoshop 25.0"}, "midjourney_0001.png")
    codes = {hit.code for hit in hits}
    assert "exif_editor_hint" in codes
    assert "aigc_filename_hint" in codes


# ---------------------------------------------------------------------------
# RuleResult
# ---------------------------------------------------------------------------

def test_rule_result_roundtrip_and_severity():
    result = RuleResult()
    result.add("warn_code", "warn", "detail")
    result.add("block_code", "block", "detail")
    result.add("bad_severity", "fatal", "降级为 info")

    assert result.blocked is True
    assert result.max_severity == "block"
    assert result.hits[2].severity == "info"

    restored = RuleResult.from_dict(result.to_dict())
    assert restored.blocked is True
    assert {hit.code for hit in restored.hits} == {"warn_code", "block_code", "bad_severity"}
    assert RuleResult.from_dict(None).blocked is False


# ---------------------------------------------------------------------------
# run_rules（storage 打桩，不碰真实文件存储）
# ---------------------------------------------------------------------------

class _FakeStorage:
    def __init__(self, path):
        self._path = path

    @contextmanager
    def local_copy(self, file_path):
        yield str(self._path)


async def _no_duplicates(*args, **kwargs):
    return []


@pytest.mark.asyncio
async def test_run_rules_uses_storage_and_skips_duplicate_scan(tmp_path, monkeypatch):
    image_path = _save_image(tmp_path / "stored.jpg")
    monkeypatch.setattr(rules, "get_storage", lambda: _FakeStorage(image_path))
    monkeypatch.setattr(rules, "find_near_duplicates", _no_duplicates)

    class _Photo:
        id = "photo-1"
        filename = "stored.jpg"
        original_path = "originals/stored.jpg"
        thumb_path = "thumbnails/stored.jpg"
        exif_data = {"Make": "Canon"}

    result = await rules.run_rules(db=None, photo=_Photo())  # type: ignore[arg-type]

    assert result.checked is True
    assert result.width == 400
    assert result.blocked is False
    assert not any(hit.code == "rule_layer_error" for hit in result.hits)


@pytest.mark.asyncio
async def test_run_rules_degrades_when_storage_fails(monkeypatch):
    class _BrokenStorage:
        @contextmanager
        def local_copy(self, file_path):
            raise FileNotFoundError("gone")

    monkeypatch.setattr(rules, "get_storage", lambda: _BrokenStorage())

    class _Photo:
        id = "photo-2"
        filename = "gone.jpg"
        original_path = "originals/gone.jpg"
        thumb_path = None
        exif_data = None

    result = await rules.run_rules(db=None, photo=_Photo())  # type: ignore[arg-type]

    assert result.checked is True
    assert result.blocked is True
    assert "file_missing" in {hit.code for hit in result.hits}


def test_rule_hit_payload_is_stable():
    assert RuleHit(code="x", severity="info", detail="d").to_dict() == {
        "code": "x",
        "severity": "info",
        "detail": "d",
    }
