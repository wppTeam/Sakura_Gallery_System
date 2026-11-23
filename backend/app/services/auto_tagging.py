"""审核即打标：把快筛 VLM 的同一次结构化输出落成标签与分类。

设计取舍
--------
- **不额外调用模型**：``moderation.prefilter`` 已经在看图，这里只把它 JSON 里的
  ``caption`` / ``tags`` / ``facets`` 三个字段解析落库，等于「一次推理，两件事」。
  2c4g 上模型调用是主要成本与延迟，所以不做第二条打标链路。
- **只落平台既有词汇**：``facets`` 必须能被 ``taxonomy.resolve_taxonomy_node``
  （名称 / key / 别名）命中，否则安静跳过；``tags`` 走 ``tag_normalization``
  归一化，已有别名就复用，避免「樱花/樱花树/樱花盛开」把标签表撑爆。
- **幂等**：重复审核同一张照片不会重复加标签；只有新建关联时才加
  ``tags.usage_count``，既有分类节点按 facet 更新。
- **不 commit**：共用审核事务边界（worker / API 负责提交）；任何一步失败只记
  warning，绝不让打标把审核搞挂。
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo
from app.models.tag import PhotoTag, Tag
from app.models.taxonomy import PhotoClassification, TaxonomyFacet, TaxonomyNode
from app.services.tag_normalization import (
    normalize_tag_name,
    resolve_tag_by_name_or_alias,
)
from app.services.taxonomy import (
    get_facet_by_key,
    resolve_taxonomy_node,
    set_photo_classification,
    validate_selectable_node,
)

logger = logging.getLogger(__name__)

# 允许自动打标的 facet（顺序即提示词里的展示顺序）；facility 等长尾词表不参与，
# 避免提示词过长、也避免模型在 200 个设施里瞎猜。
AUTO_TAGGING_FACETS: tuple[str, ...] = (
    "season",
    "campus",
    "photo_type",
    "plant",
    "natural_phenomenon",
    "landscape",
    "building",
    "technique",
)

FACET_LABELS = {
    "season": "季节",
    "campus": "校区",
    "photo_type": "题材",
    "plant": "植物",
    "natural_phenomenon": "自然现象",
    "landscape": "景观/地点",
    "building": "楼宇",
    "technique": "表现手法",
}

MAX_TAG_LENGTH = 20
_CATALOG_TTL_SECONDS = 600
_catalog_cache: dict[str, tuple[float, str]] = {}

_TAG_NOISE = re.compile(r"[\s\"'“”‘’《》<>【】\[\]()（）,，。.;；:：!！?？#]+")


def _clean_tag(raw: Any) -> str | None:
    """把模型给的标签清成适合入库的名字；不合格返回 None。"""
    if not isinstance(raw, str):
        return None
    text = _TAG_NOISE.sub(" ", raw).strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    if len(text) > MAX_TAG_LENGTH:
        return None
    lowered = text.lower()
    if lowered in {"摄影", "照片", "图片", "作品", "原创", "photo", "image", "摄影作品"}:
        return None
    return text


def normalize_suggestions(prefilter: dict[str, Any] | None, *, max_tags: int = 6) -> dict[str, Any]:
    """把快筛 JSON 里的打标字段收敛成稳定结构（脏数据全部丢弃）。"""
    data = prefilter or {}
    raw_tags = data.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    tags: list[str] = []
    seen: set[str] = set()
    if isinstance(raw_tags, list):
        for item in raw_tags:
            cleaned = _clean_tag(item)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            tags.append(cleaned)
            if len(tags) >= max_tags:
                break

    raw_facets = data.get("facets") or {}
    facets: dict[str, str] = {}
    if isinstance(raw_facets, dict):
        for facet_key in AUTO_TAGGING_FACETS:
            value = raw_facets.get(facet_key)
            if isinstance(value, str):
                value = value.strip()
            elif isinstance(value, (list, tuple)) and value:
                # 模型偶尔会返回数组；单值 facet 取第一个
                value = str(value[0]).strip()
            else:
                continue
            if value and value.lower() not in {"null", "none", "unknown", "不确定"}:
                facets[facet_key] = value[:60]

    caption = data.get("caption")
    if not isinstance(caption, str) or not caption.strip():
        caption = None
    else:
        caption = caption.strip()[:120]

    return {"tags": tags, "facets": facets, "caption": caption}


async def build_taxonomy_catalog(db: AsyncSession, *, use_cache: bool = True) -> str:
    """生成提示词里的分类目录文本（按进程缓存 10 分钟）。

    格式：``- 季节(season)：春季 / 夏季 / 秋季 / 冬季``。只列 active + selectable 节点，
    模型看到的就是平台真正能落库的词。
    """
    cache_key = "catalog"
    now = time.time()
    if use_cache:
        cached = _catalog_cache.get(cache_key)
        if cached and now - cached[0] < _CATALOG_TTL_SECONDS:
            return cached[1]

    result = await db.execute(
        select(TaxonomyFacet.key, TaxonomyNode.name)
        .join(TaxonomyNode, TaxonomyNode.facet_id == TaxonomyFacet.id)
        .where(
            TaxonomyFacet.is_active.is_(True),
            TaxonomyNode.is_active.is_(True),
            TaxonomyNode.is_selectable.is_(True),
            TaxonomyFacet.key.in_(AUTO_TAGGING_FACETS),
        )
        .order_by(TaxonomyFacet.sort_order, TaxonomyNode.sort_order, TaxonomyNode.name)
    )
    grouped: dict[str, list[str]] = {key: [] for key in AUTO_TAGGING_FACETS}
    for facet_key, node_name in result.all():
        if facet_key in grouped and node_name:
            grouped[facet_key].append(str(node_name))

    lines = []
    for facet_key in AUTO_TAGGING_FACETS:
        names = grouped.get(facet_key) or []
        if not names:
            continue
        lines.append(f"- {FACET_LABELS[facet_key]}({facet_key})：{' / '.join(names)}")
    catalog = "\n".join(lines) if lines else "（分类目录不可用，全部 facets 给 null）"
    _catalog_cache[cache_key] = (now, catalog)
    return catalog


def clear_catalog_cache() -> None:
    _catalog_cache.clear()


async def _apply_tags(db: AsyncSession, photo: Photo, tag_names: list[str]) -> list[str]:
    """把标签挂到照片上，返回实际生效的标签名（幂等）。"""
    applied: list[str] = []
    for name in tag_names:
        normalized = normalize_tag_name(name)
        if not normalized:
            continue
        tag = await resolve_tag_by_name_or_alias(db, name)
        created = False
        if tag is None:
            tag = Tag(name=normalized, category="auto")
            db.add(tag)
            await db.flush()
            created = True
        existing = await db.execute(
            select(PhotoTag).where(PhotoTag.photo_id == photo.id, PhotoTag.tag_id == tag.id)
        )
        link = existing.scalar_one_or_none()
        if link is None:
            db.add(PhotoTag(photo_id=photo.id, tag_id=tag.id))
            tag.usage_count = int(tag.usage_count or 0) + 1
            applied.append(tag.name)
        elif created:
            applied.append(tag.name)
    return applied


async def _apply_facets(
    db: AsyncSession, photo: Photo, facets: dict[str, str]
) -> tuple[dict[str, str], bool]:
    """把 facets 名称解析成节点并写分类；返回 (生效分类, 是否真的发生了写入)。"""
    applied: dict[str, str] = {}
    changed = False
    for facet_key, raw_value in facets.items():
        if facet_key not in AUTO_TAGGING_FACETS:
            continue
        try:
            node = await resolve_taxonomy_node(db, facet_key, raw_value)
            if node is None:
                continue
            validate_selectable_node(node, facet_key)
            facet = await get_facet_by_key(db, facet_key)
            if facet is not None:
                existing = await db.execute(
                    select(PhotoClassification.node_id).where(
                        PhotoClassification.photo_id == photo.id,
                        PhotoClassification.facet_id == facet.id,
                    )
                )
                if node.id not in set(existing.scalars().all()):
                    changed = True
            await set_photo_classification(db, photo, facet_key, node)
            applied[facet_key] = node.name
        except Exception as exc:  # noqa: BLE001 - 单个分类失败不影响其它分类
            logger.info(
                "auto tagging facet skipped photo=%s facet=%s value=%s: %s",
                photo.id,
                facet_key,
                raw_value,
                exc,
            )
    return applied, changed


async def apply_prefilter_tags(
    db: AsyncSession,
    photo: Photo,
    prefilter: dict[str, Any] | None,
    *,
    max_tags: int = 6,
) -> dict[str, Any]:
    """把快筛结果里的 caption/tags/facets 落库（不 commit），返回摘要供审核记录展示。"""
    suggestions = normalize_suggestions(prefilter, max_tags=max_tags)
    summary: dict[str, Any] = {
        "caption": suggestions["caption"],
        "tags": [],
        "facets": {},
        "requested_tags": suggestions["tags"],
        "applied": False,
    }
    if not suggestions["tags"] and not suggestions["facets"] and not suggestions["caption"]:
        return summary

    try:
        applied_tags = await _apply_tags(db, photo, suggestions["tags"])
        applied_facets, facets_changed = await _apply_facets(db, photo, suggestions["facets"])
    except Exception as exc:
        logger.warning("auto tagging failed photo=%s: %s", photo.id, exc, exc_info=True)
        summary["error"] = f"{exc.__class__.__name__}: {exc}"[:300]
        return summary

    meta = dict(photo.exif_data or {})
    if suggestions["caption"]:
        meta["_ai_caption"] = suggestions["caption"]
    if applied_tags or applied_facets:
        meta["_ai_tagging"] = {
            "tags": applied_tags,
            "facets": applied_facets,
            "at": datetime.utcnow().isoformat(timespec="seconds"),
        }
    if meta != (photo.exif_data or {}):
        photo.exif_data = meta

    summary.update(
        {
            "tags": applied_tags,
            "facets": applied_facets,
            "applied": bool(applied_tags or facets_changed),
        }
    )
    await db.flush()
    return summary


__all__ = [
    "AUTO_TAGGING_FACETS",
    "FACET_LABELS",
    "apply_prefilter_tags",
    "build_taxonomy_catalog",
    "clear_catalog_cache",
    "normalize_suggestions",
]
