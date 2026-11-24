#!/usr/bin/env python3
"""把存量人像作品标记为 sensitive 并生成脱敏图（人像隐私分级回填）。

判定依据（任一命中）：
1. ``photos.category == "Portrait"``（旧版人像分类）；
2. 该作品任一 ``moderation_reviews.prefilter.has_identifiable_person`` 为 true；
3. 该作品任一 ``moderation_reviews.escalation.has_identifiable_person`` 为 true。

用法（必须在 backend 目录下运行，env_file=".env" 相对 cwd 解析）::

    cd backend && .venv/bin/python ../scripts/backfill_portrait_privacy.py --dry-run
    cd backend && .venv/bin/python ../scripts/backfill_portrait_privacy.py --limit 100

脱敏图落 ``uploads/redacted/{id}_redacted.jpg`` 与 ``_redacted_thumb.jpg``；
已存在的会跳过（``--force`` 重建）。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.moderation import ModerationReview  # noqa: E402
from app.models.photo import Photo  # noqa: E402
from app.services import privacy  # noqa: E402


def _person_flag(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    value = payload.get("has_identifiable_person")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "是", "有")
    return False


async def run(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        photos = (
            await db.execute(
                select(Photo).order_by(Photo.created_at.asc()).limit(args.limit or 10000)
            )
        ).scalars().all()
        reviews = (
            await db.execute(select(ModerationReview))
        ).scalars().all()
        person_photo_ids = {
            review.photo_id
            for review in reviews
            if _person_flag(review.prefilter) or _person_flag(review.escalation)
        }

        scanned = marked = redacted = failed = skipped = 0
        for photo in photos:
            scanned += 1
            reasons = []
            if (photo.category or "") == "Portrait":
                reasons.append("legacy_portrait_category")
            if photo.id in person_photo_ids:
                reasons.append("moderation.person")
            if not reasons:
                continue
            if privacy.is_sensitive(photo) and privacy.has_redacted_media(photo) and not args.force:
                skipped += 1
                continue
            if args.dry_run:
                print(f"[dry-run] {photo.id} {photo.title or photo.filename} reasons={reasons}")
                marked += 1
                continue
            try:
                if not privacy.is_sensitive(photo):
                    photo.privacy_level = privacy.PRIVACY_SENSITIVE
                meta = photo.exif_data if isinstance(photo.exif_data, dict) else {}
                meta = dict(meta)
                meta["_privacy"] = {
                    "level": privacy.PRIVACY_SENSITIVE,
                    "reason": ",".join(reasons),
                }
                photo.exif_data = meta
                ok = await privacy.ensure_redacted_images(db, photo, force=args.force)
                marked += 1
                if ok:
                    redacted += 1
                else:
                    failed += 1
                await db.commit()
                print(
                    f"[ok] {photo.id} {photo.title or photo.filename} "
                    f"redacted={photo.redacted_path or '-'} reasons={reasons}"
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                await db.rollback()
                print(f"[fail] {photo.id}: {exc}")

        print(
            f"\nscanned={scanned} marked={marked} redacted={redacted} "
            f"skipped={skipped} failed={failed} dry_run={args.dry_run}"
        )
        return 1 if failed and args.strict else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="回填人像隐私分级与脱敏图")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要处理的作品")
    parser.add_argument("--limit", type=int, default=0, help="最多扫描多少张作品（0=全部）")
    parser.add_argument("--force", action="store_true", help="已脱敏的也重建")
    parser.add_argument("--strict", action="store_true", help="有失败时退出码 1")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
