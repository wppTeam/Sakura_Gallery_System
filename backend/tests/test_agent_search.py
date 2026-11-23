"""Agent 检索链路测试：planner / retriever / explainer / service / API 契约。

模型调用一律 mock（不访问真实中转站），覆盖：
- 意图解析成功与失败回退
- 多路融合去重（词法 + 向量 RRF/加权）
- facet 计数、澄清追问、AI 异常降级
- limit 硬上限、无向量依赖时正常返回
- GET /api/v1/search 的字段契约（前端联调依据）
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.config import get_settings
from app.core.database import Base
from app.main import app
from app.core.security import create_access_token
from app.models.photo import Photo
from app.models.search_trace import AgentSearchTrace
from app.models.tag import PhotoTag, Tag
from app.models.user import User
from app.services.agent_search import explainer, planner, retriever
from app.services.agent_search import service as agent_service
from app.services.agent_search.service import run_agent_search
from app.services.ai_client import AICallFailed
from app.services.lexical_search import SearchHit

_NOW = datetime(2026, 11, 20, 12, 0, 0)


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


async def _seed(session) -> None:
    session.add(
        User(
            id="admin-user",
            student_id="20260004",
            email="admin@buct.edu.cn",
            hashed_password="x",
            full_name="Admin",
            role="admin",
            is_active=True,
        )
    )
    session.add_all(
        [
            Photo(
                id="photo-cherry",
                uploader_id="u1",
                filename="cherry.jpg",
                title="秋季樱花大道",
                author="小明",
                description="昌平校区的樱花开了",
                season="秋季",
                category="风光",
                campus="昌平校区",
                width=1600,
                height=1067,
                status="approved",
                processing_status="completed",
                published_at=_NOW - timedelta(hours=1),
                created_at=_NOW - timedelta(hours=1),
                views=0,
            ),
            Photo(
                id="photo-ginkgo",
                uploader_id="u2",
                filename="ginkgo.jpg",
                title="金色银杏",
                description="校园里的银杏叶",
                season="秋季",
                category="风光",
                campus="昌平校区",
                width=1200,
                height=1600,
                status="approved",
                processing_status="completed",
                published_at=_NOW - timedelta(hours=2),
                created_at=_NOW - timedelta(hours=2),
                views=0,
            ),
        ]
    )
    await session.flush()
    cherry = Tag(name="樱花", category="object", usage_count=10)
    ginkgo = Tag(name="银杏", category="object", usage_count=5)
    session.add_all([cherry, ginkgo])
    await session.flush()
    session.add_all(
        [
            PhotoTag(photo_id="photo-cherry", tag_id=cherry.id),
            PhotoTag(photo_id="photo-ginkgo", tag_id=ginkgo.id),
        ]
    )
    await session.commit()


@pytest.fixture
def agent_env(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'agent.db').as_posix()}", future=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            await _seed(session)

    asyncio.run(init())

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_SEARCH_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_SEARCH_EXPLAIN", True)
    monkeypatch.setattr(settings, "AGENT_SEARCH_CLARIFY_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_SEARCH_TRACE_ENABLED", False)
    monkeypatch.setattr(settings, "AGENT_SEARCH_TIMEOUT", 3.0)

    yield session_factory, settings
    asyncio.run(engine.dispose())


@pytest.fixture
def client(agent_env):
    session_factory, _settings = agent_env

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_agent_search_success(agent_env, monkeypatch) -> None:
    session_factory, _settings = agent_env

    async def planner_ok(*args, **kwargs):
        return _mock_result(
            {
                "keywords": ["樱花"],
                "filters": {"season": "秋季"},
                "semantic_query": "樱花",
                "confidence": 0.92,
            }
        )

    async def explain_ok(*args, **kwargs):
        return _mock_result(
            {
                "explanation": "为你找到秋季校园里的樱花照片。",
                "match_reasons": {"photo-cherry": "标题命中「樱花」"},
            }
        )

    monkeypatch.setattr(planner, "chat_json", planner_ok)
    monkeypatch.setattr(explainer, "chat_json", explain_ok)

    async def scenario():
        async with session_factory() as session:
            return await run_agent_search(session, "樱花", limit=10)

    result = asyncio.run(scenario())
    assert result.search_mode == "agent"
    assert [hit.photo_id for hit in result.results] == ["photo-cherry"]
    assert result.explanation == "为你找到秋季校园里的樱花照片。"
    assert result.results[0].match_reason == "标题命中「樱花」"
    tools = [step.tool for step in result.steps]
    assert tools[0] == "planner" and "lexical_search" in tools
    assert result.steps[0].status == "ok"
    assert result.intent is not None and result.intent.confidence == 0.92
    assert result.facets is not None and result.facets.total >= 1
    assert result.query_time_ms >= 0


def test_planner_failure_falls_back_to_heuristic(agent_env, monkeypatch) -> None:
    session_factory, _settings = agent_env

    async def planner_boom(*args, **kwargs):
        raise AICallFailed("planner down")

    async def explain_ok(*args, **kwargs):
        return _mock_result({"explanation": "按关键词为你找到相关照片。"})

    monkeypatch.setattr(planner, "chat_json", planner_boom)
    monkeypatch.setattr(explainer, "chat_json", explain_ok)

    async def scenario():
        async with session_factory() as session:
            return await run_agent_search(session, "樱花", limit=10)

    result = asyncio.run(scenario())
    assert [hit.photo_id for hit in result.results] == ["photo-cherry"]
    assert result.search_mode == "agent"
    assert result.fallback_reason and "planner" in result.fallback_reason
    planner_step = result.steps[0]
    assert planner_step.status == "degraded"
    assert result.intent is not None and result.intent.source == "heuristic"


def test_explainer_failure_does_not_break_results(agent_env, monkeypatch) -> None:
    session_factory, _settings = agent_env

    async def planner_ok(*args, **kwargs):
        return _mock_result({"keywords": ["樱花"], "semantic_query": "樱花"})

    async def explain_boom(*args, **kwargs):
        raise AICallFailed("explainer down")

    monkeypatch.setattr(planner, "chat_json", planner_ok)
    monkeypatch.setattr(explainer, "chat_json", explain_boom)

    async def scenario():
        async with session_factory() as session:
            return await run_agent_search(session, "樱花", limit=10)

    result = asyncio.run(scenario())
    assert [hit.photo_id for hit in result.results] == ["photo-cherry"]
    assert result.explanation  # 规则兜底说明
    explain_step = result.steps[-1]
    assert explain_step.tool == "explainer"
    assert explain_step.status == "degraded"


def test_clarification_is_returned(agent_env, monkeypatch) -> None:
    session_factory, _settings = agent_env

    async def planner_clarify(*args, **kwargs):
        return _mock_result(
            {
                "keywords": ["樱花"],
                "needs_clarification": True,
                "clarify_question": "你想看哪个季节的樱花？",
                "clarify_options": ["春季", "秋季"],
            }
        )

    async def explain_ok(*args, **kwargs):
        return _mock_result({"explanation": "根据关键词找到 1 张照片。"})

    monkeypatch.setattr(planner, "chat_json", planner_clarify)
    monkeypatch.setattr(explainer, "chat_json", explain_ok)

    async def scenario():
        async with session_factory() as session:
            return await run_agent_search(session, "樱花", limit=10)

    result = asyncio.run(scenario())
    assert result.clarify == "你想看哪个季节的樱花？"
    assert result.clarify_options == ["春季", "秋季"]


def test_fast_mode_skips_llm_calls(agent_env, monkeypatch) -> None:
    session_factory, _settings = agent_env
    calls: list[str] = []

    async def fail_if_called(*args, **kwargs):
        calls.append(kwargs.get("operation", "unknown"))
        raise AssertionError("fast mode must not call the model")

    monkeypatch.setattr(planner, "chat_json", fail_if_called)
    monkeypatch.setattr(explainer, "chat_json", fail_if_called)

    async def scenario():
        async with session_factory() as session:
            return await run_agent_search(session, "樱花", limit=10, mode="fast")

    result = asyncio.run(scenario())
    assert calls == []
    assert result.search_mode == "fast"
    assert [hit.photo_id for hit in result.results] == ["photo-cherry"]
    skipped_tools = {step.tool for step in result.steps if step.status == "skipped:fast_mode"}
    assert {"planner", "explainer"} <= skipped_tools
    assert any(step.tool == "lexical_search" and step.status == "ok" for step in result.steps)


def test_no_vector_dependency_is_reported_as_skipped(agent_env, monkeypatch) -> None:
    session_factory, _settings = agent_env

    async def planner_ok(*args, **kwargs):
        return _mock_result({"keywords": ["樱花"], "semantic_query": "樱花"})

    async def explain_ok(*args, **kwargs):
        return _mock_result({"explanation": "找到相关照片。"})

    monkeypatch.setattr(planner, "chat_json", planner_ok)
    monkeypatch.setattr(explainer, "chat_json", explain_ok)

    async def scenario():
        async with session_factory() as session:
            return await run_agent_search(session, "樱花", limit=10)

    result = asyncio.run(scenario())
    vector_steps = [step for step in result.steps if step.tool == "vector_search"]
    assert len(vector_steps) == 1
    assert vector_steps[0].status.startswith("skipped:")
    assert result.results  # 无向量依赖时词法结果仍正常返回


def test_latency_budget_skips_llm_explainer(agent_env, monkeypatch) -> None:
    session_factory, _settings = agent_env

    async def planner_ok(*args, **kwargs):
        return _mock_result({"keywords": ["樱花"], "semantic_query": "樱花"})

    async def explainer_boom(*args, **kwargs):
        raise AssertionError("latency budget should skip the LLM explainer")

    monkeypatch.setattr(planner, "chat_json", planner_ok)
    monkeypatch.setattr(explainer, "chat_json", explainer_boom)
    # 预算压到 0 → 规划 + 检索后必然判定超预算
    monkeypatch.setattr(agent_service, "AGENT_SEARCH_LATENCY_BUDGET_MS", 0)

    async def scenario():
        async with session_factory() as session:
            return await run_agent_search(session, "樱花", limit=10)

    result = asyncio.run(scenario())
    assert [hit.photo_id for hit in result.results] == ["photo-cherry"]
    assert result.explanation  # 规则兜底说明，不是 None
    explain_step = result.steps[-1]
    assert explain_step.tool == "explainer"
    assert explain_step.status == "skipped:latency_budget"


def test_limit_is_hard_capped(agent_env, monkeypatch) -> None:
    session_factory, _settings = agent_env

    async def planner_ok(*args, **kwargs):
        return _mock_result({"keywords": ["樱花"], "semantic_query": "樱花"})

    async def explain_ok(*args, **kwargs):
        return _mock_result({"explanation": "找到相关照片。"})

    monkeypatch.setattr(planner, "chat_json", planner_ok)
    monkeypatch.setattr(explainer, "chat_json", explain_ok)

    async def scenario():
        async with session_factory() as session:
            return await run_agent_search(session, "樱花", limit=500)

    result = asyncio.run(scenario())
    assert len(result.results) <= 100
    assert result.total <= 100


def test_fusion_deduplicates_across_modalities(agent_env) -> None:
    session_factory, _settings = agent_env

    async def scenario():
        async with session_factory() as session:
            lexical_hits = [SearchHit(photo_id="photo-cherry", score=0.5)]
            vector_results = [
                SimpleNamespace(photo_id="photo-cherry", score=0.9),
                SimpleNamespace(photo_id="photo-ginkgo", score=0.8),
            ]
            return await retriever._fuse(
                session, lexical_hits, vector_results, limit=10
            )

    fused, vector_only = asyncio.run(scenario())
    ids = [hit.photo_id for hit in fused]
    assert ids.count("photo-cherry") == 1
    assert "photo-ginkgo" in ids
    assert vector_only == 1
    cherry = next(hit for hit in fused if hit.photo_id == "photo-cherry")
    assert cherry.score == pytest.approx(0.7 * 0.5 + 0.3 * 0.9, abs=1e-3)
    ginkgo = next(hit for hit in fused if hit.photo_id == "photo-ginkgo")
    assert ginkgo.matched_fields == ["vector"]
    assert ginkgo.match_reason == "语义相似"


# ---- API 契约 ----


def test_search_endpoint_fast_contract(client) -> None:
    response = client.get("/api/v1/search", params={"q": "樱花", "mode": "fast", "limit": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["search_mode"] == "fast"
    assert isinstance(payload["query_time_ms"], (int, float))
    assert isinstance(payload["steps"], list)

    item = payload["results"][0]
    assert item["photo_id"] == item["id"] == "photo-cherry"
    assert item["title"] == "秋季樱花大道"
    assert item["thumb_url"] == "/api/v1/photos/photo-cherry/image/thumbnail"
    assert item["author"] == "小明"
    assert item["width"] == 1600 and item["height"] == 1067
    assert item["aspect_ratio"] == pytest.approx(1.4995, abs=1e-3)
    assert item["tags"] == ["樱花"]
    assert item["score"] > 0
    assert "classifications" in item and "matched_fields" in item

    # 隐私：不返回学号/真实姓名/完整 EXIF
    raw = response.text
    for forbidden in ("student_id", "uploader_name", "exif_data", "20260004"):
        assert forbidden not in raw


def test_search_endpoint_agent_mode(client, agent_env, monkeypatch) -> None:
    session_factory, settings = agent_env
    monkeypatch.setattr(settings, "AGENT_SEARCH_TRACE_ENABLED", True)

    async def planner_ok(*args, **kwargs):
        return _mock_result(
            {"keywords": ["樱花"], "filters": {"season": "秋季"}, "semantic_query": "樱花"}
        )

    async def explain_ok(*args, **kwargs):
        return _mock_result({"explanation": "找到秋季校园里的樱花照片。"})

    monkeypatch.setattr(planner, "chat_json", planner_ok)
    monkeypatch.setattr(explainer, "chat_json", explain_ok)

    response = client.get("/api/v1/search", params={"q": "樱花", "mode": "agent"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["search_mode"] == "agent"
    assert payload["explanation"] == "找到秋季校园里的樱花照片。"
    assert payload["intent"]["keywords"] == ["樱花"]
    assert payload["intent"]["filters"] == {"season": "秋季"}
    tools = [step["tool"] for step in payload["steps"]]
    assert "planner" in tools and "lexical_search" in tools
    assert payload["facets"]["season"]
    assert payload["trace_id"]
    assert payload["results"][0]["match_reason"]


def test_facets_and_suggest_endpoints(client) -> None:
    facets = client.get("/api/v1/search/facets", params={"q": "樱花"})
    assert facets.status_code == 200
    payload = facets.json()
    assert payload["total"] == 1
    assert {"value", "label", "count"} <= set(payload["season"][0])

    suggest = client.get("/api/v1/search/suggest", params={"q": "樱"})
    assert suggest.status_code == 200
    suggest_payload = suggest.json()
    assert "樱花" in suggest_payload["suggestions"]
    assert suggest_payload["items"][0]["type"] == "tag"


def test_trace_endpoint_requires_admin(agent_env, client) -> None:
    session_factory, _settings = agent_env

    async def insert_trace():
        async with session_factory() as session:
            session.add(
                AgentSearchTrace(
                    trace_id="trace-test-1",
                    query="樱花",
                    intent={"keywords": ["樱花"]},
                    facets={"total": 1},
                    steps=[{"tool": "planner", "status": "ok"}],
                    result_count=1,
                    explanation="找到 1 张照片。",
                    model_id="mock-model",
                    latency_ms=12,
                )
            )
            await session.commit()

    asyncio.run(insert_trace())

    unauthorized = client.get("/api/v1/search/traces/trace-test-1")
    assert unauthorized.status_code in (401, 403)

    token = create_access_token({"sub": "20260004"})
    authorized = client.get(
        "/api/v1/search/traces/trace-test-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert authorized.status_code == 200
    trace_payload = authorized.json()
    assert trace_payload["trace_id"] == "trace-test-1"
    assert trace_payload["query"] == "樱花"

    missing = client.get(
        "/api/v1/search/traces/does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 404


def test_fast_mode_returns_old_fields_for_legacy_view(client) -> None:
    response = client.get("/api/v1/search", params={"q": "樱花", "mode": "fast"})
    assert response.status_code == 200
    payload = response.json()
    for key in ("results", "total", "query_time_ms", "search_mode", "fallback_reason", "index_version"):
        assert key in payload
    assert isinstance(payload["results"][0]["score"], float)
    assert isinstance(payload["results"][0]["classifications"], dict)
