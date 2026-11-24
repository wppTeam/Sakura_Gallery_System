"""以图搜图的探针签名：把上传图变成可参与视觉相似打分的“虚拟作品”。

约束（2c4g 公网环境刻意做轻）：

- 图片**只在内存里**处理，不落盘、不写数据库、不进对象存储；
- 限 8MB、40MP 以内，先看文件头尺寸再解码，避免小体积大像素的图把内存打满；
- 只算 dhash（构图/光影）与光谱色卡（主色调），不调用任何 AI 模型，无 token 成本；
- 无法解码 / 非主流格式 / 尺寸过小直接给用户可读的错误。

探针图没有标签、季节、校区信息，``score_pair`` 会按可用信号归一化，不会因为
缺信号而整体低分。
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from app.services.moderation_rules import dhash_from_bytes
from app.services.spectrum import classify_image_bytes
from app.services.visual_similarity import VisualProbe

# 上传上限 8MB；手机直出 JPEG 一般在 2–6MB。
MAX_PROBE_BYTES = 8 * 1024 * 1024
# 40MP（约 8000×5000）以内；更大的图解码一次就要数百 MB，2c4g 上不接受。
MAX_PROBE_PIXELS = 40_000_000
# 太小的图没有可用的构图信息。
MIN_PROBE_EDGE = 64
_SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ProbeError(ValueError):
    """探针图不可用（调用方据此返回 4xx 的中文提示）。"""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def build_visual_probe(data: bytes) -> VisualProbe:
    """校验上传图并生成探针签名；不可用时抛 ``ProbeError``。"""
    if not data:
        raise ProbeError("请上传一张图片")
    if len(data) > MAX_PROBE_BYTES:
        raise ProbeError("图片不能超过 8MB，请压缩后再试", status_code=413)

    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
    except Exception as exc:  # noqa: BLE001 - 交给用户可读提示
        raise ProbeError("图片无法解析，请换一张试试") from exc

    if image_format not in _SUPPORTED_FORMATS:
        raise ProbeError("仅支持 JPEG / PNG / WebP 图片")
    if min(width, height) < MIN_PROBE_EDGE:
        raise ProbeError("图片太小了，长边至少需要 64 像素")
    if width * height > MAX_PROBE_PIXELS:
        raise ProbeError("图片像素过大（超过 4000 万），请压缩后再试", status_code=413)

    dhash = dhash_from_bytes(data)
    if not dhash:
        raise ProbeError("图片无法解析，请换一张试试")

    exif_data: dict[str, object] = {"_dhash": dhash}
    spectrum = classify_image_bytes(data)
    if spectrum:
        exif_data["_spectrum"] = spectrum

    return VisualProbe(
        id=f"probe-{uuid.uuid4().hex[:12]}",
        exif_data=exif_data,
        width=int(width),
        height=int(height),
    )


def probe_source_label(filename: str | None) -> str:
    """探针图来源说明（响应里回给前端展示，不含临时路径）。"""
    name = Path(filename or "").name
    return name[:120] if name else "上传的图片"
