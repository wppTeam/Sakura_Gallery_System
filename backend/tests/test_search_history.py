"""Agent 检索多轮追问（history 上下文）测试。

覆盖：
1. 上下文清洗（去空、去重、截断、只留最近 3 轮、排除当前查询）；
2. planner prompt 带上「对话上下文」；
3. 规则兜底：只在省略式追问时合并上一轮关键词/时段，新话题不受影响；
4. HTTP 端点把 ``history`` 透传给检索服务（GET 重复参数）。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.config import get_settings
from app.core.database import Base
from app.main import app
from app.services.agent_search import planner
from app.services.agent_search.types import AgentSearchResult

_NOW = None


def _mock_result(data: dict) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        model_id="mock-model",
        total_tokens=12,
        cost_usd=0.0,
        text="",
        provider="mock",
        prompt_tokens=6,
        completion_tokens=6,
        latency_ms=1.0,
        source="mock",
        raw=None,
    )


# ---------- 上下文清洗 ----------


def test_normalize_history_trims_dedupes_and_limits() -> None:
    history = ["校园的春天", " 校园的春天 ", "", "   ", "那黄昏呢", "还有春天的吗", "x" * 400]
    cleaned = planner.normalize_history(history)
    assert cleaned == ["那黄昏呢", "还有春天的吗", "x" * planner.MAX_HISTORY_CHARS]


def test_normalize_history_excludes_current_query() -> None:
    assert planner.normalize_history(["樱花", "那黄昏呢"], exclude="那黄昏呢") == ["樱花"]


def test_normalize_history_handles_none_and_non_strings() -> None:
    assert planner.normalize_history(None) == []
    assert planner.normalize_history(["a", 1, None, "b"]) == ["a", "b"]  # type: ignore[list-item]


# ---------- planner prompt ----------


def test_planner_user_message_includes_context() -> None:
    message = planner._planner_user_message(
        "那黄昏呢", {"campus": "昌平校区"}, ["校园的春天", "雨后的图书馆"]
    )
    assert "用户查询：那黄昏呢" in message
    assert "对话上下文" in message
    assert "校园的春天" in message and "雨后的图书馆" in message
    assert "省略式追问" in message
    assert "昌平校区" in message


def test_planner_user_message_without_context_has_no_section() -> None:
    message = planner._planner_user_message("樱花", None, None)
    assert "对话上下文" not in message


def test_plan_query_passes_history_to_model(monkeypatch) -> None:
    seen: dict[str, str] = {}

    async def fake_chat_json(*args, **kwargs):
        seen["user"] = kwargs.get("user", "")
        return _mock_result({"keywords": ["黄昏"], "filters": {"period": "dusk"}})

    monkeypatch.setattr(planner, "chat_json", fake_chat_json)
    settings = get_settings()
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_SEARCH_ENABLED", True)

    outcome = asyncio.run(
        planner.plan_query(None, "那黄昏呢", history=["校园的春天"])  # type: ignore[arg-type]
    )
    assert "校园的春天" in seen["user"]
    assert outcome.intent.filters.get("period") == "dusk"
    assert outcome.step.args.get("history") == 1


# ---------- 规则兜底 ----------


def test_heuristic_merges_context_for_follow_up() -> None:
    intent = planner.heuristic_intent("那黄昏呢", ["校园的春天"])
    assert intent.source == "heuristic"
    assert intent.filters.get("period") == "dusk"
    assert intent.semantic_query.startswith("校园的春天")
    assert "承接上一轮提问" in intent.assumed
    assert any("春天" in keyword for keyword in intent.keywords)


def test_heuristic_ignores_context_for_new_topic() -> None:
    intent = planner.heuristic_intent("图书馆的夜晚", ["校园的春天"])
    assert intent.filters.get("period") == "night"
    assert "承接上一轮提问" not in intent.assumed
    assert intent.semantic_query == "图书馆的夜晚"
    assert not any("春天" in keyword for keyword in intent.keywords)


def test_heuristic_without_history_keeps_plain_terms() -> None:
    intent = planner.heuristic_intent("樱花")
    assert intent.filters == {}
    assert intent.assumed == []
    assert intent.keywords == ["樱花"]


# ---------- HTTP 端点透传 ----------


@pytest.fixture
def search_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_search_endpoint_passes_history_parameter(search_client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_agent_search(db, query, filters=None, limit=20, offset=0, *, mode="agent", history=None):
        captured.update({"query": query, "mode": mode, "history": history})
        return AgentSearchResult(
            results=[],
            total=0,
            facets=None,
            explanation=None,
            steps=[],
            clarify=None,
            clarify_options=[],
            intent=planner.heuristic_intent(query),
            trace_id=None,
            search_mode=mode,
            fallback_reason=None,
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.search.run_agent_search", fake_run_agent_search
    )

    response = search_client.get(
        "/api/v1/search",
        params=[
            ("q", "那黄昏呢"),
            ("mode", "fast"),
            ("history", "校园的春天"),
            ("history", "雨后的图书馆"),
        ],
    )
    assert response.status_code == 200
    assert captured["query"] == "那黄昏呢"
    assert captured["mode"] == "fast"
    assert captured["history"] == ["校园的春天", "雨后的图书馆"]
    assert response.json()["search_mode"] == "fast"
