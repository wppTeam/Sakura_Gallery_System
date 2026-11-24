"""策展自动归档：作品过审 / 下架时，自动维护「光的一日」与「樱色光谱」的成员。

为什么需要它：`scripts/seed_curation.py` 是一次性重建脚本，运营手动跑；但平台每天
都有新作品过审、也有作品被下架。如果不在审核链路里同步，首页「光的一日」「樱色光谱」
会停在上一次跑脚本的时刻，越用越旧。

归属规则（与 seed / 公开接口共用同一套单源定义）：
- 光的一日：`captured_at` 所在时段 → `light_of_day.period_for_hour().slug`
- 樱色光谱：上传时算出的 `exif_data["_spectrum"]["palette"]` → `spectrum-{palette}`
- 只有 `status=approved` 且非 sensitive 的作品才归档；被 reject / 撤回 / 标敏感时从
  这两个自动策展里移除。
  （公开接口本来就会过滤非 approved / sensitive，这里同步成员是为了让数据本身保持
  干净，避免「已下架却还挂在专题里」的脏数据累积。）

设计取舍：只动「自动策展」的两个前缀（light-* / spectrum-*），不碰人工 editorial
专题与用户手账；成员追加到末尾（position=max+1），不重排既有顺序——人工排序 / 手写
引言仍以 seed 脚本为准。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Collection, CollectionPhoto, Photo
from app.services.light_of_day import period_for_hour
from app.services.spectrum import PALETTE_BY_KEY

logger = logging.getLogger(__name__)

# 「光的一日」四个专题的元信息（seed 脚本与自动创建共用，避免两处文案漂移）。
LIGHT_COLLECTIONS: dict[str, dict] = {
    "light-dawn": {
        "title": "晨 · 还没醒的校园",
        "subtitle": "五点到九点，光比人先到",
        "description": (
            "清晨的校园是另一座校园：长椅上还有露水，食堂后门在卸货，"
            "第一节课的自行车铃从很远的地方传来。这一册只收天亮之后、"
            "热闹之前的那些光。"
        ),
        "sort_order": 20,
    },
    "light-noon": {
        "title": "昼 · 光在正上方",
        "subtitle": "九点到十五点，影子最短的时刻",
        "description": (
            "正午的光最诚实，没有阴影可以躲：花被照得发白，湖面亮成一块锡纸，"
            "人走在路上都眯着眼睛。它不好拍，但拍下来都很干净。"
        ),
        "sort_order": 21,
    },
    "light-dusk": {
        "title": "暮 · 一日将尽",
        "subtitle": "十五点以后，光开始变软",
        "description": (
            "下午四点以后，校园像被谁调低了饱和度：红砖变暖，湖面变金，"
            "走廊尽头的窗把光切成一格一格。这是一天里最容易想起谁的时刻，"
            "所以这一册最长。"
        ),
        "sort_order": 22,
    },
    "light-night": {
        "title": "夜 · 灯与星",
        "subtitle": "十九点以后，另一种校园",
        "description": (
            "晚上十点以后还在外面的人，会遇见另一种校园：路灯把树影放大，"
            "自习室的窗户像一格格灯箱，偶尔抬头能看见星。夜晚的颜色少，"
            "但每一块都很沉。"
        ),
        "sort_order": 23,
    },
}

# 「樱色光谱」五个专题的元信息。
SPECTRUM_COLLECTIONS: dict[str, dict] = {
    "spectrum-pink": {
        "title": "樱粉光谱",
        "subtitle": "花瓣、暮色与一点点少女感",
        "description": "被主色判为樱粉的作品合集：从玉兰到晚霞，从操场跑道到食堂的灯光。",
        "sort_order": 30,
    },
    "spectrum-gold": {
        "title": "金色光谱",
        "subtitle": "阳光、灯与暖色织物",
        "description": "金色是时间留下的颜色：晒过的墙、傍晚的湖、秋天的银杏和橘子汽水。",
        "sort_order": 31,
    },
    "spectrum-green": {
        "title": "绿色光谱",
        "subtitle": "草木、山野与生长",
        "description": "校园里最不缺的颜色。叶子、球场、雨后的草坪，以及所有正在长高的东西。",
        "sort_order": 32,
    },
    "spectrum-blue": {
        "title": "蓝色光谱",
        "subtitle": "天空、水面与夜色",
        "description": "蓝色是留白最多的颜色：晴天的天、冬天的湖、熄灯后的走廊。",
        "sort_order": 33,
    },
    "spectrum-ink": {
        "title": "墨色光谱",
        "subtitle": "低饱和、逆光与静谧的黑",
        "description": "不是没有颜色，而是颜色都很轻：雾天、逆光、深夜，和所有不好意思太鲜艳的时刻。",
        "sort_order": 34,
    },
}

AUTO_CURATED_SLUGS = frozenset(LIGHT_COLLECTIONS) | frozenset(SPECTRUM_COLLECTIONS)
_CURATED_META: dict[str, dict] = {**LIGHT_COLLECTIONS, **SPECTRUM_COLLECTIONS}


def light_slug_for(photo: Photo) -> Optional[str]:
    """`captured_at` 所在时段对应的专题 slug；没有拍摄时间则不入光的一日。"""
    captured_at = getattr(photo, "captured_at", None)
    if captured_at is None:
        return None
    slug = period_for_hour(captured_at.hour).slug
    return slug if slug in LIGHT_COLLECTIONS else None


def spectrum_slug_for(photo: Photo) -> Optional[str]:
    """按上传时采样的主色卡定位光谱专题；老图没有 `_spectrum` 则跳过。"""
    exif = photo.exif_data or {}
    meta = exif.get("_spectrum") if isinstance(exif, dict) else None
    key = meta.get("palette") if isinstance(meta, dict) else None
    if not key or key not in PALETTE_BY_KEY:
        return None
    slug = f"spectrum-{key}"
    return slug if slug in SPECTRUM_COLLECTIONS else None


def target_slugs(photo: Photo) -> list[str]:
    """该作品当前应归属的自动策展专题（approved 且非 sensitive 才有）。

    敏感作品（含可识别人像）在公开端默认不展示，收录进自动策展只会让专题成员与
    可见数量对不上，因此与 seed / 公开接口保持同一口径：敏感作品不进自动策展。
    """
    if photo.status != "approved":
        return []
    if (photo.privacy_level or "normal") == "sensitive":
        return []
    slugs: list[str] = []
    light = light_slug_for(photo)
    if light:
        slugs.append(light)
    spectrum = spectrum_slug_for(photo)
    if spectrum:
        slugs.append(spectrum)
    return slugs


async def _ensure_collection(db: AsyncSession, slug: str, meta: dict) -> Collection:
    existing = (
        await db.execute(select(Collection).where(Collection.slug == slug))
    ).scalars().first()
    if existing is not None:
        return existing
    collection = Collection(
        slug=slug,
        title=meta["title"],
        subtitle=meta.get("subtitle"),
        description=meta.get("description"),
        kind="editorial",
        visibility="public",
        status="published",
        sort_order=meta.get("sort_order", 0),
    )
    db.add(collection)
    await db.flush()
    logger.info("curation: 自动创建专题 %s", slug)
    return collection


async def _next_position(db: AsyncSession, collection_id: str) -> int:
    current = (
        await db.execute(
            select(func.coalesce(func.max(CollectionPhoto.position), -1)).where(
                CollectionPhoto.collection_id == collection_id
            )
        )
    ).scalar()
    return int(current or 0) + 1


async def sync_photo_curation(db: AsyncSession, photo: Photo) -> dict[str, list[str]]:
    """让一张作品的自动策展成员与它当前的状态 / 元数据一致（幂等，不 commit）。

    返回 ``{"added": [...], "removed": [...]}``，便于审核链路记日志与测试断言。
    """
    targets = target_slugs(photo)
    target_set = set(targets)

    rows = (
        await db.execute(
            select(CollectionPhoto, Collection.slug)
            .join(Collection, Collection.id == CollectionPhoto.collection_id)
            .where(
                CollectionPhoto.photo_id == photo.id,
                Collection.slug.in_(AUTO_CURATED_SLUGS),
            )
        )
    ).all()

    added: list[str] = []
    removed: list[str] = []
    current: set[str] = set()
    for entry, slug in rows:
        if slug in target_set:
            current.add(slug)
            continue
        await db.delete(entry)
        removed.append(slug)

    for slug in targets:
        if slug in current:
            continue
        collection = await _ensure_collection(db, slug, _CURATED_META[slug])
        db.add(
            CollectionPhoto(
                collection_id=collection.id,
                photo_id=photo.id,
                position=await _next_position(db, collection.id),
            )
        )
        added.append(slug)

    if added or removed:
        logger.info(
            "curation: photo=%s added=%s removed=%s", photo.id, added, removed
        )
    await db.flush()
    return {"added": added, "removed": removed}


async def sync_all_photos(
    db: AsyncSession,
    *,
    limit: Optional[int] = None,
    commit_every: int = 50,
    commit: bool = True,
) -> dict[str, int]:
    """回填 / 修复存量作品的策展成员（CLI 脚本与部署后校正用）。

    ``commit=False`` 时只在事务内 flush、不提交，供 ``--dry-run`` 用真实事务回滚。
    """
    query = select(Photo).where(Photo.status == "approved").order_by(Photo.created_at.asc())
    if limit:
        query = query.limit(limit)
    photos = (await db.execute(query)).scalars().all()
    scanned = added = removed = 0
    for index, photo in enumerate(photos, start=1):
        result = await sync_photo_curation(db, photo)
        scanned += 1
        added += len(result["added"])
        removed += len(result["removed"])
        if commit and index % commit_every == 0:
            await db.commit()
    if commit:
        await db.commit()
    else:
        await db.flush()
    return {"scanned": scanned, "added": added, "removed": removed}


__all__ = [
    "AUTO_CURATED_SLUGS",
    "LIGHT_COLLECTIONS",
    "SPECTRUM_COLLECTIONS",
    "light_slug_for",
    "spectrum_slug_for",
    "sync_all_photos",
    "sync_photo_curation",
    "target_slugs",
]
