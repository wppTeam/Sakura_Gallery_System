"""
Image processing service for thumbnails, compression, responsive variants,
LQIP placeholders and EXIF sanitization.

AGENTS.md §6（必须遵守）:
1. 原图只读、保留原始构图 —— 任何派生物都不得裁切；
2. 只缩小不放大（never upscale）；
3. 缩略图 / 压缩图 / 变体按 EXIF Orientation 呈现正确方向，原图文件永不改写；
4. 派生物幂等：目标文件已存在则跳过，``force=True`` 时重建；
5. EXIF 入库前脱敏：GPSInfo / MakerNote / 序列号 / Artist 等一律剥离。

派生规格:
- 缩略图 ``create_thumbnail``      : JPEG，长边 640，≤1MB
- 压缩图 ``create_compressed``     : JPEG，长边 ≤1600，≤5MB
- 响应式变体 ``generate_variants`` : WebP 主用 + JPEG 兜底，长边 320/640/1080/1600/2400
- LQIP ``create_lqip``             : 长边 20 的 WebP data URI（免 blurhash 依赖）
"""
from __future__ import annotations

import base64
import io
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from PIL import Image, ImageOps
from PIL.ExifTags import TAGS

from app.core.config import get_settings

settings = get_settings()

# 缩略图：前端瀑布流卡片使用，长边 640 足够 2x 屏
THUMBNAIL_LONG_EDGE = 640
THUMBNAIL_QUALITY = 82
THUMBNAIL_MAX_BYTES = 1024 * 1024  # 1MB

# 压缩图：详情页 / 未登录浏览，长边 1600 对齐变体档位
COMPRESSED_LONG_EDGE = 1600
COMPRESSED_QUALITY = 85
COMPRESSED_MAX_BYTES = 5 * 1024 * 1024  # 5MB

# 响应式变体档位（AGENTS.md §6）。只生成不超过原图长边的档位，绝不放大。
VARIANT_LONG_EDGES = (320, 640, 1080, 1600, 2400)
VARIANT_WEBP_QUALITY = 82
VARIANT_JPEG_QUALITY = 82

# LQIP：20px 内联占位图
LQIP_LONG_EDGE = 20
LQIP_QUALITY = 42

# EXIF 白名单：只保留摄影参数与时间，其余（尤其是 GPS）一律丢弃。
EXIF_WHITELIST = frozenset({
    # 机身与镜头
    "Make",
    "Model",
    "LensMake",
    "LensModel",
    "LensSpecification",
    "Software",
    # 时间
    "DateTime",
    "DateTimeOriginal",
    "DateTimeDigitized",
    "OffsetTime",
    "OffsetTimeOriginal",
    "OffsetTimeDigitized",
    "SubsecTime",
    "SubsecTimeOriginal",
    "SubsecTimeDigitized",
    # 曝光参数
    "ExposureTime",
    "FNumber",
    "ISOSpeedRatings",
    "PhotographicSensitivity",
    "FocalLength",
    "FocalLengthIn35mmFilm",
    "ExposureBiasValue",
    "ExposureProgram",
    "ExposureMode",
    "MeteringMode",
    "WhiteBalance",
    "Flash",
    "LightSource",
    "MaxApertureValue",
    "ShutterSpeedValue",
    "ApertureValue",
    "DigitalZoomRatio",
    # 尺寸 / 色彩
    "Orientation",
    "ColorSpace",
    "ExifImageWidth",
    "ExifImageHeight",
    "PixelXDimension",
    "PixelYDimension",
    # 场景
    "SceneCaptureType",
    "Contrast",
    "Saturation",
    "Sharpness",
    "SubjectDistanceRange",
})

# 明确禁止入库的敏感字段（即使将来白名单误加也要挡住）。用于测试与审计。
EXIF_FORBIDDEN_FIELDS = frozenset({
    "GPSInfo",
    "MakerNote",
    "UserComment",
    "Artist",
    "Copyright",
    "ImageDescription",
    "XPAuthor",
    "XPComment",
    "XPKeywords",
    "XPSubject",
    "XPTitle",
    "CameraOwnerName",
    "BodySerialNumber",
    "LensSerialNumber",
    "SerialNumber",
    "ImageUniqueID",
    "HostComputer",
    "OwnerName",
    "SensitivityType",
})

# 这些标签在 EXIF 中是有理数（numerator/denominator），入库前统一转 float
_RATIONAL_EXIF_KEYS = frozenset({
    "ExposureTime",
    "FNumber",
    "FocalLength",
    "ExposureBiasValue",
    "MaxApertureValue",
    "ApertureValue",
    "ShutterSpeedValue",
    "DigitalZoomRatio",
})


def _json_safe(value: Any) -> Any:
    """把 EXIF 中的 bytes / IFDRational / tuple 转成 JSON 可序列化值。"""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    # IFDRational / Fraction 等有理数
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        try:
            return round(float(value), 6)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    if isinstance(value, (tuple, list)):
        items = [_json_safe(item) for item in value]
        return [item for item in items if item is not None]
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            safe_item = _json_safe(item)
            if safe_item is not None:
                cleaned[str(key)] = safe_item
        return cleaned
    try:
        return str(value)
    except Exception:  # pragma: no cover - 防御性兜底
        return None


def _read_exif(image_path: str) -> Dict[str, Any]:
    """读取原始 EXIF（可读键名），不做脱敏。"""
    raw_exif: Dict[str, Any] = {}
    try:
        with Image.open(image_path) as img:
            exif_raw = img._getexif()
    except Exception:
        return raw_exif
    if not exif_raw:
        return raw_exif
    for tag_id, value in exif_raw.items():
        name = TAGS.get(tag_id, str(tag_id))
        raw_exif[name] = value
    return raw_exif


def sanitize_exif(exif_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    按白名单脱敏 EXIF。

    - 只保留 :data:`EXIF_WHITELIST` 中的摄影参数；
    - GPSInfo / MakerNote / 机身与镜头序列号 / Artist 等一律丢弃；
    - 输出保证 ``json.dumps`` 可序列化。
    """
    cleaned: Dict[str, Any] = {}
    for key, value in (exif_data or {}).items():
        if key in EXIF_FORBIDDEN_FIELDS or key not in EXIF_WHITELIST:
            continue
        if key in _RATIONAL_EXIF_KEYS and isinstance(value, (tuple, list)) and len(value) == 2:
            try:
                value = float(value[0]) / float(value[1]) if float(value[1]) else None
            except (TypeError, ValueError, ZeroDivisionError):
                value = None
        safe_value = _json_safe(value)
        if safe_value is not None and safe_value != "":
            cleaned[key] = safe_value
    return cleaned


def extract_safe_exif(image_path: str) -> Dict[str, Any]:
    """读取并脱敏 EXIF；入库必须使用这个函数。"""
    return sanitize_exif(_read_exif(image_path))


def extract_exif(image_path: str) -> Dict[str, Any]:
    """
    读取原始 EXIF（未脱敏，仅白名单过滤之外的兼容入口）。

    .. deprecated::
        公开响应 / 入库请使用 :func:`extract_safe_exif`。
        此函数保留仅为兼容旧脚本与诊断用途。
    """
    return {
        key: _json_safe(value)
        for key, value in _read_exif(image_path).items()
        if _json_safe(value) is not None
    }


def _display_size(image_path: str) -> tuple[int, int]:
    """返回按 EXIF Orientation 校正后的显示尺寸（不裁切原图文件）。"""
    with Image.open(image_path) as img:
        width, height = img.size
        try:
            orientation = img.getexif().get(0x0112)
        except Exception:
            orientation = None
    if orientation in (5, 6, 7, 8):
        width, height = height, width
    return width, height


def _load_oriented(image_path: str) -> Image.Image:
    """打开图片并按 EXIF Orientation 校正方向（返回独立图像，原文件不动）。"""
    with Image.open(image_path) as src:
        img = ImageOps.exif_transpose(src)
        img.load()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def _resize_long_edge(img: Image.Image, long_edge: int) -> Image.Image:
    """等比缩放到指定长边；原图长边不足时原样返回（绝不放大）。"""
    width, height = img.size
    current = max(width, height)
    if current <= long_edge:
        return img
    scale = long_edge / float(current)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)


def _write_jpeg_with_limit(
    img: Image.Image,
    target_path: str,
    start_quality: int = 82,
    max_size_bytes: int = THUMBNAIL_MAX_BYTES,
) -> int:
    """写 JPEG，按质量阶梯回退直到不超过 max_size_bytes。返回文件字节数。"""
    size = 0
    for quality in (start_quality, 78, 72, 66, 60, 52):
        img.save(target_path, "JPEG", quality=quality, optimize=True)
        size = os.path.getsize(target_path)
        if size <= max_size_bytes:
            return size
    return size


def create_thumbnail(
    image_path: str,
    thumb_path: str,
    max_width: int = THUMBNAIL_LONG_EDGE,
    quality: int = THUMBNAIL_QUALITY,
    max_size_bytes: int = THUMBNAIL_MAX_BYTES,
) -> tuple[str, int, int]:
    """
    生成等比缩略图（长边=``max_width``，不裁切，不放大）。

    Args:
        image_path: 原图路径
        thumb_path: 缩略图输出路径（JPEG）
        max_width: 缩略图长边上限
        quality: JPEG 初始质量
        max_size_bytes: 文件大小上限

    Returns:
        tuple: ``(thumb_path, thumb_width, thumb_height)``
    """
    img = _load_oriented(image_path)
    img = _resize_long_edge(img, max_width)
    Path(thumb_path).parent.mkdir(parents=True, exist_ok=True)
    _write_jpeg_with_limit(img, thumb_path, start_quality=quality, max_size_bytes=max_size_bytes)
    width, height = img.size
    return thumb_path, width, height


def create_compressed(
    image_path: str,
    compressed_path: str,
    max_size_bytes: int = COMPRESSED_MAX_BYTES,
    max_long_edge: int = COMPRESSED_LONG_EDGE,
) -> tuple[str, int, int, int]:
    """
    生成详情页用压缩图：长边 ≤ ``max_long_edge``（默认 1600），文件 ≤ ``max_size_bytes``。

    不裁切、不放大；质量不够时逐级降质量，再逐级缩小尺寸（不低于 800 长边）。

    Returns:
        tuple: ``(compressed_path, width, height, file_size_bytes)``
    """
    img = _load_oriented(image_path)
    img = _resize_long_edge(img, max_long_edge)
    Path(compressed_path).parent.mkdir(parents=True, exist_ok=True)

    edge = max(img.size)
    size = _write_jpeg_with_limit(
        img,
        compressed_path,
        start_quality=COMPRESSED_QUALITY,
        max_size_bytes=max_size_bytes,
    )
    while size > max_size_bytes and edge > 800:
        edge = max(800, int(edge * 0.85))
        img = _resize_long_edge(img, edge)
        size = _write_jpeg_with_limit(
            img,
            compressed_path,
            start_quality=70,
            max_size_bytes=max_size_bytes,
        )
    width, height = img.size
    return compressed_path, width, height, size


def generate_variants(
    image_path: str,
    output_dir: str,
    photo_uuid: Optional[str] = None,
    sizes: Optional[Sequence[int]] = None,
    webp_quality: int = VARIANT_WEBP_QUALITY,
    jpeg_quality: int = VARIANT_JPEG_QUALITY,
    force: bool = False,
) -> Dict[int, Dict[str, Any]]:
    """
    生成响应式变体：每个档位同时输出 WebP（主用）与 JPEG（兜底）。

    - 档位默认 ``320/640/1080/1600/2400``；
    - 只生成不超过原图长边的档位（原图小于 320 时用原长边一档），绝不放大；
    - 不裁切，按 EXIF Orientation 输出。

    Returns:
        dict: ``{size: {"width", "height", "webp", "jpeg", "webp_bytes", "jpeg_bytes"}}``
    """
    requested = tuple(sizes) if sizes else VARIANT_LONG_EDGES
    stem = photo_uuid or Path(image_path).stem
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    img = _load_oriented(image_path)
    native_long_edge = max(img.size)
    targets = sorted({int(size) for size in requested if 0 < int(size) <= native_long_edge})
    if not targets:
        targets = [native_long_edge]

    variants: Dict[int, Dict[str, Any]] = {}
    # 从大到小逐级缩放（避免每次从 6000px 原图重采样）
    for size in sorted(targets, reverse=True):
        img = _resize_long_edge(img, size)
        webp_path = out_dir / f"{stem}_{size}.webp"
        jpeg_path = out_dir / f"{stem}_{size}.jpg"
        already_exists = (
            not force
            and webp_path.exists()
            and jpeg_path.exists()
            and webp_path.stat().st_size > 0
            and jpeg_path.stat().st_size > 0
        )
        if not already_exists:
            img.save(webp_path, "WEBP", quality=webp_quality, method=4)
            img.save(jpeg_path, "JPEG", quality=jpeg_quality, optimize=True)
        width, height = img.size
        variants[size] = {
            "width": width,
            "height": height,
            "webp": str(webp_path),
            "jpeg": str(jpeg_path),
            "webp_bytes": os.path.getsize(webp_path),
            "jpeg_bytes": os.path.getsize(jpeg_path),
        }
    return variants


def _build_placeholder(image_path: str) -> tuple[str, str]:
    """生成 20px 内联占位图 data URI 与主色，用于消除加载跳动。"""
    img = _load_oriented(image_path)
    img = _resize_long_edge(img, LQIP_LONG_EDGE)
    buffer = io.BytesIO()
    img.save(buffer, "WEBP", quality=LQIP_QUALITY, method=4)
    data_uri = "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    color_img = img.resize((1, 1), Image.Resampling.BILINEAR)
    red, green, blue = color_img.getpixel((0, 0))[:3]
    return data_uri, "#{:02x}{:02x}{:02x}".format(red, green, blue)


def create_lqip(image_path: str) -> str:
    """生成 LQIP 内联占位图（``data:image/webp;base64,...``，长边 ≤ 20px）。"""
    return _build_placeholder(image_path)[0]


def create_lqip_meta(image_path: str) -> Dict[str, str]:
    """生成 LQIP 占位图 + 主色，返回 ``{"lqip": data_uri, "color": "#rrggbb"}``。"""
    data_uri, color = _build_placeholder(image_path)
    return {"lqip": data_uri, "color": color}


def get_image_dimensions(image_path: str) -> tuple[int, int]:
    """读取原图像素尺寸（不做 Orientation 校正，保持历史语义）。"""
    with Image.open(image_path) as img:
        return img.size


def extract_date_taken(exif_data: Dict[str, Any]) -> Optional[datetime]:
    """从（已脱敏的）EXIF 中解析拍摄时间。"""
    for field in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
        value = (exif_data or {}).get(field)
        if not value or not isinstance(value, str):
            continue
        try:
            return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            continue
    return None


def process_uploaded_image(
    original_path: str,
    photo_uuid: str,
    output_dir: Optional[str] = None,
    *,
    variants_dir: Optional[str] = None,
    generate_placeholder: bool = True,
    force: bool = False,
    strict: bool = False,
) -> Dict[str, Any]:
    """
    处理上传图：方向校正尺寸、脱敏 EXIF、缩略图、压缩图、LQIP（可选变体）。

    保持向后兼容：原有三个位置参数 ``(original_path, photo_uuid, output_dir)``
    与返回字典键 ``width/height/thumb_path/compressed_path/exif_data/captured_at``
    均不变；新增键 ``lqip``、``lqip_color``、``variants``。

    Args:
        original_path: 原图路径（只读，不会被改写）
        photo_uuid: 照片 UUID，用于派生文件名
        output_dir: 缩略图/压缩图输出目录，默认 ``uploads/thumbnails``
        variants_dir: 指定时生成 WebP/JPEG 响应式变体到该目录
        generate_placeholder: 是否生成 LQIP（``exif_data["_lqip"]``）
        force: 已存在的派生物是否重建（默认幂等跳过）
        strict: 为 True 时异常向上抛出（种子脚本/测试使用）

    Returns:
        dict: 处理结果
    """
    results: Dict[str, Any] = {
        "width": None,
        "height": None,
        "thumb_path": None,
        "compressed_path": None,
        "exif_data": {},
        "captured_at": None,
        "lqip": None,
        "lqip_color": None,
        "variants": {},
    }

    try:
        # 1. 显示尺寸（按 Orientation 校正，不裁切）
        width, height = _display_size(original_path)
        results["width"] = width
        results["height"] = height

        # 2. 脱敏 EXIF + 拍摄时间
        exif_data = extract_safe_exif(original_path)
        results["exif_data"] = exif_data
        results["captured_at"] = extract_date_taken(exif_data)

        # 3. 缩略图（长边 640，等比不裁切）
        derived_dir = Path(output_dir) if output_dir else (Path(settings.UPLOAD_DIR) / "thumbnails")
        derived_dir.mkdir(parents=True, exist_ok=True)

        thumb_path = derived_dir / f"{photo_uuid}_thumb.jpg"
        if force or not thumb_path.exists() or thumb_path.stat().st_size == 0:
            create_thumbnail(original_path, str(thumb_path))
        results["thumb_path"] = str(thumb_path)

        # 4. 压缩图（长边 ≤1600）：始终生成，避免详情页直接拉十几 MB 原图
        compressed_path = derived_dir / f"{photo_uuid}_compressed.jpg"
        if force or not compressed_path.exists() or compressed_path.stat().st_size == 0:
            create_compressed(original_path, str(compressed_path))
        results["compressed_path"] = str(compressed_path)

        # 5. LQIP 内联占位图
        if generate_placeholder:
            placeholder = create_lqip_meta(original_path)
            results["lqip"] = placeholder["lqip"]
            results["lqip_color"] = placeholder["color"]
            exif_data["_lqip"] = placeholder["lqip"]
            exif_data["_lqip_color"] = placeholder["color"]

        # 6. 响应式变体（仅显式要求时生成；需要端点/存储层配合才能对外提供 URL）
        if variants_dir:
            variants = generate_variants(
                original_path, variants_dir, photo_uuid=photo_uuid, force=force
            )
            results["variants"] = variants

    except Exception as exc:  # noqa: BLE001 - 上传流程不应因单图失败而整体失败
        if strict:
            raise
        print(f"Error processing image: {exc}")

    return results
