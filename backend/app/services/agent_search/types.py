"""Agent 检索公共类型（纯 dataclass，无重依赖）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.lexical_search import FacetResult, SearchHit


def _json_safe(value: Any) -> Any:
    """把 step args 里的值收敛为 JSON 可序列化类型（trace.steps 是 JSON 列）。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return str(value)


@dataclass
class SearchStep:
    """一次工具调用（planner / lexical_search / facets / vector_search / explainer …）。"""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    result_count: Optional[int] = None
    latency_ms: Optional[float] = None
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "args": _json_safe(self.args),
            "result_count": self.result_count,
            "latency_ms": round(self.latency_ms, 2) if self.latency_ms is not None else None,
            "status": self.status,
        }


@dataclass
class SearchIntent:
    """planner 解析出的检索意图。"""

    query: str = ""
    keywords: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    semantic_query: str = ""
    assumed: list[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_clarification: bool = False
    clarify_question: Optional[str] = None
    clarify_options: list[str] = field(default_factory=list)
    expected_facets: list[str] = field(default_factory=list)
    source: str = "heuristic"  # "llm" | "heuristic"

    def to_dict(self) -> dict[str, Any]:
        filters = {
            str(key): (value if isinstance(value, str) else _json_safe(value))
            for key, value in self.filters.items()
            if value not in (None, "", [])
        }
        return {
            "query": self.query,
            "keywords": list(self.keywords),
            "filters": filters,
            "semantic_query": self.semantic_query,
            "assumed": list(self.assumed),
            "confidence": round(float(self.confidence or 0.0), 3),
            "needs_clarification": bool(self.needs_clarification),
            "expected_facets": list(self.expected_facets),
            "source": self.source,
        }


@dataclass
class PlanOutcome:
    intent: SearchIntent
    step: SearchStep
    fallback_reason: Optional[str] = None
    model_id: Optional[str] = None
    total_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class ExplainOutcome:
    explanation: Optional[str]
    step: SearchStep
    fallback_reason: Optional[str] = None
    model_id: Optional[str] = None
    total_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class RetrievalOutcome:
    hits: list[SearchHit]
    total: int
    facets: Optional[FacetResult]
    steps: list[SearchStep]
    fallback_reason: Optional[str] = None
    keyword_weights: dict[str, float] = field(default_factory=dict)


@dataclass
class AgentSearchResult:
    """service 输出，由 API 层转换成响应模型。"""

    results: list[SearchHit]
    total: int
    facets: Optional[FacetResult]
    explanation: Optional[str]
    steps: list[SearchStep]
    clarify: Optional[str]
    clarify_options: list[str]
    intent: SearchIntent
    trace_id: Optional[str]
    search_mode: str = "agent"
    fallback_reason: Optional[str] = None
    index_version: Optional[str] = None
    query_time_ms: float = 0.0
    model_id: Optional[str] = None
    total_tokens: int = 0
    cost_usd: float = 0.0
    trace: Any = None
