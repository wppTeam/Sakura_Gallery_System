# 2c4g 单机部署调研（2026-11-23）

> 目标：FastAPI + PostgreSQL + 对象存储 + 可选队列，跑在 **2 vCPU / 4 GB 公网服务器**上，
> nginx 反代、图片纵深处理、AI 审核 worker 共存，不跑 Milvus/MinIO 等重型中间件。
> 标签：**[官方]** 文档；**[本项目实测]** AGENTS.md / 本机实测；**[估算]** 推算未实测。

## 0. 结论先行

| 决策 | 方案 | 关键数字 | 理由 |
|---|---|---|---|
| **采用** | nginx → `uvicorn --workers 2` | 2 vCPU 配 2 worker；单 worker 运行时约 100–130 MB | 每 worker 一份解释器；2 个既吃满双核又能一个重载时另一个顶住 |
| **采用** | PostgreSQL 16 单机 + `shared_buffers=512MB` | PG 总 RSS 约 800 MB–1.1 GB | 4 GB 里给 DB 四分之一是安全比例；再高会挤掉应用 |
| **采用** | 队列 = **DB outbox 表 + 独立 asyncio worker 进程**；复杂时换 `dramatiq + Redis` | outbox worker 约 120–180 MB；Redis 常驻 15–30 MB（`maxmemory 64mb`） | 发布/审核任务必须可重试、可重启恢复；`BackgroundTasks` 进程一重启任务就丢 |
| **不采用** | Celery | prefork 每个子进程重复加载应用，**[估算]** 每 worker 150–250 MB | 依赖多（celery+redis+kombu+billiard），2c4g 上启动 2 个 prefork 子进程就吃掉 400 MB |
| **不采用** | arq | — | 官方 README 明确 **"In maintenance only mode"**（issue #510），不适合新项目 |
| **采用** | 对象存储 Cloudflare R2（S3 兼容，boto3 直连） | 标准存储 **$0.015/GB·月**，**出网流量全免**；免费 10 GB + 100 万 Class A + 1000 万 Class B | 图站 90% 成本是流量，R2 把 egress 免掉是决定性优势 |
| **不采用** | 自建 MinIO 在同一台 2c4g | 常驻 100–300 MB + 磁盘 | 与 PG/应用抢内存；单盘无冗余；还要自己做备份与升级 |
| **不采用** | 阿里云 OSS 作主存储 | 标准型本地冗余 **0.12 元/GB/月**（官方），外网流出另计 | 存储不贵，**外网下行流量贵**；没有 CDN 包时段时图站会失控（流量单价未取到，未实测） |
| **采用** | 图片处理 `pyvips`（libvips） | **0.57 s / 94 MB** vs Pillow **1.8 s / 230 MB** vs ImageMagick **4.4 s / 1500 MB**（社区基准） | 同一台机器上出 5 档变体，内存峰值差 2.4 倍、速度差 3 倍 |
| **采用** | 5 档变体预生成（320/640/1080/1600/2400）+ WebP 主用、JPEG 兜底 + blurhash LQIP | 单作品全档约 **0.6–0.9 MB** | 一次生成、永久命中 CDN/immutable 缓存，比请求时实时转码省 CPU |
| **采用** | 2–4 GB swap + `docker compose` 资源限制 | `deploy.resources.limits` cpus/memory | 2c4g 跑多进程，没有 swap 时一次峰值就 OOM 杀 PG |

**一句话**：2 worker + PG 512 MB + outbox worker + R2 预签名直传 + pyvips 预生成变体；
不在同一台机器上跑 MinIO/Milvus/Celery，把内存留给 PG 和图片处理。

---

## 1. 内存预算表（4 GB 总盘子）

| 组件 | 常驻 RSS | 峰值 | 备注 |
|---|---|---|---|
| OS + sshd + 监控 + docker daemon | 300–400 MB | 500 MB | 精简镜像后可更低 |
| PostgreSQL 16（`shared_buffers=512MB`） | 800 MB | 1.1 GB | 含连接、WAL、工作内存 |
| uvicorn worker × 2（FastAPI + SQLAlchemy + boto3 + PIL） | 2 × 120 MB = 240 MB | 2 × 180 MB | 本项目实测全栈 import 峰值 **61 MB**，运行时按 2× 估 |
| nginx | 15–20 MB | 40 MB | 反代 + gzip + 静态 |
| outbox / 审核 worker × 1 | 120–180 MB | 300 MB | 图像变体 + VLM 调用，pyvips 峰值计入 |
| Redis（可选） | 15–30 MB | 64 MB | `maxmemory 64mb` + `allkeys-lru` |
| **合计** | **≈1.5–1.9 GB** | **≈2.2–2.6 GB** | 余 1.4 GB 给页缓存与突发 |
| swap | 2–4 GB | — | 只防 OOM，不指望性能 |

**PG 参数建议（4 GB 机器）**：

```
shared_buffers = 512MB
effective_cache_size = 1536MB
work_mem = 8MB              # 注意：每个排序/哈希节点各自分配，连接数×节点数是乘数
maintenance_work_mem = 256MB
max_connections = 60        # 应用 2 worker × (5 + 5 overflow) + 管理余量
```

`max_connections` 别开大：每个连接有固定开销，2c4g 上 100 连接会明显挤内存。
应用侧 `create_async_engine(pool_size=5, max_overflow=5, pool_recycle=1800)`，每个 worker 各 5 条常驻。

## 2. 进程模型：worker 数怎么定

- **[官方]** FastAPI 部署文档给出的方式是"Gunicorn/Uvicorn 多 worker 进程"，`uvicorn --workers 2`
  即 master + 2 个子进程，各自独立解释器与连接池（https://fastapi.tiangolo.com/deployment/server-workers/）。
- **2 vCPU → 2 worker**。async 应用单 worker 也能扛 IO 并发，但 2 个才有"一个在跑 CPU 任务时另一个仍能服务"的余量。
- **不要 4 worker**：核数不够时只增加上下文切换与内存，QPS 不涨。
- 防内存泄漏：`--limit-max-requests 10000`（处理 1 万请求后优雅重启子进程）。
- 定时任务不要塞进 web 进程：单开一个 `python -m app.worker` 进程，用 `SELECT ... FOR UPDATE SKIP LOCKED` 领任务。

## 3. 队列选型（发布/AI 审核/图片变体）

| 方案 | 常驻内存 | 持久化 | 重试 | 结论 |
|---|---|---|---|---|
| `BackgroundTasks` | 0（同进程） | ❌ 进程重启即丢 | ❌ | 只用于"发通知邮件"这类丢了也无所谓的副作用；**审核/变体不能用** |
| **DB outbox 表 + 独立 worker（采用）** | 120–180 MB | ✅ PG | ✅ 自写退避 | 零新增依赖；`status/attempts/next_run_at` 三列即可；2c4g 上最稳 |
| **dramatiq + Redis（升级路径）** | Redis 20 MB + worker 100 MB | ✅（Redis 需 AOF） | ✅ 内建 | 需要 dashboard/限流/多队列时再上；依赖比 Celery 轻得多 |
| Celery | 150–250 MB/子进程 | ✅ | ✅ | **不采用**：prefork 重复加载应用，依赖链长，2c4g 不划算 |
| arq | ~80 MB | ✅ | ✅ | **不采用**：上游已进入 maintenance only |

> 判断标准：任务是否"必须在重启后继续"。是 → outbox；否 → `BackgroundTasks`。
> AI 审核（要花 2–5 秒且要计费记账）和图片变体（要写 5 个文件）都属于"是"。

## 4. 对象存储：R2 vs OSS vs MinIO

| 项 | Cloudflare R2 [官方] | 阿里云 OSS 标准型 [官方] | 自建 MinIO |
|---|---|---|---|
| 存储 | **$0.015/GB·月** | **0.12 元/GB/月**（本地冗余） | 磁盘成本 |
| 出网流量 | **$0 / 全免** | 外网下行流量另计（未实测单价） | 带宽即成本 |
| 请求 | Class A **$4.50/百万**、Class B **$0.36/百万** | 按请求数计费 | 0 |
| 免费额度 | **10 GB·月 + 100 万 A + 1000 万 B** | 无 | — |
| 兼容性 | S3 API（boto3 改 endpoint 即可） | S3 兼容 | S3 兼容 |

**成本算例 [估算]**：50 GB 原图+变体、每月 200 万次图片请求、2 TB 下行。

- R2：存储 50×0.015 = **$0.75**；Class B 200 万/2 = 2×$0.36 = $0.72；流量 **$0** → **≈$1.5/月**。
- OSS：存储 50×0.12 = 6 元；下行 2 TB 若按 0.5 元/GB 计 ≈ **1000 元/月**（单价未实测，仅示意量级）；
  上 CDN 流量包才会降到百元级，但要多一套配置与回源。
- MinIO：磁盘 100 GB 一次性，但**备份、升级、单点故障全是自己的事**，且常驻内存从 PG 的预算里抢。

**接入方式（关键：图片不经 Python 转发）**

1. 上传：前端向 `/api/uploads/presign` 要预签名 PUT（15 分钟有效、限制 `content-type` 与 `content-length`），浏览器直传 R2。
2. 回执：前端把 `key` 回传后端，后端入 `works(status=pending)` 并投 outbox。
3. 读取：列表/详情返回预签名 GET（10 分钟）或直接给公开域名 URL；**不要**让 FastAPI 做 `StreamingResponse` 代理图片。
4. 缓存：对象 `Cache-Control: public, max-age=31536000, immutable`，key 里带变体名（不可变才敢长缓存）。
5. nginx 兜底：`client_max_body_size 25M`（现有配置已设）；预签名路径 `proxy_request_buffering off` 不适用（直传不经过 nginx）。

## 5. 图片管线（2 vCPU 上最吃 CPU 的部分）

| 库 | 基准耗时 | 峰值内存 | 结论 |
|---|---|---|---|
| **libvips / pyvips** | **0.57 s** | **94 MB** | **采用**（冷启动需系统 `libvips`，Debian/Ubuntu 有包） |
| pyvips（Python 绑定开销） | ~0.6 s | ~100 MB | 同上 |
| Pillow-SIMD 5.3 | 0.9–1.0 s | ~230 MB | 备选（wheel 自带，装起来最省事） |
| Pillow（stock） | 1.8 s | ~230 MB | 已装，留作兜底/EXIF 读取 |
| ImageMagick 7.1.1 | 4.4 s | ~1500 MB | **不采用**（子进程 + 内存黑洞） |

*基准任务：解码 JPEG → crop → resize 50% → sharpen → JPEG 编码；5000×5000 TIFF 场景 pyvips 峰值 **49 MB** vs Pillow 230 MB（社区/官方 wiki 汇总）。*

**变体规格与体积 [估算]**：原图 24 MP JPEG ≈ 5–8 MB。

| 变体 | 宽/长边 | WebP 体积 | 用途 |
|---|---|---|---|
| 320 | 320 | 20–30 KB | 列表缩略/网格 |
| 640 | 640 | 50–70 KB | 卡片 |
| 1080 | 1080 | 110–150 KB | 详情页 |
| 1600 | 1600 | 180–260 KB | 大图/视网膜 |
| 2400 | 2400 | 300–450 KB | 下载预览 |
| 合计 | — | **≈0.65–0.95 MB/作品** | 加原图 ≈6–9 MB/作品 |

5000 件作品 ≈ **35–45 GB**，落在 R2 免费额度之上但月费 <$1。

**我建议的取舍**：`1080` 与 `2400` 两个档按需生成（首次访问时生成并写回对象存储），
`320/640/1600` 上传后立即生成 —— 2 vCPU 上一次性 5 档会同时占满 CPU 数秒，而 99% 的浏览只看前两档。

**LQIP**：blurhash 或 20 px 内联 base64（约 300–600 B），在列表接口直接返回，避免加载跳动。

## 6. docker compose 资源限制示例

```yaml
services:
  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --limit-max-requests 10000
    deploy:
      resources:
        limits:   { cpus: "1.5", memory: 700M }
        reservations: { memory: 300M }
  worker:
    build: ./backend
    command: python -m app.worker
    deploy:
      resources:
        limits:   { cpus: "0.8", memory: 400M }
  postgres:
    image: postgres:16
    command: ["postgres","-c","shared_buffers=512MB","-c","work_mem=8MB","-c","max_connections=60"]
    deploy:
      resources:
        limits: { memory: 1300M }
  nginx:
    image: nginx:alpine
    deploy:
      resources:
        limits: { memory: 80M }
```

- **[官方]** `deploy.resources.limits` 在 `docker compose` v2 非 swarm 模式下生效（https://docs.docker.com/compose/compose-file/deploy/），
  本机 `docker 29.10.0` 已具备（实测存在，未实测该字段在目标机的行为）。
- cpus 总和 1.5+0.8+0.5 ≈ 2.8 超卖是故意留的：CPU 是可压缩资源，memory 才是硬限制。
- 所有容器 `restart: unless-stopped`；日志 `logging: { driver: json-file, options: { max-size: 10m, max-file: "3" } }`。

## 7. 上线清单（按顺序执行）

1. 建 2–4 GB swap（`fallocate -l 4G /swapfile && mkswap && swapon`），写进 `/etc/fstab`。
2. 系统 `apt install libvips42 nginx postgresql-16`；PG 调参写入 `postgresql.conf` 后重启。
3. `docker compose up -d --build`；`curl -f localhost:8000/healthz` 验证。
4. nginx 反代 8000，开 `gzip on`、`proxy_read_timeout 60s`、`keepalive 32`（现有 `deploy/nginx.conf` 已是这个结构）。
5. 配 R2 bucket + CORS（允许站点域名 PUT/GET）+ 生命周期规则（未引用 7 天删除临时上传）。
6. 备份：`pg_dump` 每日到 R2（`pg_dump | gzip | aws s3 cp -`），保留 14 天；R2 开对象版本。
7. 监控：`/healthz` 5 分钟探活 + 磁盘 >80% 告警 + `docker stats` 每日快照；日志轮转见上。
8. 压测：`hey -n 2000 -c 50` 打列表/详情接口，确认 2 worker 下 P95 <300 ms、CPU 不持续 >90%。

## 8. 风险

- **R1｜内存抖动**：2c4g 上 PG + 2 worker + 图片处理同时峰值可到 2.6 GB，若并发上传多则会 OOM。对策：swap + compose memory limit + 图片任务串行（worker 并发 1–2）。
- **R2｜libvips 安装**：pyvips 依赖系统 libvips（LGPL），目标机若用极小镜像需手动装；装不上就退回 Pillow-SIMD（慢 2–3 倍、内存 2.4 倍，但能跑）。
- **R3｜单机单点**：一台机器挂全站挂。对策：R2 存图、PG 每日备份到 R2、DNS 可切；不要在同一台机器做"高可用"幻觉。
- **R4｜出网带宽**：小带宽机器（常见 3–5 Mbps）直出大图会很慢。对策：所有图片走 R2/公开域名，不经过源站；源站只出 JSON。

## 9. 来源

- FastAPI server workers（多进程部署）：https://fastapi.tiangolo.com/deployment/server-workers/
- Docker Compose `deploy.resources`：https://docs.docker.com/compose/compose-file/deploy/
- Cloudflare R2 定价与免费额度：https://developers.cloudflare.com/r2/pricing/
- 阿里云 OSS 计费概览（标准型 0.12 元/GB/月）：https://help.aliyun.com/zh/oss/product-overview/billing-overview
- libvips 速度与内存基准：https://github.com/libvips/libvips/wiki/Speed-and-memory-use
- pyvips 绑定：https://github.com/libvips/pyvips
- dramatiq（轻量 Redis 队列）：https://github.com/Bogdanp/dramatiq/
- arq 维护状态：https://github.com/python-arq/arq
- Celery worker 模型：https://docs.celeryq.dev/en/stable/userguide/workers.html
