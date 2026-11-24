"""樱色光谱：按作品主色把作品归入五个色卡（樱粉 / 金 / 绿 / 蓝 / 墨）。

这是「我们自己的东西」之一：不依赖人工选题，用作品自身的色彩自动策展。
实现刻意做得很轻（2c4g 友好，不引入 numpy）：

- 采样用已生成的缩略图 / 原图（640 长边即可），等比缩到 64×64；
- 逐像素转 HSV：低饱和（<0.12）或过暗（<0.18）记入「墨」；
- 其余按色相区间归类，统计占比；主色 = 占比最高的色卡，代表色 = 该类像素均值；
- 采样失败返回 None，调用方只 warning，绝不影响上传/审核。

结果写入 ``photo.exif_data["_spectrum"] = {"palette", "hex", "ratio"}``；
内部键不进公开 EXIF 白名单，对外由 ``GET /api/v1/collections/spectrum`` 暴露色卡元数据。
"""

from __future__ import annotations

import colorsys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Palette:
    key: str
    name: str
    hex: str
    description: str
    slug: str


PALETTES: tuple[Palette, ...] = (
    Palette(
        key="pink",
        name="樱粉",
        hex="#e8628c",
        description="花瓣、暮色与一点点少女感的粉",
        slug="spectrum-pink",
    ),
    Palette(
        key="gold",
        name="金",
        hex="#d99a3d",
        description="阳光、灯与暖色织物，被时间晒过的颜色",
        slug="spectrum-gold",
    ),
    Palette(
        key="green",
        name="绿",
        hex="#4f8f6a",
        description="草木、山野与生长，校园里最不缺的颜色",
        slug="spectrum-green",
    ),
    Palette(
        key="blue",
        name="蓝",
        hex="#5b8fc0",
        description="天空、水面与夜色，安静而开阔",
        slug="spectrum-blue",
    ),
    Palette(
        key="ink",
        name="墨",
        hex="#3a2f35",
        description="低饱和、逆光与静谧的黑，留白最多的那一类",
        slug="spectrum-ink",
    ),
)

PALETTE_BY_KEY: dict[str, Palette] = {p.key: p for p in PALETTES}
SPECTRUM_SLUGS: tuple[str, ...] = tuple(p.slug for p in PALETTES)

_SAMPLE_EDGE = 64

# 采样阈值：只有「有颜色」的像素参与归类；整张图几乎没有彩色时才算「墨」。
# 这样白底的花、逆光的操场仍会归到花色，而真正的灰/黑/雾天归墨。
_MIN_SAT = 0.10
_MIN_VAL = 0.12
_MIN_COLORED_RATIO = 0.25


def _hue_bucket(hue: float) -> str:
    """色相 → 色卡 key（度，0–360）。紫/洋红并入樱粉，避免第六种颜色。"""
    if hue >= 315.0 or hue < 20.0:
        return "pink"
    if hue < 65.0:
        return "gold"
    if hue < 170.0:
        return "green"
    if hue < 260.0:
        return "blue"
    return "pink"


def classify_image(path: str | Path, *, edge: int = _SAMPLE_EDGE) -> dict | None:
    """返回 ``{"palette", "hex", "ratio"}``；无法读取/解码时返回 None。"""
    from PIL import Image

    try:
        with Image.open(path) as im:
            return _classify_pil(im, edge=edge)
    except Exception:  # noqa: BLE001 - 采样失败不应中断业务
        return None


def classify_image_bytes(data: bytes, *, edge: int = _SAMPLE_EDGE) -> dict | None:
    """对图片字节直接采样分类（以图搜图的探针图用，不落盘）。"""
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as im:
            return _classify_pil(im, edge=edge)
    except Exception:  # noqa: BLE001 - 采样失败不应中断业务
        return None


def _classify_pil(im, *, edge: int = _SAMPLE_EDGE) -> dict | None:
    """对已打开的 Pillow 图像采样分类（上传图/本地文件共用）。"""
    from PIL import ImageOps  # 函数内 import：保持模块导入轻量

    try:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB").resize((edge, edge))
        pixels = list(im.getdata())
    except Exception:  # noqa: BLE001 - 采样失败不应中断业务
        return None
    if not pixels:
        return None

    counts: dict[str, int] = defaultdict(int)
    sums: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    colored = 0
    for r, g, b in pixels:
        hue, sat, val = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        if sat < _MIN_SAT or val < _MIN_VAL:
            continue
        colored += 1
        key = _hue_bucket(hue * 360.0)
        counts[key] += 1
        bucket = sums[key]
        bucket[0] += r
        bucket[1] += g
        bucket[2] += b

    total = len(pixels)
    if not colored or colored / total < _MIN_COLORED_RATIO:
        # 几乎没有彩色：算作「墨」，代表色取整图均值
        r = sum(p[0] for p in pixels) // total
        g = sum(p[1] for p in pixels) // total
        b = sum(p[2] for p in pixels) // total
        return {
            "palette": "ink",
            "hex": f"#{r:02x}{g:02x}{b:02x}",
            "ratio": round(max(colored / total, 0.01), 3),
            "coverage": round(colored / total, 3),
        }

    dominant = max(counts, key=lambda k: counts[k])
    r, g, b = (channel // counts[dominant] for channel in sums[dominant])
    return {
        "palette": dominant,
        "hex": f"#{r:02x}{g:02x}{b:02x}",
        "ratio": round(counts[dominant] / colored, 3),
        "coverage": round(colored / total, 3),
    }


def palette_slug(palette_key: str) -> str | None:
    palette = PALETTE_BY_KEY.get(palette_key)
    return palette.slug if palette else None


def spectrum_meta(photo) -> dict | None:
    """从 ``photo.exif_data["_spectrum"]`` 读取光谱元数据（没有则 None）。"""
    exif = getattr(photo, "exif_data", None) or {}
    meta = exif.get("_spectrum") if isinstance(exif, dict) else None
    if not isinstance(meta, dict):
        return None
    if meta.get("palette") not in PALETTE_BY_KEY:
        return None
    return meta
