#!/usr/bin/env bash
# =============================================================================
# 视觉百花 Sakura Gallery — 生产备份脚本（PG 逻辑备份 + uploads 数据卷）
# -----------------------------------------------------------------------------
# 备份内容：
#   1) PostgreSQL 全库逻辑备份（pg_dump -Fc，可 pg_restore 精确到表/行恢复）
#   2) uploads 数据卷（仅 STORAGE_BACKEND=local 时有意义；S3/COS 模式下自动跳过，
#      媒体请用对象存储的版本控制/生命周期规则做备份）
# 默认保留 7 天，可用环境变量覆盖：
#   BACKUP_DIR（默认 /var/backups/sakura-gallery）
#   BACKUP_KEEP_DAYS（默认 7）
#   ENV_FILE（默认 <repo>/deploy/.env.prod）
#   BACKUP_UPLOADS（auto|1|0，默认 auto：local→备份，s3→跳过）
#
# 异地备份：STORAGE_BACKEND=s3 且有 S3_ACCESS_KEY 时，PG 备份会自动再上传到
#   对象存储 backups/ 前缀（详见步骤 2.5；可用 BACKUP_REMOTE=0 关闭）。
#
# 手动执行：
#   sudo bash deploy/backup.sh
# 定时执行（crontab -e，每日 03:17，避开整点）：
#   17 3 * * * cd /opt/sakura-gallery && BACKUP_DIR=/var/backups/sakura-gallery \
#     bash deploy/backup.sh >> /var/log/sakura-backup.log 2>&1
#
# 恢复思路见 docs/DEPLOY_2C4G.md §8；备份文件含用户数据，权限保持 600/700。
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/deploy/docker-compose.prod.yml"
SERVER_OVERRIDE="$ROOT/deploy/docker-compose.server.yml"
ENV_FILE="${ENV_FILE:-$ROOT/deploy/.env.prod}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/sakura-gallery}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
BACKUP_UPLOADS="${BACKUP_UPLOADS:-auto}"

log() { printf '[backup] %s\n' "$*" >&2; }
die() { log "错误：$*"; exit 1; }

[ -f "$COMPOSE_FILE" ] || die "找不到 $COMPOSE_FILE"
[ -f "$ENV_FILE" ] || die "找不到 $ENV_FILE（先 cp deploy/.env.prod.example deploy/.env.prod 并填写）"
command -v docker >/dev/null 2>&1 || die "未安装 docker"

# 服务器部署用 prod + server 两个 compose 文件叠加；本地单文件也能跑。
COMPOSE_ARGS=(-f "$COMPOSE_FILE")
if [ -f "$SERVER_OVERRIDE" ]; then
  COMPOSE_ARGS+=(-f "$SERVER_OVERRIDE")
fi
compose() { docker compose "${COMPOSE_ARGS[@]}" --env-file "$ENV_FILE" "$@"; }

# 判断是否要备份 uploads：S3/COS 模式下媒体在对象存储，本地卷只是暂存，跳过省空间。
if [ "$BACKUP_UPLOADS" = "auto" ]; then
  storage_backend="$(grep -E '^STORAGE_BACKEND=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]' || true)"
  if [ "$storage_backend" = "s3" ]; then
    BACKUP_UPLOADS=0
  else
    BACKUP_UPLOADS=1
  fi
fi

umask 077
mkdir -p "$BACKUP_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
log "备份开始：$(date '+%F %T %Z') → $BACKUP_DIR"

# ---------------------------------------------------------------------------
# 1) PostgreSQL：用容器内的 POSTGRES_* 环境，避免宿主再存一份口令
#    -Fc = custom 格式（压缩 + pg_restore 可选表恢复）
# ---------------------------------------------------------------------------
PG_DUMP="$BACKUP_DIR/pg-$TS.dump"
log "导出 PostgreSQL ..."
compose exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges' \
  > "$PG_DUMP"
[ -s "$PG_DUMP" ] || { rm -f "$PG_DUMP"; die "pg_dump 产物为空（postgres 容器是否在运行？）"; }
log "PG 备份完成：$PG_DUMP ($(du -h "$PG_DUMP" | cut -f1))"

# ---------------------------------------------------------------------------
# 2) uploads 数据卷：优先在运行中的 backend 容器内 tar，容器不在则起一次性容器
#    --no-owner/--no-privileges 只影响 SQL 对象属主，数据本身完整
# ---------------------------------------------------------------------------
UPLOADS_TAR="$BACKUP_DIR/uploads-$TS.tar.gz"
if [ "$BACKUP_UPLOADS" = "1" ]; then
log "打包 uploads 数据卷 ..."
if ! compose exec -T backend tar czf - -C /app uploads > "$UPLOADS_TAR" 2>/dev/null; then
  log "backend 未运行，改用一次性容器读取 uploads 卷 ..."
  compose run --rm -T --no-deps --entrypoint sh backend \
    -c 'tar czf - -C /app uploads' > "$UPLOADS_TAR"
fi
[ -s "$UPLOADS_TAR" ] || { rm -f "$UPLOADS_TAR"; die "uploads 打包失败"; }
log "uploads 备份完成：$UPLOADS_TAR ($(du -h "$UPLOADS_TAR" | cut -f1))"
else
  log "STORAGE_BACKEND=s3，跳过 uploads（媒体在对象存储，请用 COS 版本控制/生命周期备份）"
fi

# ---------------------------------------------------------------------------
# 2.5) 对象存储异地备份（COS/R2/MinIO）：把 PG 备份上传到桶内 backups/ 前缀
#      备份写在本机同一块盘上不算备份；对象存储侧建议再开版本控制/生命周期。
#      实现：借 backend 容器内已安装的 boto3 + 容器内 S3_* 配置，宿主机不装依赖。
#      可覆盖：BACKUP_REMOTE=auto|1|0、BACKUP_REMOTE_PREFIX=backups、
#              BACKUP_REMOTE_KEEP_DAYS=30
# ---------------------------------------------------------------------------
REMOTE_BACKUP="${BACKUP_REMOTE:-auto}"
REMOTE_PREFIX="${BACKUP_REMOTE_PREFIX:-backups}"
REMOTE_KEEP_DAYS="${BACKUP_REMOTE_KEEP_DAYS:-30}"
if [ "$REMOTE_BACKUP" = "auto" ]; then
  storage_backend="$(grep -E '^STORAGE_BACKEND=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]' || true)"
  s3_key="$(grep -E '^S3_ACCESS_KEY=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]' || true)"
  if [ "$storage_backend" = "s3" ] && [ -n "$s3_key" ]; then
    REMOTE_BACKUP=1
  else
    REMOTE_BACKUP=0
  fi
fi

if [ "$REMOTE_BACKUP" = "1" ]; then
  log "上传 PG 备份到对象存储 ${REMOTE_PREFIX}/ ..."
  BACKEND_CID="$(compose ps -q backend 2>/dev/null | head -1 || true)"
  if [ -z "$BACKEND_CID" ]; then
    log "警告：backend 容器未运行，跳过对象存储备份（本地备份仍在 $PG_DUMP）"
  else
    REMOTE_NAME="$(basename "$PG_DUMP")"
    # 用 docker cp 传脚本（小文件），dump 走 stdin，避免容器内 uid 不同导致的权限问题
    docker cp "$ROOT/deploy/backup_upload.py" "$BACKEND_CID:/tmp/backup_upload.py" >/dev/null
    if cat "$PG_DUMP" | docker exec -i "$BACKEND_CID" python /tmp/backup_upload.py \
        --file - \
        --key "${REMOTE_PREFIX}/${REMOTE_NAME}" \
        --keep-days "$REMOTE_KEEP_DAYS"; then
      log "对象存储备份完成：s3://<bucket>/${REMOTE_PREFIX}/${REMOTE_NAME}"
    else
      log "警告：对象存储上传失败（本地备份仍在 $PG_DUMP）"
    fi
    docker exec "$BACKEND_CID" rm -f /tmp/backup_upload.py >/dev/null 2>&1 || true
  fi
fi

# ---------------------------------------------------------------------------
# 3) 清理过期备份（只动本脚本产物的文件名模式，绝不 rm -rf 目录）
# ---------------------------------------------------------------------------
if [ "$KEEP_DAYS" -gt 0 ] 2>/dev/null; then
  log "清理 ${KEEP_DAYS} 天前的备份 ..."
  find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name 'pg-*.dump' -o -name 'uploads-*.tar.gz' \) \
    -mtime "+$KEEP_DAYS" -print -delete || true
fi

log "备份结束：$(date '+%F %T %Z')；当前目录占用 $(du -sh "$BACKUP_DIR" | cut -f1)"

