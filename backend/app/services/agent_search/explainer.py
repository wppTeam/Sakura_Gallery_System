"""结果解释器（explainer）：有结果时一次 chat_json 生成中文说明 + 匹配理由。

失败策略：任何异常都只降级为规则说明（deterministic），绝不向上抛。
"""
from __future__ import annotations

import json
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
from app.services.agent_search.types import ExplainOutcome, SearchIntent, SearchStep
from app.services.lexical_search import SearchHit

logger = logging.getLogger(__name__)
settings = get_settings()

EXPLAINER_SYSTEM_PROMPT = """你是「视觉百花 / Sakura Gallery」校园摄影站的检索结果解释器。
用 1-3 句自然中文告诉用户：这批结果与查询的关系、命中了哪些题材/季节/校园元素。
要求：具体、克制、不编造（只能用给定数据）；总长 ≤120 字；不要 markdown。

输出 JSON（不要 markdown 代码块、不要解释）：
{
  "explanation": "这批照片主要是春季樱花与校园建筑同框的场景，共命中 12 张。",
  "match_reasons": {"<photo_id>": "标题含「樱花」，标签命中樱花+春日"}  // 可选，≤5 条
}"""


def _maybe_trim(text: Any, limit: int) -> Optional[str]:
    if not isinstance(text, str):
        return None
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def deterministic_explanation(query: str, hits: list[SearchHit]) -> Optional[str]:
    """规则版说明：不花模型钱，用于解释器失败 / AI 关闭时。"""
    if not hits:
        return None
    tags: list[str] = []
    for hit in hits[:8]:
        for tag in hit.tags or []:
            if tag not in tags:
                tags.append(tag)
            if len(tags) >= 4:
                break
        if len(tags) >= 4:
            break
    seasons: list[str] = []
    for hit in hits[:8]:
        if hit.season and hit.season not in seasons:
            seasons.append(hit.season)
    parts = [f"围绕「{query[:40]}」找到 {len(hits)} 张相关照片"]
    if tags:
        parts.append("主要涉及 " + "、".join(tags[:4]))
    if seasons:
        parts.append("季节集中在 " + "、".join(seasons[:2]))
    if not tags and not seasons:
        parts.append("按标题、描述、标签与分类的综合匹配排序")
    return "，".join(parts) + "。"


def _top_hits_payload(hits: list[SearchHit], limit: int = 5) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for hit in hits[:limit]:
        payload.append(
            {
                "photo_id": hit.photo_id,
                "title": (hit.title or "")[:60],
                "tags": list(hit.tags or [])[:6],
                "season": hit.season,
                "category": hit.category,
                "campus": hit.campus,
                "matched_fields": list(hit.matched_fields or []),
                "score": hit.score,
            }
        )
    return payload


def _user_message(query: str, intent: SearchIntent, hits: list[SearchHit]) -> str:
    payload = {
        "query": query,
        "keywords": list(intent.keywords or [])[:8],
        "filters": {
            key: value
            for key, value in (intent.filters or {}).items()
            if value not in (None, "", [])
        },
        "total": len(hits),
        "top_hits": _top_hits_payload(hits),
    }
    return (
        "检索结果如下（JSON）：\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n请按系统提示输出解释 JSON。"
    )


def _apply_match_reasons(data: dict[str, Any], hits: list[SearchHit]) -> int:
    raw = data.get("match_reasons") or data.get("reasons") or {}
    if not isinstance(raw, dict):
        return 0
    by_id = {hit.photo_id: hit for hit in hits}
    applied = 0
    for photo_id, reason in raw.items():
        hit = by_id.get(str(photo_id))
        if hit is None:
            continue
        text = _maybe_trim(reason, 60)
        if not text:
            continue
        hit.match_reason = text
        applied += 1
        if applied >= 5:
            break
    return applied


def _ai_timeout() -> float:
    try:
        configured = float(settings.AGENT_SEARCH_TIMEOUT or 8)
    except (TypeError, ValueError):
        configured = 8.0
    return max(2.0, min(configured, 6.0))


async def explain(
    db: AsyncSession,
    *,
    query: str,
    intent: SearchIntent,
    hits: list[SearchHit],
) -> ExplainOutcome:
    """生成结果解释；永不抛错。"""
    started = time.perf_counter()
    latency = lambda: (time.perf_counter() - started) * 1000  # noqa: E731

    if not hits:
        return ExplainOutcome(
            explanation=None,
            step=SearchStep(tool="explainer", args={"hits": 0}, status="skipped:no_results"),
        )

    if not settings.AGENT_SEARCH_EXPLAIN:
        return ExplainOutcome(
            explanation=None,
            step=SearchStep(
                tool="explainer", args={"hits": len(hits)}, status="skipped:explain_disabled"
            ),
        )

    if not settings.AI_ENABLED:
        return ExplainOutcome(
            explanation=deterministic_explanation(query, hits),
            step=SearchStep(
                tool="explainer",
                args={"hits": len(hits)},
                status="skipped:ai_disabled",
                latency_ms=latency(),
            ),
            fallback_reason="ai_disabled",
        )

    model = (settings.AGENT_SEARCH_MODEL or "").strip() or None
    try:
        result = await chat_json(
            db,
            operation="agent_search.explain",
            system=EXPLAINER_SYSTEM_PROMPT,
            user=_user_message(query, intent, hits),
            model=model,
            max_tokens=2048,
            temperature=0.2,
            timeout=_ai_timeout(),
            ref_type="search_query",
        )
        data = result.data if isinstance(result.data, dict) else {}
        explanation = _maybe_trim(
            data.get("explanation") or data.get("summary") or data.get("text"), 220
        )
        applied = _apply_match_reasons(data, hits)
        if explanation is None:
            explanation = deterministic_explanation(query, hits)
            return ExplainOutcome(
                explanation=explanation,
                step=SearchStep(
                    tool="explainer",
                    args={"hits": len(hits), "model": result.model_id},
                    status="degraded",
                    latency_ms=latency(),
                ),
                fallback_reason="explainer_invalid_output",
                model_id=result.model_id,
                total_tokens=result.total_tokens,
                cost_usd=result.cost_usd,
            )
        return ExplainOutcome(
            explanation=explanation,
            step=SearchStep(
                tool="explainer",
                args={"hits": len(hits), "model": result.model_id, "reasons": applied},
                result_count=applied,
                status="ok",
                latency_ms=latency(),
            ),
            model_id=result.model_id,
            total_tokens=result.total_tokens,
            cost_usd=result.cost_usd,
        )
    except (AIConfigError, AIBudgetExceeded) as exc:
        reason = "ai_config_error" if isinstance(exc, AIConfigError) else "ai_budget_exceeded"
        logger.info("agent_search.explainer unavailable (%s): %s", reason, exc)
    except (AICallFailed, AIJSONError) as exc:
        reason = "explainer_call_failed"
        logger.info("agent_search.explainer failed: %s", exc)
    except Exception:  # noqa: BLE001 - 解释器绝不拖垮检索
        reason = "explainer_failed"
        logger.warning("agent_search.explainer unexpected failure", exc_info=True)

    return ExplainOutcome(
        explanation=deterministic_explanation(query, hits),
        step=SearchStep(
            tool="explainer",
            args={"hits": len(hits)},
            status="degraded",
            latency_ms=latency(),
        ),
        fallback_reason=reason,
    )
