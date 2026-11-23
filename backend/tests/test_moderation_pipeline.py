"""AI 审核流水线 / worker / 管理端 API 集成测试。

全部使用临时 SQLite + TestClient，AI 与规则层打桩，不访问网络、不读写真实存储。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps
from app.core.config import get_settings
from app.core.database import Base
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.audit_log import AuditLog
from app.models.moderation import ModerationReview
from app.models.notification import Notification
from app.models.photo import Photo
from app.models.user import User
from app.services import moderation as moderation_service
from app.services import moderation_rules, moderation_worker
from app.services.ai_client import AICallFailed, AIJSONResult
from app.services.moderation_rules import RuleResult

OWNER_ID = "user-owner"
AUDITOR_ID = "user-auditor"
REGULAR_ID = "user-regular"

OWNER_TOKEN = create_access_token({"sub": "20260001"})
REGULAR_TOKEN = create_access_token({"sub": "20260002"})
AUDITOR_TOKEN = create_access_token({"sub": "20260003"})

PHOTO_SEEDED = "photo-seeded"      # 已有一条 completed L2 review，用于队列 / 终判
PHOTO_PUBLIC = "photo-public"      # 公开接口脱敏断言
PHOTO_WORKER = "photo-worker"      # worker 幂等测试


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _prefilter(tier: str = "L0", confidence: float = 0.95, **overrides) -> dict:
    data = {
        "has_identifiable_person": False,
        "likely_aigc": False,
        "sensitive_content": False,
        "copyright_risk": "low",
        "watermark": False,
        "text_in_image": False,
        "suggested_tier": tier,
        "confidence": confidence,
        "reason": "测试用快筛结论",
    }
    data.update(overrides)
    return data


def _escalation(tier: str = "L2", decision: str = "hold", confidence: float = 0.9, **overrides) -> dict:
    data = {
        "final_tier": tier,
        "decision": decision,
        "risk_points": ["含可识别人物"],
        "needs_human": decision == "hold",
        "confidence": confidence,
        "reason": "测试用复核结论",
    }
    data.update(overrides)
    return data


def _chat_factory(responses: dict[str, dict], calls: list[str] | None = None):
    async def fake_chat(db, *, operation, **kwargs):
        if calls is not None:
            calls.append(operation)
        data = responses[operation]
        return AIJSONResult(
            data=data,
            text=json.dumps(data, ensure_ascii=False),
            provider="fake-provider",
            model_id="fake-model",
            prompt_tokens=12,
            completion_tokens=8,
            total_tokens=20,
            cost_usd=0.00001,
            latency_ms=42,
        )

    return fake_chat


async def _raise_chat(db, *, operation, **kwargs):
    raise AssertionError(f"本用例不应调用 AI: {operation}")


def _rules_ok():
    async def fake_run_rules(db, photo):
        result = RuleResult(checked=True)
        result.width, result.height = 1600, 1067
        return result

    return fake_run_rules


def _rules_blocked():
    async def fake_run_rules(db, photo):
        result = RuleResult(checked=True)
        result.add("near_duplicate", "block", "与已入库照片高度相似")
        return result

    return fake_run_rules


def _patch_pipeline(monkeypatch, *, rules_runner=None, chat=None):
    monkeypatch.setattr(moderation_service, "chat_json", chat or _raise_chat)
    monkeypatch.setattr(moderation_rules, "run_rules", rules_runner or _rules_ok())

    async def fake_load_image(photo):
        return "ZmFrZS1pbWFnZQ==", "image/jpeg"

    monkeypatch.setattr(moderation_service, "_load_image_for_ai", fake_load_image)


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------

async def _seed(session_factory) -> None:
    now = datetime.utcnow()
    async with session_factory() as db:
        db.add_all(
            [
                User(
                    id=OWNER_ID,
                    student_id="20260001",
                    email="owner@example.com",
                    hashed_password=get_password_hash("password123"),
                    full_name="张三",
                    role="user",
                    is_active=True,
                ),
                User(
                    id=AUDITOR_ID,
                    student_id="20260003",
                    email="auditor@example.com",
                    hashed_password=get_password_hash("password123"),
                    full_name="审核员",
                    role="auditor",
                    is_active=True,
                ),
                User(
                    id=REGULAR_ID,
                    student_id="20260002",
                    email="regular@example.com",
                    hashed_password=get_password_hash("password123"),
                    full_name="李四",
                    role="user",
                    is_active=True,
                ),
            ]
        )
        await db.flush()
        db.add_all(
            [
                Photo(
                    id=PHOTO_SEEDED,
                    uploader_id=OWNER_ID,
                    filename="seeded.jpg",
                    title="待审作品",
                    author="视觉北化",
                    original_path="originals/seeded.jpg",
                    thumb_path="thumbnails/seeded_thumb.jpg",
                    width=1600,
                    height=1067,
                    file_size=204800,
                    mime_type="image/jpeg",
                    season="spring",
                    category="campus",
                    campus="昌平校区",
                    description="待审核的校园照片",
                    status="pending",
                    processing_status="pending",
                    views=0,
                    exif_data={"Make": "Canon", "Model": "EOS R6"},
                ),
                Photo(
                    id=PHOTO_PUBLIC,
                    uploader_id=OWNER_ID,
                    filename="public.jpg",
                    title="公开作品",
                    author="视觉北化",
                    original_path="originals/public.jpg",
                    thumb_path="thumbnails/public_thumb.jpg",
                    width=1600,
                    height=1067,
                    file_size=198765,
                    mime_type="image/jpeg",
                    season="autumn",
                    category="campus",
                    campus="昌平校区",
                    description="公开响应脱敏测试",
                    status="approved",
                    processing_status="completed",
                    views=12,
                    published_at=now,
                    exif_data={
                        "Make": "Canon",
                        "Model": "EOS R6",
                        "FNumber": 2.8,
                        "GPSInfo": {"GPSLatitude": [39, 56, 0], "GPSLongitude": [116, 17, 0]},
                        "Artist": "张三",
                        "UserComment": "prompt: a cat",
                        "Software": "Adobe Photoshop 25.0",
                    },
                ),
                Photo(
                    id=PHOTO_WORKER,
                    uploader_id=OWNER_ID,
                    filename="worker.jpg",
                    title="异步审核作品",
                    author="视觉北化",
                    original_path="originals/worker.jpg",
                    thumb_path="thumbnails/worker_thumb.jpg",
                    width=1200,
                    height=800,
                    file_size=102400,
                    mime_type="image/jpeg",
                    season="summer",
                    category="landscape",
                    description="worker 测试",
                    status="pending",
                    processing_status="pending",
                    views=0,
                ),
            ]
        )
        db.add(
            ModerationReview(
                id="review-seeded",
                photo_id=PHOTO_SEEDED,
                status="completed",
                tier="L2",
                suggested_tier="L2",
                rules={"hits": [], "checked": True},
                prefilter=_prefilter("L2", 0.9, has_identifiable_person=True),
                escalation=_escalation(),
                latency_ms=1500,
                prompt_tokens=100,
                completion_tokens=50,
                cost_usd=0.0001,
                provider="fake-provider",
                model_id="fake-model",
            )
        )
        await db.commit()


@pytest.fixture
def moderation_env(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "MODERATION_ENABLED", True)
    monkeypatch.setattr(settings, "MODERATION_AUTO_APPROVE_L0", True)
    monkeypatch.setattr(settings, "MODERATION_AUTO_APPROVE_CONFIDENCE", 0.8)
    monkeypatch.setattr(settings, "MODERATION_ESCALATION_CONFIDENCE", 0.6)
    monkeypatch.setattr(settings, "MODERATION_RETRY", 1)
    monkeypatch.setattr(settings, "MODERATION_DAILY_CALL_BUDGET", 0)
    monkeypatch.setattr(settings, "TASK_QUEUE_BACKEND", "background")

    db_path = tmp_path / "moderation.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init_database())
    asyncio.run(_seed(session_factory))

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db
    monkeypatch.setattr(moderation_worker, "AsyncSessionLocal", session_factory)

    state = {
        "session_factory": session_factory,
        "engine": engine,
    }
    with TestClient(app) as client:
        state["client"] = client
        yield state

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _run_pipeline(state, photo_id: str) -> dict:
    async def _inner():
        async with state["session_factory"]() as db:
            photo = await db.get(Photo, photo_id)
            review = await moderation_service.moderate_photo(db, photo)
            await db.commit()
            return {
                "review_id": review.id,
                "status": review.status,
                "tier": review.tier,
                "suggested_tier": review.suggested_tier,
                "final_decision": review.final_decision,
                "final_tier": review.final_tier,
                "error": review.error,
                "rules": review.rules,
                "prefilter": review.prefilter,
                "escalation": review.escalation,
                "photo_status": photo.status,
                "published_at": photo.published_at,
            }

    return asyncio.run(_inner())


def _fetch(state, model, pk):
    async def _inner():
        async with state["session_factory"]() as db:
            return await db.get(model, pk)

    return asyncio.run(_inner())


def _fetch_all(state, stmt):
    async def _inner():
        async with state["session_factory"]() as db:
            return (await db.execute(stmt)).scalars().all()

    return asyncio.run(_inner())


# ---------------------------------------------------------------------------
# 流水线：规则层
# ---------------------------------------------------------------------------

def test_rule_block_goes_to_l2_without_ai(moderation_env, monkeypatch):
    _patch_pipeline(monkeypatch, rules_runner=_rules_blocked())

    result = _run_pipeline(moderation_env, PHOTO_SEEDED)

    assert result["status"] == "completed"
    assert result["tier"] == "L2"
    assert result["suggested_tier"] == "L2"
    assert result["prefilter"] is None
    assert result["escalation"] is None
    assert result["rules"]["hits"][0]["code"] == "near_duplicate"
    assert result["photo_status"] == "pending"


# ---------------------------------------------------------------------------
# 流水线：快筛 L0 免审
# ---------------------------------------------------------------------------

def test_l0_high_confidence_auto_approves(moderation_env, monkeypatch):
    calls: list[str] = []
    _patch_pipeline(
        monkeypatch,
        chat=_chat_factory({moderation_service.PREFILTER_OPERATION: _prefilter("L0", 0.95)}, calls),
    )

    result = _run_pipeline(moderation_env, PHOTO_WORKER)

    assert calls == [moderation_service.PREFILTER_OPERATION]
    assert result["status"] == "completed"
    assert result["tier"] == "L0"
    assert result["final_decision"] == "approve"
    assert result["final_tier"] == "L0"
    assert result["photo_status"] == "approved"
    assert result["published_at"] is not None


# ---------------------------------------------------------------------------
# 流水线：L2 复核与低置信度
# ---------------------------------------------------------------------------

def test_l2_prefilter_escalates_to_reasoning_model(moderation_env, monkeypatch):
    calls: list[str] = []
    _patch_pipeline(
        monkeypatch,
        chat=_chat_factory(
            {
                moderation_service.PREFILTER_OPERATION: _prefilter(
                    "L2", 0.9, has_identifiable_person=True
                ),
                moderation_service.ESCALATION_OPERATION: _escalation("L2", "hold", 0.85),
            },
            calls,
        ),
    )

    result = _run_pipeline(moderation_env, PHOTO_WORKER)

    assert calls == [
        moderation_service.PREFILTER_OPERATION,
        moderation_service.ESCALATION_OPERATION,
    ]
    assert result["status"] == "completed"
    assert result["tier"] == "L2"
    assert result["escalation"]["needs_human"] is True
    assert result["final_decision"] is None
    assert result["photo_status"] == "pending"


def test_low_confidence_escalates_but_does_not_auto_approve(moderation_env, monkeypatch):
    calls: list[str] = []
    _patch_pipeline(
        monkeypatch,
        chat=_chat_factory(
            {
                moderation_service.PREFILTER_OPERATION: _prefilter("L0", 0.3),
                moderation_service.ESCALATION_OPERATION: _escalation("L0", "approve", 0.9),
            },
            calls,
        ),
    )

    result = _run_pipeline(moderation_env, PHOTO_WORKER)

    assert len(calls) == 2
    assert result["tier"] == "L0"
    assert result["final_decision"] is None
    assert result["photo_status"] == "pending"


def test_ai_failure_degrades_to_manual(moderation_env, monkeypatch):
    async def failing_chat(db, *, operation, **kwargs):
        raise AICallFailed("上游 502")

    _patch_pipeline(monkeypatch, chat=failing_chat)

    result = _run_pipeline(moderation_env, PHOTO_WORKER)

    assert result["status"] == "failed"
    assert result["tier"] in ("L1", "L2")
    assert "AICallFailed" in (result["error"] or "")
    assert result["photo_status"] == "pending"


# ---------------------------------------------------------------------------
# worker：commit / 幂等
# ---------------------------------------------------------------------------

def test_worker_commits_and_reuses_completed_review(moderation_env, monkeypatch):
    calls: list[str] = []
    _patch_pipeline(
        monkeypatch,
        chat=_chat_factory({moderation_service.PREFILTER_OPERATION: _prefilter("L0", 0.95)}, calls),
    )

    first = asyncio.run(moderation_worker.run_moderation(PHOTO_WORKER))
    assert first is not None
    assert first.status == "completed"
    assert calls == [moderation_service.PREFILTER_OPERATION]

    persisted = _fetch(moderation_env, ModerationReview, first.id)
    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.rules is not None
    assert persisted.prefilter is not None

    second = asyncio.run(moderation_worker.run_moderation(PHOTO_WORKER))
    assert second is not None
    assert second.id == first.id
    assert calls == [moderation_service.PREFILTER_OPERATION]


def test_worker_skips_when_disabled(moderation_env, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)

    assert asyncio.run(moderation_worker.run_moderation(PHOTO_WORKER)) is None


# ---------------------------------------------------------------------------
# API：鉴权 / 队列 / 详情 / 统计
# ---------------------------------------------------------------------------

def test_moderation_api_requires_auditor(moderation_env):
    client = moderation_env["client"]

    assert client.get("/api/v1/admin/moderation/queue").status_code == 401
    assert (
        client.get("/api/v1/admin/moderation/queue", headers=_headers(OWNER_TOKEN)).status_code
        == 403
    )
    assert (
        client.get("/api/v1/admin/moderation/stats", headers=_headers(OWNER_TOKEN)).status_code
        == 403
    )
    assert (
        client.get("/api/v1/admin/moderation/queue", headers=_headers(AUDITOR_TOKEN)).status_code
        == 200
    )


def test_queue_filters_latest_review_per_photo(moderation_env):
    client = moderation_env["client"]

    response = client.get("/api/v1/admin/moderation/queue", headers=_headers(AUDITOR_TOKEN))
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    item = next(item for item in payload["items"] if item["photo_id"] == PHOTO_SEEDED)
    assert item["id"] == "review-seeded"
    assert item["tier"] == "L2"
    assert item["photo"]["id"] == PHOTO_SEEDED
    assert item["photo"]["thumb_url"] == f"/api/v1/photos/{PHOTO_SEEDED}/image/thumbnail"
    # 队列给审核员看，但上传者只出公开身份，禁止学号 / 真实姓名
    assert set(item["photo"]["uploader"]) == {"username", "display_name"}
    assert item["photo"]["uploader"]["display_name"] != "张三"
    assert "20260001" not in response.text
    assert "张三" not in response.text

    filtered = client.get(
        "/api/v1/admin/moderation/queue?tier=L2", headers=_headers(AUDITOR_TOKEN)
    )
    assert filtered.status_code == 200
    assert all(entry["tier"] == "L2" for entry in filtered.json()["items"])


def test_detail_returns_three_layer_evidence(moderation_env):
    client = moderation_env["client"]

    response = client.get(
        f"/api/v1/admin/moderation/{PHOTO_SEEDED}", headers=_headers(AUDITOR_TOKEN)
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["rules"]["checked"] is True
    assert payload["prefilter"]["suggested_tier"] == "L2"
    assert payload["escalation"]["needs_human"] is True
    assert payload["photo"]["thumb_url"] == f"/api/v1/photos/{PHOTO_SEEDED}/image/thumbnail"
    assert payload["photo"]["uploader"] == {"username": None, "display_name": None}

    assert (
        client.get(
            f"/api/v1/admin/moderation/{PHOTO_WORKER}", headers=_headers(AUDITOR_TOKEN)
        ).status_code
        == 404
    )
    assert (
        client.get("/api/v1/admin/moderation/photo-missing", headers=_headers(AUDITOR_TOKEN))
        .status_code
        == 404
    )


def test_stats_endpoint(moderation_env):
    client = moderation_env["client"]

    response = client.get(
        "/api/v1/admin/moderation/stats?days=7", headers=_headers(AUDITOR_TOKEN)
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["by_tier"]["L2"] >= 1
    # 已 seed 一条未终判 review；旧实现引用外层 ORM 表会笛卡尔积算错
    assert payload["pending_human"] == 1
    assert payload["daily_budget"] == 0
    assert payload["remaining_calls"] is None


# ---------------------------------------------------------------------------
# API：重跑 / 人工终判
# ---------------------------------------------------------------------------

def test_run_endpoint_enqueues_and_review_completes(moderation_env, monkeypatch):
    calls: list[str] = []
    _patch_pipeline(
        monkeypatch,
        chat=_chat_factory({moderation_service.PREFILTER_OPERATION: _prefilter("L0", 0.95)}, calls),
    )
    client = moderation_env["client"]

    response = client.post(
        f"/api/v1/admin/moderation/{PHOTO_WORKER}/run", headers=_headers(AUDITOR_TOKEN)
    )
    assert response.status_code == 202
    review_id = response.json()["review_id"]
    assert review_id

    # TestClient 会等待 BackgroundTasks 完成
    detail = client.get(
        f"/api/v1/admin/moderation/{PHOTO_WORKER}", headers=_headers(AUDITOR_TOKEN)
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"
    assert detail.json()["final_decision"] == "approve"
    assert calls == [moderation_service.PREFILTER_OPERATION]

    photo = _fetch(moderation_env, Photo, PHOTO_WORKER)
    assert photo.status == "approved"


def test_decision_approve_writes_audit_and_notification(moderation_env):
    client = moderation_env["client"]

    response = client.post(
        f"/api/v1/admin/moderation/{PHOTO_SEEDED}/decision",
        headers=_headers(AUDITOR_TOKEN),
        json={"decision": "approve", "final_tier": "L1", "reason": "人工复核通过"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["final_decision"] == "approve"
    assert payload["final_tier"] == "L1"
    assert payload["reviewer_id"] == AUDITOR_ID

    photo = _fetch(moderation_env, Photo, PHOTO_SEEDED)
    assert photo.status == "approved"
    assert photo.published_at is not None

    audits = _fetch_all(
        moderation_env,
        select(AuditLog).where(AuditLog.action == "moderation.approve"),
    )
    assert len(audits) == 1
    detail = json.loads(audits[0].detail)
    assert detail["decision"] == "approve"
    assert "张三" not in (audits[0].detail or "")

    notifications = _fetch_all(
        moderation_env,
        select(Notification).where(Notification.related_id == PHOTO_SEEDED),
    )
    assert len(notifications) == 1
    assert notifications[0].type == "photo_approved"
    assert notifications[0].user_id == OWNER_ID


def test_decision_reject_sets_photo_rejected(moderation_env):
    client = moderation_env["client"]

    response = client.post(
        f"/api/v1/admin/moderation/{PHOTO_SEEDED}/decision",
        headers=_headers(AUDITOR_TOKEN),
        json={"decision": "reject", "final_tier": "L2", "reason": "疑似侵权"},
    )
    assert response.status_code == 200
    assert response.json()["final_decision"] == "reject"

    photo = _fetch(moderation_env, Photo, PHOTO_SEEDED)
    assert photo.status == "rejected"
    notifications = _fetch_all(
        moderation_env,
        select(Notification).where(Notification.related_id == PHOTO_SEEDED),
    )
    assert notifications[0].type == "photo_rejected"
    assert "疑似侵权" in (notifications[0].content or "")


def test_decision_hold_keeps_photo_pending(moderation_env):
    client = moderation_env["client"]

    response = client.post(
        f"/api/v1/admin/moderation/{PHOTO_SEEDED}/decision",
        headers=_headers(AUDITOR_TOKEN),
        json={"decision": "hold", "final_tier": "L2", "reason": "等待补充授权材料"},
    )
    assert response.status_code == 200

    photo = _fetch(moderation_env, Photo, PHOTO_SEEDED)
    assert photo.status == "pending"


def test_decision_duplicate_conflicts_and_user_forbidden(moderation_env):
    client = moderation_env["client"]

    first = client.post(
        f"/api/v1/admin/moderation/{PHOTO_SEEDED}/decision",
        headers=_headers(AUDITOR_TOKEN),
        json={"decision": "approve", "final_tier": "L1"},
    )
    assert first.status_code == 200

    duplicated = client.post(
        f"/api/v1/admin/moderation/{PHOTO_SEEDED}/decision",
        headers=_headers(AUDITOR_TOKEN),
        json={"decision": "reject", "final_tier": "L2"},
    )
    assert duplicated.status_code == 409

    forbidden = client.post(
        f"/api/v1/admin/moderation/{PHOTO_SEEDED}/decision",
        headers=_headers(REGULAR_TOKEN),
        json={"decision": "approve"},
    )
    assert forbidden.status_code == 403


# ---------------------------------------------------------------------------
# 公开响应隐私回归
# ---------------------------------------------------------------------------

def test_public_photos_hide_private_fields(moderation_env):
    client = moderation_env["client"]

    response = client.get("/api/v1/photos/public?limit=20")
    assert response.status_code == 200
    payload = response.json()
    item = next(item for item in payload["items"] if item["id"] == PHOTO_PUBLIC)

    # 学号 / 真实姓名永不出现在公开响应
    assert item["uploader_student_id"] is None
    assert item["uploader_name"] is None
    assert "20260001" not in response.text
    assert "张三" not in response.text

    # EXIF 只保留拍摄参数，GPS / Artist / UserComment 被剔除
    exif = item["exif_data"]
    assert exif["Make"] == "Canon"
    assert exif["Model"] == "EOS R6"
    assert exif["FNumber"] == 2.8
    for private_key in ("GPSInfo", "Artist", "UserComment"):
        assert private_key not in exif
    assert "GPSInfo" not in response.text

    # 前端需要的变体路径与宽高仍在
    assert item["thumb_path"] == "thumbnails/public_thumb.jpg"
    assert item["width"] == 1600
    assert item["height"] == 1067


def test_owner_submissions_keep_admin_fields(moderation_env):
    client = moderation_env["client"]

    response = client.get("/api/v1/photos/my-submissions", headers=_headers(OWNER_TOKEN))
    assert response.status_code == 200
    items = response.json()["items"]
    item = next(item for item in items if item["id"] == PHOTO_SEEDED)
    assert item["uploader_student_id"] == "20260001"
    assert item["uploader_name"] == "张三"
