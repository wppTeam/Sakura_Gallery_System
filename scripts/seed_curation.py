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
from app.services.light_of_day import LIGHT_SLUGS, period_for_hour  # noqa: E402
from app.services.spectrum import PALETTES, classify_image  # noqa: E402
from app.services.storage import get_storage  # noqa: E402

# 专题元信息与审核链路的自动归档共用同一份定义（避免两处文案漂移）。
from app.services.curation import LIGHT_COLLECTIONS, SPECTRUM_COLLECTIONS  # noqa: E402,F811


def _light_bucket(captured_at: datetime | None) -> str | None:
    """与线上 /collections/light 使用同一套时段定义（app.services.light_of_day）。"""
    if captured_at is None:
        return None
    return period_for_hour(captured_at.hour).slug


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
