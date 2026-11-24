"""检索意图解析器（planner）：一次 chat_json 调用 + 规则兜底。

职责：把自然语言 query 解析成结构化意图（keywords / filters / semantic_query /
澄清问题），供确定性检索层执行。模型不可用、返回非 JSON、超时都只降级不抛错。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.ai_client import (
    AIBudgetExceeded,
    AICallFailed,
    AIConfigError,
    AIJSONError,
    chat_json,
)
from app.services.agent_search.types import PlanOutcome, SearchIntent, SearchStep
from app.services.lexical_search import build_search_terms
from app.services.light_of_day import normalize_period

logger = logging.getLogger(__name__)
settings = get_settings()

# planner 允许输出的结构化过滤 key（其余丢弃，避免污染 SQL）
ALLOWED_FILTER_KEYS: frozenset[str] = frozenset(
    {
        "season",
        "category",
        "campus",
        "tag",
        "building",
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
        "landmark",
        "period",
    }
)

PLANNER_SYSTEM_PROMPT = """你是「视觉百花 / Sakura Gallery」校园摄影站的检索意图解析器。
把用户的中文自然语言查询解析为 JSON，供确定性检索工具执行。

输出 JSON（不要 markdown 代码块、不要解释）：
{
  "intent": "photo_search",
  "keywords": ["樱花", "春日", "校园"],        // 2-6 个检索关键词，保留用户原词 + 必要近义扩展
  "filters": {"season": "春季", "campus": "昌平校区"},  // 可为空 {}
  "semantic_query": "春季校园里盛开的樱花",     // 一句适合语义检索的短语
  "assumed": ["默认按春季理解"],               // 隐含假设，最多 2 条，可为 []
  "confidence": 0.8,                          // 0~1
  "needs_clarification": false,               // 查询确实歧义时才 true
  "clarify_question": null,                   // needs_clarification 为 true 时的追问（≤40 字）
  "clarify_options": [],                      // 追问时的候选选项（≤4 个）
  "expected_facets": ["season", "tag"]        // 用户可能想按哪些 facet 筛选
}

filters 可选 key 与取值（不确定就不要填，宁缺毋滥）：
- season: 春季 / 夏季 / 秋季 / 冬季
- category: 风光 / 人像 / 活动 / 纪实
- campus: 昌平校区 / 朝阳校区 / 海淀校区
- tag: 具体标签，如 樱花 / 银杏 / 图书馆 / 日落 / 晚霞
- building: 楼宇名，如 第一教学楼 / 图书馆 / 体育馆
- landscape / facility / plant / animal / natural_phenomenon / photo_type / technique
- gallery_series / gallery_year / award_level / source_type
- period: 拍摄时段，只能是 dawn / noon / dusk / night 之一
  - 清晨 / 早晨 / 早上 / 日出 → dawn
  - 中午 / 正午 / 白天 → noon
  - 黄昏 / 傍晚 / 日落 → dusk
  - 夜晚 / 晚上 / 深夜 → night

规则：
1. 泛化词（照片、图片、校园、北化）不要放进 keywords。
2. 用户明确说出的筛选条件才放进 filters；从「樱花」推断「春季」这类推断只写进 assumed，不要写 filters。
3. 查询很短且明确（如「樱花」）时 keywords 就是原词本身。
4. 只有真的无法判断用户想找什么（如「好看的照片」）才 needs_clarification=true。"""


def _ai_timeout() -> float:
    try:
        configured = float(settings.AGENT_SEARCH_TIMEOUT or 8)
    except (TypeError, ValueError):
        configured = 8.0
    return max(2.0, min(configured, 8.0))


def heuristic_intent(query: str) -> SearchIntent:
    """规则兜底：只做关键词切分，不猜 filters（避免错误过滤导致空结果）。"""
    cleaned = (query or "").strip()
    terms = build_search_terms(cleaned)
    return SearchIntent(
        query=cleaned,
        keywords=terms,
        filters={},
        semantic_query=cleaned,
        assumed=[],
        confidence=0.3,
        source="heuristic",
    )


def _coerce_str_list(value: Any, *, limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    items: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                items.append(text[:40])
        if len(items) >= limit:
            break
    # 去重保序
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped[:limit]


def parse_planner_data(data: Any, query: str) -> Optional[SearchIntent]:
    """把模型返回的 dict 校验成 SearchIntent；明显无效时返回 None。"""
    if not isinstance(data, dict):
        return None
    payload: dict[str, Any] = data
    nested = data.get("intent")
    if isinstance(nested, dict):
        # 兼容 {"intent": {"keywords": ..., "filters": ...}} 形态
        payload = {**data, **nested}

    keywords = _coerce_str_list(
        payload.get("keywords") or payload.get("terms") or payload.get("keyword"), limit=6
    )
    raw_filters = payload.get("filters") or payload.get("facet_filters") or {}
    filters: dict[str, str] = {}
    if isinstance(raw_filters, dict):
        for key, value in raw_filters.items():
            key_text = str(key).strip()
            if key_text not in ALLOWED_FILTER_KEYS:
                continue
            if isinstance(value, (int, float)):
                value = str(value)
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text:
                continue
            if key_text == "period":
                canonical = normalize_period(text)
                if canonical:
                    filters[key_text] = canonical
                continue
            filters[key_text] = text[:40]

    if not keywords and not filters:
        return None
    if not keywords:
        keywords = build_search_terms(query)

    semantic_query = payload.get("semantic_query") or payload.get("rewritten_query") or ""
    semantic_query = semantic_query.strip()[:120] if isinstance(semantic_query, str) else ""

    assumed = _coerce_str_list(payload.get("assumed") or payload.get("assumptions"), limit=3)
    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    needs_clarification = bool(
        payload.get("needs_clarification")
        or payload.get("needs_clarify")
        or payload.get("need_clarification")
    )
    clarify_question = (
        payload.get("clarify_question")
        or payload.get("clarify")
        or payload.get("clarification_question")
    )
    clarify_question = (
        clarify_question.strip()[:120] if isinstance(clarify_question, str) else None
    )
    clarify_options = _coerce_str_list(
        payload.get("clarify_options") or payload.get("clarify_choices"), limit=6
    )
    expected_facets = _coerce_str_list(payload.get("expected_facets"), limit=6)

    if needs_clarification and not clarify_question:
        needs_clarification = False
    if needs_clarification and not settings.AGENT_SEARCH_CLARIFY_ENABLED:
        needs_clarification = False

    return SearchIntent(
        query=query,
        keywords=keywords[:6],
        filters=filters,
        semantic_query=semantic_query or query,
        assumed=assumed,
        confidence=confidence,
        needs_clarification=needs_clarification,
        clarify_question=clarify_question,
        clarify_options=clarify_options,
        expected_facets=expected_facets,
        source="llm",
    )


def _planner_user_message(query: str, explicit_filters: Optional[dict[str, Any]] = None) -> str:
    lines = [f"用户查询：{query}"]
    if explicit_filters:
        lines.append(f"用户在界面上已显式选择的筛选条件（无需重复解析）：{explicit_filters}")
    return "\n".join(lines)


async def plan_query(
    db: AsyncSession,
    query: str,
    *,
    explicit_filters: Optional[dict[str, Any]] = None,
) -> PlanOutcome:
    """调用一次模型解析意图；任何异常都回退到规则意图。"""
    started = time.perf_counter()
    fallback = heuristic_intent(query)

    if not settings.AGENT_SEARCH_ENABLED or not settings.AI_ENABLED:
        status = "skipped:agent_disabled" if not settings.AGENT_SEARCH_ENABLED else "skipped:ai_disabled"
        return PlanOutcome(
            intent=fallback,
            step=SearchStep(
                tool="planner",
                args={"query": query},
                status=status,
                latency_ms=(time.perf_counter() - started) * 1000,
            ),
            fallback_reason="agent_search_disabled" if status == "skipped:agent_disabled" else "ai_disabled",
        )

    model = (settings.AGENT_SEARCH_MODEL or "").strip() or None
    try:
        result = await chat_json(
            db,
            operation="agent_search.plan",
            system=PLANNER_SYSTEM_PROMPT,
            user=_planner_user_message(query, explicit_filters),
            model=model,
            max_tokens=2048,
            temperature=0.0,
            timeout=_ai_timeout(),
            ref_type="search_query",
        )
        intent = parse_planner_data(result.data, query)
        latency_ms = (time.perf_counter() - started) * 1000
        if intent is None:
            logger.warning("agent_search.planner returned unusable data, fallback to heuristic")
            return PlanOutcome(
                intent=fallback,
                step=SearchStep(
                    tool="planner",
                    args={"query": query, "model": result.model_id},
                    status="degraded",
                    latency_ms=latency_ms,
                ),
                fallback_reason="planner_invalid_output",
                model_id=result.model_id,
                total_tokens=result.total_tokens,
                cost_usd=result.cost_usd,
            )
        return PlanOutcome(
            intent=intent,
            step=SearchStep(
                tool="planner",
                args={
                    "query": query,
                    "model": result.model_id,
                    "keywords": intent.keywords,
                    "filters": intent.filters,
                },
                result_count=len(intent.keywords),
                status="ok",
                latency_ms=latency_ms,
            ),
            model_id=result.model_id,
            total_tokens=result.total_tokens,
            cost_usd=result.cost_usd,
        )
    except (AIConfigError, AIBudgetExceeded) as exc:
        reason = "ai_config_error" if isinstance(exc, AIConfigError) else "ai_budget_exceeded"
        logger.info("agent_search.planner unavailable (%s): %s", reason, exc)
    except (AICallFailed, AIJSONError) as exc:
        reason = "planner_call_failed"
        logger.warning("agent_search.planner failed: %s", exc)
    except Exception:  # noqa: BLE001 - planner 绝不拖垮检索
        reason = "planner_failed"
        logger.warning("agent_search.planner unexpected failure", exc_info=True)

    return PlanOutcome(
        intent=fallback,
        step=SearchStep(
            tool="planner",
            args={"query": query},
            status="degraded",
            latency_ms=(time.perf_counter() - started) * 1000,
        ),
        fallback_reason=reason,
    )
