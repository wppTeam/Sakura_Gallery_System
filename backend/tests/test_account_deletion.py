"""账号自助注销回归测试。

覆盖：密码 / 确认词校验、删除作品与全部派生文件、删除自建专辑 / 收藏 / 通知 /
AI 草稿、审计日志保留、最后一位管理员被拒绝、删除后无法登录。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.profile import _account_limiter
from app.core import deps
from app.core.database import Base
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.aigc_generation import AIGCGeneration
from app.models.audit_log import AuditLog
from app.models.collection import Collection, CollectionPhoto
from app.models.email_code import EmailVerificationCode
from app.models.favorite import Favorite
from app.models.notification import Notification
from app.models.photo import Photo
from app.models.user import User

PASSWORD = "Sakura2026"


@pytest.fixture
def account_env(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(uploads))
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "MODERATION_ENABLED", False)
    _account_limiter.reset()

    db_path = tmp_path / "account.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    state: dict[str, str] = {"uploads": str(uploads)}

    async def seed() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            author = User(
                student_id="20260001",
                email="author@example.com",
                full_name="注销作者",
                username="leaving_author",
                role="user",
                is_active=True,
                hashed_password=get_password_hash(PASSWORD),
                token_version=1,
            )
            admin = User(
                student_id="20260002",
                email="admin@example.com",
                full_name="管理员",
                username="site_admin",
                role="admin",
                is_active=True,
                hashed_password=get_password_hash(PASSWORD),
                token_version=1,
            )
            db.add_all([author, admin])
            await db.flush()

            photo = Photo(
                id="photo-leave-1",
                uploader_id=author.id,
                filename="leave.jpg",
                original_path="originals/leave.jpg",
                thumb_path="thumbnails/leave_thumb.jpg",
                compressed_path="compressed/leave_compressed.jpg",
                processed_path=None,
                redacted_path="redacted/leave_redacted.jpg",
                redacted_thumb_path="redacted/leave_redacted_thumb.jpg",
                exif_data={"_variants": {"640": {"width": 640, "height": 427}, "1080": {"width": 1080, "height": 720}}},
                width=1200,
                height=800,
                status="approved",
            )
            db.add(photo)
            await db.flush()

            collection = Collection(
                id="collection-leave-1",
                slug="leaving-trip",
                title="注销测试专辑",
                kind="user",
                owner_id=author.id,
                status="published",
            )
            db.add(collection)
            await db.flush()
            db.add(CollectionPhoto(id="cp-leave-1", collection_id=collection.id, photo_id=photo.id, position=0))
            db.add(Favorite(id="fav-leave-1", user_id=author.id, photo_id=photo.id))
            db.add(Notification(id="notif-leave-1", user_id=author.id, type="photo_approved", title="作品过审"))
            db.add(
                EmailVerificationCode(
                    id="code-leave-1",
                    email="author@example.com",
                    purpose="login",
                    code_hash="x",
                    expires_at=datetime.utcnow() + timedelta(minutes=10),
                )
            )
            generation = AIGCGeneration(
                id="gen-leave-1",
                user_id=author.id,
                prompt="樱花",
                size_key="square",
                status="succeeded",
                provider="dashscope",
                model_id="qwen-image-3.0-pro",
                image_format="png",
            )
            db.add(generation)
            await db.commit()

            state["author_id"] = author.id
            state["admin_id"] = admin.id

    asyncio.run(seed())

    # 派生文件真实落盘，验证注销时一并清理
    for rel in [
        "originals/leave.jpg",
        "thumbnails/leave_thumb.jpg",
        "compressed/leave_compressed.jpg",
        "redacted/leave_redacted.jpg",
        "redacted/leave_redacted_thumb.jpg",
        "variants/photo-leave-1_640.webp",
        "variants/photo-leave-1_1080.jpg",
        "generated/gen-leave-1.png",
    ]:
        path = uploads / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[deps.get_db] = override_get_db
    with TestClient(app) as client:
        yield {
            "client": client,
            "session_factory": session_factory,
            "uploads": uploads,
            "state": state,
        }
    app.dependency_overrides.clear()


def _token(student_id: str) -> str:
    return create_access_token({"sub": student_id, "ver": 1})


def _headers(student_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(student_id)}"}


def _run(coro, session_factory):
    async def _wrap():
        async with session_factory() as db:
            return await coro(db)

    return asyncio.run(_wrap())


def test_requires_password_and_confirm(account_env):
    client: TestClient = account_env["client"]
    headers = _headers("20260001")

    wrong_confirm = client.request(
        "DELETE", "/api/v1/user/account", headers=headers, json={"password": PASSWORD, "confirm": "注销账号"}
    )
    assert wrong_confirm.status_code == 400
    assert "注销" in wrong_confirm.json()["detail"]

    wrong_password = client.request(
        "DELETE", "/api/v1/user/account", headers=headers, json={"password": "WrongPass1", "confirm": "注销"}
    )
    assert wrong_password.status_code == 400
    assert "密码" in wrong_password.json()["detail"]

    # 两次失败没有删掉任何东西
    async def count_users(db):
        return len((await db.execute(select(User))).scalars().all())

    assert _run(count_users, account_env["session_factory"]) == 2


def test_delete_account_removes_content_and_files(account_env):
    client: TestClient = account_env["client"]
    uploads: Path = account_env["uploads"]
    assert (uploads / "originals/leave.jpg").exists()

    resp = client.request(
        "DELETE", "/api/v1/user/account", headers=_headers("20260001"), json={"password": PASSWORD, "confirm": "注销"}
    )
    assert resp.status_code == 204, resp.text

    async def snapshot(db):
        return {
            "users": (await db.execute(select(User))).scalars().all(),
            "photos": (await db.execute(select(Photo))).scalars().all(),
            "collections": (await db.execute(select(Collection))).scalars().all(),
            "favorites": (await db.execute(select(Favorite))).scalars().all(),
            "notifications": (await db.execute(select(Notification))).scalars().all(),
            "generations": (await db.execute(select(AIGCGeneration))).scalars().all(),
            "codes": (await db.execute(select(EmailVerificationCode))).scalars().all(),
            "audits": (await db.execute(select(AuditLog).where(AuditLog.action == "user.self_delete"))).scalars().all(),
        }

    snap = _run(snapshot, account_env["session_factory"])
    assert [u.username for u in snap["users"]] == ["site_admin"], "只保留管理员账号"
    assert snap["photos"] == []
    assert snap["collections"] == []
    assert snap["favorites"] == []
    assert snap["notifications"] == []
    assert snap["generations"] == []
    assert snap["codes"] == []
    assert len(snap["audits"]) == 1

    # 原图 / 缩略图 / 压缩图 / 变体 / 脱敏图 / AI 草稿全部清理
    for rel in [
        "originals/leave.jpg",
        "thumbnails/leave_thumb.jpg",
        "compressed/leave_compressed.jpg",
        "redacted/leave_redacted.jpg",
        "redacted/leave_redacted_thumb.jpg",
        "variants/photo-leave-1_640.webp",
        "variants/photo-leave-1_1080.jpg",
        "generated/gen-leave-1.png",
    ]:
        assert not (uploads / rel).exists(), f"{rel} 应已删除"

    # 注销后无法再登录
    login = client.post("/api/v1/auth/login", json={"identifier": "author@example.com", "password": PASSWORD})
    assert login.status_code == 401


def test_last_admin_cannot_delete_account(account_env):
    client: TestClient = account_env["client"]
    # 只剩 site_admin 一位管理员（另一位是普通用户，且上面用例可能已删——用独立 seed 断言：
    # 先确认管理员数量为 1，再尝试注销管理员）
    resp = client.request(
        "DELETE", "/api/v1/user/account", headers=_headers("20260002"), json={"password": PASSWORD, "confirm": "注销"}
    )
    assert resp.status_code == 409
    assert "管理员" in resp.json()["detail"]

    async def admin_exists(db):
        rows = (await db.execute(select(User).where(User.username == "site_admin"))).scalars().all()
        return len(rows)

    assert _run(admin_exists, account_env["session_factory"]) == 1


def test_admin_can_delete_when_another_admin_exists(account_env):
    client: TestClient = account_env["client"]

    async def add_admin(db):
        db.add(
            User(
                student_id="20260003",
                email="admin2@example.com",
                username="site_admin_2",
                role="admin",
                is_active=True,
                hashed_password=get_password_hash(PASSWORD),
                token_version=1,
            )
        )
        await db.commit()

    _run(add_admin, account_env["session_factory"])

    resp = client.request(
        "DELETE", "/api/v1/user/account", headers=_headers("20260002"), json={"password": PASSWORD, "confirm": "注销"}
    )
    assert resp.status_code == 204, resp.text

    async def remaining(db):
        rows = (await db.execute(select(User.username))).scalars().all()
        return sorted(rows)

    assert _run(remaining, account_env["session_factory"]) == ["leaving_author", "site_admin_2"]


def test_delete_requires_login(account_env):
    client: TestClient = account_env["client"]
    resp = client.request("DELETE", "/api/v1/user/account", json={"password": PASSWORD, "confirm": "注销"})
    assert resp.status_code == 401
