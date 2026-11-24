"""策展专题（album）公开接口。

- `GET /api/v1/collections/public` 列出已发布专题（编辑策展 + 用户公开专辑）；
- `GET /api/v1/collections/{slug}` 专题详情：叙事信息 + 有序作品 + 上一/下一专题。

性能约定（2c4g）：列表接口固定 2 条查询（专题 + 已审核条目），封面作品按 id
批量取回后统一序列化；不逐专题查数据库。作品复用公开序列化（隐私白名单）。
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.photos import serialize_photo
from app.core.deps import get_db
from app.crud.photo import _photo_with_relations
from app.models import Collection, CollectionPhoto, Photo
from app.schemas.collection import (
    CollectionDetail,
    CollectionListResponse,
    CollectionSummary,
)
from app.schemas.photo import PhotoResponse

router = APIRouter()

_MAX_LIMIT = 50


async def _approved_entries(
    db: AsyncSession, collection_ids: list[str]
) -> dict[str, list[str]]:
    """返回 {collection_id: [photo_id...]}，只含 approved 且按 position 排序。"""
    if not collection_ids:
        return {}
    rows = (
        await db.execute(
            select(CollectionPhoto.collection_id, CollectionPhoto.photo_id)
            .join(Photo, Photo.id == CollectionPhoto.photo_id)
            .where(
                CollectionPhoto.collection_id.in_(collection_ids),
                Photo.status == "approved",
                # 人像隐私：sensitive 作品不进专题展示（脱敏图也不进，避免扩散）
                or_(Photo.privacy_level.is_(None), Photo.privacy_level != "sensitive"),
            )
            .order_by(
                CollectionPhoto.collection_id,
                CollectionPhoto.position,
                CollectionPhoto.added_at,
            )
        )
    ).all()
    grouped: dict[str, list[str]] = defaultdict(list)
    for collection_id, photo_id in rows:
        grouped[collection_id].append(photo_id)
    return grouped


async def _photos_by_id(db: AsyncSession, photo_ids: list[str]) -> dict[str, Photo]:
    if not photo_ids:
        return {}
    rows = (
        await db.execute(
            select(Photo).options(*_photo_with_relations()).where(Photo.id.in_(photo_ids))
        )
    ).scalars().all()
    return {photo.id: photo for photo in rows}


def _pick_cover_id(collection: Collection, approved: list[str]) -> str | None:
    if collection.cover_photo_id and collection.cover_photo_id in approved:
        return collection.cover_photo_id
    return approved[0] if approved else None


async def _serialize_cover(
    db: AsyncSession,
    collection: Collection,
    approved: list[str],
    photo_map: dict[str, Photo],
) -> PhotoResponse | None:
    cover_id = _pick_cover_id(collection, approved)
    if not cover_id:
        return None
    photo = photo_map.get(cover_id)
    if photo is None:
        photo = (
            await db.execute(
                select(Photo).options(*_photo_with_relations()).where(Photo.id == cover_id)
            )
        ).scalars().first()
    if photo is None or photo.status != "approved":
        return None
    return await serialize_photo(db, photo)


async def _published_collections(db: AsyncSession) -> list[Collection]:
    rows = (
        await db.execute(
            select(Collection)
            .where(Collection.status == "published", Collection.visibility == "public")
            .order_by(Collection.sort_order.asc(), Collection.created_at.asc())
        )
    ).scalars().all()
    return list(rows)


@router.get("/public", response_model=CollectionListResponse)
async def list_public_collections(
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0, le=2000),
    db: AsyncSession = Depends(get_db),
) -> CollectionListResponse:
    """专题列表（首页「主题专题」横滑卡区使用）。"""
    collections = await _published_collections(db)
    total = len(collections)
    page = collections[offset : offset + limit]

    entries = await _approved_entries(db, [c.id for c in page])
    cover_ids = [
        cover_id
        for c in page
        if (cover_id := _pick_cover_id(c, entries.get(c.id, []))) is not None
    ]
    photo_map = await _photos_by_id(db, cover_ids)

    items: list[CollectionSummary] = []
    for collection in page:
        approved = entries.get(collection.id, [])
        cover = await _serialize_cover(db, collection, approved, photo_map)
        items.append(
            CollectionSummary(
                id=collection.id,
                slug=collection.slug,
                title=collection.title,
                subtitle=collection.subtitle,
                kind=collection.kind,
                sort_order=collection.sort_order,
                photo_count=len(approved),
                cover=cover,
            )
        )
    return CollectionListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{slug}", response_model=CollectionDetail)
async def get_public_collection(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> CollectionDetail:
    """专题详情：叙事 + 有序作品 + 上下篇。"""
    collection = (
        await db.execute(
            select(Collection).where(
                Collection.slug == slug,
                Collection.status == "published",
                Collection.visibility == "public",
            )
        )
    ).scalars().first()
    if collection is None:
        raise HTTPException(status_code=404, detail="专题不存在或未发布")

    entries = await _approved_entries(db, [collection.id])
    approved = entries.get(collection.id, [])
    photo_map = await _photos_by_id(db, approved)

    photos: list[PhotoResponse] = []
    for photo_id in approved:
        photo = photo_map.get(photo_id)
        if photo is None:
            continue
        photos.append(await serialize_photo(db, photo))

    cover = await _serialize_cover(db, collection, approved, photo_map)

    ordered = await _published_collections(db)
    slugs = [c.slug for c in ordered]
    index = slugs.index(collection.slug) if collection.slug in slugs else -1
    prev_slug = slugs[index - 1] if index > 0 else None
    next_slug = slugs[index + 1] if 0 <= index < len(slugs) - 1 else None

    return CollectionDetail(
        id=collection.id,
        slug=collection.slug,
        title=collection.title,
        subtitle=collection.subtitle,
        description=collection.description,
        kind=collection.kind,
        sort_order=collection.sort_order,
        photo_count=len(photos),
        cover=cover,
        photos=photos,
        prev_slug=prev_slug,
        next_slug=next_slug,
    )


# ── 作品 → 所属专题（详情页「收录于」chips）─────────────────────────────
photo_router = APIRouter()


@photo_router.get("/{photo_id}/collections")
async def list_collections_for_photo(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回收录该作品的已发布专题（精简字段，详情页展示用）。"""
    rows = (
        await db.execute(
            select(Collection.slug, Collection.title, Collection.kind)
            .join(CollectionPhoto, CollectionPhoto.collection_id == Collection.id)
            .join(Photo, Photo.id == CollectionPhoto.photo_id)
            .where(
                CollectionPhoto.photo_id == photo_id,
                Photo.status == "approved",
                Collection.status == "published",
                Collection.visibility == "public",
            )
            .order_by(Collection.sort_order.asc())
        )
    ).all()
    return {
        "items": [
            {"slug": slug, "title": title, "kind": kind} for slug, title, kind in rows
        ]
    }
