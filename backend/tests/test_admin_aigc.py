"""AI 生图后台管理接口测试（/api/v1/admin/aigc/*）。

覆盖：鉴权、总览聚合、生成记录筛选与分页、赠送额度（审计 + 通知 + 额度生效）、
撤销赠送、参数校验。
"""
import asyncio
import os
import tempfile
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, get_password_hash
from app.models.aigc_generation import AIGCGeneration
from app.models.aigc_quota import AigcQuotaGrant
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.user import User


@pytest.fixture()
def admin_aigc_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="sakura-admin-aigc-")
    engine = create_async_engine(f"sqlite+aiosqlite:///{os.path.join(tmpdir, 'test.db')}")
    Session = async_sessionmaker(engine, expire_on_commit=False)

    admin = User(
        student_id="20260101", username="aigc_admin", display_name="生图管理员",
        email="aigc-admin@example.com", hashed_password=get_password_hash("Sakura2026!"),
        role="admin", is_active=True,
    )
    author = User(
        student_id="20260102", username="aigc_author", display_name="创作同学",
        email="aigc-author@example.com", hashed_password=get_password_hash("Sakura2026!"),
        role="user", is_active=True,
    )
    auditor = User(
        student_id="20260103", username="aigc_auditor", display_name="审核员",
        hashed_password=get_password_hash("Sakura2026!"), role="auditor", is_active=True,
    )

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with Session() as session:
            session.add_all([admin, author, auditor])
            await session.flush()
            now = datetime.utcnow()
            session.add_all([
                AIGCGeneration(
                    user_id=author.id, prompt="黄昏的樱花", size_key="square",
                    status="succeeded", model_id="qwen-image-3.0-pro", quota_source="daily",
                    image_path="generated/a.png", image_format="png",
                    latency_ms=52000, cost_usd=0.03, created_at=now, finished_at=now,
                ),
                AIGCGeneration(
                    user_id=author.id, prompt="清晨的教学楼", size_key="landscape",
                    status="failed", model_id="qwen-image-3.0-pro", quota_source="daily",
                    error="生图超时", latency_ms=180000, cost_usd=0.0,
                    created_at=now - timedelta(days=1),
                ),
                AIGCGeneration(
                    user_id=author.id, prompt="夜晚的图书馆", size_key="portrait",
                    status="succeeded", model_id="qwen-image-3.0-pro", quota_source="bonus",
                    image_path="generated/b.png", image_format="png",
                    latency_ms=48000, cost_usd=0.03, created_at=now, finished_at=now,
                ),
                AIGCGeneration(
                    user_id=admin.id, prompt="管理员测试图", size_key="square",
                    status="succeeded", model_id="qwen-image-3.0-pro", quota_source="unlimited",
                    image_path="generated/c.png", image_format="png",
                    latency_ms=50000, cost_usd=0.03, created_at=now, finished_at=now,
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
        "session_factory": Session,
        "admin_token": create_access_token({"sub": "20260101"}),
        "author_token": create_access_token({"sub": "20260102"}),
        "auditor_token": create_access_token({"sub": "20260103"}),
        "admin_id": admin.id,
        "author_id": author.id,
    }

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fetch_all(session_factory, model):
    async def _run():
        async with session_factory() as db:
            return list((await db.execute(select(model))).scalars().all())

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------
def test_admin_aigc_requires_admin(admin_aigc_env):
    client = admin_aigc_env["client"]
    for path in ("/overview", "/generations", "/grants"):
        assert client.get(f"/api/v1/admin/aigc{path}").status_code == 401
        assert client.get(
            f"/api/v1/admin/aigc{path}", headers=_headers(admin_aigc_env["author_token"])
        ).status_code == 403
        assert client.get(
            f"/api/v1/admin/aigc{path}", headers=_headers(admin_aigc_env["auditor_token"])
        ).status_code == 403


def test_grant_requires_admin(admin_aigc_env):
    client = admin_aigc_env["client"]
    url = f"/api/v1/admin/aigc/users/{admin_aigc_env['author_id']}/grants"
    assert client.post(url, json={"amount": 1}).status_code == 401
    assert client.post(
        url, json={"amount": 1}, headers=_headers(admin_aigc_env["author_token"])
    ).status_code == 403


# ---------------------------------------------------------------------------
# 总览
# ---------------------------------------------------------------------------
def test_overview_aggregates_totals_and_quota(admin_aigc_env):
    client = admin_aigc_env["client"]
    resp = client.get(
        "/api/v1/admin/aigc/overview?days=7", headers=_headers(admin_aigc_env["admin_token"])
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["base_daily_limit"] == 3
    assert body["totals"]["total"] == 4
    assert body["totals"]["succeeded"] == 3
    assert body["totals"]["failed"] == 1
    assert body["totals"]["success_rate"] == 0.75
    assert body["totals"]["cost_usd"] == pytest.approx(0.09)
    assert body["today"]["total"] == 3
    assert len(body["by_day"]) == 2
    assert body["quota"]["granted_total"] == 0
    top = body["top_users"][0]
    assert top["user"]["username"] == "aigc_author"
    assert top["total"] == 3


def test_overview_window_excludes_old_rows(admin_aigc_env):
    client = admin_aigc_env["client"]
    body = client.get(
        "/api/v1/admin/aigc/overview?days=1", headers=_headers(admin_aigc_env["admin_token"])
    ).json()
    assert body["totals"]["total"] == 3


# ---------------------------------------------------------------------------
# 生成记录
# ---------------------------------------------------------------------------
def test_generations_filters_and_pagination(admin_aigc_env):
    client = admin_aigc_env["client"]
    headers = _headers(admin_aigc_env["admin_token"])
    base = "/api/v1/admin/aigc/generations"

    body = client.get(base, headers=headers).json()
    assert body["total"] == 4
    assert len(body["items"]) == 4
    assert body["items"][0]["user"]["username"] in {"aigc_author", "aigc_admin"}

    failed = client.get(base, params={"status": "failed"}, headers=headers).json()
    assert failed["total"] == 1
    assert failed["items"][0]["error"] == "生图超时"
    assert failed["items"][0]["image_url"] is None

    bonus = client.get(base, params={"quota_source": "bonus"}, headers=headers).json()
    assert bonus["total"] == 1
    assert bonus["items"][0]["prompt"] == "夜晚的图书馆"

    searched = client.get(base, params={"search": "樱花"}, headers=headers).json()
    assert searched["total"] == 1

    by_user = client.get(
        base, params={"user_id": admin_aigc_env["admin_id"]}, headers=headers
    ).json()
    assert by_user["total"] == 1
    assert by_user["items"][0]["quota_source"] == "unlimited"

    page = client.get(base, params={"skip": 2, "limit": 2}, headers=headers).json()
    assert (page["total"], len(page["items"]), page["skip"], page["limit"]) == (4, 2, 2, 2)

    succeeded = client.get(base, params={"status": "succeeded"}, headers=headers).json()
    assert all(item["image_url"] for item in succeeded["items"])


# ---------------------------------------------------------------------------
# 赠送额度
# ---------------------------------------------------------------------------
def test_grant_updates_quota_audit_and_notification(admin_aigc_env):
    env = admin_aigc_env
    client = env["client"]
    url = f"/api/v1/admin/aigc/users/{env['author_id']}/grants"
    resp = client.post(
        url, json={"amount": 5, "reason": "  校园内测奖励  "}, headers=_headers(env["admin_token"])
    )
    assert resp.status_code == 201, resp.text
    grant = resp.json()
    assert grant["amount"] == 5
    assert grant["reason"] == "校园内测奖励"
    assert grant["user"]["username"] == "aigc_author"
    assert grant["granted_by_name"] == "生图管理员"

    quota = client.get(
        f"/api/v1/admin/aigc/users/{env['author_id']}/quota", headers=_headers(env["admin_token"])
    ).json()
    assert quota["quota"]["bonus_total"] == 5
    assert quota["quota"]["bonus_used"] == 1  # 已有一条 bonus 成功记录
    assert quota["quota"]["bonus_remaining"] == 4
    assert len(quota["grants"]) == 1
    assert len(quota["recent"]) == 3

    author_quota = client.get("/api/v1/aigc/quota", headers=_headers(env["author_token"])).json()
    assert author_quota["bonus_remaining"] == 4
    assert author_quota["total_remaining"] == author_quota["daily_remaining"] + 4

    audits = _fetch_all(env["session_factory"], AuditLog)
    assert any(a.action == "aigc.quota_grant" and a.resource_id == env["author_id"] for a in audits)
    notes = _fetch_all(env["session_factory"], Notification)
    assert any(n.user_id == env["author_id"] and "5 张" in n.title for n in notes)

    ledger = client.get(
        "/api/v1/admin/aigc/grants", headers=_headers(env["admin_token"])
    ).json()
    assert ledger["total"] == 1
    assert ledger["items"][0]["id"] == grant["id"]


def test_grant_validates_amount_and_target(admin_aigc_env):
    env = admin_aigc_env
    client = env["client"]
    headers = _headers(env["admin_token"])
    url = f"/api/v1/admin/aigc/users/{env['author_id']}/grants"
    assert client.post(url, json={"amount": 0}, headers=headers).status_code == 422
    assert client.post(url, json={"amount": 1001}, headers=headers).status_code == 422
    assert client.post(url, json={"amount": 1, "reason": "x" * 201}, headers=headers).status_code == 422
    assert client.post(
        "/api/v1/admin/aigc/users/does-not-exist/grants", json={"amount": 1}, headers=headers
    ).status_code == 404


def test_revoke_grant_reduces_pool(admin_aigc_env):
    env = admin_aigc_env
    client = env["client"]
    headers = _headers(env["admin_token"])
    grant = client.post(
        f"/api/v1/admin/aigc/users/{env['author_id']}/grants",
        json={"amount": 3},
        headers=headers,
    ).json()
    assert client.delete(f"/api/v1/admin/aigc/grants/{grant['id']}", headers=headers).status_code == 204
    assert _fetch_all(env["session_factory"], AigcQuotaGrant) == []
    quota = client.get("/api/v1/aigc/quota", headers=_headers(env["author_token"])).json()
    assert quota["bonus_total"] == 0
    assert quota["bonus_remaining"] == 0
    audits = _fetch_all(env["session_factory"], AuditLog)
    assert any(a.action == "aigc.quota_revoke" for a in audits)
    assert client.delete("/api/v1/admin/aigc/grants/nope", headers=headers).status_code == 404


def test_user_quota_unknown_user_404(admin_aigc_env):
    client = admin_aigc_env["client"]
    assert client.get(
        "/api/v1/admin/aigc/users/nope/quota", headers=_headers(admin_aigc_env["admin_token"])
    ).status_code == 404