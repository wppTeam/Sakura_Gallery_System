# 视觉百花 Sakura Gallery — 2c4g 单机生产部署指南

> 适用机型：**2 vCPU / 4 GB 内存 / 40 GB+ 磁盘** 的单台公网 Linux 服务器（Ubuntu 22.04/24.04、Debian 12 均可）。
> 目标：`docker compose up -d --build` 一条命令拉起「PostgreSQL 16 + FastAPI 后端 + nginx 前端」，
> 不依赖 MinIO / Redis / Celery / Milvus，内存峰值控制在 2.2–2.6 GB + swap 兜底。
>
> **本文件与 deploy/ 下所有模板均不含任何真实凭据、服务器 IP 或密钥。**
> 真实值只写在 `deploy/.env.prod`（已被 `deploy/.gitignore` 忽略，权限 600）。

---

## 1. 方案总览

```
                     公网 80/443
                         │
      ┌──────────────────┴───────────────────┐
      │ 宿主机（可选）：Caddy / certbot 终止 TLS │
      └──────────────────┬───────────────────┘
                         │ HTTP（127.0.0.1:8080 或 :80）
┌────────────────────────┴─────────────────────────────┐
│ docker compose 项目 sakura-gallery（bridge 网络）      │
│                                                      │
│  nginx:1.27-alpine  ← 唯一对外端口（HTTP_PORT）        │
│    ├── /             Vite 产物（SPA try_files）        │
│    ├── /assets/      hashed 静态资源，1y immutable     │
│    └── /api/ ──► backend:8000                         │
│                                                      │
│  backend（python:3.12-slim + uvicorn --workers 2）     │
│    ├── 启动时：等 PG → alembic upgrade head → uvicorn  │
│    └── uploads 命名卷（STORAGE_BACKEND=local 时）      │
│                                                      │
│  postgres:16-alpine  ← 仅容器网络可见                  │
│    └── pgdata 命名卷（shared_buffers=512MB 等调参）    │
└──────────────────────────────────────────────────────┘
```

设计取舍（为什么不是「全家桶」）：

| 决策 | 原因 |
|------|------|
| 不装 MinIO，默认 `STORAGE_BACKEND=local` | 单机 2c4g 上再跑 MinIO 至少多 300MB 常驻内存；需要对象存储时接 Cloudflare R2/OSS（§6），2c4g 只承担 S3 客户端 |
| 不用 Redis / Celery，`TASK_QUEUE_BACKEND=background` | 后台任务用进程内 BackgroundTasks + DB outbox；少 2 个容器、少 1 个单点 |
| 不装 Milvus / torch | Milvus standalone ≥8GB 内存，2c4g 装不下；检索走 PG `pg_trgm` + `tsvector`（AGENTS.md §7） |
| `uvicorn --workers 2` | 2 vCPU 下多开 worker 只会抢 GIL + 翻倍内存与 DB 连接 |
| PG `shared_buffers=512MB` | 4GB 机器的常见取法（≈1/8 内存），再大挤占应用层 |
| 图片 `local` 模式由后端 FileResponse 输出 | 简单但吃 Python worker CPU；流量上来后切 R2/OSS 预签名（§6） |

---

## 2. 交付文件清单

| 文件 | 作用 | 备注 |
|------|------|------|
| [`deploy/docker-compose.prod.yml`](../deploy/docker-compose.prod.yml) | 生产编排：3 服务 + 2 卷 + 内存上限 + 健康检查 | 要求 Compose ≥ v2.24（`env_file.required`） |
| [`deploy/Dockerfile.backend`](../deploy/Dockerfile.backend) | 后端多阶段镜像（依赖层/代码层分离，非 root uid 10001） | 构建上下文 `backend/`；entrypoint 以 heredoc 内联 |
| [`deploy/Dockerfile.frontend`](../deploy/Dockerfile.frontend) | 前端 `node:22-alpine` 构建 → `nginx:1.27-alpine` 托管 | 构建上下文为**仓库根** |
| [`deploy/Dockerfile.frontend.dockerignore`](../deploy/Dockerfile.frontend.dockerignore) | 前端构建上下文白名单（只放行 `frontend/` 与 `deploy/nginx.prod.conf`） | 自动生效，无需额外参数 |
| [`deploy/nginx.prod.conf`](../deploy/nginx.prod.conf) | 生产 nginx：SPA + 反代 + 长缓存 + 限流 + 安全头 | 容器内 `/etc/nginx/conf.d/default.conf` |
| [`deploy/entrypoint.sh`](../deploy/entrypoint.sh) | 环境自检 → 等 PG → `alembic upgrade head` → `exec uvicorn` | 与 Dockerfile heredoc 内容逐字节一致 |
| [`deploy/.env.prod.example`](../deploy/.env.prod.example) | 全部环境变量模板（占位值） | 复制为 `.env.prod` 后填值 |
| [`deploy/.gitignore`](../deploy/.gitignore) | 确保 `.env.prod` 永不入库 | |
| [`deploy/backup.sh`](../deploy/backup.sh) | PG 逻辑备份 + uploads 卷打包，保留 7 天 | 配合 cron |
| [`backend/.dockerignore`](../backend/.dockerignore) | 后端构建上下文排除（`.venv`/`uploads`/`.env`/tests…） | 889MB uploads 不进上下文 |
| [`frontend/.dockerignore`](../frontend/.dockerignore) | 前端独立构建时的排除清单 | 生产镜像走 deploy 里的专用 ignore |
| `docs/DEPLOY_2C4G.md`（本文件） | 部署 / 运维 / 排障手册 | |

> 仓库里旧的 `deploy/deploy.sh`、`deploy/nginx.conf`、`deploy/.env.production.example`、根 `DEPLOY.md`
> 属于上一代方案（裸机 + systemd + 宿主 nginx），本轮**未改动**，仅作历史参考；请勿与新方案混用。

---

## 3. 服务器准备（一次性）

### 3.1 系统与 swap（**必做**）

4GB 机器在「构建镜像 + PG + 2 worker」并发时内存会顶到上限，必须有 swap 兜底。

```bash
# 时区
sudo timedatectl set-timezone Asia/Shanghai

# 4GB swap（至少 2GB，推荐 4GB）
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 尽量不用 swap，但 OOM 前允许ultima回收
echo 'vm.swappiness=10'   | sudo tee /etc/sysctl.d/99-sakura.conf
echo 'vm.overcommit_memory=1' | sudo tee -a /etc/sysctl.d/99-sakura.conf
sudo sysctl --system

free -h   # 确认 Swap 行不为 0
```

### 3.2 Docker Engine + Compose 插件

```bash
# 官方脚本（国内可换阿里云镜像源：见 https://developer.aliyun.com/mirror/docker-ce）
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
docker --version && docker compose version
# 要求：Docker ≥ 24（BuildKit 默认开启，Dockerfile 用到 COPY heredoc）
# 要求：Compose ≥ v2.24（env_file 的 path/required 长语法）
```

Docker 守护进程日志上限兜底（compose 已对每个容器限制，这里是全局保险）：

```bash
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
sudo systemctl restart docker
```

### 3.3 防火墙与 SSH 防护

```bash
sudo apt-get update && sudo apt-get install -y ufw fail2ban
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

sudo systemctl enable --now fail2ban
# 建议同时：禁用密码登录（PasswordAuthentication no）、改用密钥 + 非 22 端口
```

### 3.4 目录与部署用户

```bash
sudo useradd -m -s /bin/bash deployer      # 或用现有账号
sudo mkdir -p /opt/sakura-gallery /var/backups/sakura-gallery
sudo chown -R deployer:deployer /opt/sakura-gallery /var/backups/sakura-gallery
sudo chmod 700 /var/backups/sakura-gallery
# 把 deployer 加入 docker 组（等效 root 权限，注意安全）
sudo usermod -aG docker deployer
```

---

## 4. 部署步骤

以下命令均在仓库根目录（如 `/opt/sakura-gallery`）执行。可把公共参数固化成别名：

```bash
alias sakura='docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod'
```

### 4.1 拉代码

```bash
git clone <仓库地址> /opt/sakura-gallery
cd /opt/sakura-gallery
git log -1 --oneline
```

### 4.2 配置环境变量（唯一需要手工填凭据的一步）

```bash
cp deploy/.env.prod.example deploy/.env.prod
chmod 600 deploy/.env.prod

# 生成 SECRET_KEY（≥32 字符，脚本会校验）
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# 生成数据库口令（urlsafe 字符可直接放 DATABASE_URL）
python3 -c "import secrets; print(secrets.token_urlsafe(24))"

${EDITOR:-vim} deploy/.env.prod
```

必须改的项：

| 变量 | 说明 |
|------|------|
| `POSTGRES_PASSWORD` | 数据库口令（`docker` 初始化时写入 pgdata） |
| `DATABASE_URL` | 与上面口令**完全一致**：`postgresql+asyncpg://sakura:<口令>@postgres:5432/sakura_gallery` |
| `SECRET_KEY` | JWT 签名密钥；`CHANGE_ME` 或 <32 字符会被启动脚本拒绝 |
| `ALLOWED_ORIGINS` | 前端公网地址 JSON 数组，如 `'["https://sakura.example.com"]'` |
| `HTTP_PORT` | 默认 80；用宿主机 Caddy 终止 TLS 时改 `127.0.0.1:8080`（§7） |
| `AI_ENABLED` | 模板默认 `false`；配好 AI 渠道后再改 `true`（§6 之外的 AI 段） |

> 口诀：**两个文件、一个命令都不入库**——`.env.prod` 和任何 `*.pem/*.key` 不许 `git add`；
> 提交前 `git status` 确认没出现它们。

### 4.3 校验编排（不需要先构建）

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod config >/dev/null && echo "compose config OK"
```

### 4.4 构建镜像

首次构建需要拉 `python:3.12-slim` / `node:22-alpine` / `nginx:1.27-alpine`（约 400–700MB 下载）。
国内服务器建议在 `.env.prod` 打开镜像源与 pip/npm 镜像（文件末尾「构建加速」段）。

```bash
# 建议在 screen/tmux 里跑；后端 pip 安装 + 前端 tsc/vite 构建在 2c4g 上约 5–12 分钟
sakura build
```

### 4.5 启动

```bash
sakura up -d
sakura ps
```

首次启动后端会自动：等待 PG → 执行全部 alembic 迁移 → 拉起 uvicorn。
`docker compose ps` 中 `backend` 显示 `healthy` 前有 30–90 秒属正常。

### 4.6 验证

```bash
# 1) 站点存活（nginx 自带，不经过后端）
curl -fsS http://127.0.0.1/healthz && echo

# 2) 后端存活（容器内/经 nginx 均可）
# 后端镜像刻意不装 curl，用 python 标准库探活
sakura exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read().decode())"
curl -fsS http://127.0.0.1/api/v1/search/suggest?q=樱花 -H 'Host: sakura.example.com' | head -c 200

# 3) 迁移到了最新版本
sakura exec backend alembic current        # 应显示 (head)
sakura exec backend alembic heads

# 4) 服务状态与资源
sakura ps
docker stats --no-stream

# 5) 看日志（首次部署建议跟一遍启动日志）
sakura logs -f backend
```

浏览器打开 `http://<公网IP或域名>/`，应看到站点；`/docs` 属 FastAPI Swagger 面板，生产环境是否保留由后端决定（当前未关闭，若不想公开可后续在反向代理层屏蔽 `/api/docs`）。

### 4.7 创建第一个管理员

公开注册（`POST /api/v1/auth/register`）出来的账号角色都是 `user`。首个管理员需要提升：

```bash
# 1) 通过站点注册一个账号（用户名如 admin）
# 2) 直接改库（users.role 取值：admin/auditor/tagger/dept_user/user）
sakura exec postgres psql -U sakura -d sakura_gallery \
  -c "UPDATE users SET role='admin' WHERE username='admin' RETURNING id, username, role;"
```

### 4.8 配置域名与 TLS

先用 DNS 把域名 A 记录指向服务器公网 IP，再按 §7 任选一种方案终止 TLS。
**80 端口裸跑只适合验证**；上线前务必配 HTTPS（AIGC 标识、登录 JWT 都需要安全传输）。

---

## 5. 2c4g 内存预算表

> 数值来自 `docs/research/2026-11-23-small-vps-deploy.md` 的实测/估算 + 本编排的 cgroup 上限。

| 组件 | 常驻 | 峰值 | compose `mem_limit` | 说明 |
|------|------|------|---------------------|------|
| OS + Docker daemon + sshd | 300–450 MB | 500 MB | — | 最小化系统，未跑其他服务 |
| PostgreSQL 16（shared_buffers 512MB，max_conn 80） | 750–900 MB | 1.1 GB | **1024m** | shared_buffers 512 + 连接/排序/OS 页缓存 |
| backend（uvicorn --workers 2） | 240–360 MB | 500 MB | **768m** | 图片解码（Pillow）是内存峰值来源；`--limit-max-requests` 定期回收 |
| nginx（静态 + 反代） | 15–40 MB | 60 MB | **64m** | |
| **小计（运行态）** | **1.3–1.8 GB** | **2.2–2.6 GB** | | 4GB 机器余 1.4–1.8GB 给页缓存 |
| swap | — | 按需 | — | **至少 2GB、推荐 4GB**（构建期与峰值兜底） |
| 构建期（`docker build`） | 1.5–2.5 GB 瞬时 | — | — | 后端 pip/前端 vite 编译；建议先 `sakura stop` 再构建，或依赖 swap |

与任务书参数的偏差（有意为之，已在此说明）：

| 项 | 任务书 | 实际 | 原因 |
|----|--------|------|------|
| PG `mem_limit` | 512m | **1024m** | `shared_buffers=512MB` 时 PG 常驻 750–900MB，512m 会被 cgroup OOM kill（页面直接变慢/重启循环） |
| PG `maintenance_work_mem` | 256MB | 128MB | 2c4g 上 VACUUM/建索引峰值太高；128MB 对本站规模足够 |
| PG `max_connections` | 60 | 80 | 后端 pool_size=10 + max_overflow=20 × 2 worker = 最多 60，再加 alembic/psql/监控留 20 余量 |
| backend `mem_limit` | 768m | 768m | 与任务书一致，swap 兜底 |

内存相关运维命令：

```bash
free -h
docker stats --no-stream
sakura exec postgres psql -U sakura -d sakura_gallery -c "SHOW shared_buffers; SHOW max_connections;"
dmesg -T | grep -i -E 'oom|killed process' | tail   # 查 cgroup OOM 记录
```

数据库连接池：后端走 `DB_POOL_SIZE`（默认 10）/ `DB_POOL_MAX_OVERFLOW`（默认 20）/ `DB_POOL_RECYCLE`（默认 1800）配置，
真实连接数 = `workers × (pool_size + max_overflow)` = **2 × (10+20) = 60**，小于本编排的 PG `max_connections=80`。
若出现「too many connections」或 PG 内存偏紧，优先降 `DB_POOL_SIZE=5`（→ 2×15=30 连接），不要动 `workers` 以外的服务数。

---

## 6. 对象存储接入（可选，公网推荐）

三种模式：

| 模式 | 配置 | 图片路径 | 适用 |
|------|------|----------|------|
| **local（默认）** | `STORAGE_BACKEND=local` | 后端 `/api/v1/photos/{id}/image/*` → 容器 `uploads/` 卷 | 试运行/低流量；简单但吃后端 CPU |
| **S3 兼容（推荐）** | `STORAGE_BACKEND=s3` + `S3_*` | 预签名直连对象存储，不经过 Python | 公网正常运营 |
| 自建 MinIO | 额外 compose 服务或外部主机 | 同 S3 | 2c4g 不推荐（内存 + 运维成本） |

### 6.1 Cloudflare R2（推荐：egress 免费）

1. Cloudflare Dashboard → R2 → Create bucket，名字如 `sakura-gallery`（私有，不要开 Public Access）。
2. R2 → Manage API Tokens → Create API Token，权限 **Object Read & Write**，记录 `Access Key ID` / `Secret Access Key`。
3. Bucket → Settings → CORS Policy：

```json
[
  {
    "AllowedOrigins": ["https://sakura.example.com"],
    "AllowedMethods": ["GET", "HEAD", "PUT"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag", "Content-Length", "Content-Type"],
    "MaxAgeSeconds": 3600
  }
]
```

4. `deploy/.env.prod`：

```bash
STORAGE_BACKEND=s3
S3_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com   # R2 → Bucket → S3 API 里能看到
S3_BUCKET=sakura-gallery
S3_ACCESS_KEY=<R2 Access Key ID>
S3_SECRET_KEY=<R2 Secret Access Key>
S3_REGION=auto
S3_USE_SSL=true
S3_PRESIGN_EXPIRE_SECONDS=600
```

5. 重启后端并验证：`sakura up -d backend && sakura logs -f backend`；上传一张图，浏览器 Network 里图片 URL 应指向 `*.r2.cloudflarestorage.com`（预签名，带过期参数）。

### 6.2 阿里云 OSS

OSS 的 S3 兼容度有限（签名/时间头差异），boto3 直连通常不可用；两种做法：

- **推荐**：用 OSS 的 S3 兼容网关或在 OSS 前挂一层兼容入口（需自测），再按 §6.1 填 `S3_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com`；
- 或继续用 `local` 模式 + 定时 `rclone` 同步 `uploads` 卷到 OSS（备份/分发用途）。

Bucket 需为**私有**，并配置 CORS（同上）；不要在 Bucket 上开公共读。

### 6.3 自建 MinIO（仅供有 4GB+ 余量/外部存储时参考）

2c4g 上**不要**把 MinIO 加进本 compose（额外 300–500MB 常驻 + 运维）。若已有外部 MinIO：

```bash
STORAGE_BACKEND=s3
S3_ENDPOINT=http://minio.internal:9000
S3_BUCKET=sakura-gallery
S3_ACCESS_KEY=<minio access key>
S3_SECRET_KEY=<minio secret key>
S3_REGION=us-east-1
S3_USE_SSL=false       # 内网 http；公网必须 true
```

### 6.4 预签名与缓存注意

- 预签名 URL 有过期时间（`S3_PRESIGN_EXPIRE_SECONDS`），**不要**把签名后的 URL 缓存超过其有效期；前端应每次请求接口拿新 URL。
- 对象存储侧设置缓存头（`Cache-Control: public, max-age=31536000, immutable`）由后端上传时写入；本地模式的缓存头由后端 FileResponse 设置。
- 切换 `local → s3` 后，历史图片仍在 `uploads` 卷（不会自动搬运）；需要保留历史就写迁移脚本用 boto3 `upload_fileobj` 逐条搬运，搬完再删卷（先备份，见 §8）。

---

## 7. TLS（HTTPS）

容器内 nginx 只监听 80，**TLS 在宿主机层终止**（这是单机最简单也最稳的形态；也方便以后换 CDN）。两种方案二选一。

### 方案 A：宿主机 Caddy（推荐，自动续期）

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update && sudo apt-get install -y caddy
```

`/etc/caddy/Caddyfile`：

```
sakura.example.com {
    encode gzip zstd
    reverse_proxy 127.0.0.1:8080
}
```

```bash
# compose 只把 nginx 绑到回环，避免绕过 TLS 直连 80
# deploy/.env.prod: HTTP_PORT=127.0.0.1:8080
sakura up -d
sudo systemctl reload caddy
sudo ufw allow 80,443/tcp
```

然后打开 `deploy/nginx.prod.conf` 里这一段（让限流与日志拿到真实客户端 IP）：

```nginx
set_real_ip_from 172.16.0.0/12;
real_ip_header X-Forwarded-For;
```

> Caddy 会带 `X-Forwarded-Proto: https`，本配置的 `map $forwarded_proto` 会透传给后端，
> 因此 FastAPI 生成的跳转与 OpenAPI 链接是 https，不会出现混合内容。

### 方案 B：宿主机 certbot + nginx（两层 nginx）

把上面 Caddy 换成宿主 nginx，`/etc/nginx/sites-available/sakura.conf`：

```nginx
server {
    listen 80;
    server_name sakura.example.com;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl http2;
    server_name sakura.example.com;
    ssl_certificate     /etc/letsencrypt/live/sakura.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sakura.example.com/privkey.pem;
    client_max_body_size 25m;
    location / { proxy_pass http://127.0.0.1:8080; proxy_set_header Host $host;
                 proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                 proxy_set_header X-Forwarded-Proto https; }
}
```

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d sakura.example.com      # 自动续期由 certbot.timer 负责
```

同样把 `HTTP_PORT=127.0.0.1:8080` 并打开 `set_real_ip_from` 两行。
HSTS 头已在 `nginx.prod.conf` 里注释好，确认 HTTPS 稳定一周后再打开。

---

## 8. 备份与恢复

**备份同一块盘不算备份**：每天本地备份 + 每周异地（rclone 到 R2/另一台机器）。备份文件含用户数据，脚本已 `umask 077`。

### 8.1 手动 / 定时备份

```bash
# 手动
sudo BACKUP_DIR=/var/backups/sakura-gallery bash deploy/backup.sh

# 定时（每日 03:17，避开整点）
sudo crontab -u deployer -e
17 3 * * * cd /opt/sakura-gallery && BACKUP_DIR=/var/backups/sakura-gallery bash deploy/backup.sh >> /var/log/sakura-backup.log 2>&1
```

产出：`pg-YYYYmmdd-HHMMSS.dump`（`pg_dump -Fc`）+ `uploads-YYYYmmdd-HHMMSS.tar.gz`，默认保留 7 天。
异地（可选，推荐）：

```bash
# 安装 rclone 并配置 R2 remote 后
rclone copy /var/backups/sakura-gallery r2:sakura-backups/$(hostname)/ --include 'pg-*.dump' --max-age 8d
```

### 8.2 恢复 PostgreSQL

```bash
cd /opt/sakura-gallery
# 1) 停应用，避免恢复期间写入
sakura stop backend nginx

# 2) 用备份覆盖（--clean 会先 DROP 再重建，恢复完是备份时刻的完整状态）
cat /var/backups/sakura-gallery/pg-YYYYmmdd-HHMMSS.dump | \
  sakura exec -T postgres pg_restore -U sakura -d sakura_gallery --clean --if-exists --no-owner

# 3) 校验版本与数据
sakura exec backend alembic current
sakura exec postgres psql -U sakura -d sakura_gallery -c "SELECT count(*) FROM works;"

sakura up -d
```

### 8.3 恢复 uploads

```bash
# 解包回命名卷（一次性容器，不影响正在运行的服务）
cat /var/backups/sakura-gallery/uploads-YYYYmmdd-HHMMSS.tar.gz | \
  sakura run --rm -T --no-deps --entrypoint sh backend -c 'tar xzf - -C /app'
sakura exec backend sh -c 'du -sh /app/uploads && ls /app/uploads | head'
```

> 恢复演练：每季度在测试机实际恢复一次；只看「备份成功」不等于「备份可用」。

---

## 9. 升级与回滚

### 9.1 升级

```bash
cd /opt/sakura-gallery
sudo bash deploy/backup.sh          # ① 升级前必须备份
git fetch --tags && git checkout <新版本 tag>   # 或 git pull
sakura config >/dev/null            # ② 新代码改了 compose 时先校验
sakura build                        # ③ 构建新镜像（建议先 sakura stop，省内存）
sakura up -d                        # ④ 重建有变化容器；backend 启动会自动跑迁移
sakura ps && sakura logs --tail=50 backend
```

- 迁移**只向前**：`alembic downgrade` 不保证可用，回滚代码前先确认迁移是否可逆。
- 重建期间有约 10–30 秒 502 窗口（backend 重启 + 迁移）；重要时段内先在低峰操作。
- `docker image prune -f` 可清旧镜像；**不要** `docker system prune --volumes`（会删数据卷）。

### 9.2 回滚

```bash
git checkout <上一个版本 tag>
sakura build && sakura up -d
# 如果新版本已执行不可逆迁移：停止写入 → 按 §8.2 恢复升级前的 pg dump → 再回滚代码
```

---

## 10. 故障排查

### 10.1 页面 502 Bad Gateway

```bash
sakura ps                                  # backend 是否 healthy / 在重启循环
sakura logs --tail=100 backend             # 常见：迁移失败、SECRET_KEY 占位、DATABASE_URL 错
sakura exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read().decode())"
sakura exec nginx wget -qO- http://backend:8000/health   # 容器网络是否通
```

- 本配置用 `resolver 127.0.0.11` + 变量 `proxy_pass`，backend 重建后 nginx **无需**重启即可重新解析；
  若你手动改回了 `upstream` 写法，后端换 IP 后需 `sakura restart nginx`。
- 后端启动失败最常见原因：`.env.prod` 里 `SECRET_KEY`/`DATABASE_URL` 仍是模板值。
  启动脚本会直接打印明确错误（`[entrypoint] 错误：...`），按提示修即可。

### 10.2 迁移失败

```bash
sakura logs --tail=200 backend | grep -A5 -i alembic
sakura exec backend alembic current
sakura exec backend alembic heads
```

常见原因：数据库里已有旧 schema 但 `alembic_version` 表对不上（从旧库导入的情况）、
`DATABASE_URL` 指向了错的库、PG 内存不足被 OOM。修复前先备份；不确定时用 `alembic stamp <rev>` 对齐版本号而不是硬跑迁移。

### 10.3 上传返回 413 Request Entity Too Large

- 上传上限三处必须一致：后端 `MAX_UPLOAD_SIZE=20971520`（20MB）、nginx `client_max_body_size 25m`、前端上传前校验。
- 调大：改 `.env.prod` 的 `MAX_UPLOAD_SIZE` 与 `deploy/nginx.prod.conf` 的 `client_max_body_size` → `sakura up -d --build backend nginx`。
- 注意 2c4g 上把上限调到 50MB+ 会显著提高 Pillow 解码的内存峰值，谨慎。

### 10.4 429 Too Many Requests（限流）

`nginx.prod.conf` 里按 IP 限流：API 30r/s（burst 60）、登录 20r/m（burst 10）、上传 2r/s（burst 5）。
校园/宿舍 NAT 出口共享同一公网 IP 时可能误伤：

```bash
sakura logs nginx --tail=200 | grep ' 429 '
# 调整：把对应 limit_req_zone 的 rate/burst 放宽，然后
sakura up -d --build nginx
```

### 10.5 容器 OOM / 变慢

```bash
dmesg -T | grep -i -E 'oom|killed process' | tail
docker stats --no-stream
free -h
```

- PG 被 OOM：确认 `PG_MEM_LIMIT` 没被调回 512m（见 §5 偏差说明）；
- backend 被 OOM：把 `UVICORN_WORKERS` 降为 1、或把 `BACKEND_MEM_LIMIT` 提到 1024m 并相应加 swap；
- 构建期 OOM：先 `sakura stop` 释放内存再构建，或在 CI/本地构建后 `docker save|load` 传镜像。

### 10.6 图片 404 / 裂图

```bash
sakura exec backend sh -c 'ls -la /app/uploads | head'
sakura exec backend sh -c 'du -sh /app/uploads'
# 是否切换过 STORAGE_BACKEND 但历史文件没搬（§6.4）
curl -I http://127.0.0.1/api/v1/photos/1/image/thumbnail
```

- `local` 模式下图片走 `/api/v1/photos/{id}/image/*`（后端 FileResponse），若 nginx 返回 404 且后端正常，
  检查是否被 nginx 静态规则截走（本配置用 `^~ /api/` 前缀保证不截）。
- `s3` 模式下检查 `S3_*` 是否与 bucket 匹配、预签名是否过期（系统时间偏差 > 15 分钟也会签名失败）。

### 10.7 前端白屏 / 发版后用户仍看旧版

- `index.html` 已设 `no-cache`，`/assets/*` 是 hash 文件名 + 1 年 immutable；发版后强刷一次即可。
- 若 `/assets/*.js` 404：说明新 index.html 配了不存在的 asset（构建未成功或 CDN 缓存了旧 index.html）。
- `frontend/public/` 下的 `/brand`、`/fonts` 等**文件名不含 hash**，改版时请改名或加 `?v=`，否则 1 年缓存不更新。

### 10.8 `docker compose config` 报错

- `env_file ... required` / `path` 语法不支持 → Compose 版本 < 2.24，升级 Docker Compose 插件；
- `POSTGRES_PASSWORD is required` → 忘了 `--env-file deploy/.env.prod`（或 `.env.prod` 未创建）；
- 找不到 `deploy/.env.prod` 时 `config` 仍应通过（模板设计为可选），但 `up` 会因口令缺失失败——这是预期保护。

---

## 11. 已知限制与未验证项

1. **TLS 不在 compose 内**：容器 nginx 只监听 80，证书/续期由宿主机 Caddy 或 certbot 负责（§7）。
2. **单机无 HA**：PG 单点、部署机单点；磁盘损坏即全站不可用。务必执行 §8 备份 + 异地副本。
3. **前置代理时限流按代理 IP 计**：Caddy/certbot 方案下需打开 `set_real_ip_from` 两行（§7），否则所有请求看起来都来自本机。
4. **无 CDN**：静态资源由本机 nginx 直出；流量起来后可在前面加 CDN（`/assets` 已带长缓存头，接入成本低）。
5. **`frontend/public/` 非 hash 资源长缓存**：改版改文件需改名（§10.7）。
6. **默认 `STORAGE_BACKEND=local`**：图片流量经过 Python worker，2 vCPU 下高并发图片浏览会吃 CPU；公网建议切 R2/OSS（§6）。
7. **`AI_ENABLED=false` 默认**：模板不含真实 key，未配渠道前审核走规则+人工、检索走 fast；配好后改 `true` 并观察 `ai_usage_events` 成本。
8. **限流参数为经验值**：`api_general 30r/s` 等按「校园 NAT 共享出口」保守估计；实际按 §10.4 调整。
9. **构建期内存峰值**高于运行期：2c4g 必须带 swap（§3.1），否则首次构建可能被 OOM。
10. **未做的自动化**：无 CI 自动构建/推送镜像、无监控告警、无 CDN 回源配置——建议后续加 uptime 探活（定时 `curl /healthz` + 告警）与日志采集。

---

## 12. 常用运维命令速查

```bash
alias sakura='docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod'

sakura ps                       # 状态与健康
sakura logs -f --tail=100 backend
sakura restart backend          # 重启后端（会重新跑迁移，幂等）
sakura exec backend sh          # 进后端容器（非 root uid 10001）
sakura exec postgres psql -U sakura -d sakura_gallery
sakura config                   # 渲染后的最终配置（含 env_file 注入值）
docker stats --no-stream        # 实时内存/CPU
du -sh /var/lib/docker/volumes/sakura-gallery-*   # 卷占用
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod down   # 停栈（保留卷）
```

---

## 13. 验证记录（在开发机 Docker 29.10 / Compose v5.7.1 上实测）

| 验收项 | 命令 | 结果 |
|--------|------|------|
| 编排语法与插值 | `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod.example config` | ✅ 通过（exit 0，无 warning） |
| `.env.prod` 注入解析（含 `ALLOWED_ORIGINS` JSON） | 以上命令 + 临时 `.env.prod` | ✅ 注释/引号按预期解析，`ALLOWED_ORIGINS` 为合法 JSON 数组 |
| nginx 配置语法 | `docker run --rm -v "$PWD/deploy/nginx.prod.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine nginx -t` | ✅ `test is successful` |
| 后端镜像构建 | `docker build -f deploy/Dockerfile.backend -t sakura-backend:test backend/`（本机加 `--build-arg PIP_INDEX_URL=<镜像源>`） | ✅ 成功后端镜像 446MB（python:3.12-slim 基础） |
| 前端镜像构建 | `docker build -f deploy/Dockerfile.frontend -t sakura-frontend:test .`（本机加 `--build-arg NPM_REGISTRY=https://registry.npmmirror.com`） | ✅ 成功前端镜像 84.3MB（含 dist + nginx 配置） |
| 镜像内 alembic 配置 | `docker run --rm --entrypoint alembic sakura-backend:test heads` | ✅ `f0a1b2c3d4e5 (head)` |
| entrypoint 语法 | `bash -n deploy/entrypoint.sh` | ✅ 通过 |
| Dockerfile heredoc 与 `deploy/entrypoint.sh` 一致性 | 脚本比对两段内容 | ✅ 逐字节一致 |
| **端到端联通**（临时 PG16 + backend + nginx，一次性随机密钥，全部容器测试后删除） | 起 `postgres:16-alpine` → backend 容器（entrypoint 等 PG → `alembic upgrade head`）→ 前端 nginx 容器 `:18080` | ✅ 迁移链 `f1a2b3c4d5e6 → f0a1b2c3d4e5` 全部执行、日志「数据库迁移完成（head）」；`workers=2` 启动；backend 容器内 `/health` → `{"status":"healthy"}`（约 8s 就绪）；非 root `uid=10001(sakura)`；`/app/uploads` 可写 |
| 经 nginx 的 E2E | `curl http://127.0.0.1:18080/...` | ✅ `/healthz`→`ok`；`/`→200 `text/html` + `Cache-Control: no-cache` + 安全头；SPA 深路由 `/some/deep/route`→200 index.html；`/api/v1/search/suggest?q=樱花`→200 JSON（变量 `proxy_pass` + resolver 生效）；`/api/v1/auth/login` GET→405（反代到后端）；`/brand/logo.png`→`Cache-Control: public, max-age=31536000, immutable` |

> 未验证项（需真实域名/公网/对象存储）：TLS 证书签发与自动续期、HTTPS 跳转、真实上传/审核链路、S3/R2 预签名跳转、
> 备份恢复演练、`hey` 压测、真实 2c4g 机器上的 `docker stats` 内存曲线。首次上线请按 §4.6 逐项复验。

### 13.1 构建注意事项（本机实测踩到的问题，上机前先看）

1. **pip / npm 源**：若服务器到 `files.pythonhosted.org` / `registry.npmjs.org` 很慢（本机 wheel 下载实测 ~20KB/s，
   build 会卡十几分钟），用镜像源构建即可；`deploy/docker-compose.prod.yml` 的 build args 会读取 shell 里的
   `PIP_INDEX_URL` / `NPM_REGISTRY`，所以直接：
   ```bash
   PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
   NPM_REGISTRY=https://registry.npmmirror.com \
   docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod build
   ```
   这两个变量无需写进 `.env.prod`。
2. **后端镜像不装 apt 包**：`python:3.12-slim` 已自带 `ca-certificates`（出站 HTTPS 必需）与 `tzdata`，
   容器内探活/等库都用 python 标准库（urllib / psycopg2），不依赖 curl。少一层 apt 让受限网络下的构建稳定很多。
3. **依赖版本已收敛（历史坑，留档）**：早期 `requirements-base.txt` 只写 `sqlalchemy>=2.0.0`（无上界、无 `[asyncio]`），
   实际会装到 SQLAlchemy 2.1，容器内出现两个只在镜像里暴露的问题：
   ① 缺 `greenlet` → 导入 `sqlalchemy.ext.asyncio` 直接 `ImportError`；
   ② 2.1 起 `postgresql://` 默认用 psycopg(v3)，而 `alembic/env.py` 会把 asyncpg URL 转成同步 `postgresql://`，
      依赖里只有 `psycopg2-binary` → 迁移报 `ModuleNotFoundError: No module named 'psycopg'`。
   **现已修复**：`requirements-base.txt` 钉 `sqlalchemy[asyncio]>=2.0,<2.1`（2.0.x + greenlet），
   `backend/alembic/env.py` 把同步 URL 显式转成 `postgresql+psycopg2://`；
   `deploy/Dockerfile.backend` 里的临时兜底 pip 行已删除（镜像需重新构建一次）。
4. **前端 Dockerfile 的 `ARG` 位置**：`NODE_IMAGE` / `NGINX_IMAGE` 必须声明在**第一个 `FROM` 之前**，
   否则报 `base name (${NGINX_IMAGE}) should not be blank`。当前文件已按此写法。
5. 以上构建/联调用的都是一次性容器与随机测试密钥，未写入仓库；测试容器与网络均已在结束后删除。

---

## 附录：与旧方案的对照（避免混用）

| 旧文件（未改动） | 新方案 |
|------------------|--------|
| `deploy/deploy.sh`、`server-setup.sh` | 本文件 §3/§4 + `deploy/docker-compose.prod.yml` |
| `deploy/nginx.conf`（宿主 nginx，`127.0.0.1:8000` upstream） | `deploy/nginx.prod.conf`（容器内 nginx，反代 `backend:8000`） |
| `deploy/.env.production.example` | `deploy/.env.prod.example`（键更全，含容器网络语义） |
| `deploy/visual-buct.service`（systemd 跑 uvicorn） | backend 容器 + `restart: unless-stopped` |
| 根 `DEPLOY.md` | 本文件 |
