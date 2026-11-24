#!/usr/bin/env python3
"""为存量作品回填视觉签名（dhash），供「视觉相似」检索使用。

背景
----
``/api/v1/photos/{id}/similar`` 依赖 ``photos.exif_data["_dhash"]``（16×16 dhash
感知哈希，256 bit 十六进制）。该字段在某轮迭代后才在上传流程里写入，更早入库的
种子数据没有签名，导致它们只能按光谱/标签参与相似排序。

本脚本是**幂等**的：

* 优先用缩略图（快、稳定），缺失时退到压缩图、原图；
* 本地与 S3/COS 后端都适用（统一走 ``storage.local_copy``）；
* 已有 ``_dhash`` 的作品默认跳过（``--force`` 重算）；
* 每张单独 commit，失败只 warning 不中断，最后打印统计。

用法::

    cd backend
    .venv/bin/python ../scripts/backfill_visual_signatures.py --dry-run
    .venv/bin/python ../scripts/backfill_visual_signatures.py
    .venv/bin/python ../scripts/backfill_visual_signatures.py --force --limit 5
    .venv/bin/python ../scripts/backfill_visual_signatures.py --only <photo_id>

注意：脚本必须在 ``backend/`` 目录下运行（``.env`` 的 ``env_file`` 相对 cwd 解析）。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
os.chdir(BACKEND_DIR)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models import Photo  # noqa: E402
from app.services.storage import get_storage  # noqa: E402
from app.services.visual_similarity import compute_dhash, photo_dhash  # noqa: E402

logger = logging.getLogger("backfill_visual_signatures")


def _signature_source(photo: Photo) -> str | None:
    """挑一个可解码的本地路径：缩略图 → 压缩图 → 原图。"""
    for candidate in (photo.thumb_path, photo.compressed_path, photo.original_path):
        if candidate:
            return candidate
    return None


async def _sign_one(storage, photo: Photo) -> str | None:
    source = _signature_source(photo)
    if not source:
        return None
    try:
        with storage.local_copy(source) as local_path:
            return compute_dhash(local_path)
    except Exception as exc:  # noqa: BLE001 - 单张失败不影响整体
        logger.warning("读取失败 %s: %s", photo.id, exc)
        return None


async def main() -> int:
    parser = argparse.ArgumentParser(description="回填视觉签名（dhash）")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    parser.add_argument("--force", action="store_true", help="已有签名也重算")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少张（0=全部）")
    parser.add_argument("--only", default=None, help="只处理指定 photo id")
    parser.add_argument("--status", default="approved,pending", help="逗号分隔的状态，默认 approved,pending")
    args = parser.parse_args()

    statuses = [item.strip() for item in args.status.split(",") if item.strip()]
    storage = get_storage()
    stats = {"scanned": 0, "skipped": 0, "updated": 0, "no_source": 0, "failed": 0}
    started = time.time()

    async with AsyncSessionLocal() as db:
        query = select(Photo).where(Photo.status.in_(statuses)).order_by(Photo.created_at.asc())
        if args.only:
            query = query.where(Photo.id == args.only)
        if args.limit and args.limit > 0:
            query = query.limit(args.limit)
        photos = (await db.execute(query)).scalars().all()
        for photo in photos:
            stats["scanned"] += 1
            if photo_dhash(photo) and not args.force:
                stats["skipped"] += 1
                continue
            if not _signature_source(photo):
                stats["no_source"] += 1
                continue
            dhash = await _sign_one(storage, photo)
            if not dhash:
                stats["failed"] += 1
                continue
            if args.dry_run:
                print(f"[dry-run] {photo.id} dhash={dhash}")
                stats["updated"] += 1
                continue
            exif = dict(photo.exif_data) if isinstance(photo.exif_data, dict) else {}
            exif["_dhash"] = dhash
            photo.exif_data = exif
            db.add(photo)
            await db.commit()
            stats["updated"] += 1
            print(f"{photo.id} dhash={dhash}")

    elapsed = time.time() - started
    print(
        f"\n[done] scanned={stats['scanned']} updated={stats['updated']} "
        f"skipped={stats['skipped']} no_source={stats['no_source']} "
        f"failed={stats['failed']} elapsed={elapsed:.1f}s"
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(asyncio.run(main()))
