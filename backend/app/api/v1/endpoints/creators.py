"""公开创作者主页（/api/v1/creators）。

浏览者从作品详情点作者名进来，能看到这个创作者的全部公开作品、作品总数、
被浏览/被收藏的累计数，以及 ta 自己发布的作品集（作者手账）。
`GET /api/v1/creators` 是公开创作者名录（按作品数/浏览数排序），首页与
/creators 页用它做「发现创作者」入口。

隐私约定：
- 只按 username 查询，只暴露 username / display_name / 加入时间；
- 计数只统计「已通过 + 非敏感」的作品，与公开列表口径一致；
- 不返回学号、真实姓名、邮箱等身份字段。
"""
from typing import Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.photos import _neighbor_item, serialize_photo
from app.core.deps import get_db
from app.crud import photo as photo_crud
from app.crud.photo import _photo_with_relations
from app.models.collection import Collection, CollectionPhoto
from app.models.favorite import Favorite
from app.models.photo import Photo
from app.models.user import User
from app.schemas.creator import (
    CreatorCard,
    CreatorCollectionCard,
    CreatorListResponse,
    CreatorProfile,
    CreatorResponse,
    CreatorWorkList,
)

router = APIRouter()

MAX_WORKS_LIMIT = 50
DEFAULT_WORKS_LIMIT = 12
MAX_COLLECTIONS_LIMIT = 12
DEFAULT_COLLECTIONS_LIMIT = 6
DIRECTORY_DEFAULT_LIMIT = 12
DIRECTORY_MAX_LIMIT = 50
DIRECTORY_MAX_COVERS = 3


def _public_photo_filters(user_id: str):
    """公开作品口径：作者本人 + 已通过 + 非敏感。"""
    return (
        Photo.uploader_id == user_id,
        Photo.status == "approved",
        or_(Photo.privacy_level.is_(None), Photo.privacy_level != "sensitive"),
    )


async def _get_creator(db: AsyncSession, username: str) -> User:
    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="Creator not found")
    return user


async def _count_public_works(db: AsyncSession, user_id: str) -> int:
    total = (
        await db.execute(
            select(func.count(Photo.id)).where(*_public_photo_filters(user_id))
        )
    ).scalar()
    return int(total or 0)


async def _load_works(
    db: AsyncSession, user: User, *, limit: int, offset: int
) -> Tuple[List, int]:
    """复用公开列表的查询（eager-load 分类），只按作者过滤。"""
    photos, total = await photo_crud.get_photos(
        db,
        skip=offset,
        limit=limit,
        uploader_id=user.id,
        status="approved",
        exclude_sensitive=True,
        sort_by="created_at",
        sort_order="desc",
    )
    items = []
    for photo in photos:
        items.append(
            await serialize_photo(db, photo, uploader_username=user.username)
        )
    return items, int(total or 0)


async def _load_collections(
    db: AsyncSession, user: User, *, limit: int
) -> List[CreatorCollectionCard]:
    """作者手账里「已发布 + 公开 + 至少一张公开作品」的作品集。"""
    collections = (
        (
            await db.execute(
                select(Collection)
                .where(
                    Collection.owner_id == user.id,
                    Collection.kind == "user",
                    Collection.status == "published",
                    Collection.visibility == "public",
                )
                .order_by(Collection.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    if not collections:
        return []
    ids = [collection.id for collection in collections]

    rows = (
        await db.execute(
            select(CollectionPhoto.collection_id, CollectionPhoto.photo_id)
            .join(Photo, Photo.id == CollectionPhoto.photo_id)
            .where(
                CollectionPhoto.collection_id.in_(ids),
                Photo.status == "approved",
                or_(Photo.privacy_level.is_(None), Photo.privacy_level != "sensitive"),
            )
            .order_by(
                CollectionPhoto.collection_id,
                CollectionPhoto.position,
                CollectionPhoto.added_at,
            )
        )
    ).all()

    counts: Dict[str, int] = {}
    cover_ids: Dict[str, str] = {}
    for collection_id, photo_id in rows:
        counts[collection_id] = counts.get(collection_id, 0) + 1
        cover_ids.setdefault(collection_id, photo_id)

    covers: Dict[str, object] = {}
    if cover_ids:
        cover_photos = (
            (
                await db.execute(
                    select(Photo)
                    .options(*_photo_with_relations())
                    .where(Photo.id.in_(set(cover_ids.values())))
                )
            )
            .scalars()
            .all()
        )
        cover_map = {photo.id: photo for photo in cover_photos}
        for collection_id, photo_id in cover_ids.items():
            photo = cover_map.get(photo_id)
            if photo is not None:
                covers[collection_id] = await serialize_photo(
                    db, photo, uploader_username=user.username
                )

    cards: List[CreatorCollectionCard] = []
    for collection in collections:
        count = counts.get(collection.id, 0)
        if count == 0:
            continue
        cards.append(
            CreatorCollectionCard(
                slug=collection.slug,
                title=collection.title,
                subtitle=collection.subtitle,
                photo_count=count,
                cover=covers.get(collection.id),  # type: ignore[arg-type]
            )
        )
        if len(cards) >= limit:
            break
    return cards


async def _build_profile(
    db: AsyncSession, user: User, *, collections_count: int
) -> CreatorProfile:
    filters = _public_photo_filters(user.id)
    works_count = (
        await db.execute(select(func.count(Photo.id)).where(*filters))
    ).scalar() or 0
    views_total = (
        await db.execute(select(func.coalesce(func.sum(Photo.views), 0)).where(*filters))
    ).scalar() or 0
    favorites_total = (
        await db.execute(
            select(func.count(Favorite.id))
            .join(Photo, Photo.id == Favorite.photo_id)
            .where(*filters)
        )
    ).scalar() or 0
    return CreatorProfile(
        username=user.username or "",
        display_name=user.display_name or user.username,
        joined_at=user.created_at,
        works_count=int(works_count),
        views_total=int(views_total),
        favorites_total=int(favorites_total),
        collections_count=collections_count,
    )


async def _load_directory(
    db: AsyncSession,
    *,
    sort: str,
    limit: int,
    offset: int,
) -> CreatorListResponse:
    """公开创作者名录：只看「有公开作品」的启用账号。

    计数口径与主页一致（approved + 非敏感）；封面取每位创作者最新的
    ≤3 张公开作品，用紧凑的 PhotoNeighborItem（不带 EXIF / 变体）。
    """
    public_where = (
        Photo.status == "approved",
        or_(Photo.privacy_level.is_(None), Photo.privacy_level != "sensitive"),
    )
    stats = (
        select(
            Photo.uploader_id.label("uploader_id"),
            func.count(Photo.id).label("works_count"),
            func.coalesce(func.sum(Photo.views), 0).label("views_total"),
        )
        .where(*public_where)
        .group_by(Photo.uploader_id)
        .subquery()
    )
    base = (
        select(
            User.id,
            User.username,
            User.display_name,
            User.created_at,
            stats.c.works_count,
            stats.c.views_total,
        )
        .join(stats, stats.c.uploader_id == User.id)
        .where(User.is_active.is_(True))
    )
    if sort == "views":
        order_by = (
            stats.c.views_total.desc(),
            stats.c.works_count.desc(),
            User.created_at.asc(),
        )
    else:
        order_by = (
            stats.c.works_count.desc(),
            stats.c.views_total.desc(),
            User.created_at.asc(),
        )
    rows = (
        await db.execute(base.order_by(*order_by).limit(limit).offset(offset))
    ).all()
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar() or 0

    covers: Dict[str, List] = {}
    if rows:
        user_ids = [row.id for row in rows]
        photo_rows = (
            (
                await db.execute(
                    select(Photo)
                    .where(Photo.uploader_id.in_(user_ids), *public_where)
                    .order_by(
                        Photo.uploader_id,
                        func.coalesce(Photo.published_at, Photo.created_at).desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        for photo in photo_rows:
            bucket = covers.setdefault(photo.uploader_id, [])
            if len(bucket) < DIRECTORY_MAX_COVERS:
                bucket.append(_neighbor_item(photo))

    items = [
        CreatorCard(
            username=row.username or "",
            display_name=row.display_name or row.username,
            joined_at=row.created_at,
            works_count=int(row.works_count or 0),
            views_total=int(row.views_total or 0),
            covers=covers.get(row.id, []),
        )
        for row in rows
        if row.username
    ]
    return CreatorListResponse(
        items=items, total=int(total), limit=limit, offset=offset
    )


async def _load_creator(
    db: AsyncSession,
    username: str,
    *,
    works_limit: int,
    works_offset: int,
    collections_limit: int,
) -> CreatorResponse:
    user = await _get_creator(db, username)
    collections = await _load_collections(db, user, limit=collections_limit)
    profile = await _build_profile(db, user, collections_count=len(collections))
    items, total = await _load_works(
        db, user, limit=works_limit, offset=works_offset
    )
    return CreatorResponse(
        profile=profile,
        works=CreatorWorkList(
            items=items, total=total, limit=works_limit, offset=works_offset
        ),
        collections=collections,
    )


@router.get("", response_model=CreatorListResponse)
async def list_creators(
    sort: Literal["works", "views"] = Query(
        "works", description="works=按公开作品数，views=按累计浏览数"
    ),
    limit: int = Query(DIRECTORY_DEFAULT_LIMIT, ge=1, le=DIRECTORY_MAX_LIMIT),
    offset: int = Query(0, ge=0, le=5000),
    db: AsyncSession = Depends(get_db),
) -> CreatorListResponse:
    """公开创作者名录（发现页 / 首页创作者 rail 共用）。"""
    return await _load_directory(db, sort=sort, limit=limit, offset=offset)


@router.get("/{username}", response_model=CreatorResponse)
async def get_creator(
    username: str,
    works_limit: int = Query(DEFAULT_WORKS_LIMIT, ge=1, le=MAX_WORKS_LIMIT),
    works_offset: int = Query(0, ge=0, le=5000),
    collections_limit: int = Query(
        DEFAULT_COLLECTIONS_LIMIT, ge=0, le=MAX_COLLECTIONS_LIMIT
    ),
    db: AsyncSession = Depends(get_db),
) -> CreatorResponse:
    """创作者主页首屏：个人资料 + 第一页作品 + 作品集 rail。"""
    return await _load_creator(
        db,
        username,
        works_limit=works_limit,
        works_offset=works_offset,
        collections_limit=collections_limit,
    )


@router.get("/{username}/works", response_model=CreatorWorkList)
async def list_creator_works(
    username: str,
    limit: int = Query(DEFAULT_WORKS_LIMIT, ge=1, le=MAX_WORKS_LIMIT),
    offset: int = Query(0, ge=0, le=5000),
    db: AsyncSession = Depends(get_db),
) -> CreatorWorkList:
    """创作者作品分页（「加载更多」用）。"""
    user = await _get_creator(db, username)
    items, total = await _load_works(db, user, limit=limit, offset=offset)
    return CreatorWorkList(items=items, total=total, limit=limit, offset=offset)
