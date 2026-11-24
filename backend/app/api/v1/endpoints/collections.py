"""策展专题（album）公开接口。

- `GET /api/v1/collections/public` 列出已发布专题（编辑策展 + 用户公开专辑）；
- `GET /api/v1/collections/{slug}` 专题详情：叙事信息 + 有序作品 + 上一/下一专题。

性能约定（2c4g）：列表接口固定 2 条查询（专题 + 已审核条目），封面作品按 id
批量取回后统一序列化；不逐专题查数据库。作品复用公开序列化（隐私白名单）。
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status as http_status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.photos import serialize_photo
from app.core.deps import get_current_user, get_db
from app.crud.photo import _photo_with_relations
from app.models import Collection, CollectionPhoto, Photo, User
from app.schemas.collection import (
    CollectionCreate,
    CollectionDetail,
    CollectionListResponse,
    CollectionMineResponse,
    CollectionOwnerBrief,
    CollectionPhotosUpdate,
    CollectionSummary,
    CollectionUpdate,
    CuratorAssistResponse,
    CuratorAssistRequest,
    CuratorPickItem,
    LightPeriodResponse,
    LightPeriodsResponse,
    SpectrumResponse,
    SpectrumSwatch,
)
from app.schemas.photo import PhotoResponse
from app.services.ai_client import AIError
from app.services.audit import log_audit
from app.services.curation_assistant import propose_collection
from app.services.light_of_day import LIGHT_PERIODS
from app.services.spectrum import PALETTES, SPECTRUM_SLUGS

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

_MAX_LIMIT = 50
_MAX_USER_COLLECTIONS = 50
_USER_COLLECTION_SORT_BASE = 1000


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


async def _owners_by_id(
    db: AsyncSession, owner_ids: list[str | None]
) -> dict[str, CollectionOwnerBrief]:
    ids = {oid for oid in owner_ids if oid}
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(User.id, User.username, User.display_name).where(User.id.in_(ids))
        )
    ).all()
    return {
        row[0]: CollectionOwnerBrief(username=row[1], display_name=row[2])
        for row in rows
    }


def _is_admin(user: User) -> bool:
    return getattr(user, "role", None) == "admin"


async def _entries_all(db: AsyncSession, collection_id: str) -> list[str]:
    """按 position 返回专辑内全部作品 id（不过滤审核状态，编辑页用）。"""
    rows = (
        await db.execute(
            select(CollectionPhoto.photo_id)
            .where(CollectionPhoto.collection_id == collection_id)
            .order_by(CollectionPhoto.position.asc(), CollectionPhoto.added_at.asc())
        )
    ).scalars().all()
    return list(rows)


async def _build_detail(
    db: AsyncSession,
    collection: Collection,
    *,
    approved_only: bool = True,
    owner_map: dict[str, CollectionOwnerBrief] | None = None,
) -> CollectionDetail:
    """组装专题详情；编辑场景传 ``approved_only=False`` 以看到未审核作品。"""
    if approved_only:
        approved = (await _approved_entries(db, [collection.id])).get(collection.id, [])
    else:
        approved = await _entries_all(db, collection.id)

    photo_map = await _photos_by_id(db, approved)
    photos: list[PhotoResponse] = []
    for photo_id in approved:
        photo = photo_map.get(photo_id)
        if photo is None:
            continue
        if approved_only and photo.status != "approved":
            continue
        photos.append(await serialize_photo(db, photo))

    if owner_map is None:
        owner_map = await _owners_by_id(db, [collection.owner_id])
    owner = owner_map.get(collection.owner_id) if collection.owner_id else None

    cover = await _serialize_cover(
        db, collection, [photo.id for photo in photos], photo_map
    )

    prev_slug = next_slug = None
    if collection.status == "published" and collection.visibility == "public":
        ordered = await _published_collections(db)
        slugs = [c.slug for c in ordered]
        if collection.slug in slugs:
            index = slugs.index(collection.slug)
            prev_slug = slugs[index - 1] if index > 0 else None
            next_slug = slugs[index + 1] if index < len(slugs) - 1 else None

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
        status=collection.status,
        owner=owner,
    )


async def _get_owned_collection(
    db: AsyncSession, collection_id: str, user: User
) -> Collection:
    collection = (
        await db.execute(select(Collection).where(Collection.id == collection_id))
    ).scalars().first()
    if collection is None:
        raise HTTPException(status_code=404, detail="专辑不存在")
    if collection.owner_id != user.id and not _is_admin(user):
        raise HTTPException(status_code=403, detail="只能管理自己的专辑")
    return collection


async def _allocate_user_slug(db: AsyncSession) -> str:
    for _ in range(8):
        candidate = f"u-{uuid.uuid4().hex[:10]}"
        exists = (
            await db.execute(select(Collection.id).where(Collection.slug == candidate))
        ).first()
        if exists is None:
            return candidate
    raise HTTPException(status_code=500, detail="专辑地址生成失败，请重试")


@router.get("/public", response_model=CollectionListResponse)
async def list_public_collections(
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0, le=2000),
    db: AsyncSession = Depends(get_db),
) -> CollectionListResponse:
    """专题列表（首页「主题专题」横滑卡区使用）。

    只返回至少有一张公开作品的专题：空专题（全部待审/敏感）不上首页，
    避免用户点进去看到空页。
    """
    collections = await _published_collections(db)
    all_entries = await _approved_entries(db, [c.id for c in collections])
    collections = [c for c in collections if all_entries.get(c.id)]
    total = len(collections)
    page = collections[offset : offset + limit]

    entries = {c.id: all_entries.get(c.id, []) for c in page}
    cover_ids = [
        cover_id
        for c in page
        if (cover_id := _pick_cover_id(c, entries.get(c.id, []))) is not None
    ]
    photo_map = await _photos_by_id(db, cover_ids)
    owner_map = await _owners_by_id(db, [c.owner_id for c in page])

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
                status=collection.status,
                owner=owner_map.get(collection.owner_id)
                if collection.owner_id
                else None,
            )
        )
    return CollectionListResponse(items=items, total=total, limit=limit, offset=offset)


# ── 樱色光谱（按主色自动策展）────────────────────────────────────────


@router.get("/spectrum", response_model=SpectrumResponse)
async def list_spectrum(db: AsyncSession = Depends(get_db)) -> SpectrumResponse:
    """五个色卡及其对应的光谱专题（按主色自动策展）。

    只返回存在公开作品的色卡；`cover` 为该专题的第一张公开作品（不裁切）。
    """
    collections = (
        await db.execute(
            select(Collection).where(
                Collection.slug.in_(list(SPECTRUM_SLUGS)),
                Collection.status == "published",
                Collection.visibility == "public",
            )
        )
    ).scalars().all()
    by_slug = {collection.slug: collection for collection in collections}

    entries = await _approved_entries(db, [c.id for c in collections])
    cover_ids = [
        cover_id
        for c in collections
        if (cover_id := _pick_cover_id(c, entries.get(c.id, []))) is not None
    ]
    photo_map = await _photos_by_id(db, cover_ids)

    palettes: list[SpectrumSwatch] = []
    for palette in PALETTES:
        collection = by_slug.get(palette.slug)
        approved = entries.get(collection.id, []) if collection else []
        cover = (
            await _serialize_cover(db, collection, approved, photo_map)
            if collection is not None
            else None
        )
        palettes.append(
            SpectrumSwatch(
                key=palette.key,
                name=palette.name,
                hex=palette.hex,
                description=palette.description,
                slug=palette.slug if collection is not None else None,
                photo_count=len(approved),
                cover=cover,
            )
        )
    return SpectrumResponse(palettes=palettes, total=len(collections))


# ── 光的一日（按拍摄时段自动策展）────────────────────────────────────


@router.get("/light", response_model=LightPeriodsResponse)
async def list_light_periods(
    per_period: int = Query(4, ge=1, le=8),
    db: AsyncSession = Depends(get_db),
) -> LightPeriodsResponse:
    """「光的一日」四个时段及其代表作品（首页 hero 与光的一日区块共用）。

    - 固定返回 4 个时段（晨/昼/暮/夜），顺序稳定，前端无需自己排；
    - 只取 published + public 的专题；专题为空（如晨间尚无作品）时
      `photos=[]`、`photo_count=0`，前端展示「整理中」；
    - 作品只含 approved 且非敏感，最多 `per_period` 张（默认 4）。
    """
    collections = (
        await db.execute(
            select(Collection).where(
                Collection.slug.in_([period.slug for period in LIGHT_PERIODS]),
                Collection.status == "published",
                Collection.visibility == "public",
            )
        )
    ).scalars().all()
    by_slug = {collection.slug: collection for collection in collections}

    entries = await _approved_entries(db, [c.id for c in collections])
    wanted: list[tuple[object, list[str]]] = []
    all_ids: list[str] = []
    for period in LIGHT_PERIODS:
        collection = by_slug.get(period.slug)
        approved = entries.get(collection.id, []) if collection else []
        picked = approved[:per_period]
        wanted.append((collection, picked))
        all_ids.extend(picked)

    photo_map = await _photos_by_id(db, all_ids)

    periods: list[LightPeriodResponse] = []
    for period, (collection, picked) in zip(LIGHT_PERIODS, wanted, strict=True):
        photos: list[PhotoResponse] = []
        for photo_id in picked:
            photo = photo_map.get(photo_id)
            if photo is not None:
                photos.append(await serialize_photo(db, photo))
        approved_count = len(entries.get(collection.id, [])) if collection else 0
        periods.append(
            LightPeriodResponse(
                key=period.key,
                slug=period.slug,
                label=period.label,
                time_range=period.time_range,
                title=collection.title if collection else f"{period.label} · 整理中",
                subtitle=collection.subtitle if collection else period.hint,
                intro=collection.description if collection else None,
                photo_count=approved_count,
                photos=photos,
            )
        )
    return LightPeriodsResponse(
        periods=periods,
        total=sum(1 for period in periods if period.photo_count),
    )


# ── 作者手账（用户自建专辑）──────────────────────────────────────────


@router.post(
    "/assistant",
    response_model=CuratorAssistResponse,
    summary="AI 策展助手：一句话从我的作品里挑一组（只读提案，不落库）",
)
@limiter.limit("5/minute")
async def assist_collection(
    request: Request,
    payload: CuratorAssistRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CuratorAssistResponse:
    """把作者的一句话主题 + 自己已通过作品的紧凑目录交给文本模型，返回可编辑的专辑提案。

    不创建专辑、不改作品；前端在编辑页里确认后才走 `POST /collections`。
    """
    try:
        proposal = await propose_collection(db, current_user, payload.prompt)
    except AIError as exc:
        logger.warning("curation assistant failed: %s", exc)
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 策展助手暂时不可用，请稍后再试",
        ) from exc

    if proposal.candidates == 0:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="你还没有已通过审核的作品，先投稿几张再来策展吧",
        )

    # ai_client 只 flush 记量事件、由调用方提交；这里提交才能让后台「AI 成本」看到这次调用。
    await db.commit()

    picks: list[CuratorPickItem] = []
    for item in proposal.picks:
        picks.append(
            CuratorPickItem(photo=await serialize_photo(db, item.photo), reason=item.reason)
        )
    return CuratorAssistResponse(
        title=proposal.title,
        subtitle=proposal.subtitle,
        description=proposal.description,
        photo_ids=[str(item.photo.id) for item in proposal.picks],
        picks=picks,
        note=proposal.note,
        candidates=proposal.candidates,
        cost_usd=proposal.cost_usd,
        latency_ms=proposal.latency_ms,
        model_id=proposal.model_id,
    )


@router.get("/mine", response_model=CollectionMineResponse)
async def list_my_collections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionMineResponse:
    """我的专辑（含草稿），按最近更新排序。"""
    collections = (
        await db.execute(
            select(Collection)
            .where(Collection.owner_id == current_user.id)
            .order_by(Collection.updated_at.desc())
        )
    ).scalars().all()
    entries = await _approved_entries(db, [c.id for c in collections])
    cover_ids = [
        cover_id
        for c in collections
        if (cover_id := _pick_cover_id(c, entries.get(c.id, []))) is not None
    ]
    photo_map = await _photos_by_id(db, cover_ids)
    owner = CollectionOwnerBrief(
        username=getattr(current_user, "username", None),
        display_name=getattr(current_user, "display_name", None),
    )
    items: list[CollectionSummary] = []
    for collection in collections:
        approved = entries.get(collection.id, [])
        items.append(
            CollectionSummary(
                id=collection.id,
                slug=collection.slug,
                title=collection.title,
                subtitle=collection.subtitle,
                kind=collection.kind,
                sort_order=collection.sort_order,
                photo_count=len(approved),
                cover=await _serialize_cover(db, collection, approved, photo_map),
                status=collection.status,
                owner=owner,
            )
        )
    return CollectionMineResponse(items=items, total=len(items))


@router.post("", response_model=CollectionDetail, status_code=http_status.HTTP_201_CREATED)
async def create_user_collection(
    payload: CollectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionDetail:
    """新建「作者手账」专辑；用户自建无需管理员批准（AGENTS.md §4）。"""
    owned = (
        await db.execute(
            select(func.count(Collection.id)).where(
                Collection.owner_id == current_user.id
            )
        )
    ).scalar_one()
    if owned >= _MAX_USER_COLLECTIONS:
        raise HTTPException(
            status_code=400, detail=f"最多只能创建 {_MAX_USER_COLLECTIONS} 个专辑"
        )

    collection = Collection(
        slug=await _allocate_user_slug(db),
        title=payload.title.strip(),
        subtitle=(payload.subtitle or "").strip() or None,
        description=(payload.description or "").strip() or None,
        kind="user",
        owner_id=current_user.id,
        visibility="public",
        status="published",
        sort_order=_USER_COLLECTION_SORT_BASE + owned,
    )
    db.add(collection)
    await db.flush()
    await log_audit(
        db,
        user_id=current_user.id,
        action="collection.create",
        resource_type="collection",
        resource_id=collection.id,
        detail=collection.title,
    )
    await db.commit()
    return await _build_detail(db, collection, approved_only=False)


@router.get("/{collection_id}/manage", response_model=CollectionDetail)
async def get_managed_collection(
    collection_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionDetail:
    """编辑页读取：含未审核作品，仅作者或管理员可用。"""
    collection = await _get_owned_collection(db, collection_id, current_user)
    return await _build_detail(db, collection, approved_only=False)


@router.patch("/{collection_id}", response_model=CollectionDetail)
async def update_user_collection(
    collection_id: str,
    payload: CollectionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionDetail:
    collection = await _get_owned_collection(db, collection_id, current_user)
    updates = payload.model_dump(exclude_unset=True)

    if "cover_photo_id" in updates:
        cover_id = updates["cover_photo_id"]
        if cover_id is not None:
            entries = await _entries_all(db, collection.id)
            if cover_id not in entries:
                raise HTTPException(status_code=400, detail="封面必须是专辑内的作品")
        collection.cover_photo_id = cover_id
    for field in ("title", "subtitle", "description"):
        if field in updates:
            value = updates[field]
            if isinstance(value, str):
                value = value.strip() or None
            setattr(collection, field, value)
    if updates.get("status") in ("published", "draft"):
        collection.status = updates["status"]
    if collection.title is None:
        raise HTTPException(status_code=400, detail="标题不能为空")

    await log_audit(
        db,
        user_id=current_user.id,
        action="collection.update",
        resource_type="collection",
        resource_id=collection.id,
        detail=collection.title,
    )
    await db.commit()
    return await _build_detail(db, collection, approved_only=False)


@router.put("/{collection_id}/photos", response_model=CollectionDetail)
async def replace_collection_photos(
    collection_id: str,
    payload: CollectionPhotosUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionDetail:
    """整体替换专辑作品并保序；只能放本人已审核作品。"""
    collection = await _get_owned_collection(db, collection_id, current_user)

    photo_ids = list(dict.fromkeys(payload.photo_ids))
    if photo_ids:
        rows = (
            await db.execute(
                select(Photo.id, Photo.uploader_id, Photo.status).where(
                    Photo.id.in_(photo_ids)
                )
            )
        ).all()
        found = {row[0]: row for row in rows}
        for photo_id in photo_ids:
            row = found.get(photo_id)
            if row is None:
                raise HTTPException(status_code=400, detail=f"作品不存在：{photo_id}")
            if row[1] != current_user.id and not _is_admin(current_user):
                raise HTTPException(status_code=403, detail="只能收录自己的作品")
            if row[2] != "approved":
                raise HTTPException(status_code=400, detail="只能收录已通过审核的作品")

    await db.execute(
        delete(CollectionPhoto).where(CollectionPhoto.collection_id == collection.id)
    )
    for position, photo_id in enumerate(photo_ids):
        db.add(
            CollectionPhoto(
                collection_id=collection.id,
                photo_id=photo_id,
                position=position,
            )
        )
    if collection.cover_photo_id and collection.cover_photo_id not in photo_ids:
        collection.cover_photo_id = None
    await db.commit()
    return await _build_detail(db, collection, approved_only=False)


@router.delete("/{collection_id}")
async def delete_user_collection(
    collection_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    collection = await _get_owned_collection(db, collection_id, current_user)
    title = collection.title
    await db.delete(collection)
    await log_audit(
        db,
        user_id=current_user.id,
        action="collection.delete",
        resource_type="collection",
        resource_id=collection_id,
        detail=title,
    )
    await db.commit()
    return {"ok": True, "deleted": collection_id}



@router.get("/{slug}", response_model=CollectionDetail)
async def get_public_collection(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> CollectionDetail:
    """专题详情：叙事 + 有序作品 + 上下篇 + 作者（用户专辑时）。"""
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
    return await _build_detail(db, collection)


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
