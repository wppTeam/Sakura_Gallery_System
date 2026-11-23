#!/usr/bin/env python3
"""把年度相册策展成「专题」（collections）。

数据来源：`backend/seed/demo_manifest.json` 里每张演示图的 `album` 字段
（来自作者的年度总结目录，如「2024 七之一：生活瞬间」「2023/年度精选」）。
本脚本按 album 分组建立编辑策展专题，并按清单顺序写入 collection_photos。

幂等：按 slug upsert，重建该专题的条目顺序；不会删除专题之外的作品。
只把 `status=approved` 的作品挂进专题（待审作品审核通过后重跑即可）。

用法：
    cd backend && .venv/bin/python ../scripts/seed_collections.py --dry-run
    cd backend && .venv/bin/python ../scripts/seed_collections.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "backend" / "seed" / "demo_manifest.json"

# 每个专题的叙事（顺序即首页横滑顺序）。
# key 为 slug；album_prefixes 用于匹配 manifest 的 album（前缀匹配）。
COLLECTIONS = [
    {
        "slug": "2024-seven-chapters",
        "title": "2024 · 七乐章",
        "subtitle": "生活瞬间 · 可爱的东西 · 花开花飞春又来 · The Decisive Moments · 社畜群侠传 · ta在丛中笑 · 北化与我",
        "description": "把 2024 拆成七个乐章：日常、可爱、花期、决定性瞬间、打工、笑容与校园。一年很长，最后留下的往往只是几十个瞬间。",
        "album_prefixes": ["2024 七之"],
        "sort_order": 0,
    },
    {
        "slug": "2024-chapter-1-life",
        "title": "七之一 · 生活瞬间",
        "subtitle": "没有理由按快门的时刻",
        "description": "把一年里那些没有理由按快门的时刻留下来：路过的猫、窗上的光、桌角的一杯水。",
        "album_prefixes": ["2024 七之一"],
        "sort_order": 1,
    },
    {
        "slug": "2024-chapter-2-cute",
        "title": "七之二 · 可爱的东西",
        "subtitle": "可爱是抵抗疲惫的一种能力",
        "description": "猫、玩偶、路边的小东西。它们不解决问题，但确实让一天好过一点。",
        "album_prefixes": ["2024 七之二"],
        "sort_order": 2,
    },
    {
        "slug": "2024-chapter-3-bloom",
        "title": "七之三 · 花开花飞春又来",
        "subtitle": "花期很短，春天会再来",
        "description": "花期只有几天，但我们总能在照片里再遇见一次春天。",
        "album_prefixes": ["2024 七之三"],
        "sort_order": 3,
    },
    {
        "slug": "2024-chapter-4-decisive",
        "title": "七之四 · The Decisive Moments",
        "subtitle": "光、影子与动作刚好咬合的那一下",
        "description": "决定性瞬间：迟到一秒就不是这张照片了。",
        "album_prefixes": ["2024 七之四"],
        "sort_order": 4,
    },
    {
        "slug": "2024-chapter-5-office",
        "title": "七之五 · 社畜群侠传",
        "subtitle": "工位、通勤与深夜的江湖",
        "description": "打工人的江湖群像：早高峰、加班的灯、以及下班路上忽然很好看的天空。",
        "album_prefixes": ["2024 七之五"],
        "sort_order": 5,
    },
    {
        "slug": "2024-chapter-6-smiles",
        "title": "七之六 · ta在丛中笑",
        "subtitle": "镜头里的人",
        "description": "镜头里的人，笑起来的时候最像自己。",
        "album_prefixes": ["2024 七之六"],
        "sort_order": 6,
    },
    {
        "slug": "2024-chapter-7-campus",
        "title": "七之七 · 北化与我",
        "subtitle": "校园的楼、树、路与人",
        "description": "毕业之后才会发现，最想拍的是每天走过的那条路。",
        "album_prefixes": ["2024 七之七"],
        "sort_order": 7,
    },
    {
        "slug": "2024-campus-seasons",
        "title": "校园四季",
        "subtitle": "同一片校园，走过春夏秋冬",
        "description": "同一片校园，四种季节。春天有花，夏天有云，秋天有落叶，冬天有干净的光。",
        "album_prefixes": ["2024 校园四季"],
        "sort_order": 8,
    },
    {
        "slug": "2023-annual-selection",
        "title": "2023 · 年度精选",
        "subtitle": "从一整年里挑出最舍不得删的几张",
        "description": "2023 年的最后一天，从一整年挑出最舍不得删的几张。选片的标准很不客观：看的时候会停一下。",
        "album_prefixes": ["2023/年度精选"],
        "sort_order": 9,
    },
    {
        "slug": "2023-monthly-notes",
        "title": "2023 · 月度随笔",
        "subtitle": "十二个月里随手记下的光",
        "description": "每个月的相册里放一张。不是为了好看，是为了记得那一个月大概是什么样子。",
        "album_prefixes": ["2023 · "],
        "sort_order": 10,
    },
    {
        "slug": "2023-mobile-photography",
        "title": "2023 · 手机摄影",
        "subtitle": "没有相机也可以记录",
        "description": "手机镜头里的一年：画质不够，但当时的光线和心情都在。",
        "album_prefixes": ["2023/手机摄影"],
        "sort_order": 11,
    },
]


def _load_groups(dry_run: bool) -> OrderedDict[str, list[str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_id = {photo["id"]: photo for photo in manifest["photos"]}

    groups: OrderedDict[str, list[str]] = OrderedDict()
    for collection in COLLECTIONS:
        prefixes = tuple(collection["album_prefixes"])
        photo_ids = [
            photo["id"]
            for photo in manifest["photos"]
            if str(photo.get("album") or "").startswith(prefixes)
        ]
        # 去重并保持清单顺序；真正的 approved 过滤在 DB 侧再做一次
        deduped = list(dict.fromkeys(pid for pid in photo_ids if pid in by_id))
        groups[collection["slug"]] = deduped
        if dry_run:
            print(f"[dry-run] {collection['slug']}: {len(deduped)} 张候选")
    return groups


async def main_async(dry_run: bool) -> int:
    # app.core.config 的 env_file=".env" 相对 cwd 解析：必须先切到 backend/，
    # 否则会静默退回 sqlite 默认库。
    os.chdir(REPO_ROOT / "backend")
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import Collection, CollectionPhoto, Photo

    groups = _load_groups(dry_run)
    if dry_run:
        print("[dry-run] 未写库")
        return 0

    created = updated = total_entries = 0
    async with AsyncSessionLocal() as db:
        for meta in COLLECTIONS:
            slug = meta["slug"]
            candidate_ids = groups.get(slug) or []

            # 只挂 approved 的作品（待审的先不进专题）
            approved_ids: list[str] = []
            if candidate_ids:
                rows = (
                    await db.execute(
                        select(Photo.id)
                        .where(Photo.id.in_(candidate_ids), Photo.status == "approved")
                    )
                ).scalars().all()
                approved_set = set(rows)
                approved_ids = [pid for pid in candidate_ids if pid in approved_set]

            collection = (
                await db.execute(select(Collection).where(Collection.slug == slug))
            ).scalars().first()
            if collection is None:
                collection = Collection(slug=slug, kind="editorial")
                db.add(collection)
                created += 1
            else:
                updated += 1

            collection.title = meta["title"]
            collection.subtitle = meta["subtitle"]
            collection.description = meta["description"]
            collection.sort_order = meta["sort_order"]
            collection.kind = "editorial"
            collection.visibility = "public"
            collection.status = "published"
            collection.cover_photo_id = approved_ids[0] if approved_ids else None
            await db.flush()

            # 重建条目（先删后插，保持顺序）
            existing = (
                await db.execute(
                    select(CollectionPhoto).where(CollectionPhoto.collection_id == collection.id)
                )
            ).scalars().all()
            for entry in existing:
                await db.delete(entry)
            await db.flush()

            for position, photo_id in enumerate(approved_ids):
                db.add(
                    CollectionPhoto(
                        collection_id=collection.id,
                        photo_id=photo_id,
                        position=position,
                    )
                )
                total_entries += 1

            print(f"  {slug}: {len(approved_ids)} 张")

        await db.commit()

    print(f"完成：新建 {created} 个、更新 {updated} 个专题，共 {total_entries} 条作品关联")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="策展专题种子数据（幂等）")
    parser.add_argument("--dry-run", action="store_true", help="只打印分组，不写库")
    args = parser.parse_args()
    return asyncio.run(main_async(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
