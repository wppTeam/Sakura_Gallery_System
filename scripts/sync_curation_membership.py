"""回填 / 修复「光的一日」「樱色光谱」的自动策展成员。

用途：
- 部署了策展自动归档（审核链路自动维护成员）之后，把存量作品按最新规则校正一遍；
- 主题定义 / 时段规则改动后，用它在生产容器里跑一次（幂等，可反复执行）；
- 排查「作品已下架却还在专题里」这类脏数据。

与 `scripts/seed_curation.py` 的区别：seed 会重建每个专题的完整成员与顺序（运营手工
重排后以 seed 为准），本脚本只做增量校正——把缺的加进末尾、把不该在的移出，不动顺序、
不改文案。

用法（在仓库根目录）：
    backend/.venv/bin/python scripts/sync_curation_membership.py --dry-run
    backend/.venv/bin/python scripts/sync_curation_membership.py --limit 200

容器内（镜像把 backend/ 作为 /app）：
    docker cp scripts/sync_curation_membership.py sakura-prod-backend:/tmp/
    docker exec -w /app -e PYTHONPATH=/app sakura-prod-backend \
        python /tmp/sync_curation_membership.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if not (BACKEND_ROOT / "app").is_dir():
    # 容器内直接用当前目录（镜像把 backend/ 拷成 /app）
    BACKEND_ROOT = Path.cwd()
os.chdir(BACKEND_ROOT)
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.services.curation import sync_all_photos  # noqa: E402


async def _run(args: argparse.Namespace) -> dict[str, int]:
    try:
        async with AsyncSessionLocal() as db:
            if args.dry_run:
                # 用 rollback 保证 dry-run 不落库：sync 内部会 flush，但最终不 commit。
                summary = await sync_all_photos(db, limit=args.limit, commit=False)
                await db.rollback()
                return summary
            return await sync_all_photos(db, limit=args.limit)
    finally:
        # 连接池绑定在当前事件循环上，必须在本循环内关闭，否则解释器退出时报
        # RuntimeError: Event loop is closed（脚本仍会跑完，但退出码变 1）。
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="校正自动策展专题成员")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不落库")
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少张 approved 作品")
    args = parser.parse_args()

    summary = asyncio.run(_run(args))
    mode = "dry-run" if args.dry_run else "applied"
    print(
        f"策展成员校正完成（{mode}）：scanned={summary['scanned']} "
        f"added={summary['added']} removed={summary['removed']}"
    )


if __name__ == "__main__":
    main()
