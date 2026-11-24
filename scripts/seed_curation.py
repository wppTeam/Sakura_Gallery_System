"""生成「我们自己的」策展专题：光的一日（按拍摄时段）+ 樱色光谱（按主色）。

A. 光的一日：把作品按 captured_at 归入 晨/昼/暮/夜 四个时段，各成一个专题，
   配一段手写引言——不靠人工选题，靠作品自身的拍摄时间讲故事。
B. 樱色光谱：用 `app.services.spectrum` 采样每张作品的主色，归入
   樱粉/金/绿/蓝/墨 五个色卡，各成一个专题。

脚本是幂等的（按 slug upsert，每次重建条目），可反复运行。
图片采样对本地磁盘或 S3/COS 都适用（走 storage.local_copy）。

用法（在仓库根目录）：
    backend/.venv/bin/python scripts/seed_curation.py --dry-run
    backend/.venv/bin/python scripts/seed_curation.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if not (BACKEND_ROOT / "app").is_dir():
    # 容器内（镜像把 backend/ 作为 /app）直接用当前目录
    BACKEND_ROOT = Path.cwd()
# config 的 env_file 相对 cwd 解析：必须先切到 backend/ 再 import app
os.chdir(BACKEND_ROOT)
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models import Collection, CollectionPhoto, Photo  # noqa: E402
from app.services.spectrum import PALETTES, classify_image  # noqa: E402
from app.services.storage import get_storage  # noqa: E402

LIGHT_SLUGS: tuple[str, ...] = (
    "light-dawn",
    "light-noon",
    "light-dusk",
    "light-night",
)

LIGHT_COLLECTIONS: dict[str, dict] = {
    "light-dawn": {
        "title": "晨 · 还没醒的校园",
        "subtitle": "六点到九点，光比人先到",
        "description": (
            "清晨的校园是另一座校园：长椅上还有露水，食堂后门在卸货，"
            "第一节课的自行车铃从很远的地方传来。这一册只收天亮之后、"
            "热闹之前的那些光。"
        ),
        "sort_order": 20,
    },
    "light-noon": {
        "title": "昼 · 光在正上方",
        "subtitle": "十点到十五点，影子最短的时刻",
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


def _light_bucket(captured_at: datetime | None) -> str | None:
    if captured_at is None:
        return None
    hour = captured_at.hour
    if 5 <= hour < 9:
        return "light-dawn"
    if 9 <= hour < 15:
        return "light-noon"
    if 15 <= hour < 19:
        return "light-dusk"
    return "light-night"


def _compute_spectrum(photo: Photo, storage) -> dict | None:
    source = photo.thumb_path or photo.original_path
    if not source:
        return None
    try:
        with storage.local_copy(source) as local_path:
            return classify_image(local_path)
    except Exception as exc:  # noqa: BLE001 - 单张失败跳过
        print(f"  ! 采样失败 {photo.id}: {exc}")
        return None


async def _ensure_spectrum(
    session, photos: list[Photo], *, force: bool, persist: bool = True
) -> tuple[int, int, dict[str, dict]]:
    """确保作品有 `_spectrum` 元数据；返回 (已有, 新算, 内存中的兜底映射)。

    ``persist=False``（dry-run）时不写库，只把算出来的结果放进映射供统计。
    """
    storage = get_storage()
    existing = computed = 0
    memory: dict[str, dict] = {}
    for index, photo in enumerate(photos, start=1):
        exif = dict(photo.exif_data or {})
        if exif.get("_spectrum") and not force:
            existing += 1
            memory[photo.id] = exif["_spectrum"]
            continue
        meta = _compute_spectrum(photo, storage)
        if not meta:
            continue
        computed += 1
        memory[photo.id] = meta
        if persist:
            exif["_spectrum"] = meta
            photo.exif_data = exif
            if index % 20 == 0:
                await session.commit()
    if persist:
        await session.commit()
    return existing, computed, memory


async def _upsert_collection(
    session,
    *,
    slug: str,
    meta: dict,
    photo_ids: list[str],
) -> str:
    existing = (
        await session.execute(select(Collection).where(Collection.slug == slug))
    ).scalars().first()
    if existing is None:
        collection = Collection(
            slug=slug,
            title=meta["title"],
            subtitle=meta["subtitle"],
            description=meta["description"],
            kind="editorial",
            visibility="public",
            status="published",
            sort_order=meta["sort_order"],
        )
        session.add(collection)
        await session.flush()
        action = "created"
    else:
        collection = existing
        collection.title = meta["title"]
        collection.subtitle = meta["subtitle"]
        collection.description = meta["description"]
        collection.kind = "editorial"
        collection.visibility = "public"
        collection.status = "published"
        collection.sort_order = meta["sort_order"]
        action = "updated"

    await session.execute(
        delete(CollectionPhoto).where(CollectionPhoto.collection_id == collection.id)
    )
    for position, photo_id in enumerate(photo_ids):
        session.add(
            CollectionPhoto(
                collection_id=collection.id,
                photo_id=photo_id,
                position=position,
            )
        )
    if not photo_ids:
        collection.status = "draft"
    await session.commit()
    return f"{action}:{slug} ({len(photo_ids)} 张)"


async def main_async(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as session:
        photos = list(
            (
                await session.execute(
                    select(Photo)
                    .where(
                        Photo.status == "approved",
                        (Photo.privacy_level.is_(None))
                        | (Photo.privacy_level != "sensitive"),
                    )
                    .order_by(Photo.published_at.asc().nullslast(), Photo.created_at.asc())
                )
            ).scalars()
        )
        if not photos:
            print("没有已审核作品，先跑 scripts/seed_demo.py")
            return 1
        print(f"已审核且非敏感作品：{len(photos)} 张")

        existing, computed, spectrum_memory = await _ensure_spectrum(
            session,
            photos,
            force=args.force_spectrum,
            persist=not args.dry_run,
        )
        print(f"光谱元数据：已有 {existing} 张，新算 {computed} 张")

        # A. 光的一日
        buckets: dict[str, list[str]] = {slug: [] for slug in LIGHT_SLUGS}
        for photo in photos:
            bucket = _light_bucket(photo.captured_at)
            if bucket:
                buckets[bucket].append(photo.id)

        # B. 樱色光谱
        spectrums: dict[str, list[tuple[float, str]]] = {p.slug: [] for p in PALETTES}
        for photo in photos:
            meta = spectrum_memory.get(photo.id) or (photo.exif_data or {}).get("_spectrum") or {}
            slug = next(
                (p.slug for p in PALETTES if p.key == meta.get("palette")), None
            )
            if slug:
                spectrums[slug].append((float(meta.get("ratio") or 0), photo.id))
        for slug in spectrums:
            spectrums[slug].sort(key=lambda pair: pair[0], reverse=True)

        plan: list[tuple[str, dict, list[str]]] = []
        for slug in LIGHT_SLUGS:
            plan.append((slug, LIGHT_COLLECTIONS[slug], buckets[slug]))
        for palette in PALETTES:
            slug = palette.slug
            plan.append(
                (slug, SPECTRUM_COLLECTIONS[slug], [pid for _, pid in spectrums[slug]])
            )

        for slug, meta, photo_ids in plan:
            print(f"  {slug}: {len(photo_ids)} 张 -> {meta['title']}")
        if args.dry_run:
            print("(dry-run，未写入)")
            return 0

        for slug, meta, photo_ids in plan:
            message = await _upsert_collection(
                session, slug=slug, meta=meta, photo_ids=photo_ids
            )
            print(f"  {message}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="生成光的一日 / 樱色光谱策展专题")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    parser.add_argument(
        "--force-spectrum",
        action="store_true",
        help="重算所有作品的 _spectrum（默认只补缺失）",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
