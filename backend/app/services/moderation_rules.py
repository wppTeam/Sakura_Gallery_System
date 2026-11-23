"""AI 审核规则前置层（不花模型钱）。

在上传后的第一时间做确定性检查，把能机器判断的风险拦下来，减少 VLM 调用：

- 文件类型 / 体积 / 可解码性 / 尺寸 / 极端宽高比；
- EXIF 隐私检查：GPS 定位、可能含真实姓名的字段（Artist / Copyright / UserComment）；
- EXIF / XMP 中的“生成式 AI”痕迹（Stable Diffusion、Midjourney 等软件名与 prompt 字段）；
- 感知哈希查重：自实现 16x16 dhash（256 bit），与最近入库照片比对近重复。

设计原则：
- **纯函数优先**：`RuleHit` / `RuleResult` 数据类 + 无副作用函数，方便单测；
- **绝不抛到上传请求**：`run_rules` 内部兜底，异常降级为一条 warn 命中；
- 不引入新依赖：只使用 Pillow（项目已有）；
- 任意外部 I/O 只走 `storage.local_copy`，同时兼容本地与 S3 后端。
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo
from app.services.storage import get_storage

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

SEVERITY_RANK = {"info": 0, "warn": 1, "block": 2}

# 文件层常量（不放进 Settings，避免动 Lead 的 config.py）
ALLOWED_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF"})
MIN_LONG_EDGE = 200
MIN_FILE_BYTES = 256
MAX_ASPECT_RATIO = 5.0  # 超过 5:1 或 1:5 只警告（全景图合法，不硬拦）
# 查重时最多回看最近多少张已入库照片（避免上传高峰期扫全表）
DUPLICATE_SCAN_LIMIT = 200
_DHASH_CACHE_LIMIT = 600


@dataclass(slots=True)
class RuleHit:
    """一条规则命中。"""

    code: str
    severity: str  # block | warn | info
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleHit":
        return cls(
            code=str(data.get("code") or "unknown"),
            severity=str(data.get("severity") or "info"),
            detail=str(data.get("detail") or ""),
        )


@dataclass(slots=True)
class RuleResult:
    """一次规则前置的完整结果。"""

    hits: list[RuleHit] = field(default_factory=list)
    width: int | None = None
    height: int | None = None
    file_size: int | None = None
    image_format: str | None = None
    dhash: str | None = None
    checked: bool = False

    def add(self, code: str, severity: str, detail: str = "") -> None:
        if severity not in SEVERITY_RANK:
            severity = "info"
        self.hits.append(RuleHit(code=code, severity=severity, detail=detail))

    def extend(self, hits: Iterable[RuleHit]) -> None:
        for hit in hits:
            self.add(hit.code, hit.severity, hit.detail)

    @property
    def blocked(self) -> bool:
        return any(hit.severity == "block" for hit in self.hits)

    @property
    def max_severity(self) -> str:
        if not self.hits:
            return "none"
        return max((hit.severity for hit in self.hits), key=lambda s: SEVERITY_RANK.get(s, 0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "max_severity": self.max_severity,
            "checked": self.checked,
            "width": self.width,
            "height": self.height,
            "file_size": self.file_size,
            "image_format": self.image_format,
            "dhash": self.dhash,
            "hits": [hit.to_dict() for hit in self.hits],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RuleResult":
        data = data or {}
        return cls(
            hits=[RuleHit.from_dict(item) for item in (data.get("hits") or [])],
            width=data.get("width"),
            height=data.get("height"),
            file_size=data.get("file_size"),
            image_format=data.get("image_format"),
            dhash=data.get("dhash"),
            checked=bool(data.get("checked")),
        )


# ---------------------------------------------------------------------------
# 感知哈希（dhash 16x16 = 256 bit，自实现，无新依赖）
# ---------------------------------------------------------------------------

DHASH_SIZE = 16


def _pil():
    """延迟 import Pillow：基础环境未装 Pillow 时不影响导入本模块。"""
    from PIL import Image, ImageOps  # noqa: F401

    return Image, ImageOps


def dhash_from_image(image: Any, *, hash_size: int = DHASH_SIZE) -> str:
    """对 Pillow Image 计算 dhash，返回 64 位十六进制字符串（256 bit）。"""
    _, ImageOps = _pil()
    gray = ImageOps.exif_transpose(image).convert("L")
    resized = gray.resize((hash_size + 1, hash_size))
    pixels = list(resized.getdata())
    bits = 0
    index = 0
    row_width = hash_size + 1
    for row in range(hash_size):
        base = row * row_width
        for col in range(hash_size):
            if pixels[base + col] > pixels[base + col + 1]:
                bits |= 1 << index
            index += 1
    return f"{bits:0{hash_size * hash_size // 4}x}"


def dhash_from_bytes(data: bytes, *, hash_size: int = DHASH_SIZE) -> str | None:
    """对图片字节计算 dhash；无法解码返回 None。"""
    import io

    Image, _ = _pil()
    try:
        with Image.open(io.BytesIO(data)) as image:
            return dhash_from_image(image, hash_size=hash_size)
    except Exception:  # noqa: BLE001 - 损坏 / 非图片，交给文件层规则报告
        return None


def dhash_from_path(path: str | Path, *, hash_size: int = DHASH_SIZE) -> str | None:
    """对本地图片文件计算 dhash；无法解码返回 None。"""
    Image, _ = _pil()
    try:
        with Image.open(path) as image:
            return dhash_from_image(image, hash_size=hash_size)
    except Exception:  # noqa: BLE001
        return None


def hamming_distance_hex(hash_a: str, hash_b: str) -> int:
    """两个十六进制 dhash 的汉明距离（非法输入返回 1024 表示“完全不同”）。"""
    try:
        return (int(hash_a, 16) ^ int(hash_b, 16)).bit_count()
    except (TypeError, ValueError):
        return 1024


def hashes_within(hash_a: str, hash_b: str, threshold: int) -> bool:
    """判断两个 dhash 是否在阈值内（近重复）。"""
    return hamming_distance_hex(hash_a, hash_b) <= max(0, int(threshold))


# ---------------------------------------------------------------------------
# 文件层检查
# ---------------------------------------------------------------------------

def _file_hit(result: RuleResult, code: str, severity: str, detail: str) -> None:
    result.add(code, severity, detail)


def inspect_image_file(
    path: str | Path,
    *,
    filename: str | None = None,
    max_bytes: int | None = None,
    min_long_edge: int = MIN_LONG_EDGE,
) -> RuleResult:
    """检查本地图片文件：存在性 / 体积 / 类型 / 可解码性 / 尺寸 / 宽高比。"""
    result = RuleResult(checked=True)
    local_path = Path(path) if path else None

    if local_path is None or not str(path).strip():
        _file_hit(result, "file_missing", "block", "照片缺少存储路径")
        return result
    try:
        if not local_path.exists() or not local_path.is_file():
            _file_hit(result, "file_missing", "block", "照片文件不存在或不可读")
            return result
    except OSError as exc:
        _file_hit(result, "file_missing", "block", f"照片文件不可读：{exc.__class__.__name__}")
        return result

    try:
        size = local_path.stat().st_size
    except OSError:
        size = 0
    result.file_size = size
    if size <= 0:
        _file_hit(result, "file_empty", "block", "照片文件为空")
        return result
    if size < MIN_FILE_BYTES:
        _file_hit(result, "file_too_small", "block", f"照片文件过小（{size} B）")
    limit = int(max_bytes if max_bytes is not None else settings.MAX_UPLOAD_SIZE or 0)
    if limit > 0 and size > limit:
        _file_hit(
            result,
            "file_too_large",
            "block",
            f"照片体积 {size / 1024 / 1024:.1f} MB 超过上限 {limit / 1024 / 1024:.1f} MB",
        )

    Image, _ = _pil()
    width = height = 0
    image_format = None
    try:
        with Image.open(local_path) as image:
            image_format = (image.format or "").upper() or None
            width, height = image.size
    except Exception:  # noqa: BLE001
        _file_hit(result, "file_undecodable", "block", "图片无法解码（损坏或非图片文件）")
        return result

    result.width = width
    result.height = height
    result.image_format = image_format

    if image_format and image_format not in ALLOWED_IMAGE_FORMATS:
        _file_hit(result, "file_unsupported_format", "block", f"不支持的图片格式：{image_format}")
    if width <= 0 or height <= 0:
        _file_hit(result, "image_invalid_size", "block", "图片尺寸异常")
    elif max(width, height) < int(min_long_edge):
        _file_hit(result, "image_too_small", "warn", f"图片长边仅 {max(width, height)}px，展示质量不足")
    if width > 0 and height > 0:
        ratio = max(width / height, height / width)
        if ratio > MAX_ASPECT_RATIO:
            _file_hit(result, "image_extreme_aspect", "warn", f"极端宽高比 {ratio:.1f}:1，请确认构图未被裁切")

    # 解码失败的文件不计算哈希，避免把损坏图写入查重缓存
    if not any(hit.code == "file_undecodable" for hit in result.hits):
        try:
            result.dhash = dhash_from_path(local_path)
        except Exception:  # noqa: BLE001
            result.dhash = None
    return result


# ---------------------------------------------------------------------------
# EXIF 隐私检查
# ---------------------------------------------------------------------------

_GPS_KEY_RE = re.compile(r"^(?:gps|location)", re.IGNORECASE)
_PERSONAL_EXIF_KEYS = frozenset(
    {"Artist", "Copyright", "XPAuthor", "XPSubject", "ImageDescription", "UserComment", "OwnerName"}
)
_SOFTWARE_KEYS = ("Software", "ProcessingSoftware", "CreatorTool", "HostComputer")

_AIGC_SOFTWARE_RE = re.compile(
    r"stable\s*diffusion|midjourney|dall[\s·.\-]?e|comfyui|novelai|firefly|flux\.?|imagen|"
    r"sora|runway|krea|leonardo|playground(?:\s*ai)?|generative|ai\s*generat|"
    r"qwen-image|z-image|文心一格|通义万相|即梦|可灵|豆包",
    re.IGNORECASE,
)
_EDITOR_SOFTWARE_RE = re.compile(
    r"photoshop|lightroom|snapseed|vsco|picsart|gimp|affinity|capture\s*one|"
    r"美图|醒图|泼辣|光影魔术手",
    re.IGNORECASE,
)
_AIGC_META_RE = re.compile(
    r"negative[_\s-]?prompt|positive[_\s-]?prompt|prompt\s*[:=]|sampler|cfg[_\s-]?scale|"
    r"model[_\s-]?hash|lora|seed\s*[:=]|steps\s*[:=]|denois",
    re.IGNORECASE,
)
_AIGC_FILENAME_RE = re.compile(
    r"midjourney|dalle|dall-e|stable-?diffusion|sd-?webui|comfyui|novelai|aigc|ai-?gen",
    re.IGNORECASE,
)


def _iter_exif_pairs(exif_data: Any) -> Iterable[tuple[str, Any]]:
    """递归遍历 EXIF dict，产出 (key, value)。"""
    if not isinstance(exif_data, dict):
        return
    for key, value in exif_data.items():
        yield str(key), value
        if isinstance(value, dict):
            for nested_key, nested_value in _iter_exif_pairs(value):
                yield nested_key, nested_value


def detect_exif_privacy_hits(exif_data: dict[str, Any] | None) -> list[RuleHit]:
    """检查 EXIF 隐私风险：GPS 定位（硬拦，入库前应剥离）与可能含真实姓名的字段。"""
    hits: list[RuleHit] = []
    if not exif_data:
        return hits

    gps_keys: list[str] = []
    personal_keys: list[str] = []
    for key, value in _iter_exif_pairs(exif_data):
        if _GPS_KEY_RE.search(key):
            gps_keys.append(key)
            continue
        if key in _PERSONAL_EXIF_KEYS and value not in (None, "", [], {}):
            personal_keys.append(key)

    if gps_keys:
        hits.append(
            RuleHit(
                code="exif_gps_present",
                severity="block",
                detail=f"EXIF 含 GPS 定位信息（{', '.join(sorted(set(gps_keys))[:5])}），入库前必须剥离",
            )
        )
    if personal_keys:
        hits.append(
            RuleHit(
                code="exif_personal_fields",
                severity="warn",
                detail=f"EXIF 含可能识别身份的字段（{', '.join(sorted(set(personal_keys)))}），公开响应已过滤",
            )
        )
    return hits


def detect_aigc_hits(exif_data: dict[str, Any] | None, filename: str | None = None) -> list[RuleHit]:
    """探测生成式 AI 痕迹：EXIF/XMP 软件名、prompt 类字段、文件名线索。"""
    hits: list[RuleHit] = []
    aigc_evidence: list[str] = []
    editor_evidence: list[str] = []

    for key, value in _iter_exif_pairs(exif_data or {}):
        text = str(value) if value is not None else ""
        if not text:
            continue
        if key in _SOFTWARE_KEYS or key.lower() in {k.lower() for k in _SOFTWARE_KEYS}:
            if _AIGC_SOFTWARE_RE.search(text):
                aigc_evidence.append(f"{key}={text[:60]}")
            elif _EDITOR_SOFTWARE_RE.search(text):
                editor_evidence.append(f"{key}={text[:60]}")
        elif _AIGC_SOFTWARE_RE.search(text):
            aigc_evidence.append(f"{key}={text[:60]}")
        elif _AIGC_META_RE.search(f"{key}={text}"):
            aigc_evidence.append(f"{key}")

    if aigc_evidence:
        hits.append(
            RuleHit(
                code="aigc_metadata",
                severity="warn",
                detail="EXIF/XMP 发现 AI 生成痕迹：" + "; ".join(aigc_evidence[:4]),
            )
        )
    if editor_evidence:
        hits.append(
            RuleHit(
                code="exif_editor_hint",
                severity="info",
                detail="EXIF 软件字段显示经过后期处理：" + "; ".join(editor_evidence[:3]),
            )
        )
    if filename and _AIGC_FILENAME_RE.search(filename):
        hits.append(
            RuleHit(
                code="aigc_filename_hint",
                severity="info",
                detail=f"文件名疑似 AI 生成（{filename[:80]}），请核对投稿声明",
            )
        )
    return hits


# ---------------------------------------------------------------------------
# 感知哈希查重
# ---------------------------------------------------------------------------

_DHASH_CACHE: dict[str, str] = {}


def _cache_put(photo_id: str, value: str) -> None:
    if len(_DHASH_CACHE) >= _DHASH_CACHE_LIMIT:
        _DHASH_CACHE.clear()
    _DHASH_CACHE[photo_id] = value


def clear_dhash_cache() -> None:
    """清空进程内 dhash 缓存（测试用）。"""
    _DHASH_CACHE.clear()


def _hash_stored_photo(photo_id: str, thumb_path: str | None, original_path: str | None) -> str:
    """读取已入库照片并计算 dhash（同步，供线程池调用）。"""
    cached = _DHASH_CACHE.get(photo_id)
    if cached is not None:
        return cached
    storage = get_storage()
    for candidate in (thumb_path, original_path):
        if not candidate:
            continue
        try:
            with storage.local_copy(candidate) as local_path:
                value = dhash_from_path(local_path)
            if value:
                _cache_put(photo_id, value)
                return value
        except Exception:  # noqa: BLE001 - 单张读取失败不影响查重整体
            continue
    _cache_put(photo_id, "")
    return ""


async def find_near_duplicates(
    db: AsyncSession,
    target_hash: str | None,
    *,
    exclude_photo_id: str | None = None,
    threshold: int | None = None,
    scan_limit: int = DUPLICATE_SCAN_LIMIT,
) -> list[RuleHit]:
    """与最近入库的照片做 dhash 近重复检测。"""
    if not target_hash:
        return []
    limit = max(1, min(int(scan_limit or DUPLICATE_SCAN_LIMIT), 1000))
    stmt = select(Photo.id, Photo.thumb_path, Photo.original_path).order_by(
        Photo.created_at.desc()
    ).limit(limit)
    if exclude_photo_id:
        stmt = stmt.where(Photo.id != exclude_photo_id)
    try:
        rows = (await db.execute(stmt)).all()
    except Exception:  # noqa: BLE001 - 查重失败不阻断审核
        logger.warning("near duplicate scan failed", exc_info=True)
        return []

    max_distance = int(
        threshold if threshold is not None else settings.MODERATION_DUPLICATE_HAMMING or 5
    )
    hits: list[RuleHit] = []
    for photo_id, thumb_path, original_path in rows:
        candidate = await asyncio.to_thread(_hash_stored_photo, photo_id, thumb_path, original_path)
        if not candidate:
            continue
        distance = hamming_distance_hex(target_hash, candidate)
        if distance <= max_distance:
            hits.append(
                RuleHit(
                    code="near_duplicate",
                    severity="block",
                    detail=(
                        f"与已入库照片 {photo_id} 高度相似（dhash 汉明距离 {distance} ≤ "
                        f"{max_distance}），疑似重复投稿或侵权，需人工确认"
                    ),
                )
            )
            # 一条命中足够触发人工，避免刷屏
            break
    return hits


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------

def _inspect_sync(storage, storage_path: str, filename: str) -> RuleResult:
    """同步版本的规则检查（Pillow 解码 + dhash + EXIF）。

    单独抽出来是为了丢线程池：S3 拉取与 Pillow 解码都是阻塞操作，
    直接在 async 上下文里跑会把事件循环卡住（审核是后台任务但共享同一 loop）。
    """
    with storage.local_copy(storage_path) as local_path:
        return inspect_image_file(local_path, filename=filename)


async def run_rules(db: AsyncSession, photo: Photo) -> RuleResult:
    """对一张照片执行完整规则前置。绝不抛异常，失败降级为 warn 命中。"""
    result = RuleResult()
    try:
        storage_path = photo.original_path or photo.thumb_path
        try:
            result = await asyncio.to_thread(
                _inspect_sync, get_storage(), storage_path, photo.filename
            )
        except (FileNotFoundError, OSError):
            result.checked = True
            result.add("file_missing", "block", "照片文件不存在或不可读")
        except Exception as exc:  # noqa: BLE001
            result.checked = True
            result.add("file_unreadable", "warn", f"照片读取失败：{exc.__class__.__name__}")

        result.extend(detect_exif_privacy_hits(photo.exif_data))
        result.extend(detect_aigc_hits(photo.exif_data, photo.filename))
        if result.dhash and not result.blocked:
            result.extend(
                await find_near_duplicates(db, result.dhash, exclude_photo_id=photo.id)
            )
        return result
    except Exception as exc:  # noqa: BLE001 - 规则层失败绝不阻断上传/审核
        logger.warning("moderation rules failed for photo=%s", getattr(photo, "id", "?"), exc_info=True)
        result.checked = True
        result.add("rule_layer_error", "warn", f"规则层异常降级：{exc.__class__.__name__}")
        return result


__all__ = [
    "RuleHit",
    "RuleResult",
    "SEVERITY_RANK",
    "DHASH_SIZE",
    "dhash_from_image",
    "dhash_from_bytes",
    "dhash_from_path",
    "hamming_distance_hex",
    "hashes_within",
    "inspect_image_file",
    "detect_exif_privacy_hits",
    "detect_aigc_hits",
    "find_near_duplicates",
    "clear_dhash_cache",
    "run_rules",
]
