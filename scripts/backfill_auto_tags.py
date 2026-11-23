#!/usr/bin/env python3
"""对存量作品回填「审核即打标」的标签 / 分类 / 一句话描述。

为什么需要它
------------
「审核即打标」发生在审核流水线里（``app/services/auto_tagging.py``）：
上传 → 快筛 VLM 顺带输出 ``caption`` / ``tags`` / ``facets`` → 落库。
但在该能力上线前入库的作品（种子数据、旧上传）没有这些字段，检索与前端
标签区就显示为空。本脚本用**同一套提示词与归一化逻辑**逐张补一次。

成本
----
每张图一次视觉模型调用（输出约 400–800 tokens）。63 张约 ¥0.1–0.2。
默认跳过已回填过的作品（``photo.exif_data["_ai_tagging"]`` 存在），可 ``--force`` 重跑。

用法
----
    cd backend
    .venv/bin/python ../scripts/backfill_auto_tags.py --dry-run
    .venv/bin/python ../scripts/backfill_auto_tags.py --limit 5
    .venv/bin/python ../scripts/backfill_auto_tags.py            # 全部
    .venv/bin/python ../scripts/backfill_auto_tags.py --force --only p-xxx

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

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
os.chdir(BACKEND_DIR)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.photo import Photo  # noqa: E402
from app.prompts.moderation import get_prefilter_prompt  # noqa: E402
from app.services import auto_tagging  # noqa: E402
from app.services.ai_client import AIError, chat_json  # noqa: E402
from app.services.moderation import _load_image_for_ai  # noqa: E402

logger = logging.getLogger("backfill_auto_tags")


async def _process_photo(db, photo: Photo, *, dry_run: bool) -> dict:
    image_base64, image_mime = await _load_image_for_ai(photo)
    if not image_base64:
        return {"status": "no-image"}

    taxonomy_catalog = await auto_tagging.build_taxonomy_catalog(db)
    user_prompt = get_prefilter_prompt(
        title=photo.title,
        description=photo.description,
        category=photo.category,
        season=photo.season,
        author=photo.author,
        rules=None,
        taxonomy_catalog=taxonomy_catalog,
    )
    result = await chat_json(
        db,
        operation="moderation.tagging",
        user=user_prompt,
        image_base64=image_base64,
        image_mime=image_mime,
        max_tokens=int(get_settings().MODERATION_PREFILTER_MAX_TOKENS or 1024),
        temperature=float(get_settings().MODERATION_PREFILTER_TEMPERATURE or 0.1),
        ref_type="photo",
        ref_id=str(photo.id),
    )
    if dry_run:
        suggestions = auto_tagging.normalize_suggestions(result.data)
        return {
            "status": "dry-run",
            "tags": suggestions["tags"],
            "facets": suggestions["facets"],
            "caption": suggestions["caption"],
            "tokens": result.total_tokens,
            "cost_usd": result.cost_usd,
        }

    summary = await auto_tagging.apply_prefilter_tags(db, photo, result.data)
    return {
        "status": "updated" if summary.get("applied") or summary.get("caption") else "empty",
        "tags": summary.get("tags") or [],
        "facets": summary.get("facets") or {},
        "caption": summary.get("caption"),
        "tokens": result.total_tokens,
        "cost_usd": result.cost_usd,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="回填存量作品的 AI 标签/分类")
    parser.add_argument("--dry-run", action="store_true", help="只打印模型输出，不写库")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少张（0 = 全部）")
    parser.add_argument("--force", action="store_true", help="已有 _ai_tagging 的作品也重跑")
    parser.add_argument("--only", action="append", default=[], help="只处理指定 photo id（可重复）")
    parser.add_argument("--all-status", action="store_true", help="包含 pending/rejected（默认只回填 approved）")
    parser.add_argument("--sleep", type=float, default=0.0, help="每张之间休眠秒数（限速用）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    stats = {"scanned": 0, "updated": 0, "empty": 0, "skipped": 0, "failed": 0, "no-image": 0}
    tokens = 0
    cost = 0.0
    started = time.time()

    async with AsyncSessionLocal() as db:
        query = select(Photo).where(Photo.status != "deleted")
        if not args.all_status:
            query = query.where(Photo.status == "approved")
        if args.only:
            query = query.where(Photo.id.in_(args.only))
        query = query.order_by(Photo.created_at)
        photos = list((await db.execute(query)).scalars().all())

        for photo in photos:
            if args.limit and stats["scanned"] >= args.limit:
                break
            stats["scanned"] += 1
            meta = photo.exif_data if isinstance(photo.exif_data, dict) else {}
            if meta.get("_ai_tagging") and not args.force:
                stats["skipped"] += 1
                logger.info("skip %s (already tagged)", photo.id)
                continue
            try:
                outcome = await _process_photo(db, photo, dry_run=args.dry_run)
                stats[outcome["status"]] = stats.get(outcome["status"], 0) + 1
                tokens += int(outcome.get("tokens") or 0)
                cost += float(outcome.get("cost_usd") or 0)
                if outcome["status"] in {"updated", "dry-run"}:
                    if not args.dry_run:
                        await db.commit()
                    logger.info(
                        "%s %s tags=%s facets=%s caption=%s",
                        "would-update" if args.dry_run else "updated",
                        photo.id,
                        outcome.get("tags"),
                        outcome.get("facets"),
                        outcome.get("caption"),
                    )
            except AIError as exc:
                stats["failed"] += 1
                await db.rollback()
                logger.warning("ai failed %s: %s", photo.id, exc)
            except Exception as exc:  # noqa: BLE001 - 单张失败继续
                stats["failed"] += 1
                await db.rollback()
                logger.warning("failed %s: %s", photo.id, exc, exc_info=True)
            if args.sleep:
                await asyncio.sleep(args.sleep)

    elapsed = time.time() - started
    print("\n== backfill summary ==")
    print(f"scanned : {stats['scanned']}")
    print(f"updated : {stats['updated']} (empty={stats['empty']}, skipped={stats['skipped']})")
    print(
        f"failed  : {stats['failed']}   no-image: {stats['no-image']}"
    )
    print(f"tokens  : {tokens}   cost ≈ ${cost:.4f}")
    print(f"elapsed : {elapsed:.1f}s")
    if args.dry_run:
        print("(dry-run: nothing written)")
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
