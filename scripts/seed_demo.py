#!/usr/bin/env python3
"""Sakura Gallery 演示/开发环境种子数据脚本。

数据来源是作者本人（王海翔 / JackWPP）2023、2024 两个年度摄影总结的只读归档目录。
脚本只读取 NAS，把原图复制进 ``backend/uploads/``，随后走**生产同一条**图片管线：

* 等比缩放、绝不裁切（保留 16:9 / 4:5 等原始构图）；
* 缩略图长边 640、压缩图长边 ≤1600（JPEG，供列表/详情兜底）；
* 响应式变体 320 / 640 / 1080 / 1600 / 2400，WebP 主用 + JPEG 兜底；
* 20px 内联 LQIP 写入 ``photos.exif_data["_lqip"]``；
* EXIF 白名单脱敏：GPS、序列号、用户注释、Artist 等一律剥离后才入库。

用法（在仓库根目录或 backend 下执行均可）::

    backend/.venv/bin/python scripts/seed_demo.py --dry-run
    backend/.venv/bin/python scripts/seed_demo.py --limit 8
    backend/.venv/bin/python scripts/seed_demo.py
    backend/.venv/bin/python scripts/seed_demo.py --reset     # 先清理旧演示数据再重新入库

设计要点：

* 选片是**确定性**的（按文件名自然序 + 均匀抽样 + 内容 sha256 去重），重复执行结果一致；
* 照片/用户 id 用 uuid5 派生，重复执行不会产生重复数据（已存在的照片会跳过）；
* 用户口令优先取环境变量 ``SEED_DEMO_PASSWORD``，否则随机生成并写入
  ``backend/.seed-demo-credentials.json``（0600，已在 .gitignore 中忽略）；
* ``--reset`` 只删除本脚本写入的演示照片（按上传者与 manifest 定位），不碰其它数据。

注意：这是**开发演示**账号与演示数据，不具备生产含义；NAS 目录全程只读。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

# settings 的 .env / UPLOAD_DIR 都是相对路径：必须在 import app.* 之前切到 backend/
os.chdir(BACKEND_DIR)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

import app.models  # noqa: E402,F401  # 注册全部 ORM 表（reset 需要按外键清理）
from app.core.config import get_settings  # noqa: E402
from app.core.database import AsyncSessionLocal, Base  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.models import Photo, PhotoTag, Tag, User  # noqa: E402
from app.services.image_processing import process_uploaded_image  # noqa: E402
from app.services.storage import PersistedMedia, get_storage  # noqa: E402
from app.services.taxonomy import (  # noqa: E402
    ensure_default_taxonomy,
    resolve_legacy_photo_classifications,
    resolve_taxonomy_node,
    set_photo_classifications,
)

settings = get_settings()

# ── 数据源（只读 NAS）───────────────────────────────────────────────────
SOURCE_2023 = Path("/mnt/publicaccess/wppbackup/2023-end of year remix (2)")
SOURCE_2024 = Path("/mnt/publicaccess/wppbackup/2024-end of year-remix")

DEFAULT_MANIFEST = BACKEND_DIR / "seed" / "demo_manifest.json"
CREDENTIAL_FILE = BACKEND_DIR / ".seed-demo-credentials.json"

AUTHOR_NAME = "王海翔"
AUTHOR_EMAIL = "jackwpp@example.com"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}

# 公开身份（username / display_name）与 student_id 分离：公开端只展示前者。
# student_id 这里是本地演示值，不是真实学号；真实账号由学校 SSO 提供。
SEED_USERS: tuple[dict[str, str], ...] = (
    {
        "key": "author", "student_id": "jackwpp", "username": "jackwpp", "display_name": AUTHOR_NAME,
        "full_name": AUTHOR_NAME, "role": "user", "email": AUTHOR_EMAIL,
    },
    {
        "key": "admin", "student_id": "seed-admin", "username": "sakura_staff", "display_name": "视觉百花编辑部",
        "full_name": "视觉百花管理员", "role": "admin", "email": "seed-admin@example.com",
    },
    {
        "key": "auditor", "student_id": "seed-auditor", "username": "sakura_review", "display_name": "内容审核员",
        "full_name": "内容审核员", "role": "auditor", "email": "seed-auditor@example.com",
    },
    {
        "key": "viewer", "student_id": "seed-viewer", "username": "sakura_viewer", "display_name": "测试同学",
        "full_name": "测试同学", "role": "user", "email": "seed-viewer@example.com",
    },
)

SEASON_LABEL = {"Spring": "春季", "Summer": "夏季", "Autumn": "秋季", "Winter": "冬季"}
SEASON_BY_MONTH = {
    12: "Winter", 1: "Winter", 2: "Winter",
    3: "Spring", 4: "Spring", 5: "Spring",
    6: "Summer", 7: "Summer", 8: "Summer",
    9: "Autumn", 10: "Autumn", 11: "Autumn",
}
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}

# 2024「套曲 平凡的一天」七个乐章：题材 / 校区 / 题材细分 / 默认标签
ALBUM_META: dict[str, dict[str, Any]] = {
    "一": {"count": 5, "category": "Documentary", "tags": ["日常"], "campus": None, "photo_type": None},
    "二": {"count": 5, "category": "Documentary", "tags": ["可爱"], "campus": None, "photo_type": None},
    "三": {"count": 5, "category": "Landscape", "tags": ["花"], "campus": None, "photo_type": "自然生态"},
    "四": {"count": 5, "category": "Documentary", "tags": ["街头"], "campus": None, "photo_type": None},
    "五": {"count": 4, "category": "Activity", "tags": ["活动"], "campus": None, "photo_type": None},
    "六": {"count": 6, "category": "Documentary", "tags": ["笑容"], "campus": None, "photo_type": None, "status": "pending"},
    "七": {"count": 5, "category": "Landscape", "tags": ["校园", "北化"], "campus": "昌平校区", "photo_type": None},
}

# 2023 月度随笔的关键词 → 题材 / 标签
CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Activity", ("活动", "比赛", "现场", "演出", "合唱", "音乐会", "舞台", "运动", "毕业", "会议", "晚会", "谢幕")),
    ("Documentary", ("笑", "人像", "同学", "朋友", "街头", "家人", "妈妈", "高中生", "市民", "大爷", "合影", "小狗", "猫", "可爱", "逼哥", "市民")),
    ("Landscape", ("海", "夕阳", "晚霞", "山", "湖", "花", "雪", "云", "建筑", "夜景", "风光", "天空", "城市", "街道", "光影", "俯瞰")),
)
TAG_KEYWORDS: dict[str, str] = {
    "海": "海边", "夕阳": "夕阳", "晚霞": "晚霞", "雪": "雪", "花": "花",
    "猫": "猫", "狗": "狗", "合唱": "合唱", "街头": "街头", "校园": "校园",
    "夜景": "夜景", "山": "山", "湖": "湖", "天空": "天空", "建筑": "建筑",
    "笑": "笑容", "阳光": "阳光", "云": "云", "树": "树",
}

SEED_BASE = datetime.utcnow().replace(microsecond=0) - timedelta(hours=2)


# ── 小工具 ──────────────────────────────────────────────────────────────


def log(message: str) -> None:
    print(message, flush=True)


def _truncate(text: str, limit: int = 200) -> str:
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _natural_key(path: Path) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(path: Path) -> str:
    return str(path.resolve())


def _relative_to_uploads(path: str | Path, uploads_dir: Path) -> str:
    return str(Path(path).resolve().relative_to(uploads_dir.resolve()))


def _has_gps(path: Path) -> bool:
    """只读图片头判断源文件是否带 GPS IFD（用于 manifest 证明已剥离）。"""
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            gps = exif.get_ifd(0x8825) if exif else {}
            return bool(gps)
    except Exception:  # noqa: BLE001 - 损坏文件不应中断选片
        return False


def _evenly_indices(total: int, n: int) -> list[int]:
    if total <= 0 or n <= 0:
        return []
    if n >= total:
        return list(range(total))
    if n == 1:
        return [total // 2]
    return sorted({round(i * (total - 1) / (n - 1)) for i in range(n)})


def _pick_order(items: Sequence[Any], n: int) -> list[Any]:
    """返回“优先抽 n 张均匀分布样本，其余作为去重替补”的顺序列表。"""
    if not items:
        return []
    idx = _evenly_indices(len(items), n)
    idx_set = set(idx)
    return [items[i] for i in idx] + [items[i] for i in range(len(items)) if i not in idx_set]


def _round_robin(lists: Sequence[Sequence[Any]]) -> list[Any]:
    merged: list[Any] = []
    longest = max((len(items) for items in lists), default=0)
    for index in range(longest):
        for items in lists:
            if index < len(items):
                merged.append(items[index])
    return merged


def _short_title(commentary: Sequence[str], stem: str, limit: int = 24) -> str:
    for raw in commentary:
        text = raw.strip().lstrip("-*").strip()
        text = re.sub(r"^[【\[（(]", "", text).rstrip("。，、！？!?.,;；:：~～")
        if text:
            return _truncate(text, limit)
    return _truncate(stem, limit)


def _category_from_text(text: str) -> str:
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return category
    return "Landscape"


def _tags_from_text(text: str, limit: int = 3) -> list[str]:
    tags: list[str] = []
    for keyword, tag in TAG_KEYWORDS.items():
        if keyword in text and tag not in tags:
            tags.append(tag)
        if len(tags) >= limit:
            break
    return tags


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        clean = item.strip()
        if clean and clean not in seen:
            seen.add(clean)
            ordered.append(clean)
    return ordered


# ── 选片模型 ────────────────────────────────────────────────────────────


@dataclass
class Candidate:
    source: Path
    group: str
    album: str
    category: str
    title_prefix: str
    description: str
    tags: list[str] = field(default_factory=list)
    title: str | None = None
    season: str | None = None
    season_auto: bool = False
    fallback_month: int | None = None
    campus: str | None = None
    photo_type: str | None = None
    status: str = "approved"
    sha256: str = ""
    photo_id: str = ""
    gps_in_source: bool = False


@dataclass
class GroupSpec:
    key: str
    label: str
    count: int
    entries: list[Candidate]


@dataclass
class ProcessedPhoto:
    candidate: Candidate
    photo_id: str
    width: int
    height: int
    file_size: int
    captured_at: datetime | None
    season: str | None
    exif_data: dict[str, Any]
    stored: PersistedMedia
    variants: dict[int, dict[str, Any]]
    gps_in_source: bool
    lqip_chars: int
    original_recompressed: bool = False


# ── 2024「套曲 平凡的一天」─────────────────────────────────────────────

ALBUM_HEADING_RE = re.compile(r"^##\s*七之([一二三四五六七])[：:]\s*(.+?)\s*$")
ALBUM_SONG_RE = re.compile(r"^七之([一二三四五六七])[：:]\s*(.+?)--\s*\*\*(.+?)\*\*")
ALBUM_DIR_RE = re.compile(r"^七之([一二三四五六七])[：:]")


def parse_2024_plan(plan_path: Path) -> dict[str, dict[str, Any]]:
    """解析 2024 策划.md：乐章名 + 对应歌曲 + 导语段落。"""
    albums: dict[str, dict[str, Any]] = {}
    songs: dict[str, str] = {}
    current: str | None = None

    for raw in plan_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        song_match = ALBUM_SONG_RE.match(line)
        if song_match:
            songs.setdefault(song_match.group(1), song_match.group(3).strip())
            continue
        heading_match = ALBUM_HEADING_RE.match(line)
        if heading_match:
            num = heading_match.group(1)
            albums.setdefault(num, {"album": heading_match.group(2).strip(), "paragraphs": []})
            current = num
            continue
        if line.startswith("#"):
            current = None
            continue
        if current:
            albums[current]["paragraphs"].append(line)

    for num, meta in albums.items():
        meta["song"] = songs.get(num, "")
    return albums


def _album_intro(paragraphs: Sequence[str], limit: int = 200) -> str:
    text = ""
    for paragraph in paragraphs:
        text = paragraph if not text else f"{text} {paragraph}"
        if len(text) >= 90:
            break
    return _truncate(text, limit)


def _find_album_dir(root: Path, num: str) -> Path | None:
    for entry in sorted(root.iterdir(), key=_natural_key):
        if not entry.is_dir():
            continue
        match = ALBUM_DIR_RE.match(entry.name)
        if match and match.group(1) == num:
            return entry
    return None


def _image_files(directory: Path) -> list[Path]:
    return [
        path
        for path in sorted(directory.iterdir(), key=_natural_key)
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    ]


def build_2024_album_groups(root: Path) -> list[GroupSpec]:
    plan = parse_2024_plan(root / "策划.md") if (root / "策划.md").exists() else {}
    groups: list[GroupSpec] = []
    for num in ["一", "二", "三", "四", "五", "六", "七"]:
        meta = ALBUM_META[num]
        album_dir = _find_album_dir(root, num)
        if album_dir is None:
            log(f"[warn] 找不到 2024 乐章目录 七之{num}，跳过")
            continue
        files = _image_files(album_dir)
        if not files:
            log(f"[warn] 七之{num} 目录没有图片，跳过")
            continue
        plan_meta = plan.get(num, {})
        album_name = plan_meta.get("album") or album_dir.name.split("：", 1)[-1].split(":", 1)[-1]
        song = plan_meta.get("song", "")
        intro = _album_intro(plan_meta.get("paragraphs", [])) or f"2024 年度总结 · {album_name}"
        description = _truncate(f"配乐 {song}｜{intro}" if song else intro, 200)
        tags = _dedupe(["2024年度总结", album_name, *meta.get("tags", [])])
        entries: list[Candidate] = []
        for source in _pick_order(files, meta["count"]):
            entries.append(
                Candidate(
                    source=source,
                    group=f"2024/七之{num}",
                    album=f"2024 七之{num}：{album_name}",
                    category=meta["category"],
                    title_prefix=f"七之{num} · {album_name}",
                    description=description,
                    tags=list(tags),
                    season_auto=True,
                    campus=meta.get("campus"),
                    photo_type=meta.get("photo_type"),
                    status=meta.get("status", "approved"),
                )
            )
        groups.append(
            GroupSpec(key=f"2024/七之{num}", label=f"2024 七之{num}：{album_name}", count=meta["count"], entries=entries)
        )
    return groups


def build_2024_season_group(root: Path) -> GroupSpec | None:
    per_season: list[list[Candidate]] = []
    season_dir_names = {"Spring": "春", "Summer": "夏", "Autumn": "秋", "Winter": "冬"}
    for season, label in SEASON_LABEL.items():
        season_dir = root / season_dir_names[season]
        if not season_dir.is_dir():
            log(f"[warn] 找不到 2024 季节目录 {season_dir.name}，跳过")
            continue
        files = _image_files(season_dir)
        if not files:
            continue
        entries: list[Candidate] = []
        for source in _pick_order(files, 2):
            entries.append(
                Candidate(
                    source=source,
                    group="2024/校园四季",
                    album="2024 校园四季",
                    category="Landscape",
                    title_prefix=f"2024 校园{label}",
                    description=_truncate(f"2024 年校园的{label}（昌平校区）。", 200),
                    tags=_dedupe(["2024年度总结", "校园四季", label]),
                    season=season,
                    campus="昌平校区",
                    photo_type="自然生态",
                )
            )
        per_season.append(entries)
    if not per_season:
        return None
    return GroupSpec(key="2024/校园四季", label="2024 校园四季", count=8, entries=_round_robin(per_season))


# ── 2023 月度随笔 / 年度精选 / 手机摄影 ───────────────────────────────

MONTH_DIR_RE = re.compile(r"^(\d{1,2})月$")
IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
MONTH_DIR_MD_NAMES = ("{month}月.md", "N月.md")


def parse_month_markdown(md_path: Path) -> dict[str, list[str]]:
    """解析月度随笔：图片 basename → 该图的评注行。"""
    entries: dict[str, list[str]] = {}
    current: str | None = None
    for raw in md_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        match = IMAGE_REF_RE.search(line)
        if match:
            basename = re.split(r"[\\/]", match.group(1))[-1].strip()
            current = basename
            entries.setdefault(basename, [])
            continue
        if line.startswith(("- ", "* ")) and current:
            entries[current].append(line[2:].strip())
            continue
        if line == "---":
            current = None
    return entries


def _month_markdown(month_dir: Path) -> Path | None:
    markdowns = sorted(month_dir.glob("*.md"))
    return markdowns[0] if markdowns else None


def build_2023_month_group(root: Path) -> GroupSpec | None:
    month_dirs: list[tuple[int, Path]] = []
    for entry in sorted(root.iterdir(), key=_natural_key):
        match = MONTH_DIR_RE.match(entry.name)
        if match and entry.is_dir():
            month_dirs.append((int(match.group(1)), entry))
    month_dirs.sort(key=lambda item: item[0])

    per_month: list[list[Candidate]] = []
    for month, month_dir in month_dirs:
        files = _image_files(month_dir)
        if not files:
            log(f"[warn] {month_dir.name} 没有图片，跳过")
            continue
        markdown_path = _month_markdown(month_dir)
        commentary_map = parse_month_markdown(markdown_path) if markdown_path else {}
        commented = [path for path in files if commentary_map.get(path.name)]
        ordered = commented + [path for path in files if path not in commented]

        entries: list[Candidate] = []
        for source in ordered:
            commentary = commentary_map.get(source.name, [])
            text = " ".join(commentary)
            description = _truncate(" ".join(commentary), 200) or f"2023 年 {month} 月精选。"
            tags = _dedupe(["2023年度总结", f"{month}月", *_tags_from_text(text)])
            entries.append(
                Candidate(
                    source=source,
                    group="2023/月度随笔",
                    album=f"2023 · {month}月",
                    category=_category_from_text(text),
                    title_prefix=f"{month}月",
                    description=description,
                    tags=tags,
                    title=f"{month}月 · {_short_title(commentary, source.stem)}",
                    season=SEASON_BY_MONTH[month],
                    fallback_month=month,
                )
            )
        per_month.append(entries)

    if not per_month:
        return None
    return GroupSpec(
        key="2023/月度随笔",
        label="2023 月度随笔",
        count=len(per_month),
        entries=_round_robin(per_month),
    )


def _build_numbered_group(
    group_key: str,
    label: str,
    files: Sequence[Path],
    count: int,
    title_prefix: str,
    description: str,
    tags: Sequence[str],
    category: str,
    season_auto: bool,
) -> GroupSpec | None:
    if not files:
        return None
    entries: list[Candidate] = []
    for source in files:
        entries.append(
            Candidate(
                source=source,
                group=group_key,
                album=group_key,
                category=category,
                title_prefix=title_prefix,
                description=description,
                tags=list(tags),
                season_auto=season_auto,
            )
        )
    return GroupSpec(key=group_key, label=label, count=min(count, len(entries)), entries=entries)


def build_2023_best9_group(root: Path) -> GroupSpec | None:
    best_dir = root / "年度 9张图"
    files = _image_files(best_dir) if best_dir.is_dir() else []
    if not files:
        return None
    ordered = _pick_order(files, 5)
    return _build_numbered_group(
        group_key="2023/年度精选",
        label="2023 年度精选",
        files=ordered,
        count=5,
        title_prefix="2023 年度精选",
        description="2023 年度九图：一年里最想留下的九张。",
        tags=["2023年度总结", "年度精选"],
        category="Landscape",
        season_auto=True,
    )


def build_2023_phone_group(root: Path) -> GroupSpec | None:
    phone_dir = root / "年度 手机摄影"
    files = _image_files(phone_dir) if phone_dir.is_dir() else []
    if not files:
        return None
    with_gps = [path for path in files if _has_gps(path)]
    without_gps = [path for path in files if path not in with_gps]
    head = _pick_order(with_gps, 2) + _pick_order(without_gps, 2)
    rest = [path for path in files if path not in head]
    ordered = head + rest
    return _build_numbered_group(
        group_key="2023/手机摄影",
        label="2023 手机摄影",
        files=ordered,
        count=4,
        title_prefix="2023 手机摄影",
        description="2023 手机摄影：随身记录。",
        tags=["2023年度总结", "手机摄影"],
        category="Documentary",
        season_auto=True,
    )


# ── 选片（确定性 + 内容去重）──────────────────────────────────────────


def build_groups(root_2023: Path, root_2024: Path) -> list[GroupSpec]:
    groups: list[GroupSpec] = []
    if root_2024.is_dir():
        groups.extend(build_2024_album_groups(root_2024))
        season_group = build_2024_season_group(root_2024)
        if season_group:
            groups.append(season_group)
    else:
        log(f"[warn] 2024 素材目录不存在：{root_2024}")
    if root_2023.is_dir():
        month_group = build_2023_month_group(root_2023)
        if month_group:
            groups.append(month_group)
        for builder in (build_2023_best9_group, build_2023_phone_group):
            group = builder(root_2023)
            if group:
                groups.append(group)
    else:
        log(f"[warn] 2023 素材目录不存在：{root_2023}")
    return groups


def select_candidates(groups: list[GroupSpec], limit: int | None = None) -> list[Candidate]:
    seen: set[str] = set()
    chosen_per_group: list[list[Candidate]] = []

    for spec in groups:
        chosen: list[Candidate] = []
        for cand in spec.entries:
            if not cand.sha256:
                cand.sha256 = sha256_file(cand.source)
            if cand.sha256 in seen:
                log(f"[dedupe] 跳过重复图像：{cand.source.name}（{spec.label}）")
                continue
            seen.add(cand.sha256)
            cand.photo_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sakura-seed:{cand.group}:{cand.sha256[:24]}"))
            cand.gps_in_source = _has_gps(cand.source)
            chosen.append(cand)
            if len(chosen) >= spec.count:
                break
        if len(chosen) < spec.count:
            log(f"[warn] {spec.label} 去重后只剩 {len(chosen)} 张（计划 {spec.count}）")
        for index, cand in enumerate(chosen, start=1):
            if not cand.title:
                cand.title = f"{cand.title_prefix} {index:02d}"
        chosen_per_group.append(chosen)

    interleaved: list[Candidate] = []
    longest = max((len(items) for items in chosen_per_group), default=0)
    for round_index in range(longest):
        for chosen in chosen_per_group:
            if round_index < len(chosen):
                interleaved.append(chosen[round_index])
    if limit is not None:
        interleaved = interleaved[: max(limit, 0)]
    return interleaved


# ── 图片处理 ────────────────────────────────────────────────────────────


def resolve_season(candidate: Candidate, captured_at: datetime | None) -> str | None:
    if candidate.season:
        return candidate.season
    month = captured_at.month if captured_at else candidate.fallback_month
    return SEASON_BY_MONTH.get(month) if month else None


def _fit_upload_limit(path: Path, max_bytes: int) -> bool:
    """把超过上传上限的原图就地重编码到上限内（保持分辨率、构图与 EXIF），返回是否改动。

    种子数据直接落盘绕过上传接口，但演示要复现真实链路（审核规则层也会校验体积），
    因此对个别的 20MB+ 原图做等尺寸重编码，避免被 file_too_large 规则误拦。
    """
    if path.stat().st_size <= max_bytes:
        return False
    with Image.open(path) as img:
        raw_exif = img.info.get("exif")
        for quality in (92, 88, 84, 80, 76):
            tmp = path.with_suffix(path.suffix + ".tmp")
            img.save(tmp, format="JPEG", quality=quality, exif=raw_exif, optimize=True)
            if tmp.stat().st_size <= max_bytes:
                tmp.replace(path)
                log(f"[recompress] {path.name} → {quality=} {path.stat().st_size/1048576:.1f}MB")
                return True
            tmp.unlink()
    raise RuntimeError(f"无法把原图压到上传上限内：{path}")


def _verify_derivatives(
    original_width: int,
    original_height: int,
    thumb_path: str,
    compressed_path: str,
    variants: dict[int, dict[str, Any]],
) -> None:
    with Image.open(thumb_path) as thumb:
        thumb_width, thumb_height = thumb.size
    with Image.open(compressed_path) as compressed:
        compressed_width, compressed_height = compressed.size
    original_ratio = original_width / original_height
    thumb_ratio = thumb_width / thumb_height
    compressed_ratio = compressed_width / compressed_height
    if abs(thumb_ratio - original_ratio) > 0.01 or abs(compressed_ratio - original_ratio) > 0.01:
        raise RuntimeError(
            f"派生图比例与原图不一致（疑似裁切）：{original_width}x{original_height} "
            f"thumb={thumb_width}x{thumb_height} compressed={compressed_width}x{compressed_height}"
        )
    if max(thumb_width, thumb_height) > 640:
        raise RuntimeError(f"缩略图长边超过 640：{thumb_width}x{thumb_height}")
    if max(compressed_width, compressed_height) > 1600:
        raise RuntimeError(f"压缩图长边超过 1600：{compressed_width}x{compressed_height}")
    native_long_edge = max(original_width, original_height)
    for size, info in variants.items():
        if size > native_long_edge:
            raise RuntimeError(f"变体 {size} 大于原图长边 {native_long_edge}（不应放大）")
        if info["webp_bytes"] <= 0 or info["jpeg_bytes"] <= 0:
            raise RuntimeError(f"变体 {size} 为空文件")


def process_one(
    candidate: Candidate,
    index: int,
    total: int,
    storage: Any,
    uploads_dir: Path,
    *,
    skip_variants: bool = False,
) -> ProcessedPhoto:
    started = time.time()
    photo_uuid = candidate.photo_id
    variants_dir = None if skip_variants else uploads_dir / "variants" / photo_uuid
    stage_dir = Path(tempfile.mkdtemp(prefix="buct-seed-stage-"))
    try:
        staged_original = stage_dir / candidate.source.name
        shutil.copy2(candidate.source, staged_original)
        recompressed = _fit_upload_limit(
            staged_original,
            int(settings.MAX_UPLOAD_SIZE) - 512 * 1024,  # 留 0.5MB 余量，与真实上传限制对齐
        )
        result = process_uploaded_image(
            str(staged_original),
            photo_uuid,
            output_dir=str(stage_dir),
            variants_dir=str(variants_dir) if variants_dir else None,
            generate_placeholder=True,
            strict=True,
        )
        width = result.get("width")
        height = result.get("height")
        thumb_path = result.get("thumb_path")
        compressed_path = result.get("compressed_path")
        if not width or not height or not thumb_path or not compressed_path:
            raise RuntimeError("图片处理结果缺少尺寸/缩略图/压缩图")
        if not Path(thumb_path).is_file() or not Path(compressed_path).is_file():
            raise RuntimeError("缩略图或压缩图未生成")
        variants = {int(size): info for size, info in (result.get("variants") or {}).items()}
        _verify_derivatives(width, height, str(thumb_path), str(compressed_path), variants)

        stored = storage.persist_photo_files(photo_uuid, str(staged_original), str(thumb_path), str(compressed_path))
        if not stored.original_path or not Path(settings.UPLOAD_DIR, stored.original_path).is_file():
            raise RuntimeError("原图未落盘")
        if not Path(settings.UPLOAD_DIR, stored.thumb_path or "").is_file():
            raise RuntimeError("缩略图未落盘")

        relative_variants: dict[int, dict[str, Any]] = {}
        for size, info in variants.items():
            relative_variants[size] = {
                "width": info["width"],
                "height": info["height"],
                "webp": _relative_to_uploads(info["webp"], uploads_dir),
                "jpeg": _relative_to_uploads(info["jpeg"], uploads_dir),
                "webp_bytes": info["webp_bytes"],
                "jpeg_bytes": info["jpeg_bytes"],
            }

        exif_data = dict(result.get("exif_data") or {})
        lqip = exif_data.get("_lqip") or ""
        if not lqip.startswith("data:image/webp;base64,"):
            raise RuntimeError("LQIP 未生成")
        captured_at = result.get("captured_at")
        season = resolve_season(candidate, captured_at)
        elapsed = time.time() - started
        log(
            f"[{index:>2}/{total}] {candidate.title:<34} {width}x{height} "
            f"→ {candidate.category}/{season or '-'} 变体={sorted(relative_variants)} ({elapsed:.1f}s)"
        )
        return ProcessedPhoto(
            candidate=candidate,
            photo_id=photo_uuid,
            width=int(width),
            height=int(height),
            file_size=int(stored.file_size or candidate.source.stat().st_size),
            captured_at=captured_at,
            season=season,
            exif_data=exif_data,
            stored=stored,
            variants=relative_variants,
            gps_in_source=candidate.gps_in_source,
            lqip_chars=len(lqip),
            original_recompressed=recompressed,
        )
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


# ── 数据库写入 ──────────────────────────────────────────────────────────


async def _upsert_users(session: Any, password: str) -> dict[str, str]:
    hashed = get_password_hash(password)
    ids: dict[str, str] = {}
    for spec in SEED_USERS:
        username = spec.get("username") or None
        if username:
            conflict = await session.scalar(
                select(User).where(User.username == username, User.student_id != spec["student_id"])
            )
            if conflict is not None:
                log(f"[warn] username={username} 已被占用，跳过设置公开用户名")
                username = None
        existing = await session.scalar(select(User).where(User.student_id == spec["student_id"]))
        if existing:
            existing.full_name = spec["full_name"]
            existing.username = username
            existing.display_name = spec.get("display_name") or spec["full_name"]
            existing.role = spec["role"]
            existing.email = spec["email"]
            existing.hashed_password = hashed
            existing.is_active = True
            ids[spec["key"]] = existing.id
        else:
            user = User(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"sakura-seed-user:{spec['student_id']}")),
                student_id=spec["student_id"],
                username=username,
                display_name=spec.get("display_name") or spec["full_name"],
                email=spec["email"],
                hashed_password=hashed,
                full_name=spec["full_name"],
                role=spec["role"],
                is_active=True,
            )
            session.add(user)
            ids[spec["key"]] = user.id
    await session.flush()
    return ids


async def _upsert_tags(session: Any, names: Sequence[str]) -> dict[str, Tag]:
    mapping: dict[str, Tag] = {}
    for name in names:
        existing = await session.scalar(select(Tag).where(Tag.name == name))
        if existing is None:
            existing = Tag(name=name, category="主题")
            session.add(existing)
            await session.flush()
        mapping[name] = existing
    return mapping


async def seed_database(photos: Sequence[ProcessedPhoto], password: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        await ensure_default_taxonomy(session)
        await session.flush()
        user_ids = await _upsert_users(session, password)
        author_id = user_ids["author"]

        all_tag_names = sorted({tag for item in photos for tag in item.candidate.tags})
        tags = await _upsert_tags(session, all_tag_names)
        # 标签热度按“全部种子照片”统计（含此前已入库、本次跳过的），保证重复执行后计数仍正确
        tag_usage = Counter(name for item in photos for name in set(item.candidate.tags))
        for name, tag in tags.items():
            tag.usage_count = tag_usage.get(name, 0)

        inserted = 0
        skipped = 0
        for index, item in enumerate(photos):
            candidate = item.candidate
            existing = await session.get(Photo, item.photo_id)
            if existing is not None:
                skipped += 1
                log(f"[skip] 已存在，跳过入库：{candidate.title}")
                continue
            created_at = SEED_BASE - timedelta(minutes=index * 37)
            published_at = created_at + timedelta(hours=2) if candidate.status == "approved" else None
            photo = Photo(
                id=item.photo_id,
                uploader_id=author_id,
                filename=candidate.source.name,
                title=candidate.title,
                author=AUTHOR_NAME,
                original_path=item.stored.original_path,
                processed_path=None,
                thumb_path=item.stored.thumb_path,
                compressed_path=item.stored.compressed_path,
                width=item.width,
                height=item.height,
                file_size=item.file_size,
                mime_type="image/jpeg",
                season=item.season,
                category=candidate.category,
                campus=candidate.campus,
                description=candidate.description,
                exif_data=item.exif_data,
                status=candidate.status,
                processing_status="manual" if candidate.status == "approved" else "pending",
                created_at=created_at,
                updated_at=created_at,
                captured_at=item.captured_at,
                published_at=published_at,
                views=(12 + (index * 29) % 300) if candidate.status == "approved" else 0,
            )
            session.add(photo)
            await session.flush()  # 触发器会据此生成 search_tokens / search_vector

            for tag_name in candidate.tags:
                tag = tags[tag_name]
                session.add(PhotoTag(photo_id=photo.id, tag_id=tag.id))

            classifications = await resolve_legacy_photo_classifications(
                session,
                season=item.season,
                category=(None if candidate.photo_type else candidate.category),
                campus=candidate.campus,
            )
            if candidate.photo_type:
                node = await resolve_taxonomy_node(session, "photo_type", candidate.photo_type)
                if node is not None:
                    classifications["photo_type"] = node.id
            if classifications:
                await set_photo_classifications(session, photo, classifications)
            inserted += 1

        await session.commit()
        return {"inserted": inserted, "skipped": skipped, "user_ids": user_ids}


# ── 清理（--reset）─────────────────────────────────────────────────────


def _manifest_photo_ids(manifest_path: Path) -> set[str]:
    if not manifest_path.exists():
        return set()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(entry.get("id")) for entry in payload.get("photos", []) if entry.get("id")}


async def reset_demo(manifest_path: Path, uploads_dir: Path) -> dict[str, Any]:
    manifest_ids = _manifest_photo_ids(manifest_path)
    markers = [spec["student_id"] for spec in SEED_USERS]

    async with AsyncSessionLocal() as session:
        seed_user_ids = list((await session.scalars(select(User.id).where(User.student_id.in_(markers)))).all())
        photo_ids = set(manifest_ids)
        if seed_user_ids:
            photo_ids |= set((await session.scalars(select(Photo.id).where(Photo.uploader_id.in_(seed_user_ids)))).all())

        file_paths: list[str] = []
        if photo_ids:
            rows = await session.scalars(select(Photo).where(Photo.id.in_(photo_ids)))
            for photo in rows:
                for path in (photo.original_path, photo.thumb_path, photo.compressed_path):
                    if path:
                        file_paths.append(path)

            for table in Base.metadata.sorted_tables:
                for fk in table.foreign_keys:
                    if fk.column.table.name != "photos":
                        continue
                    column = fk.parent
                    await session.execute(delete(table).where(column.in_(photo_ids)))
            await session.execute(delete(Photo).where(Photo.id.in_(photo_ids)))
        await session.commit()

    storage = get_storage()
    removed = 0
    for relative in file_paths:
        if storage.delete_file(relative):
            removed += 1
    for photo_id in photo_ids:
        variant_dir = uploads_dir / "variants" / photo_id
        if variant_dir.is_dir():
            shutil.rmtree(variant_dir, ignore_errors=True)
    if manifest_path.exists():
        manifest_path.unlink()
    return {"photos": len(photo_ids), "files": removed}


# ── manifest / 输出 ─────────────────────────────────────────────────────


def build_manifest(photos: Sequence[ProcessedPhoto], user_ids: dict[str, str]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for item in photos:
        candidate = item.candidate
        entries.append(
            {
                "id": item.photo_id,
                "title": candidate.title,
                "album": candidate.album,
                "group": candidate.group,
                "status": candidate.status,
                "category": candidate.category,
                "season": item.season,
                "campus": candidate.campus,
                "photo_type": candidate.photo_type,
                "tags": candidate.tags,
                "width": item.width,
                "height": item.height,
                "captured_at": item.captured_at.isoformat() if item.captured_at else None,
                "mime_type": "image/jpeg",
                "file_size": item.file_size,
                "source": _resolve(candidate.source),
                "source_sha256": candidate.sha256,
                "gps_in_source": item.gps_in_source,
                "target_filename": candidate.source.name,
                "files": {
                    "original": item.stored.original_path,
                    "thumbnail": item.stored.thumb_path,
                    "compressed": item.stored.compressed_path,
                    "variants": {str(size): info for size, info in sorted(item.variants.items())},
                },
                "lqip_chars": item.lqip_chars,
                "original_recompressed": item.original_recompressed,
            }
        )
    by_album = Counter(item["album"] for item in entries)
    total_bytes = sum(int(item["file_size"] or 0) for item in entries)
    return {
        "schema": 1,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "generator": "scripts/seed_demo.py",
        "source_dirs": {"2023": str(SOURCE_2023), "2024": str(SOURCE_2024)},
        "users": [
            {
                "student_id": spec["student_id"],
                "username": spec.get("username"),
                "display_name": spec.get("display_name"),
                "full_name": spec["full_name"],
                "role": spec["role"],
                "email": spec["email"],
                "id": user_ids.get(spec["key"]),
            }
            for spec in SEED_USERS
        ],
        "photos": entries,
        "stats": {
            "total": len(entries),
            "approved": sum(1 for item in entries if item["status"] == "approved"),
            "pending": sum(1 for item in entries if item["status"] == "pending"),
            "total_bytes": total_bytes,
            "by_album": dict(sorted(by_album.items())),
        },
    }


def write_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"[manifest] 写入 {manifest_path}（{len(payload['photos'])} 张）")


def write_credentials(password: str) -> Path:
    payload = {
        "note": "本地开发演示账号，非真实凭据；可用 SEED_DEMO_PASSWORD 环境变量覆盖",
        "password": password,
        "login": "POST /api/v1/auth/login  body={identifier, password}",
        "users": [
            {
                "student_id": spec["student_id"],
                "username": spec.get("username"),
                "display_name": spec.get("display_name"),
                "role": spec["role"],
            }
            for spec in SEED_USERS
        ],
    }
    CREDENTIAL_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CREDENTIAL_FILE.chmod(0o600)
    return CREDENTIAL_FILE


def print_plan(candidates: Sequence[Candidate]) -> None:
    groups = Counter(candidate.group for candidate in candidates)
    log("\n=== 选片计划 ===")
    for group, count in sorted(groups.items()):
        log(f"  {group:<20} {count:>2} 张")
    approved = sum(1 for item in candidates if item.status == "approved")
    pending = sum(1 for item in candidates if item.status == "pending")
    total_bytes = sum(item.source.stat().st_size for item in candidates)
    with_gps = sum(1 for item in candidates if item.gps_in_source)
    log(
        f"  合计 {len(candidates)} 张（approved={approved}, pending={pending}）"
        f"，源文件 {total_bytes / 1024 / 1024:.1f} MB，含 GPS 源图 {with_gps} 张"
    )
    log("\n  预览（前 8 张）：")
    for item in candidates[:8]:
        log(f"    - [{item.group}] {item.title}  ({item.source.name})")
    upload_dir = Path(settings.UPLOAD_DIR)
    usage = shutil.disk_usage(upload_dir if upload_dir.exists() else REPO_ROOT)
    if usage.free < total_bytes * 2:
        log(f"  [warn] 磁盘剩余 {usage.free / 1024 / 1024 / 1024:.1f} GB，可能不足以复制原图与变体")


def print_summary(photos: Sequence[ProcessedPhoto], elapsed: float, seed_stats: dict[str, Any]) -> None:
    by_group = Counter(item.candidate.group for item in photos)
    positions = Counter(item.candidate.campus for item in photos if item.candidate.campus)
    approved = sum(1 for item in photos if item.candidate.status == "approved")
    pending = sum(1 for item in photos if item.candidate.status == "pending")
    log("\n=== 入库结果 ===")
    for group, count in sorted(by_group.items()):
        log(f"  {group:<20} {count:>2} 张")
    log(f"  approved={approved}  pending={pending}  skipped={seed_stats.get('skipped', 0)}")
    if positions:
        log(f"  校区分布：{dict(positions)}")
    total_bytes = sum(item.file_size for item in photos)
    variants_count = sum(len(item.variants) for item in photos)
    lqip_count = sum(1 for item in photos if item.lqip_chars > 0)
    gps_count = sum(1 for item in photos if item.gps_in_source)
    log(f"  原图 {total_bytes / 1024 / 1024:.1f} MB，变体 {variants_count} 张，LQIP {lqip_count} 张，源图带 GPS 且已剥离 {gps_count} 张")
    log(f"  耗时 {elapsed:.1f}s")
    log("  NAS 只读：全程未修改素材目录")


# ── 入口 ────────────────────────────────────────────────────────────────


def resolve_password() -> tuple[str, bool]:
    """口令优先级：环境变量 > 已有凭据文件（保证重复执行登录不受影响）> 随机生成。"""
    env_password = os.environ.get("SEED_DEMO_PASSWORD")
    if env_password:
        return env_password, False
    if CREDENTIAL_FILE.exists():
        try:
            payload = json.loads(CREDENTIAL_FILE.read_text(encoding="utf-8"))
            existing = payload.get("password")
            if existing:
                return str(existing), True
        except (OSError, json.JSONDecodeError):
            pass
    return secrets.token_urlsafe(9), False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sakura Gallery 演示数据种子脚本")
    parser.add_argument("--dry-run", action="store_true", help="只做选片与体检，不写文件、不写库")
    parser.add_argument("--limit", type=int, default=None, help="最多入库 N 张（用于冒烟验证）")
    parser.add_argument("--reset", action="store_true", help="先删除本脚本此前写入的演示照片与文件，再重新入库")
    parser.add_argument("--no-variants", action="store_true", help="跳过响应式变体（仅调试用）")
    parser.add_argument("--keep-going", action="store_true", help="单张处理失败时继续（默认中止）")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="manifest 输出路径")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    started = time.time()
    root_2023 = SOURCE_2023
    root_2024 = SOURCE_2024
    for root in (root_2023, root_2024):
        if not root.is_dir():
            log(f"[error] 素材目录不存在：{root}")
            return 2

    groups = build_groups(root_2023, root_2024)
    if not groups:
        log("[error] 没有可用选片")
        return 2
    candidates = select_candidates(groups, args.limit)
    if not candidates:
        log("[error] 选片结果为空")
        return 2
    print_plan(candidates)
    if args.dry_run:
        log("\n[dry-run] 未写入任何文件或数据库。")
        return 0

    uploads_dir = Path(settings.UPLOAD_DIR).resolve()
    storage = get_storage()

    if args.reset:
        reset_stats = await reset_demo(args.manifest, uploads_dir)
        log(f"[reset] 清理演示照片 {reset_stats['photos']} 条、文件 {reset_stats['files']} 个")

    password, reused_password = resolve_password()
    if reused_password:
        log("[creds] 复用已有 .seed-demo-credentials.json 中的演示口令")
    processed: list[ProcessedPhoto] = []
    failures = 0
    for index, candidate in enumerate(candidates, start=1):
        try:
            processed.append(
                process_one(
                    candidate,
                    index,
                    len(candidates),
                    storage,
                    uploads_dir,
                    skip_variants=args.no_variants,
                )
            )
        except Exception as exc:  # noqa: BLE001
            failures += 1
            log(f"[error] {candidate.title}（{candidate.source.name}）处理失败：{exc}")
            if not args.keep_going:
                return 3

    if not processed:
        log("[error] 没有任何图片处理成功")
        return 3

    seed_stats = await seed_database(processed, password)
    creds_path = write_credentials(password)
    manifest = build_manifest(processed, seed_stats["user_ids"])
    write_manifest(args.manifest, manifest)

    print_summary(processed, time.time() - started, seed_stats)
    log(f"\n[done] 演示账号口令见 {creds_path}（已 gitignore，0600）")
    if failures:
        log(f"[warn] {failures} 张处理失败，已跳过")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
