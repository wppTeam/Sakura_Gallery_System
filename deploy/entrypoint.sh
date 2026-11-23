#!/bin/sh
# =============================================================================
# 视觉百花 Sakura Gallery — 后端容器启动入口
# -----------------------------------------------------------------------------
# 镜像内路径：/usr/local/bin/entrypoint.sh
# ⚠️ 本文件与 deploy/Dockerfile.backend 中的 COPY heredoc 内容必须完全一致
#    （后端构建上下文是 backend/，无法 COPY 仓库里的 deploy/ 目录）。
#    修改流程：先改本文件 → 同步粘贴到 Dockerfile heredoc → 重新构建。
# 流程：① 环境自检（占位值 fail fast）→ ② 等 PostgreSQL 就绪
#       → ③ alembic upgrade head（有限重试）→ ④ exec uvicorn（PID 1，信号直通）
# =============================================================================
set -eu

log() { printf '[entrypoint] %s\n' "$*" >&2; }
die() { log "错误：$*"; exit 1; }

: "${DATABASE_URL:?DATABASE_URL 未设置（检查 deploy/.env.prod 是否随容器注入）}"
DEBUG="${DEBUG:-false}"

# ---------------------------------------------------------------------------
# ① 环境自检：生产环境绝不带着占位值启动
# ---------------------------------------------------------------------------
case "${SECRET_KEY:-}" in
  "")
    die "SECRET_KEY 未设置；生成方式：python3 -c 'import secrets; print(secrets.token_urlsafe(64))'"
    ;;
  *CHANGE_ME* | *your-secret-key-here* | *changethis*)
    die "SECRET_KEY 仍是模板占位值；生成方式：python3 -c 'import secrets; print(secrets.token_urlsafe(64))'"
    ;;
esac
case "$DATABASE_URL" in
  *CHANGE_ME*)
    die "DATABASE_URL 仍含 CHANGE_ME；请在 deploy/.env.prod 填入真实数据库口令（特殊字符需 URL 编码）"
    ;;
esac
if [ "$DEBUG" != "true" ] && [ "${#SECRET_KEY}" -lt 32 ]; then
  die "生产环境（DEBUG=$DEBUG）SECRET_KEY 长度应 ≥ 32，当前只有 ${#SECRET_KEY} 字符"
fi
log "环境自检通过（DEBUG=$DEBUG）"

# ---------------------------------------------------------------------------
# ② 等待 PostgreSQL 就绪
#    走 psycopg2（requirements-base.txt 已装），比只等 TCP 端口更可靠：
#    容器端口先通、数据库仍在做 initdb/恢复时会把 alembic 弄失败。
# ---------------------------------------------------------------------------
case "$DATABASE_URL" in
  postgresql://* | postgresql+asyncpg://* | postgresql+psycopg2://*)
    log "等待 PostgreSQL 就绪 ..."
    attempt=1
    max_attempts="${DB_WAIT_ATTEMPTS:-60}"
    wait_interval="${DB_WAIT_INTERVAL:-2}"
    while :; do
      if python - <<'PY'
import os
import sys

import psycopg2

url = os.environ["DATABASE_URL"]
for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://"):
    if url.startswith(prefix):
        url = "postgresql://" + url[len(prefix):]
        break
try:
    conn = psycopg2.connect(url, connect_timeout=3)
    conn.close()
except Exception as exc:  # noqa: BLE001 - 启动探活要吞掉所有驱动异常
    print("[entrypoint] PostgreSQL 暂不可用: %s" % exc, file=sys.stderr)
    sys.exit(1)
PY
      then
        log "PostgreSQL 已就绪"
        break
      fi
      if [ "$attempt" -ge "$max_attempts" ]; then
        die "等待 PostgreSQL 超时（${max_attempts} 次 × ${wait_interval}s）；检查 postgres 容器状态与 DATABASE_URL 主机名/口令"
      fi
      attempt=$((attempt + 1))
      sleep "$wait_interval"
    done
    ;;
  *)
    log "DATABASE_URL 非 PostgreSQL（可能是 SQLite 调试），跳过等待"
    ;;
esac

# ---------------------------------------------------------------------------
# ③ 数据库迁移：alembic upgrade head
#    多副本同时启动时可能竞争，此方案为单机单副本部署；失败最多重试 3 次。
# ---------------------------------------------------------------------------
log "执行数据库迁移：alembic upgrade head"
attempt=1
max_migrate_attempts="${MIGRATE_ATTEMPTS:-3}"
until alembic upgrade head; do
  if [ "$attempt" -ge "$max_migrate_attempts" ]; then
    die "数据库迁移失败（已尝试 ${attempt} 次）；查看上方 alembic 错误，或手动执行 docker compose -f deploy/docker-compose.prod.yml run --rm backend alembic current"
  fi
  log "迁移失败，第 ${attempt}/${max_migrate_attempts} 次重试，5s 后继续 ..."
  attempt=$((attempt + 1))
  sleep 5
done
log "数据库迁移完成（head）"

# ---------------------------------------------------------------------------
# ④ 启动 uvicorn（exec 让 uvicorn 成为 PID 1，docker stop 的 SIGTERM 可直达）
#    - workers 2         ：2 vCPU 的小机器，多开会抢 GIL 且翻倍内存/DB 连接
#    - proxy-headers     ：信任 nginx 传来的 X-Forwarded-Proto，否则 FastAPI 生成
#                          的跳转/文档链接会是 http
#    - limit-max-requests：定期回收 worker，规避潜在内存泄漏（配合无 --reload）
# ---------------------------------------------------------------------------
log "启动 uvicorn：workers=${UVICORN_WORKERS:-2} port=${PORT:-8000}"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${UVICORN_WORKERS:-2}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}" \
  --limit-max-requests "${UVICORN_LIMIT_MAX_REQUESTS:-10000}"
