"""人像隐私分级与脱敏。

规则（AGENTS.md §5 肖像权）：
- 含可识别人像的作品标记为 ``privacy_level="sensitive"``；
- sensitive 作品默认不进公共列表；对外只提供强模糊脱敏图；
- 原图 / 下载仅作者本人与 admin/auditor 可见；
- 脱敏图生成失败不阻断审核，但会在 ``exif_data["_privacy"]`` 记录 error，
  公共接口在缺脱敏图时拒绝返回该作品（宁可不展示，也不泄露原图）。
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo
from app.models.user import User

logger = logging.getLogger(__name__)

PRIVACY_NORMAL = "normal"
PRIVACY_SENSITIVE = "sensitive"
PRIVACY_LEVELS = (PRIVACY_NORMAL, PRIVACY_SENSITIVE)


def is_sensitive(photo: Photo) -> bool:
    return (photo.privacy_level or PRIVACY_NORMAL) == PRIVACY_SENSITIVE


def has_redacted_media(photo: Photo) -> bool:
    return bool(photo.redacted_path and photo.redacted_thumb_path)


def is_owner_or_reviewer(photo: Photo, user: Optional[User]) -> bool:
    if user is None:
        return False
    if user.role in ("admin", "auditor"):
        return True
    return photo.uploader_id == user.id


def should_redact_for_viewer(photo: Photo, user: Optional[User]) -> bool:
    """公开/登录用户看 sensitive 作品时只给脱敏图；作者与审核员看原图。"""
    return is_sensitive(photo) and not is_owner_or_reviewer(photo, user)


def _privacy_meta(photo: Photo) -> dict[str, Any]:
    exif = photo.exif_data if isinstance(photo.exif_data, dict) else {}
    meta = exif.get("_privacy")
    return dict(meta) if isinstance(meta, dict) else {}


def _write_privacy_meta(photo: Photo, meta: dict[str, Any]) -> None:
    exif = dict(photo.exif_data or {})
    exif["_privacy"] = meta
    photo.exif_data = exif


def _generate_redacted_sync(photo_id: str, original_path: str) -> dict[str, Optional[str]]:
    from app.services.image_processing import create_redacted_images
    from app.services.storage import get_storage

    storage = get_storage()
    with storage.local_copy(original_path) as local_path:
        with tempfile.TemporaryDirectory(prefix="sakura-redact-") as tmp_dir:
            images = create_redacted_images(local_path, tmp_dir, photo_id)
            return storage.persist_redacted(
                photo_id,
                images.get("redacted", {}).get("path"),
                images.get("redacted_thumb", {}).get("path"),
            )


async def ensure_redacted_images(
    db: AsyncSession, photo: Photo, *, force: bool = False
) -> bool:
    """确保 sensitive 作品有脱敏图；成功返回 True（失败只记 warning，不抛）。"""
    if not is_sensitive(photo):
        return False
    if has_redacted_media(photo) and not force:
        return True
    if not photo.original_path:
        return False
    meta = _privacy_meta(photo)
    try:
        import asyncio

        persisted = await asyncio.to_thread(
            _generate_redacted_sync, photo.id, photo.original_path
        )
        photo.redacted_path = persisted.get("redacted_path")
        photo.redacted_thumb_path = persisted.get("redacted_thumb_path")
        meta.update(
            {
                "level": PRIVACY_SENSITIVE,
                "redacted_at": datetime.utcnow().isoformat(timespec="seconds"),
                "error": None,
            }
        )
        _write_privacy_meta(photo, meta)
        await db.flush()
        return has_redacted_media(photo)
    except Exception as exc:  # noqa: BLE001 - 脱敏失败不应阻断审核主流程
        logger.warning("生成脱敏图失败 photo=%s: %s", photo.id, exc, exc_info=True)
        meta.update({"level": PRIVACY_SENSITIVE, "error": f"{exc.__class__.__name__}: {exc}"[:300]})
        _write_privacy_meta(photo, meta)
        await db.flush()
        return False


async def mark_photo_sensitive(
    db: AsyncSession, photo: Photo, *, reason: str, redact: bool = True
) -> bool:
    """标记为含可识别人像，并（默认）生成脱敏图。返回脱敏图是否就绪。"""
    if not is_sensitive(photo):
        photo.privacy_level = PRIVACY_SENSITIVE
    meta = _privacy_meta(photo)
    meta.setdefault("reason", reason)
    meta["level"] = PRIVACY_SENSITIVE
    meta.setdefault("marked_at", datetime.utcnow().isoformat(timespec="seconds"))
    _write_privacy_meta(photo, meta)
    if not redact:
        return has_redacted_media(photo)
    return await ensure_redacted_images(db, photo)


__all__ = [
    "PRIVACY_NORMAL",
    "PRIVACY_SENSITIVE",
    "ensure_redacted_images",
    "has_redacted_media",
    "is_owner_or_reviewer",
    "is_sensitive",
    "mark_photo_sensitive",
    "should_redact_for_viewer",
]
