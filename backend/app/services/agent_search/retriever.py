"""检索执行器：词法（必选）+ facet（必选）+ 向量（可选）融合。

设计约束（2c4g 机器）：
- 词法检索只用 ``lexical_search`` 的一条打分+过滤+分页 SQL，facet 一条聚合 SQL；
- 向量链路（torch / sentence_transformers / pymilvus）完全延迟 import，
  依赖缺失时只记录 ``skipped:no_vector_dep``，绝不让接口 500；
- 多路结果按 photo_id 去重后加权融合（lexical 0.7 + vector 0.3），
  向量只参与排序，不额外加 SQL（详情用一条批量查询补齐）。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services import lexical_search
from app.services.agent_search.types import RetrievalOutcome, SearchIntent, SearchStep
from app.services.lexical_search import (
    FacetResult,
    SearchHit,
    build_match_reason,
    build_search_terms,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# 融合权重：保证融合后分数仍落在 [0, 1]
FUSION_LEXICAL_WEIGHT = 0.7
FUSION_VECTOR_WEIGHT = 0.3
# 由 planner 推断出来、可以为了召回而放宽的 facet key
RELAXABLE_TAXONOMY_KEYS = frozenset(
    {
        "building",
        "landmark",
        "landscape",
        "facility",
        "plant",
        "animal",
        "natural_phenomenon",
        "photo_type",
        "technique",
        "gallery_series",
        "gallery_year",
        "award_level",
        "source_type",
    }
)
# 照片列级过滤：放宽时最后才丢（尤其是用户显式选的）
PHOTO_COLUMN_FILTER_KEYS = frozenset({"season", "category", "campus", "tag"})


def _vector_module():
    """延迟拿到 vector_search_service 模块（依赖缺失时该模块本身仍可 import）。"""
    from app.services import vector_search_service

    return vector_search_service


def _terms_for_intent(query: str, intent: SearchIntent) -> list[str]:
    """query + planner 关键词 + 语义改写短语 → 有限个检索词。"""
    keywords = [item for item in (intent.keywords or []) if isinstance(item, str)]
    semantic = (intent.semantic_query or "").strip()
    cleaned_query = (query or "").strip()
    if semantic and semantic != cleaned_query and len(semantic) <= 80:
        keywords.append(semantic)
    return build_search_terms(cleaned_query, keywords)


def _filters_for_vector(filters: dict[str, Any]) -> dict[str, str]:
    """VectorSearchService 只接受 dict[str, str]。"""
    flat: dict[str, str] = {}
    for key, value in (filters or {}).items():
        if isinstance(value, (list, tuple, set, frozenset)):
            items = [str(item) for item in value if item not in (None, "")]
            if items:
                flat[key] = items[0]
        elif value not in (None, ""):
            flat[key] = str(value)
    return flat


def _annotate(hits: list[SearchHit], terms: list[str]) -> None:
    for hit in hits:
        if not hit.match_reason:
            hit.match_reason = build_match_reason(hit, terms)
        if hit.photo_id in (None, ""):
            continue


async def _lexical(
    db: AsyncSession,
    *,
    query: str,
    terms: list[str],
    filters: dict[str, Any],
    limit: int,
    offset: int,
) -> list[SearchHit]:
    hits = await lexical_search.search_photos(
        db,
        query,
        keywords=terms,
        filters=filters,
        limit=limit,
        offset=offset,
    )
    _annotate(hits, terms)
    return hits


async def _is_really_empty(
    db: AsyncSession,
    *,
    query: str,
    terms: list[str],
    filters: dict[str, Any],
    offset: int,
) -> bool:
    """offset > 0 时空页不代表无命中，先数一下总数再决定是否放宽筛选。"""
    if offset <= 0:
        return True
    total = await lexical_search.count_matched(db, query, keywords=terms, filters=filters)
    return total == 0


def _relaxed_filter_candidates(
    filters: dict[str, Any], explicit_filters: dict[str, Any]
) -> list[dict[str, Any]]:
    """为空结果生成由窄到宽的放宽选项（显式筛选永不放宽）。"""
    planner_keys = [key for key in filters if key not in explicit_filters]
    if not planner_keys:
        return []
    candidates: list[dict[str, Any]] = []

    taxonomy_only = [
        key for key in planner_keys if key in RELAXABLE_TAXONOMY_KEYS and key not in explicit_filters
    ]
    if taxonomy_only:
        candidates.append({key: value for key, value in filters.items() if key not in taxonomy_only})

    soft = [key for key in planner_keys if key in PHOTO_COLUMN_FILTER_KEYS]
    if soft:
        candidates.append({key: value for key, value in filters.items() if key not in soft})

    if not candidates:
        candidates.append(dict(explicit_filters))
    return candidates


async def _fuse(
    db: AsyncSession,
    lexical_hits: list[SearchHit],
    vector_results: list[Any],
    *,
    limit: int,
) -> tuple[list[SearchHit], int]:
    """按 photo_id 去重后加权融合，返回 (融合结果, 向量独有的数量)。"""
    lexical_by_id = {hit.photo_id: hit for hit in lexical_hits}
    vector_scores: dict[str, float] = {}
    for item in vector_results:
        photo_id = str(getattr(item, "photo_id", "") or "")
        if not photo_id:
            continue
        try:
            raw = float(getattr(item, "score", 0.0) or 0.0)
        except (TypeError, ValueError):
            raw = 0.0
        vector_scores[photo_id] = max(0.0, min(1.0, raw))

    if not vector_scores:
        return lexical_hits[:limit], 0

    vector_only_ids = [pid for pid in vector_scores if pid not in lexical_by_id]
    fetched: dict[str, SearchHit] = {}
    if vector_only_ids:
        try:
            fetched = await lexical_search.get_hits_by_ids(db, vector_only_ids)
        except Exception:  # noqa: BLE001 - 补详情失败不影响词法结果
            logger.warning("agent_search: failed to fetch vector-only hits", exc_info=True)
            fetched = {}

    fused: list[tuple[float, SearchHit]] = []
    for photo_id, hit in lexical_by_id.items():
        score = FUSION_LEXICAL_WEIGHT * max(0.0, min(1.0, float(hit.score or 0.0)))
        if photo_id in vector_scores:
            score += FUSION_VECTOR_WEIGHT * vector_scores[photo_id]
        fused.append((score, hit))

    for photo_id in vector_only_ids:
        hit = fetched.get(photo_id)
        if hit is None:
            continue
        hit.score = round(FUSION_VECTOR_WEIGHT * vector_scores[photo_id], 4)
        hit.matched_fields = ["vector"]
        hit.match_reason = "语义相似"
        fused.append((hit.score, hit))

    fused.sort(key=lambda item: (-item[0], item[1].photo_id))
    results: list[SearchHit] = []
    for score, hit in fused[:limit]:
        hit.score = round(max(0.0, min(1.0, score)), 4)
        results.append(hit)
    return results, len(vector_only_ids)


async def retrieve(
    db: AsyncSession,
    *,
    query: str,
    intent: SearchIntent,
    explicit_filters: Optional[dict[str, Any]] = None,
    limit: int = 20,
    offset: int = 0,
    include_facets: bool = True,
    max_search_calls: Optional[int] = None,
) -> RetrievalOutcome:
    """执行一次检索（不含 planner/explainer 的 LLM 调用）。"""
    explicit_filters = dict(explicit_filters or {})
    terms = _terms_for_intent(query, intent)
    filters = dict(intent.filters or {})
    limit = max(1, min(int(limit or 20), lexical_search.LIMIT_MAX))
    offset = max(0, int(offset or 0))

    try:
        configured_steps = int(settings.AGENT_SEARCH_MAX_STEPS or 3)
    except (TypeError, ValueError):
        configured_steps = 3
    if max_search_calls is None:
        max_search_calls = max(1, configured_steps - 1)

    # offset 之后还要够一页，一次性多取一点；LIMIT_MAX 兜底
    fetch_limit = min(offset + limit, lexical_search.LIMIT_MAX)

    steps: list[SearchStep] = []
    fallback_reason: Optional[str] = None

    started = time.perf_counter()
    hits = await _lexical(
        db, query=query, terms=terms, filters=filters, limit=fetch_limit, offset=0
    )
    used_filters = dict(filters)
    steps.append(
        SearchStep(
            tool="lexical_search",
            args={
                "query": query,
                "keywords": terms,
                "filters": used_filters,
                "limit": fetch_limit,
                "offset": 0,
            },
            result_count=len(hits),
            latency_ms=(time.perf_counter() - started) * 1000,
            status="ok" if hits else "empty",
        )
    )

    # 空结果：由窄到宽放宽 planner 推断的过滤条件（最多 max_search_calls-1 次）
    attempts = 1
    while not hits and attempts < max_search_calls:
        if not await _is_really_empty(
            db, query=query, terms=terms, filters=used_filters, offset=offset
        ):
            break
        candidates = _relaxed_filter_candidates(used_filters, explicit_filters)
        candidate = candidates[0] if candidates else None
        if candidate is None or candidate == used_filters:
            break
        started = time.perf_counter()
        hits = await _lexical(
            db, query=query, terms=terms, filters=candidate, limit=fetch_limit, offset=0
        )
        used_filters = candidate
        attempts += 1
        steps.append(
            SearchStep(
                tool="lexical_search",
                args={
                    "query": query,
                    "keywords": terms,
                    "filters": used_filters,
                    "limit": fetch_limit,
                    "offset": 0,
                    "relaxed": True,
                },
                result_count=len(hits),
                latency_ms=(time.perf_counter() - started) * 1000,
                status="ok" if hits else "empty",
            )
        )
        if hits:
            fallback_reason = "filters_relaxed"
            break

    # facet 聚合（一条 SQL，基于最终生效的 filters）
    facets: Optional[FacetResult] = None
    if include_facets:
        started = time.perf_counter()
        try:
            facets = await lexical_search.compute_facets(
                db, query, keywords=terms, filters=used_filters
            )
            facet_status = "ok"
        except Exception:  # noqa: BLE001 - facet 失败不影响结果
            logger.warning("agent_search: facet aggregation failed", exc_info=True)
            facets = None
            facet_status = "degraded"
        steps.append(
            SearchStep(
                tool="facets",
                args={"filters": used_filters},
                result_count=facets.total if facets else 0,
                latency_ms=(time.perf_counter() - started) * 1000,
                status=facet_status,
            )
        )

    # 可选向量增强：依赖缺失/索引不可用都只标 skipped
    vector_step = SearchStep(tool="vector_search", args={"query": query}, status="skipped")
    lexical_hits = list(hits)
    vector_results: list[Any] = []
    try:
        vss = _vector_module()
        available = bool(vss.is_vector_available())
        reason = ""
        if not available and hasattr(vss, "vector_unavailable_reason"):
            try:
                reason = str(vss.vector_unavailable_reason() or "")
            except Exception:  # noqa: BLE001
                reason = ""
        if not available:
            vector_step.status = "skipped:no_vector_dep"
            vector_step.args["reason"] = reason or "vector dependencies not installed"
        elif not (query or intent.semantic_query):
            vector_step.status = "skipped:empty_query"
        else:
            started = time.perf_counter()
            semantic_query = (intent.semantic_query or query or "").strip()
            outcome = await vss.get_vector_search_service().search(
                db,
                semantic_query,
                filters=_filters_for_vector(used_filters),
                limit=min(max(fetch_limit, limit), lexical_search.LIMIT_MAX),
            )
            mode = getattr(outcome, "search_mode", "") or ""
            if mode in {"vector", "hybrid"} and getattr(outcome, "results", None):
                vector_results = list(outcome.results)
                vector_step.status = "ok"
                vector_step.result_count = len(vector_results)
            else:
                vector_step.status = "skipped:index_unavailable"
                vector_step.args["reason"] = (
                    getattr(outcome, "fallback_reason", None) or f"search_mode={mode or 'unknown'}"
                )
            vector_step.latency_ms = (time.perf_counter() - started) * 1000
    except Exception:  # noqa: BLE001 - 向量链路任何异常都不能拖垮检索
        logger.warning("agent_search: vector search failed, fallback to lexical only", exc_info=True)
        vector_step.status = "degraded"
        vector_step.latency_ms = None
        vector_results = []
    steps.append(vector_step)

    fused_hits = lexical_hits
    if vector_results:
        fused_hits, vector_only = await _fuse(
            db, lexical_hits, vector_results, limit=fetch_limit
        )
        vector_step.args["vector_only"] = vector_only
    fused_hits = fused_hits[offset : offset + limit]

    # 总数
    if facets is not None:
        total = facets.total
    else:
        total = len(fused_hits)
        try:
            total = await lexical_search.count_matched(
                db, query, keywords=terms, filters=used_filters
            )
        except Exception:  # noqa: BLE001
            logger.warning("agent_search: count_matched failed", exc_info=True)

    return RetrievalOutcome(
        hits=list(fused_hits),
        total=int(total or 0),
        facets=facets,
        steps=steps,
        fallback_reason=fallback_reason,
        keyword_weights={"keywords": terms},
    )
