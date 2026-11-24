"""就绪检查 /health/ready 测试"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import Base
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture()
def ready_env(monkeypatch, tmp_path):
    db_path = tmp_path / "ready.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())

    settings = get_settings()
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    from app import main

    monkeypatch.setattr(main, "AsyncSessionLocal", Session)

    yield {"client": TestClient(main.app), "settings": settings}

    asyncio.run(engine.dispose())


def test_health_liveness_does_not_require_database(ready_env):
    resp = ready_env["client"].get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_health_ready_ok(ready_env):
    resp = ready_env["client"].get("/health/ready")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] is True
    assert body["checks"]["storage"] == "ok"


def test_health_ready_reports_503_when_database_down(ready_env, monkeypatch):
    from app import main

    class BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: BrokenSession())
    resp = ready_env["client"].get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] is False


def test_health_ready_tolerates_storage_error(ready_env, monkeypatch):
    settings = ready_env["settings"]
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(settings, "S3_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.setattr(settings, "S3_BUCKET", "missing-bucket")
    resp = ready_env["client"].get("/health/ready")
    # 存储探测失败不阻塞就绪
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["checks"]["database"] is True
    assert body["checks"]["storage"] == "error"
