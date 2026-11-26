"""站内 AI 生图（AI 创作台）接口与服务测试。

覆盖：配置读取、鉴权、参数校验、每日额度、状态/图片仅本人可取、
后台生成成功/失败落库与用量事件、卡死任务回收、删除草稿。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import aigc as aigc_api
from app.core import deps
from app.core.config import get_settings
from app.core.database import Base
from app.core.security import create_access_token
from app.main import app
from app.models.ai_usage import AIUsageEvent
from app.models.aigc_generation import AIGCGeneration
from app.models.aigc_quota import AigcQuotaGrant
from app.models.user import User
from app.services import aigc_generation as aigc_service
from app.services.aigc_generation import GenerationError

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def aigc_env(tmp_path: Path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "AIGC_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "AIGC_IMAGE_DAILY_LIMIT", 3)
    aigc_api.limiter.reset()

    db_path = tmp_path / "aigc.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    state: dict = {}

    async def seed() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            owner = User(
                student_id="20269901",
                email="aigc-owner@example.com",
                full_name="创作作者",
                username="aigc_owner",
                role="user",
                is_active=True,
                hashed_password="x",
                token_version=1,
            )
            other = User(
                student_id="20269902",
                email="aigc-other@example.com",
                full_name="路人",
                username="aigc_other",
                role="user",
                is_active=True,
                hashed_password="x",
                token_version=1,
            )
            admin = User(
                student_id="20269903",
                email="aigc-admin@example.com",
                full_name="管理员",
                username="aigc_admin",
                role="admin",
                is_active=True,
                hashed_password="x",
                token_version=1,
            )
            db.add_all([owner, other, admin])
            await db.commit()
            state["owner"] = owner
            state["other"] = other
            state["admin"] = admin

    asyncio.run(seed())
    state["engine"] = engine
    state["session_factory"] = session_factory

    async def _get_db_override():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[deps.get_db] = _get_db_override
    monkeypatch.setattr(
        "app.api.v1.endpoints.aigc.run_generation",
        lambda generation_id, **kwargs: state.setdefault("enqueued", []).append(generation_id),
    )
    state["tokens"] = {
        "owner": create_access_token({"sub": state["owner"].student_id, "ver": 1}),
        "other": create_access_token({"sub": state["other"].student_id, "ver": 1}),
        "admin": create_access_token({"sub": state["admin"].student_id, "ver": 1}),
    }

    yield state

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _post(client, headers: dict, prompt: str):
    """绕开 3 次/分钟的 IP 限流，专测额度逻辑。"""
    aigc_api.limiter.reset()
    return client.post("/api/v1/aigc/generations", json={"prompt": prompt}, headers=headers)


def _add_generation(session_factory, user_id: str, **overrides) -> AIGCGeneration:
    async def _run() -> AIGCGeneration:
        async with session_factory() as db:
            generation = AIGCGeneration(
                user_id=user_id,
                prompt=overrides.get("prompt", "黄昏的校园"),
                size_key=overrides.get("size_key", "square"),
                status=overrides.get("status", "queued"),
                model_id="qwen-image-3.0-pro",
                width=1328,
                height=1328,
                image_path=overrides.get("image_path"),
                image_format=overrides.get("image_format"),
                quota_source=overrides.get("quota_source", "daily"),
                created_at=overrides.get("created_at", datetime.utcnow()),
                updated_at=overrides.get("updated_at", datetime.utcnow()),
            )
            db.add(generation)
            await db.commit()
            await db.refresh(generation)
            return generation

    return asyncio.run(_run())


def _add_grant(session_factory, user_id: str, amount: int, reason: str | None = None):
    async def _run() -> AigcQuotaGrant:
        async with session_factory() as db:
            grant = AigcQuotaGrant(user_id=user_id, amount=amount, reason=reason)
            db.add(grant)
            await db.commit()
            await db.refresh(grant)
            return grant

    return asyncio.run(_run())


def _write_generated_file(settings, generation_id: str) -> str:
    rel = f"generated/{generation_id}.png"
    path = Path(settings.UPLOAD_DIR) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_BYTES)
    return rel


# ---------------------------------------------------------------------------
# 配置与创建
# ---------------------------------------------------------------------------
def test_config_lists_sizes_and_model(aigc_env):
    settings = get_settings()
    with TestClient(app) as client:
        resp = client.get("/api/v1/aigc/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["model"] == settings.AIGC_IMAGE_MODEL
    keys = {item["key"] for item in data["sizes"]}
    assert keys == set(settings.AIGC_IMAGE_SIZES.keys())
    square = next(item for item in data["sizes"] if item["key"] == "square")
    assert (square["width"], square["height"], square["ratio"]) == (1328, 1328, "1:1")
    assert data["daily_limit"] == 3


def test_config_reports_disabled_when_switch_off(aigc_env, monkeypatch):
    monkeypatch.setattr(get_settings(), "AIGC_GENERATION_ENABLED", False)
    with TestClient(app) as client:
        assert client.get("/api/v1/aigc/config").json()["enabled"] is False


def test_create_requires_login(aigc_env):
    with TestClient(app) as client:
        resp = client.post("/api/v1/aigc/generations", json={"prompt": "黄昏的校园"})
    assert resp.status_code == 401


def test_create_returns_202_and_queues_task(aigc_env):
    state = aigc_env
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/aigc/generations",
            json={"prompt": "  黄昏的校园  ", "size": "landscape"},
            headers=_headers(state["tokens"]["owner"]),
        )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["status"] == "queued"
    assert data["prompt"] == "黄昏的校园"
    assert data["size"] == "landscape"
    assert (data["width"], data["height"]) == (1664, 928)
    assert data["image_url"] is None
    assert data["model"] == get_settings().AIGC_IMAGE_MODEL
    assert data["id"] in state["enqueued"]


def test_create_validates_prompt_and_size(aigc_env):
    state = aigc_env
    headers = _headers(state["tokens"]["owner"])
    with TestClient(app) as client:
        too_short = client.post("/api/v1/aigc/generations", json={"prompt": "   "}, headers=headers)
        bad_size = client.post(
            "/api/v1/aigc/generations", json={"prompt": "黄昏的校园", "size": "huge"}, headers=headers
        )
    assert too_short.status_code == 400
    assert "提示词" in too_short.json()["detail"]
    assert bad_size.status_code == 400


def test_daily_limit_blocks_new_generation(aigc_env, monkeypatch):
    state = aigc_env
    monkeypatch.setattr(get_settings(), "AIGC_IMAGE_DAILY_LIMIT", 1)
    headers = _headers(state["tokens"]["owner"])
    with TestClient(app) as client:
        first = client.post("/api/v1/aigc/generations", json={"prompt": "黄昏的校园"}, headers=headers)
        second = client.post("/api/v1/aigc/generations", json={"prompt": "清晨的校园"}, headers=headers)
        listing = client.get("/api/v1/aigc/generations", headers=headers)
    assert first.status_code == 202
    assert second.status_code == 429
    assert "额度" in second.json()["detail"]
    body = listing.json()
    assert body["quota"]["daily_used"] == 1
    assert body["quota"]["daily_limit"] == 1
    assert body["quota"]["bonus_remaining"] == 0
    assert body["total"] == 1


def test_bonus_pool_covers_after_daily_limit(aigc_env, monkeypatch):
    """每日额度用尽后自动扣赠送池，且 quota_source 如实落库。"""
    state = aigc_env
    monkeypatch.setattr(get_settings(), "AIGC_IMAGE_DAILY_LIMIT", 1)
    _add_grant(state["session_factory"], state["owner"].id, 2, reason="内测奖励")
    headers = _headers(state["tokens"]["owner"])
    with TestClient(app) as client:
        first = _post(client, headers, "黄昏的校园")
        second = _post(client, headers, "清晨的校园")
        third = _post(client, headers, "正午的校园")
        fourth = _post(client, headers, "夜晚的校园")
        quota = client.get("/api/v1/aigc/quota", headers=headers)
    assert [first.status_code, second.status_code, third.status_code] == [202, 202, 202]
    assert first.json()["quota_source"] == "daily"
    assert second.json()["quota_source"] == "bonus"
    assert third.json()["quota_source"] == "bonus"
    assert fourth.status_code == 429
    body = quota.json()
    assert body["unlimited"] is False
    assert (body["daily_used"], body["daily_remaining"]) == (1, 0)
    assert (body["bonus_total"], body["bonus_used"], body["bonus_remaining"]) == (2, 2, 0)
    assert body["total_remaining"] == 0


def test_failed_bonus_generation_does_not_consume_pool(aigc_env, monkeypatch):
    state = aigc_env
    monkeypatch.setattr(get_settings(), "AIGC_IMAGE_DAILY_LIMIT", 1)
    _add_grant(state["session_factory"], state["owner"].id, 1)
    _add_generation(state["session_factory"], state["owner"].id, status="failed")
    _add_generation(
        state["session_factory"], state["owner"].id, status="failed", quota_source="bonus"
    )
    headers = _headers(state["tokens"]["owner"])
    with TestClient(app) as client:
        daily = client.post("/api/v1/aigc/generations", json={"prompt": "黄昏的校园"}, headers=headers)
        bonus = client.post("/api/v1/aigc/generations", json={"prompt": "清晨的校园"}, headers=headers)
        quota = client.get("/api/v1/aigc/quota", headers=headers)
    assert (daily.status_code, bonus.status_code) == (202, 202)
    assert bonus.json()["quota_source"] == "bonus"
    assert quota.json()["bonus_remaining"] == 0


def test_admin_has_unlimited_quota(aigc_env, monkeypatch):
    state = aigc_env
    monkeypatch.setattr(get_settings(), "AIGC_IMAGE_DAILY_LIMIT", 1)
    headers = _headers(state["tokens"]["admin"])
    with TestClient(app) as client:
        for _ in range(4):
            resp = _post(client, headers, "黄昏的校园")
            assert resp.status_code == 202
            assert resp.json()["quota_source"] == "unlimited"
        quota = client.get("/api/v1/aigc/quota", headers=headers).json()
    assert quota["unlimited"] is True
    assert quota["daily_used"] == 0  # 管理员不消耗任何额度


def test_quota_endpoint_requires_login(aigc_env):
    with TestClient(app) as client:
        assert client.get("/api/v1/aigc/quota").status_code == 401


def test_failed_generation_does_not_consume_quota(aigc_env, monkeypatch):
    state = aigc_env
    monkeypatch.setattr(get_settings(), "AIGC_IMAGE_DAILY_LIMIT", 1)
    _add_generation(state["session_factory"], state["owner"].id, status="failed")
    headers = _headers(state["tokens"]["owner"])
    with TestClient(app) as client:
        resp = client.post("/api/v1/aigc/generations", json={"prompt": "黄昏的校园"}, headers=headers)
    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# 状态 / 图片 / 删除
# ---------------------------------------------------------------------------
def test_status_and_image_owner_and_admin_only(aigc_env):
    state = aigc_env
    settings = get_settings()
    generation = _add_generation(state["session_factory"], state["owner"].id, status="succeeded")
    generation.image_path = _write_generated_file(settings, generation.id)
    generation.image_format = "png"
    generation.image_bytes = len(PNG_BYTES)

    async def persist() -> None:
        async with state["session_factory"]() as db:
            row = await db.get(AIGCGeneration, generation.id)
            row.image_path = generation.image_path
            row.image_format = "png"
            row.image_bytes = len(PNG_BYTES)
            await db.commit()

    asyncio.run(persist())

    with TestClient(app) as client:
        owner_view = client.get(
            f"/api/v1/aigc/generations/{generation.id}", headers=_headers(state["tokens"]["owner"])
        )
        image = client.get(
            f"/api/v1/aigc/generations/{generation.id}/image",
            headers=_headers(state["tokens"]["owner"]),
        )
        other_view = client.get(
            f"/api/v1/aigc/generations/{generation.id}", headers=_headers(state["tokens"]["other"])
        )
        other_image = client.get(
            f"/api/v1/aigc/generations/{generation.id}/image",
            headers=_headers(state["tokens"]["other"]),
        )
        admin_image = client.get(
            f"/api/v1/aigc/generations/{generation.id}/image",
            headers=_headers(state["tokens"]["admin"]),
        )
        anonymous = client.get(f"/api/v1/aigc/generations/{generation.id}")
    assert owner_view.status_code == 200
    assert owner_view.json()["image_url"].endswith(f"/{generation.id}/image")
    assert image.status_code == 200
    assert image.content == PNG_BYTES
    assert image.headers["content-type"].startswith("image/png")
    assert other_view.status_code == 403
    assert other_image.status_code == 403
    assert admin_image.status_code == 200
    assert anonymous.status_code == 401


def test_image_404_before_finished(aigc_env):
    state = aigc_env
    generation = _add_generation(state["session_factory"], state["owner"].id, status="running")
    with TestClient(app) as client:
        resp = client.get(
            f"/api/v1/aigc/generations/{generation.id}/image",
            headers=_headers(state["tokens"]["owner"]),
        )
    assert resp.status_code == 404


def test_stale_running_is_expired(aigc_env):
    state = aigc_env
    generation = _add_generation(
        state["session_factory"],
        state["owner"].id,
        status="running",
        updated_at=datetime.utcnow() - timedelta(hours=1),
    )
    with TestClient(app) as client:
        resp = client.get(
            f"/api/v1/aigc/generations/{generation.id}", headers=_headers(state["tokens"]["owner"])
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    assert "中断" in resp.json()["error"]


def test_delete_generation_removes_file(aigc_env):
    state = aigc_env
    settings = get_settings()
    generation = _add_generation(state["session_factory"], state["owner"].id, status="succeeded")
    rel = _write_generated_file(settings, generation.id)
    path = Path(settings.UPLOAD_DIR) / rel

    async def persist() -> None:
        async with state["session_factory"]() as db:
            row = await db.get(AIGCGeneration, generation.id)
            row.image_path = rel
            row.image_format = "png"
            await db.commit()

    asyncio.run(persist())
    assert path.is_file()
    with TestClient(app) as client:
        resp = client.delete(
            f"/api/v1/aigc/generations/{generation.id}", headers=_headers(state["tokens"]["owner"])
        )
        after = client.get(
            f"/api/v1/aigc/generations/{generation.id}", headers=_headers(state["tokens"]["owner"])
        )
    assert resp.status_code == 204
    assert after.status_code == 404
    assert not path.exists()


# ---------------------------------------------------------------------------
# 后台生成服务
# ---------------------------------------------------------------------------
def _run_service_generation(aigc_env, generation_id: str, monkeypatch, result=None, error=None):
    calls: dict = {}

    async def fake_submit(client, prompt, size):
        calls["prompt"] = prompt
        calls["size"] = size
        if error:
            raise GenerationError(error)
        return "provider-task-1"

    async def fake_poll(client, task_id):
        return {"task_id": task_id, "task_status": "SUCCEEDED"}

    async def fake_download(client, url):
        if result is None:
            raise GenerationError("下载失败")
        return result

    async def fake_generate(prompt, size_key):
        calls["generate"] = (prompt, size_key)
        return {
            "data": PNG_BYTES,
            "format": "png",
            "task_id": "provider-task-1",
            "latency_ms": 1234,
            "width": 1328,
            "height": 1328,
        }

    monkeypatch.setattr(aigc_service, "generate_image", fake_generate)
    monkeypatch.setattr(aigc_service, "_submit_task", fake_submit)
    monkeypatch.setattr(aigc_service, "_poll_task", fake_poll)
    monkeypatch.setattr(aigc_service, "_download_image", fake_download)

    asyncio.run(
        aigc_service.run_generation(
            generation_id, session_factory=aigc_env["session_factory"]
        )
    )
    return calls


def test_run_generation_success_persists_file_and_usage(aigc_env, monkeypatch):
    state = aigc_env
    settings = get_settings()
    monkeypatch.setattr(settings, "AIGC_IMAGE_PRICE_USD", 0.12)
    generation = _add_generation(state["session_factory"], state["owner"].id, status="queued")

    _run_service_generation(aigc_env, generation.id, monkeypatch)

    async def check():
        async with state["session_factory"]() as db:
            row = await db.get(AIGCGeneration, generation.id)
            usage = (
                await db.execute(
                    select(AIUsageEvent).where(AIUsageEvent.ref_id == generation.id)
                )
            ).scalars().all()
            return row, usage

    row, usage = asyncio.run(check())
    assert row.status == "succeeded"
    assert row.image_path == f"generated/{generation.id}.png"
    assert row.image_format == "png"
    assert row.width == 1328 and row.height == 1328
    assert row.cost_usd == pytest.approx(0.12)
    assert (Path(settings.UPLOAD_DIR) / row.image_path).read_bytes() == PNG_BYTES
    assert len(usage) == 1
    assert usage[0].operation == "aigc.generate"
    assert usage[0].success is True
    assert usage[0].cost_usd == pytest.approx(0.12)


def test_run_generation_failure_marks_failed(aigc_env, monkeypatch):
    state = aigc_env
    generation = _add_generation(state["session_factory"], state["owner"].id, status="queued")

    async def boom(prompt, size_key):
        raise GenerationError("生图渠道不可用")

    monkeypatch.setattr(aigc_service, "generate_image", boom)
    asyncio.run(
        aigc_service.run_generation(generation.id, session_factory=state["session_factory"])
    )

    async def check():
        async with state["session_factory"]() as db:
            row = await db.get(AIGCGeneration, generation.id)
            usage = (
                await db.execute(
                    select(AIUsageEvent).where(AIUsageEvent.ref_id == generation.id)
                )
            ).scalars().all()
            return row, usage

    row, usage = asyncio.run(check())
    assert row.status == "failed"
    assert "不可用" in row.error
    assert row.finished_at is not None
    assert len(usage) == 1
    assert usage[0].success is False
    assert usage[0].cost_usd == 0
