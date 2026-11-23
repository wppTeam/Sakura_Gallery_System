"""Agent 检索编排服务。

流程（agent 模式）::

    planner(1 次 LLM) → retriever(词法 SQL + facet SQL + 可选向量)
                      → explainer(1 次 LLM，有结果且开启时)
                      → 可选落库 AgentSearchTrace

任何环节异常都降级到纯词法 fast 路径；trace/解释器/向量缺失绝不导致 500。
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.search_trace import AgentSearchTrace
from app.services import lexical_search
from app.services.agent_search import explainer, planner, retriever
from app.services.agent_search.types import (
    AgentSearchResult,
    ExplainOutcome,
    SearchIntent,
    SearchStep,
)
from app.services.lexical_search import FacetResult, SearchHit

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_LIMIT = 100

# Agent 模式总延迟目标（毫秒，不含模型冷启动）。planner 是推理模型，单次约 1.5-2.5s；
# 若规划 + 检索已接近预算，再串行调 explainer 会明显超时，此时跳过 LLM 解释、
# 改用规则兜底说明（step 标 skipped:latency_budget），保证接口 P95 可控。
AGENT_SEARCH_LATENCY_BUDGET_MS = 3000
_EXPLAINER_EXPECTED_MS = 1200


def _clamp_limit(limit: int) -> int:
    try:
        configured = int(settings.AGENT_SEARCH_LIMIT_MAX or MAX_LIMIT)
    except (TypeError, ValueError):
        configured = MAX_LIMIT
    hard_max = max(1, min(configured, MAX_LIMIT))
    try:
        requested = int(limit or 20)
    except (TypeError, ValueError):
        requested = 20
    return max(1, min(requested, hard_max))


def _merge_reasons(*reasons: Optional[str]) -> Optional[str]:
    seen: list[str] = []
    for reason in reasons:
        if not reason:
            continue
        for part in str(reason).split(" | "):
            part = part.strip()
            if part and part not in seen:
                seen.append(part)
    return " | ".join(seen) if seen else None


def _fast_intent(query: str, explicit_filters: dict[str, Any]) -> SearchIntent:
    intent = planner.heuristic_intent(query)
    intent.filters = dict(explicit_filters)
    return intent


async def _empty_result(
    *,
    query: str,
    intent: SearchIntent,
    steps: list[SearchStep],
    fallback_reason: Optional[str],
    clarify: Optional[str] = None,
    clarify_options: Optional[list[str]] = None,
) -> AgentSearchResult:
    return AgentSearchResult(
        results=[],
        total=0,
        facets=None,
        explanation=None,
        steps=steps,
        clarify=clarify,
        clarify_options=list(clarify_options or []),
        intent=intent,
        trace_id=None,
        search_mode="agent",
        fallback_reason=fallback_reason,
    )


async def _maybe_clarify(
    db: AsyncSession,
    *,
    query: str,
    intent: SearchIntent,
    hits: list[SearchHit],
    steps: list[SearchStep],
    fallback_reason: Optional[str],
) -> tuple[Optional[str], list[str], Optional[str]]:
    """返回 (clarify_question, options, fallback_reason)。"""
    if not settings.AGENT_SEARCH_CLARIFY_ENABLED:
        return None, [], fallback_reason
    if intent.needs_clarification and intent.clarify_question:
        steps.append(
            SearchStep(
                tool="clarify",
                args={"question": intent.clarify_question},
                status="awaiting_user",
            )
        )
        return intent.clarify_question, list(intent.clarify_options or []), fallback_reason
    if hits:
        return None, [], fallback_reason

    # 空结果：给几个可点选的检索建议，避免用户面对空白页
    prefix = (query or "").strip()
    if not prefix:
        return None, [], fallback_reason
    started = time.perf_counter()
    options: list[str] = []
    try:
        suggestions = await lexical_search.suggest(db, prefix, limit=5)
        options = [item["text"] for item in suggestions if item.get("text")][:4]
        status = "ok" if options else "empty"
    except Exception:  # noqa: BLE001 - 建议失败不影响主流程
        logger.warning("agent_search: suggest failed", exc_info=True)
        status = "degraded"
    steps.append(
        SearchStep(
            tool="suggest",
            args={"prefix": prefix},
            result_count=len(options),
            latency_ms=(time.perf_counter() - started) * 1000,
            status=status,
        )
    )
    if options:
        clarify = f"没有找到与「{prefix}」完全匹配的照片，试试这些关键词："
    else:
        clarify = f"没有找到与「{prefix}」匹配的照片，换个更具体的说法试试？"
    return clarify, options, fallback_reason


async def _run_fast(
    db: AsyncSession,
    *,
    query: str,
    explicit_filters: dict[str, Any],
    limit: int,
    offset: int,
    reason: str,
    search_mode: str = "fast",
) -> AgentSearchResult:
    """纯词法路径：planner/explainer 都跳过（不花模型钱）。"""
    intent = _fast_intent(query, explicit_filters)
    retrieval = await retriever.retrieve(
        db,
        query=query,
        intent=intent,
        explicit_filters=explicit_filters,
        limit=limit,
        offset=offset,
        include_facets=True,
    )
    steps: list[SearchStep] = [
        SearchStep(
            tool="planner",
            args={"query": query, "mode": "fast"},
            result_count=len(intent.keywords),
            status=f"skipped:{reason}",
        ),
        *retrieval.steps,
        SearchStep(tool="explainer", args={"mode": "fast"}, status=f"skipped:{reason}"),
    ]
    fallback_reason = _merge_reasons(reason, retrieval.fallback_reason)
    clarify, clarify_options, fallback_reason = await _maybe_clarify(
        db,
        query=query,
        intent=intent,
        hits=retrieval.hits,
        steps=steps,
        fallback_reason=fallback_reason,
    )
    return AgentSearchResult(
        results=retrieval.hits,
        total=retrieval.total,
        facets=retrieval.facets,
        explanation=None,
        steps=steps,
        clarify=clarify,
        clarify_options=clarify_options,
        intent=intent,
        trace_id=None,
        search_mode=search_mode,
        fallback_reason=fallback_reason,
    )


async def _explain_within_budget(
    db: AsyncSession,
    *,
    query: str,
    intent: SearchIntent,
    hits: list[SearchHit],
    elapsed_ms: float,
) -> ExplainOutcome:
    """在总延迟预算内决定是否调用 LLM 解释器。

    planner 通常是 1.5-2.5s 的推理调用；若规划 + 检索已花掉大部分预算，
    再串行调 explainer 会让接口远超 3s 目标，此时直接用规则说明兜底。
    """
    if (
        settings.AGENT_SEARCH_EXPLAIN
        and hits
        and elapsed_ms + _EXPLAINER_EXPECTED_MS > AGENT_SEARCH_LATENCY_BUDGET_MS
    ):
        step = SearchStep(
            tool="explainer",
            args={
                "skipped": "latency_budget",
                "elapsed_ms": round(elapsed_ms, 1),
                "budget_ms": AGENT_SEARCH_LATENCY_BUDGET_MS,
            },
            result_count=len(hits),
            latency_ms=None,
            status="skipped:latency_budget",
        )
        return ExplainOutcome(
            explanation=explainer.deterministic_explanation(query, hits),
            step=step,
        )
    return await explainer.explain(db, query=query, intent=intent, hits=hits)


async def _run_agent(
    db: AsyncSession,
    *,
    query: str,
    explicit_filters: dict[str, Any],
    limit: int,
    offset: int,
) -> AgentSearchResult:
    started = time.perf_counter()
    plan = await planner.plan_query(db, query, explicit_filters=explicit_filters)
    intent = plan.intent
    intent.query = query
    # 显式筛选优先（覆盖 planner 的推断）
    intent.filters = {**intent.filters, **explicit_filters}
    if not (intent.semantic_query or "").strip():
        intent.semantic_query = query

    retrieval = await retriever.retrieve(
        db,
        query=query,
        intent=intent,
        explicit_filters=explicit_filters,
        limit=limit,
        offset=offset,
        include_facets=True,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    explain = await _explain_within_budget(
        db,
        query=query,
        intent=intent,
        hits=retrieval.hits,
        elapsed_ms=elapsed_ms,
    )

    steps: list[SearchStep] = [plan.step, *retrieval.steps, explain.step]
    fallback_reason = _merge_reasons(
        plan.fallback_reason, retrieval.fallback_reason, explain.fallback_reason
    )
    clarify, clarify_options, fallback_reason = await _maybe_clarify(
        db,
        query=query,
        intent=intent,
        hits=retrieval.hits,
        steps=steps,
        fallback_reason=fallback_reason,
    )

    return AgentSearchResult(
        results=retrieval.hits,
        total=retrieval.total,
        facets=retrieval.facets,
        explanation=explain.explanation,
        steps=steps,
        clarify=clarify,
        clarify_options=clarify_options,
        intent=intent,
        trace_id=None,
        search_mode="agent",
        fallback_reason=fallback_reason,
        model_id=plan.model_id or explain.model_id,
        total_tokens=(plan.total_tokens or 0) + (explain.total_tokens or 0),
        cost_usd=round((plan.cost_usd or 0.0) + (explain.cost_usd or 0.0), 6),
    )


def _build_trace(result: AgentSearchResult, query: str, trace_id: str) -> AgentSearchTrace:
    facets = result.facets.to_dict() if isinstance(result.facets, FacetResult) else None
    return AgentSearchTrace(
        trace_id=trace_id,
        query=(query or "")[:4000],
        intent=result.intent.to_dict(),
        facets=facets,
        steps=[step.to_dict() for step in result.steps],
        result_count=len(result.results),
        clarify=result.clarify,
        explanation=result.explanation,
        model_id=result.model_id,
        latency_ms=int(result.query_time_ms or 0),
        total_tokens=int(result.total_tokens or 0),
        cost_usd=float(result.cost_usd or 0.0),
        error=result.fallback_reason,
    )


async def save_trace(db: AsyncSession, trace: AgentSearchTrace) -> bool:
    """尽力保存 trace；失败只回滚这一次写入，不影响检索结果。"""
    try:
        db.add(trace)
        await db.flush()
        return True
    except Exception:  # noqa: BLE001 - trace 绝不能影响接口
        logger.warning("agent_search: failed to persist trace", exc_info=True)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


async def run_agent_search(
    db: AsyncSession,
    query: str,
    filters: Optional[dict[str, Any]] = None,
    limit: int = 20,
    offset: int = 0,
    *,
    mode: str = "agent",
) -> AgentSearchResult:
    """Agent 检索入口：永远返回结果对象，不抛业务异常。"""
    started = time.perf_counter()
    query = (query or "").strip()
    effective_limit = _clamp_limit(limit)
    try:
        effective_offset = max(0, int(offset or 0))
        if effective_offset > 1000:
            effective_offset = 1000
    except (TypeError, ValueError):
        effective_offset = 0
    try:
        explicit_filters = lexical_search.normalize_filters(filters or {})
    except Exception:  # noqa: BLE001 - 非法 filter 不应 500
        logger.warning("agent_search: failed to normalize filters", exc_info=True)
        explicit_filters = {}

    requested_mode = (mode or "agent").lower()
    trace_enabled = bool(settings.AGENT_SEARCH_TRACE_ENABLED)
    trace_id = uuid.uuid4().hex if trace_enabled else None

    result: AgentSearchResult
    try:
        if requested_mode == "fast":
            reason = "fast_mode"
            result = await _run_fast(
                db,
                query=query,
                explicit_filters=explicit_filters,
                limit=effective_limit,
                offset=effective_offset,
                reason=reason,
                search_mode="fast",
            )
        elif not settings.AGENT_SEARCH_ENABLED:
            result = await _run_fast(
                db,
                query=query,
                explicit_filters=explicit_filters,
                limit=effective_limit,
                offset=effective_offset,
                reason="agent_search_disabled",
                search_mode="fast",
            )
        elif not settings.AI_ENABLED:
            result = await _run_fast(
                db,
                query=query,
                explicit_filters=explicit_filters,
                limit=effective_limit,
                offset=effective_offset,
                reason="ai_disabled",
                search_mode="fast",
            )
        else:
            result = await _run_agent(
                db,
                query=query,
                explicit_filters=explicit_filters,
                limit=effective_limit,
                offset=effective_offset,
            )
    except Exception:  # noqa: BLE001 - 任何异常降级为纯词法 fast
        logger.exception("agent_search: agent pipeline failed, falling back to lexical fast path")
        try:
            result = await _run_fast(
                db,
                query=query,
                explicit_filters=explicit_filters,
                limit=effective_limit,
                offset=effective_offset,
                reason="agent_search_failed",
                search_mode="fast",
            )
        except Exception:  # noqa: BLE001 - 检索彻底失败时返回空页而不是 500
            logger.exception("agent_search: lexical fallback failed too")
            result = AgentSearchResult(
                results=[],
                total=0,
                facets=None,
                explanation=None,
                steps=[
                    SearchStep(
                        tool="lexical_search",
                        args={"query": query},
                        status="failed:search_error",
                    )
                ],
                clarify=None,
                clarify_options=[],
                intent=_fast_intent(query, explicit_filters),
                trace_id=None,
                search_mode="fast",
                fallback_reason="search_failed",
            )

    result.query_time_ms = round((time.perf_counter() - started) * 1000, 2)
    result.trace_id = trace_id

    # 索引实现标识（给前端排障用，探测失败不影响结果）
    try:
        result.index_version = await lexical_search.index_version(db)
    except Exception:  # noqa: BLE001
        result.index_version = None

    if trace_enabled and trace_id:
        trace = _build_trace(result, query, trace_id)
        result.trace = trace
        if await save_trace(db, trace):
            pass
        else:
            result.trace_id = None
            result.trace = None

    logger.info(
        "agent_search: mode=%s results=%d total=%d latency=%.0fms steps=%s reason=%s",
        result.search_mode,
        len(result.results),
        result.total,
        result.query_time_ms,
        [step.tool for step in result.steps],
        result.fallback_reason,
    )
    return result


class AgentSearchService:
    """薄封装，便于依赖注入 / 测试。"""

    async def search(
        self,
        db: AsyncSession,
        query: str,
        filters: Optional[dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
        *,
        mode: str = "agent",
    ) -> AgentSearchResult:
        return await run_agent_search(
            db, query, filters=filters, limit=limit, offset=offset, mode=mode
        )


_service: Optional[AgentSearchService] = None


def get_agent_search_service() -> AgentSearchService:
    global _service
    if _service is None:
        _service = AgentSearchService()
    return _service
