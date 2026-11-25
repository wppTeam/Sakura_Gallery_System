"""补充检索语料（search_document）维护。

背景
----
``photos.search_tokens`` 由 DB trigger 从 title + description 生成；AI 快筛写入
``exif_data["_ai_caption"]`` 的画面描述此前不可检索（只用于 sitemap/分享卡）。
本模块把「可见文案之外、但值得被搜到」的文本（AI 画面描述 + 自由标签）写进
``photos.search_document``，trigger 会把它一起分词。

设计约束
--------
- 只写自己的列，不依赖调用方事务边界；是否 commit 由调用方决定。
- AI 打标、手动增删标签、回填脚本都必须调用 ``refresh_search_document``，
  否则「过了审、打了标，但搜不到」。
- 图片敏感/未过审时也不会从库里清掉语料：检索 SQL 已经按
  ``status='approved'`` 与 ``privacy_level != 'sensitive'`` 过滤，清空反而
  让重新过审时需要重建。
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import photo as photo_crud
from app.models.photo import Photo

logger = logging.getLogger(__name__)

# AI 画面描述在公开检索里最多取多长（快筛 prompt 要求 ≤40 字，这里留余量）
MAX_CAPTION_CHARS = 200
# AI 打标标签最多写多少（防止异常数据撑爆列）
MAX_TAG_CHARS = 24
MAX_TAG_COUNT = 12


def build_search_document(
    *,
    caption: Optional[str] = None,
    tags: Optional[Iterable[str]] = None,
) -> str:
    """把补充检索语料拼成一段可分词文本（去重、限长、稳定顺序）。"""
    parts: list[str] = []

    if isinstance(caption, str) and caption.strip():
        parts.append(caption.strip()[:MAX_CAPTION_CHARS])

    seen: set[str] = set()
    for raw in tags or []:
        if not isinstance(raw, str):
            continue
        name = raw.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        parts.append(name[:MAX_TAG_CHARS])
        if len(seen) >= MAX_TAG_COUNT:
            break

    return " ".join(parts)


def photo_caption(photo: Photo) -> Optional[str]:
    """读取 AI 快筛写入的画面描述（内部键，不进公开 EXIF 白名单）。"""
    exif = photo.exif_data if isinstance(photo.exif_data, dict) else None
    if not exif:
        return None
    raw = exif.get("_ai_caption")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


async def refresh_search_document(db: AsyncSession, photo: Photo) -> str:
    """重算并写入 ``photo.search_document``，返回写入的文本（可能为空串）。

    调用方负责 ``db.commit()``；同一事务里连续调用是幂等的。
    """
    tags = await photo_crud.get_photo_tags(db, photo.id)
    document = build_search_document(
        caption=photo_caption(photo),
        tags=[tag.name for tag in tags],
    )
    if (photo.search_document or "") != document:
        photo.search_document = document or None
        db.add(photo)
        # 让 trigger 在本事务内就能刷新 search_tokens，便于随即进行检索断言
        await db.flush()
    return document


async def refresh_all_search_documents(
    db: AsyncSession,
    *,
    limit: Optional[int] = None,
    commit_every: int = 50,
) -> dict[str, int]:
    """批量回填（脚本/迁移后使用）；逐张刷新并分批 commit。"""
    stmt = select(Photo).order_by(Photo.created_at.asc())
    if limit:
        stmt = stmt.limit(limit)
    photos = list((await db.execute(stmt)).scalars().all())

    scanned = 0
    updated = 0
    for photo in photos:
        scanned += 1
        before = photo.search_document
        await refresh_search_document(db, photo)
        if photo.search_document != before:
            updated += 1
        if commit_every > 0 and scanned % commit_every == 0:
            await db.commit()

    await db.commit()
    return {"scanned": scanned, "updated": updated}
