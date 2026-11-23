import os
import sys
from pathlib import Path

# Stabilize settings loading during test collection.
os.environ["DEBUG"] = "false"
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("AI_ENABLED", "false")
# 测试一律用临时 SQLite：避免把真实 .env 里的 PostgreSQL 连接带进测试，
# 否则 TestClient 每次新建 event loop 都会复用上一个 loop 的 asyncpg 连接而报
# "attached to a different loop"。
import tempfile

_TEST_DB_PATH = Path(tempfile.mkdtemp(prefix="sakura-gallery-tests-")) / "test.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TEST_DB_PATH.as_posix()}")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# 禁用应用 lifespan 的 init_db()
# ---------------------------------------------------------------------------
# 每个测试自己建 schema（SQLite 临时库）并 override get_db；lifespan 若仍去连
# 全局 engine，会在不同的 event loop 之间复用连接池而报错。
from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def _noop_lifespan(app):  # noqa: ANN001
    yield


try:
    from app.main import app as _fastapi_app  # noqa: E402

    _fastapi_app.router.lifespan_context = _noop_lifespan
except Exception:  # pragma: no cover - 导入失败时交给具体测试报错
    pass
