#!/usr/bin/env python3
"""回填 photos.search_document（补充检索语料：AI 画面描述 + 标签）。

背景：`_ai_caption` 由快筛写入 exif_data，2026-11-25 之前不可检索；
新增 search_document 列 + trigger 并入分词后，需要给存量作品补一遍。

用法（仓库根目录）：
    cd backend && .venv/bin/python ../scripts/backfill_search_documents.py --dry-run
    cd backend && .venv/bin/python ../scripts/backfill_search_documents.py --limit 10
    cd backend && .venv/bin/python ../scripts/backfill_search_documents.py

容器内（生产镜像把 backend/ 拷成 /app）：
    docker exec -w /app -e PYTHONPATH=/app sakura-prod-backend \
        python /tmp/backfill_search_documents.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if not (BACKEND_DIR / "app").is_dir():
    BACKEND_DIR = Path.cwd()

sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.photo import Photo  # noqa: E402
from app.services.search_index import refresh_search_document  # noqa: E402


async def _run(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(Photo).order_by(Photo.created_at.asc())
            if args.limit:
                stmt = stmt.limit(args.limit)
            photos = list((await db.execute(stmt)).scalars().all())

            scanned = 0
            changed = 0
            empty = 0
            for photo in photos:
                scanned += 1
                before = (photo.search_document or "").strip()
                doc = await refresh_search_document(db, photo)
                if not doc:
                    empty += 1
                if (doc or "") != before:
                    changed += 1
                if args.dry_run:
                    # dry-run 不落库：回滚整个事务前的 flush 也不产生持久影响
                    continue
                if args.batch and scanned % args.batch == 0:
                    await db.commit()
                    print(f"  … committed {scanned}", flush=True)

            if args.dry_run:
                await db.rollback()
            else:
                await db.commit()

        elapsed = time.perf_counter() - started
        print(
            f"search documents: scanned={scanned} changed={changed} "
            f"empty={empty} dry_run={args.dry_run} elapsed={elapsed:.2f}s"
        )
        return 0
    finally:
        # dispose 必须与创建它的 event loop 在同一个协程里完成
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="回填 photos.search_document")
    parser.add_argument("--dry-run", action="store_true", help="只计算不落库")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 张")
    parser.add_argument("--batch", type=int, default=50, help="每 N 张提交一次")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
