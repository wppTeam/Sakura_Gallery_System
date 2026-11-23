#!/usr/bin/env python3
"""为已有照片补齐响应式变体（320/640/1080/1600/2400，WebP+JPEG）与档位元信息。

背景：真实上传流程在某轮迭代后才开始同步生成变体，更早入库的演示数据
（seed_demo.py 生成的 63 张 + AIGC 样例 + 手工导入）只在
``uploads/variants/{uuid}/`` 子目录里有文件、数据库里没有
``exif_data["_variants"]`` 元信息，导致公开响应不返回 ``variants``、
前端无法用 ``<picture>/srcset`` 取合适档位。

本脚本是**幂等**的：

* 平铺旧布局：``uploads/variants/{uuid}/{uuid}_{size}.webp`` → ``uploads/variants/{uuid}_{size}.webp``；
* 缺失档位用 ``generate_variants()`` 重新生成（与原图同比例、不放大）；
* 把 ``{size: {width, height}}`` 写入 ``photos.exif_data["_variants"]``；
* 已完整的照片直接跳过。

用法::

    backend/.venv/bin/python scripts/backfill_variants.py --dry-run
    backend/.venv/bin/python scripts/backfill_variants.py
    backend/.venv/bin/python scripts/backfill_variants.py --force   # 已完整也重建
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
os.chdir(BACKEND_DIR)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.config import get_settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models import Photo  # noqa: E402
from app.services.image_processing import VARIANT_LONG_EDGES, generate_variants  # noqa: E402

settings = get_settings()
UPLOADS = Path(settings.UPLOAD_DIR).resolve()
VARIANTS_DIR = UPLOADS / "variants"


def _flat_path(photo_id: str, size: int, fmt: str) -> Path:
    suffix = "webp" if fmt == "webp" else "jpg"
    return VARIANTS_DIR / f"{photo_id}_{size}.{suffix}"


def _flatten_legacy(photo_id: str, dry_run: bool) -> int:
    """把旧版 per-uuid 子目录里的变体平铺到 variants/ 下，返回搬移文件数。"""
    legacy_dir = VARIANTS_DIR / photo_id
    if not legacy_dir.is_dir():
        return 0
    moved = 0
    for src in sorted(legacy_dir.iterdir()):
        if not src.is_file():
            continue
        target = VARIANTS_DIR / src.name
        if target.exists():
            if not dry_run:
                src.unlink()
        else:
            if not dry_run:
                shutil.move(str(src), target)
            moved += 1
    if not dry_run:
        try:
            legacy_dir.rmdir()
        except OSError:
            pass
    return moved


def _existing_meta(photo_id: str) -> dict[str, dict[str, Any]] | None:
    webps = sorted(VARIANTS_DIR.glob(f"{photo_id}_*.webp"))
    if not webps:
        return None
    meta: dict[str, dict[str, Any]] = {}
    for webp in webps:
        stem, _, size_text = webp.stem.rpartition("_")
        if stem != photo_id or not size_text.isdigit():
            continue
        jpg = _flat_path(photo_id, int(size_text), "jpeg")
        if not jpg.exists():
            return None
        meta[size_text] = {"width": int(size_text), "height": None}
    return meta or None


async def backfill(dry_run: bool, force: bool, limit: int | None) -> int:
    created = 0
    updated = 0
    skipped = 0
    failed: list[str] = []
    started = time.time()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Photo).order_by(Photo.created_at))
        photos = list(result.scalars().all())
        if limit:
            photos = photos[:limit]

        for index, photo in enumerate(photos, start=1):
            exif = dict(photo.exif_data or {})
            meta = exif.get("_variants")
            if isinstance(meta, dict) and meta and not force:
                skipped += 1
                continue

            original = (UPLOADS / photo.original_path).resolve()
            if not original.is_file():
                failed.append(f"{photo.id}: 原图不存在 {photo.original_path}")
                continue

            moved = _flatten_legacy(photo.id, dry_run)
            existing = _existing_meta(photo.id)
            need_generate = force or not existing

            if need_generate:
                if dry_run:
                    print(f"[dry] 生成变体 {photo.id} <- {photo.original_path}")
                    created += 1
                    continue
                try:
                    VARIANTS_DIR.mkdir(parents=True, exist_ok=True)
                    generated = generate_variants(
                        str(original),
                        str(VARIANTS_DIR),
                        photo_uuid=photo.id,
                        force=force,
                    )
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{photo.id}: 生成失败 {exc}")
                    continue
                variant_meta = {
                    str(size): {"width": info["width"], "height": info["height"]}
                    for size, info in generated.items()
                }
                created += 1
            else:
                variant_meta = {}
                for size_text, info in (existing or {}).items():
                    width = photo.width
                    height = photo.height
                    if width and height:
                        long_edge = max(width, height)
                        scale = int(size_text) / long_edge if long_edge else 1
                        info = {
                            "width": round(width * scale),
                            "height": round(height * scale),
                        }
                    variant_meta[size_text] = info
                updated += 1

            exif["_variants"] = variant_meta
            photo.exif_data = exif
            if not dry_run:
                await session.commit()
            print(
                f"[{index:>3}/{len(photos)}] {'gen' if need_generate else 'meta'} "
                f"{photo.id} 档位={sorted(variant_meta, key=int)} 平铺={moved}"
            )

    print(
        f"\n完成：生成 {created} / 补元信息 {updated} / 跳过 {skipped} / 失败 {len(failed)}，"
        f"耗时 {time.time() - started:.1f}s"
    )
    for item in failed[:20]:
        print("  !", item)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="为已有照片补齐响应式变体与档位元信息")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要做什么")
    parser.add_argument("--force", action="store_true", help="已完整也重新生成")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 张（调试用）")
    args = parser.parse_args()
    if settings.STORAGE_BACKEND != "local":
        print("当前 STORAGE_BACKEND 不是 local，本脚本只处理本地文件系统。")
        return 2
    print(f"UPLOAD_DIR={UPLOADS} 档位={list(VARIANT_LONG_EDGES)}")
    return asyncio.run(backfill(args.dry_run, args.force, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
