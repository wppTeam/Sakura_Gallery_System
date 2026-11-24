"""AI 成本观测接口（GET /api/v1/admin/ai/usage）测试。"""
import asyncio
import os
import tempfile
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, get_password_hash
from app.models.ai_usage import AIUsageEvent
from app.models.user import User


@pytest.fixture()
def ai_usage_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="sakura-aiusage-")
    engine = create_async_engine(f"sqlite+aiosqlite:///{os.path.join(tmpdir, 'test.db')}")
    Session = async_sessionmaker(engine, expire_on_commit=False)

    admin = User(
        student_id="20260001", username="ai_admin", display_name="AI 管理员",
        hashed_password=get_password_hash("Sakura2026!"), role="admin", is_active=True,
    )
    normal = User(
        student_id="20260002", username="ai_user", display_name="普通同学",
        hashed_password=get_password_hash("Sakura2026!"), role="user", is_active=True,
    )

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with Session() as session:
            session.add_all([admin, normal])
            now = datetime.utcnow()
            session.add_all([
                AIUsageEvent(
                    operation="moderation.prefilter", provider="openai_compatible",
                    model_id="qwen3-vl-plus", ref_type="photo", ref_id="p1",
                    prompt_tokens=1400, completion_tokens=120, total_tokens=1520,
                    cost_usd=0.0004, latency_ms=4000, success=True, created_at=now,
                ),
                AIUsageEvent(
                    operation="moderation.escalation", provider="openai_compatible",
                    model_id="deepseek-v4.1-flash-1017", ref_type="photo", ref_id="p1",
                    prompt_tokens=2600, completion_tokens=550, total_tokens=3150,
                    cost_usd=0.0007, latency_ms=8000, success=True, created_at=now,
                ),
                AIUsageEvent(
                    operation="agent_search.plan", provider="openai_compatible",
                    model_id="deepseek-v4.1-flash-1017", ref_type="search", ref_id="t1",
                    prompt_tokens=800, completion_tokens=200, total_tokens=1000,
                    cost_usd=0.0002, latency_ms=2000, success=True,
                    created_at=now - timedelta(days=2),
                ),
                AIUsageEvent(
                    operation="agent_search.explain", provider="openai_compatible",
                    model_id="deepseek-v4.1-flash-1017", ref_type="search", ref_id="t1",
                    prompt_tokens=300, completion_tokens=0, total_tokens=0,
                    cost_usd=0.0, latency_ms=15000, success=False,
                    error="timeout", created_at=now,
                ),
            ])
            await session.commit()

    asyncio.run(_init())

    async def override_get_db():
        async with Session() as session:
            yield session

    from app.main import app
    app.dependency_overrides[get_db] = override_get_db

    yield {
        "client": TestClient(app),
        "admin_token": create_access_token({"sub": "20260001"}),
        "user_token": create_access_token({"sub": "20260002"}),
    }

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_ai_usage_requires_admin(ai_usage_env):
    client = ai_usage_env["client"]
    assert client.get("/api/v1/admin/ai/usage").status_code == 401
    resp = client.get(
        "/api/v1/admin/ai/usage",
        headers={"Authorization": f"Bearer {ai_usage_env['user_token']}"},
    )
    assert resp.status_code == 403


def test_ai_usage_aggregates(ai_usage_env):
    client = ai_usage_env["client"]
    resp = client.get(
        "/api/v1/admin/ai/usage?days=7&recent_limit=3",
        headers={"Authorization": f"Bearer {ai_usage_env['admin_token']}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    totals = data["totals"]
    assert totals["calls"] == 4
    assert totals["success"] == 3
    assert totals["failed"] == 1
    assert totals["total_tokens"] == 1520 + 3150 + 1000 + 0
    assert abs(totals["cost_usd"] - 0.0013) < 1e-9
    assert totals["avg_latency_ms"] == pytest.approx((4000 + 8000 + 2000 + 15000) / 4, abs=0.2)

    operations = {b["key"]: b for b in data["by_operation"]}
    assert set(operations) == {
        "moderation.prefilter", "moderation.escalation", "agent_search.plan", "agent_search.explain",
    }
    assert operations["moderation.escalation"]["calls"] == 1
    assert operations["moderation.escalation"]["total_tokens"] == 3150

    models = {b["key"]: b for b in data["by_model"]}
    assert models["qwen3-vl-plus"]["calls"] == 1
    assert models["deepseek-v4.1-flash-1017"]["calls"] == 3
    assert models["deepseek-v4.1-flash-1017"]["total_tokens"] == 4150

    assert len(data["by_day"]) == 2  # 今天 + 两天前
    assert sum(b["calls"] for b in data["by_day"]) == 4

    assert len(data["recent"]) == 3
    assert data["recent"][0]["created_at"]  # 最近事件按时间倒序返回且字段齐全


def test_ai_usage_days_window_excludes_old_events(ai_usage_env):
    client = ai_usage_env["client"]
    resp = client.get(
        "/api/v1/admin/ai/usage?days=1",
        headers={"Authorization": f"Bearer {ai_usage_env['admin_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["totals"]["calls"] == 3  # 两天前的 agent_search.plan 被排除
    assert all(b["key"] != "agent_search.plan" for b in data["by_operation"])
