"""作品导航：详情页「上一张 / 下一张」与灯箱胶片条的数据来源。

详情页原本只展示单张作品，看下一张必须返回列表。这里按「上下文」给出相邻
作品序列，让浏览可以像观展一样连续：

- ``latest``：全站公开作品的最新流（``coalesce(published_at, created_at)`` 倒序）；
- ``collection:<slug>``：某个公开专题内的策展顺序（``collection_photos.position``）。

设计取舍：

- 只返回**紧凑字段**（id / 标题 / 宽高 / AIGC 角标 / LQIP 色）而不是完整
  ``PhotoResponse``：胶片条一次要 10 张左右，完整序列化会白传十几个 KB 的
  EXIF / 变体 / 标签，而前端缩略图 URL 本来就能由 id 拼出来。
- 候选集与公开列表一致：``approved`` 且 ``privacy_level`` 不是 ``sensitive``，
  避免从导航里泄漏人像作品的轮廓。
- ``latest`` 用 keyset 查询（四条小 SQL：总数、位置、向前窗口、向后窗口），
  不把所有 id 拉进内存；专题最多 100 件，直接一次查完再切窗口。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionPhoto
from app.models.photo import Photo

#: 当前作品前后各最多取几张（胶片条窗口），与前端保持宽松上限即可。
MAX_SIDE_ITEMS = 8
DEFAULT_SIDE_ITEMS = 5

CONTEXT_LATEST = "latest"
CONTEXT_COLLECTION = "collection"

_PUBLIC_STATUS = "approved"
_PRIVACY_NORMAL = "normal"


@dataclass(frozen=True)
class NavContext:
    """当前作品所处的上下文（前端显示「最新发布」/「专题名」与「3 / 24」）。"""

    kind: str
    slug: Optional[str]
    title: Optional[str]
    position: int
    total: int


@dataclass(frozen=True)
class Neighbors:
    """相邻作品窗口。

    ``items`` 包含当前作品本身（在 ``index`` 位置），前端胶片条可以直接渲染；
    ``prev_id`` / ``next_id`` 是相对于当前作品的紧邻作品（可能落在窗口之外，
    翻页时前端据此跳转并重新取一次导航）。
    """

    context: NavContext
    items: list[Photo]
    index: int
    prev_id: Optional[str]
    next_id: Optional[str]


def parse_context(value: Optional[str]) -> tuple[str, Optional[str]]:
    """把 ``collection:<slug>`` 解析成 (kind, slug)；其它值都当 latest。"""
    if value and value.startswith(f"{CONTEXT_COLLECTION}:"):
        slug = value.split(":", 1)[1].strip()
        if slug:
            return CONTEXT_COLLECTION, slug
    return CONTEXT_LATEST, None


def _clamp_side(value: int, default: int = DEFAULT_SIDE_ITEMS) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(parsed, MAX_SIDE_ITEMS))


def _published_key():
    """作品在最新流里的排序键：优先发布时间，老数据回退创建时间。"""
    return func.coalesce(Photo.published_at, Photo.created_at)


def _public_filters():
    return (
        Photo.status == _PUBLIC_STATUS,
        func.coalesce(Photo.privacy_level, _PRIVACY_NORMAL) == _PRIVACY_NORMAL,
    )


async def _latest_neighbors(
    db: AsyncSession,
    photo: Photo,
    *,
    before: int,
    after: int,
) -> Neighbors:
    key = _published_key()
    target_key = photo.published_at or photo.created_at
    base = _public_filters()

    total = int(
        await db.scalar(select(func.count()).select_from(Photo).where(*base)) or 0
    )

    newer_cond = or_(key > target_key, and_(key == target_key, Photo.id > photo.id))
    older_cond = or_(key < target_key, and_(key == target_key, Photo.id < photo.id))

    position = 1 + int(
        await db.scalar(
            select(func.count()).select_from(Photo).where(*base, newer_cond)
        )
        or 0
    )

    newer_rows = list(
        (
            await db.execute(
                select(Photo)
                .where(*base, newer_cond)
                .order_by(key.asc(), Photo.id.asc())
                .limit(before)
            )
        )
        .scalars()
        .all()
    )
    older_rows = list(
        (
            await db.execute(
                select(Photo)
                .where(*base, older_cond)
                .order_by(key.desc(), Photo.id.desc())
                .limit(after)
            )
        )
        .scalars()
        .all()
    )

    # newer_rows 是「离当前由近到远」，渲染顺序要按序列正序，这里翻转。
    items = list(reversed(newer_rows)) + [photo] + older_rows
    return Neighbors(
        context=NavContext(
            kind=CONTEXT_LATEST,
            slug=None,
            title="最新发布",
            position=position,
            total=total,
        ),
        items=items,
        index=len(newer_rows),
        prev_id=newer_rows[0].id if newer_rows else None,
        next_id=older_rows[0].id if older_rows else None,
    )


async def _collection_neighbors(
    db: AsyncSession,
    photo: Photo,
    *,
    slug: str,
    before: int,
    after: int,
) -> Optional[Neighbors]:
    collection = await db.scalar(
        select(Collection).where(
            Collection.slug == slug,
            Collection.status == "published",
            Collection.visibility == "public",
        )
    )
    if collection is None:
        return None

    ordered = list(
        (
            await db.execute(
                select(Photo)
                .join(CollectionPhoto, CollectionPhoto.photo_id == Photo.id)
                .where(CollectionPhoto.collection_id == collection.id, *_public_filters())
                .order_by(CollectionPhoto.position.asc(), CollectionPhoto.added_at.asc())
            )
        )
        .scalars()
        .all()
    )
    index = next(
        (idx for idx, item in enumerate(ordered) if item.id == photo.id), None
    )
    if index is None:
        # 当前作品不在这个专题里（例如被移出，或本身是人像敏感作品），
        # 退化为全站最新流，避免详情页出现空导航。
        return None

    start = max(0, index - before)
    end = min(len(ordered), index + after + 1)
    items = ordered[start:end]
    return Neighbors(
        context=NavContext(
            kind=CONTEXT_COLLECTION,
            slug=collection.slug,
            title=collection.title,
            position=index + 1,
            total=len(ordered),
        ),
        items=items,
        index=index - start,
        prev_id=ordered[index - 1].id if index > 0 else None,
        next_id=ordered[index + 1].id if index + 1 < len(ordered) else None,
    )


async def get_neighbors(
    db: AsyncSession,
    photo: Photo,
    *,
    context: Optional[str] = None,
    before: int = DEFAULT_SIDE_ITEMS,
    after: int = DEFAULT_SIDE_ITEMS,
) -> Neighbors:
    """返回当前作品的相邻序列；``context`` 不可用时退回全站最新流。

    调用方负责作品本身的可见性判断（与 ``GET /photos/public/{id}`` 一致），
    这里只保证候选项不会把待审 / 人像敏感作品带出去。
    """

    kind, slug = parse_context(context)
    side_before = _clamp_side(before)
    side_after = _clamp_side(after)

    if kind == CONTEXT_COLLECTION and slug:
        result = await _collection_neighbors(
            db, photo, slug=slug, before=side_before, after=side_after
        )
        if result is not None:
            return result

    return await _latest_neighbors(db, photo, before=side_before, after=side_after)
