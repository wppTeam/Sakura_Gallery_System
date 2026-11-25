"""作品派生文件清理。

上传/处理链路会产生多份派生文件：原图、缩略图、压缩图、响应式变体、人像脱敏图。
删除作品（作者主动删除、后台批量清理、账号注销）时必须把它们全部清掉，否则在
2c4g 机器上会迅速堆成孤儿文件。

存储后端通过 ``storage.delete_file()`` 抽象（本地文件 / S3 对象），删除不存在的
路径返回 False，不抛错。
"""
from __future__ import annotations

from typing import Any, Dict

from app.services.image_processing import VARIANT_LONG_EDGES


def variant_meta(photo: Any) -> Dict[str, Any]:
    """读取入库时写入 ``exif_data["_variants"]`` 的档位元信息（内部键）。"""
    exif = photo.exif_data if isinstance(photo.exif_data, dict) else None
    meta = exif.get("_variants") if exif else None
    return meta if isinstance(meta, dict) else {}


def delete_photo_assets(storage: Any, photo: Any) -> int:
    """删除作品关联的全部文件，返回成功删除的文件数。

    变体按约定命名 ``variants/{photo_id}_{size}.{webp|jpg}``；即使缺少
    ``exif_data["_variants"]`` 元信息，也按默认档位尝试删除（老作品兼容）。
    """
    paths = [
        photo.original_path,
        photo.thumb_path,
        photo.processed_path,
        photo.compressed_path,
        photo.redacted_path,
        photo.redacted_thumb_path,
    ]
    sizes = sorted({int(key) for key in variant_meta(photo) if str(key).isdigit()})
    if not sizes:
        sizes = list(VARIANT_LONG_EDGES)
    for size in sizes:
        paths.append(f"variants/{photo.id}_{size}.webp")
        paths.append(f"variants/{photo.id}_{size}.jpg")

    removed = 0
    for path in paths:
        if path and storage.delete_file(path):
            removed += 1
    return removed
