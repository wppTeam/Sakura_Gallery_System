#!/usr/bin/env bash
# =============================================================================
# 视觉百花 Sakura Gallery — 生产备份脚本（PG 逻辑备份 + uploads 数据卷）
# -----------------------------------------------------------------------------
# 备份内容：
#   1) PostgreSQL 全库逻辑备份（pg_dump -Fc，可 pg_restore 精确到表/行恢复）
#   2) uploads 数据卷（STORAGE_BACKEND=local 时的原图与变体）
# 默认保留 7 天，可用环境变量覆盖：
#   BACKUP_DIR（默认 /var/backups/sakura-gallery）
#   BACKUP_KEEP_DAYS（默认 7）
#   ENV_FILE（默认 <repo>/deploy/.env.prod）
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
ENV_FILE="${ENV_FILE:-$ROOT/deploy/.env.prod}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/sakura-gallery}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"

log() { printf '[backup] %s\n' "$*" >&2; }
die() { log "错误：$*"; exit 1; }

[ -f "$COMPOSE_FILE" ] || die "找不到 $COMPOSE_FILE"
[ -f "$ENV_FILE" ] || die "找不到 $ENV_FILE（先 cp deploy/.env.prod.example deploy/.env.prod 并填写）"
command -v docker >/dev/null 2>&1 || die "未安装 docker"

compose() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }

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
log "打包 uploads 数据卷 ..."
if ! compose exec -T backend tar czf - -C /app uploads > "$UPLOADS_TAR" 2>/dev/null; then
  log "backend 未运行，改用一次性容器读取 uploads 卷 ..."
  compose run --rm -T --no-deps --entrypoint sh backend \
    -c 'tar czf - -C /app uploads' > "$UPLOADS_TAR"
fi
[ -s "$UPLOADS_TAR" ] || { rm -f "$UPLOADS_TAR"; die "uploads 打包失败"; }
log "uploads 备份完成：$UPLOADS_TAR ($(du -h "$UPLOADS_TAR" | cut -f1))"

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

# ---------------------------------------------------------------------------
# 4) 可选：异机/对象存储备份（备份在同一块盘上不算备份）
#    rclone copy "$BACKUP_DIR" r2:sakura-backups/$(hostname)/ --include "pg-*.dump"
#    aws s3 cp "$PG_DUMP" "s3://sakura-backups/$(hostname)/" --endpoint-url https://... 
# ---------------------------------------------------------------------------
