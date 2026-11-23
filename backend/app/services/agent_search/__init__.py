"""Agent 驱动图片检索（planner → retriever → explainer）。

公开入口：
- :func:`run_agent_search` / :class:`AgentSearchService`：完整 Agent 流程，异常自动降级
- :func:`app.services.lexical_search.search_photos`：纯词法确定性检索
"""
from app.services.agent_search.types import (
    AgentSearchResult,
    ExplainOutcome,
    PlanOutcome,
    RetrievalOutcome,
    SearchIntent,
    SearchStep,
)
from app.services.agent_search.service import (
    AgentSearchService,
    get_agent_search_service,
    run_agent_search,
    save_trace,
)

__all__ = [
    "AgentSearchResult",
    "AgentSearchService",
    "ExplainOutcome",
    "PlanOutcome",
    "RetrievalOutcome",
    "SearchIntent",
    "SearchStep",
    "get_agent_search_service",
    "run_agent_search",
    "save_trace",
]
