# 视觉百花 Sakura Gallery — 开发指南

> 北化学生自建的**开源创作资源共享平台**。前身是内部校园媒体资产管理系统（视觉北化 / Visual BUCT），
> 现重定位为面向学生自助发布的开放平台。
>
> **本文件不含任何凭据。** 服务器地址、SSH 账号、sudo 口令、数据库与对象存储密钥一律不写入仓库。
> 运维凭据存本地未跟踪文件或密码管理器；旧版 AGENTS.md 曾明文记录这些，已在本次重写中移除。

---

## 1. 定位与内容类型

不是图库，是**创作资源共享站**。三类内容共用一套发布、检索、互动与授权机制：

| kind | 说明 | 第一版优先级 |
|------|------|-------------|
| `photo` | 校园摄影作品 | **主** |
| `aigc` | AI 生成图像 | **主** |
| `template` | PPT 等模板素材 | 次（做，但排在后面） |

设计取向：**樱花粉柔色系 + 二次元**。结构综合 Unsplash 的影像优先与真实宽高比瀑布流。
详见 [`design/DIRECTION.md`](design/DIRECTION.md)。

## 2. 架构

```
前端 Vue 3 + Vite + TS + Naive UI + Tailwind 4（构建产物由 nginx 静态托管）
   │
   └── Nginx ── FastAPI (uvicorn --workers 2) ── PostgreSQL
                    │                            │
                    ├── S3 / R2 / MinIO          └── Alembic 迁移
                    │   （媒体走预签名 307 跳转，不经 Python 转发字节）
                    ├── Redis / Celery（可选，默认 BackgroundTasks）
                    ├── Milvus + bge-small-zh（可选，语义检索增强，2c4g 不装）
                    └── AI 渠道（审核 VLM / 打标 / 查询改写 / 生图）
```

生产编排见 [`deploy/docker-compose.prod.yml`](deploy/docker-compose.prod.yml)（postgres + backend + nginx，
无 Redis/Celery/Milvus/MinIO 服务），逐步上机说明见 [`docs/DEPLOY_2C4G.md`](docs/DEPLOY_2C4G.md)。

**公共端重建，admin 后台保留。** `views/admin/*` 与 `TaggingWorkspace.vue` 沿用 Naive UI 不动。

## 3. 数据模型约定

**统一 `works` 基表 + `kind` 判别 + 分类型元数据表。** 不要往 photo 表硬塞其他类型的字段。

```
works         id, kind, title, uploader_id, license, status, tier,
              visibility, aigc_label, views/likes/downloads, published_at
photo_meta    work_id, exif(脱敏), camera, width/height, captured_at,
              place, season, bloom, variants, blurhash, aspect_ratio
aigc_meta     work_id, model, provider, prompt, prompt_public, params,
              seed, source_work_id, label_written
template_meta work_id, file_key, format, slides, ratio, fonts[],
              font_risk, previews[], file_size
```

- 计数用原子 UPDATE，不要读改写
- 分页硬上限 `limit = min(limit, 100)`，默认 20
- 索引：`works(kind, status, published_at)`、`works(uploader_id)`、likes/comments/follows 外键

## 4. 发布与审核：三级 + Agent

**三级发布**（这是"比旧版自由度高"的落地形式）：

| 级 | 含义 | 处理 |
|----|------|------|
| **L0** | 原创摄影、合规 AIGC、字体风险已标注的模板 | **免审即发**，直接进最新流 |
| **L1** | 进首页精选 / 八景专辑 / 搜索加权 | 需人工或社区评审 |
| **L2** | 涉可识别人物、疑似侵权或深伪 | **强制前审** |

用户自助建专辑、自定义标签、装修个人主页**不需要管理员批准**。

**Agent 审核链路（已落地，`backend/app/services/moderation*.py`）**：

1. **规则前置**（不花模型钱，`moderation_rules.py`）：文件类型/体积/可解码/最小边、
   GPS 存在性、AIGC 软件元数据探测、EXIF 编辑器痕迹、16×16 dHash 查重
   （回看最近 200 张，汉明距离阈值 `MODERATION_DUPLICATE_HAMMING`）。
   命中 block 直接判 L2（如 `exif_gps_present`），不再调用模型。
2. **快筛 VLM**：`qwen3-vl-plus`（实测 1.9–4.0s / 约 60–150 输出 tokens），输出结构化 JSON：
   `has_identifiable_person / likely_aigc / sensitive / copyright_risk /
   suggested_tier / reason / confidence`
3. **复核推理**：`deepseek-v4.1-flash-1017`，**只处理 L2 或置信度
   < `MODERATION_ESCALATION_CONFIDENCE` 的样本**。推理型，
   `MODERATION_ESCALATION_MAX_TOKENS=3072`（给小会被思维链吃光而截断）。
4. **自动放行**：L0 且置信度 ≥ `MODERATION_AUTO_APPROVE_CONFIDENCE` 时自动 approved；其余进人工队列。
5. **永不阻塞上传**：任何异常都降级为 `review.status=failed`、photo 保持 pending，绝不让上传 500。
6. **队列持久化（durable queue）**：入队先写 `moderation_reviews(status=queued)` 再尽力立即执行，
   进程重启/崩溃不丢任务；API 进程内嵌 worker（`MODERATION_WORKER_EMBEDDED`）每
   `MODERATION_WORKER_POLL_SECONDS` 秒领取 queued 记录，PG 用 `FOR UPDATE SKIP LOCKED`
   保证多 uvicorn worker 不重复领取；`running` 超过 `MODERATION_WORKER_STALE_SECONDS`
   视为崩溃自动回收重跑。手动推进：`POST /moderation/drain`。
7. **审核即打标（auto_tagging）**：同一次快筛调用顺带输出 `caption / tags / facets`，
   直接落成 `photo_tags` 与 `photo_classifications`（`MODERATION_AUTO_TAGGING` 开关，
   最多 `AUTO_TAGGING_MAX_TAGS` 个标签）。facets 只接受 taxonomy 里 active + selectable
   的节点名（提示词已附分类目录），解析不到安静跳过；打标失败只记 warning，绝不影响
   审核结论。实现见 `backend/app/services/auto_tagging.py`，存量回填用
   `scripts/backfill_auto_tags.py`（`--dry-run/--limit/--force`）。

审核 API（`/api/v1/admin`，admin+auditor）：`GET /moderation/queue`、`GET /moderation/{photo_id}`、
`POST /moderation/{photo_id}/run`、`POST /moderation/{photo_id}/decision`（approve/reject/hold，写 AuditLog + Notification）、
`POST /moderation/batch-decision`（批量终判，逐条独立提交并返回每条 ok/error）、
`GET /moderation/stats`、`POST /moderation/drain`（运维手动消费队列）。所有模型调用统一走 `backend/app/services/ai_client.py` 的 `chat_json()`
（渠道解析、预算闸门、重试、JSON 修复、用量与成本落 `ai_usage_events`）。
架构、配置项与降级矩阵见 [`docs/AI_PLATFORM.md`](docs/AI_PLATFORM.md)。

**策展专题（collections，已落地）**：`collections` + `collection_photos` 两张表
（`backend/app/models/collection.py`），把年度相册 / 八景 / 四季组织成可浏览的专题，
对应本文件「用户自助建专辑不需要管理员批准」的落地形式。公开接口：
`GET /api/v1/collections/public`、`GET /api/v1/collections/{slug}`、
`GET /api/v1/photos/{photo_id}/collections`（详情页「收录于」）。
约定：专题只展示 `status=approved` 的作品；`photo_count` 与实际可见条目一致；
封面**不裁切**（前端 `object-fit: contain`）；专题内顺序用 `position` 显式维护，
不要依赖创建时间。种子数据用 `scripts/seed_collections.py`（幂等，按 slug upsert）。

## 5. 合规约定（不可省）

- **AIGC 标识是法定要求**（《人工智能生成合成内容标识办法》，2025-09-01 施行）：
  ① 上传强制声明 ② 展示显式角标 + 详情说明 ③ **下载文件写入隐式标识（XMP/EXIF）**
  ④ 图生图换脸类额外限制。四件都要做，不是加个 tag。
  **现状（四件已落地）**：
  ① `POST /photos/upload` 的 `aigc_declared` 为必填 Form，缺失 400；声明 true 时记录
    `aigc_meta`（model/provider/prompt/prompt_public/source_work_id/face_swap/consent_confirmed/declared_at）。
  ② `photos.is_aigc` / `aigc_label`（"AI 生成"）/ `aigc_meta` / `label_written` 四列（迁移
    `b1c2d3e4f5a6_add_aigc_labeling.py`）；公开响应出 `is_aigc`/`kind`/`aigc_label`/`aigc_meta`
    （prompt 仅在 `prompt_public=true` 时出），前端投稿/详情/卡片/审核页接线。
  ③ `GET /photos/{id}/download` 对 `is_aigc` 作品在**返回字节**里写 XMP 隐式标识
    （`backend/app/services/aigc_labeling.py`：JPEG APP1 / PNG iTXt，按文件头嗅探真实格式，
    不修改库内原图），响应头 `X-AIGC-Label: AIGC`、`X-AIGC-Implicit-Label: xmp`，并回写
    `label_written=true`；WebP/GIF 暂不支持写入，降级为 `unsupported-format`。
  ④ 图生图（`aigc_source_work_id`）与换脸（`aigc_face_swap`）未传 `consent_confirmed=true` 时上传 400；
    审核策略 `_apply_aigc_declaration_policy` 把声明 AIGC 的作品 tier 抬到 ≥L1，图生图/换脸强制 L2，
    且 AIGC 作品不参与自动放行（`_can_auto_approve` 要求 `not photo.is_aigc`）。
- **个人信息白名单**（已在 `backend/app/api/v1/endpoints/photos.py` 落地）：公开响应**不得**包含
  `uploader_student_id`、真实姓名、完整 `exif_data`。学号永不公开，公开身份用 `username` / `display_name`
  （`users.username` 唯一、`users.display_name`，见 `f0a1b2c3d4e5` 迁移）。
  `serialize_photo`（公开）与 `serialize_photo_admin`（鉴权）已拆分；公开 EXIF 走 `_PUBLIC_EXIF_KEYS`
  白名单（27 项）+ `_sanitize_public_exif`；GPS 在入库时由 `sanitize_exif` 剥离。
  `/photos/my-submissions` 等 owner/admin 端点保留管理端信息。
- **字体授权**：非商用**不豁免**著作权，分发行为本身即需授权。策略是
  **抽清单 + 标风险等级 + 详情页明示，不硬拦不拒收**，把判断交给下载者。
  推荐开源免费商用字体：思源系列、霞鹜系列、站酷系列。
- **肖像权**：涉可识别人物需被摄者同意，走 L2。

### 人像隐私分级（2026-11-24 落地）

- `photos.privacy_level`：`normal` | `sensitive`。审核快筛/复核命中
  `has_identifiable_person`，或旧版 `category == "Portrait"`，即标为 `sensitive`。
- **默认不展示**：公共列表/检索/专题/收藏默认排除 sensitive；前端需显式
  `include_sensitive=true` 且达到 `portrait_visibility` 要求（默认需登录）才纳入，
  且只给**脱敏图**。
- 脱敏图：强高斯模糊（半径≈短边 6%）+ 14× 像素化，只缩不裁，落
  `uploads/redacted/{id}_redacted.jpg`（1600）与 `_redacted_thumb.jpg`（640）。
- 访问控制：匿名访问 sensitive 详情/媒体一律 404；登录用户看脱敏图；原图、
  原图下载仅作者本人与 admin/auditor 可用。
- 实现：`backend/app/services/privacy.py`（标记/生成/判定）、
  `backend/app/services/moderation.py`（审核命中自动标记）、
  `scripts/backfill_portrait_privacy.py`（存量回填）。
- 脱敏失败不阻断审核，但公共端在缺脱敏图时拒绝返回该作品（宁可不展示）。

### 认证、邮箱验证与登录安全（2026-11 落地）

- **登录方式**：学号 / 邮箱 / `username` + 密码；另支持**邮箱验证码免密登录**
  （`POST /auth/login-with-code`，`ALLOW_PASSWORDLESS_EMAIL_LOGIN`）。
- **邮箱验证码**：`email_verification_codes` 表只存 HMAC 哈希（不存明文），
  6 位数字、10 分钟有效、60 秒冷却、每小时 10 次上限、最多 5 次尝试；
  用途 `register / login / reset_password / verify_email`。
  发信通道 `EMAIL_PROVIDER=console|smtp|resend`（实现 `backend/app/services/email.py`），
  生产用 Resend/SMTP；**未配置发信通道时 `REQUIRE_EMAIL_VERIFICATION` 必须为 false**，
  否则注册会被 503 拦住（有意 fail-closed）。
- **注册**：`REQUIRE_EMAIL_VERIFICATION=true` 或显式传 `email_code` 时必须校验邮箱验证码，
  通过后置 `email_verified=true`。
- **找回密码**：`/auth/password/forgot` 对未注册账号返回同样提示（防账号枚举）；
  `/auth/password/reset` 成功后 `token_version++`（旧 token 全部失效）并清空登录锁定。
- **登录安全**：连续失败 `LOGIN_MAX_FAILED_ATTEMPTS` 次锁定 `LOGIN_LOCK_MINUTES` 分钟；
  敏感端点用 slowapi 限流（email-code 5/min、register 5/min、login 10/min），429 带 `Retry-After`。
- **管理端**：`GET /admin/users` 支持 `search/role/is_active/email_verified/sort`；
  `GET /admin/users/stats` 返回用户概览（含 `recent_logins`）；
  `POST /admin/users/{id}/verify-email` 手动标记邮箱已验证（写审计日志）。
- **禁止**：验证码明文存库、响应里回显验证码（`dev_code` 仅 `DEBUG=true` 且
  `EMAIL_ENABLED=false` 时返回，生产不出现）、发信密钥写进仓库或日志。

## 6. 图像与资产管线

**原图只读、保留原始构图，禁止裁切。**
已在 `backend/app/services/image_processing.py` 落地：删除强制 3:2 / 2:3 中心裁切，
改为等比缩放且**不放大**（只缩长边），`process_uploaded_image` 保留旧签名兼容旧调用方。

- 变体长边 `320 / 640 / 1080 / 1600 / 2400`，WebP 主用 + JPEG 兜底
  （`generate_variants()`；只取 ≤ 原图长边，绝不放大）
- `create_thumbnail` 长边 640 JPEG、`create_compressed` 长边 1600 JPEG
- LQIP：20px WebP data-URI 存 `photo.exif_data["_lqip"]`（颜色 `_lqip_color`），
  API 以 `lqip` / `lqip_color` 字段返回，内部键不进公开 EXIF
- `sanitize_exif` 白名单只保留相机/镜头/拍摄时间/曝光/ISO/焦距/朝向
- **上传即生成变体**（`UPLOAD_GENERATE_VARIANTS=true` 默认开）：`process_uploaded_image(variants_dir=...)`
  产出 `variants/{uuid}_{size}.webp|.jpg`，storage 三后端同名落盘/上传；档位宽高存
  `exif_data["_variants"]`（内部键），公开响应出 `variants` 字典：
  `{"640": {"webp": "/api/v1/photos/{id}/image/variant/640?format=webp", "jpeg": "...", "width", "height"}}`
- 媒体端点：`/api/v1/photos/{id}/image/{original|thumbnail|compressed}` 与
  `/image/variant/{size}?format=webp|jpeg`；缺档或老作品无 meta 时按
  thumbnail → compressed → original 兜底（不返回 404，前端不断链）
- 存量作品用 `scripts/backfill_variants.py`（幂等，可 `--dry-run`）补齐文件与 `_variants` 元信息
- 图片不经 Python 流式转发：本地模式返回 `FileResponse`（sendfile/responses 层），
  S3 模式返回 **307 预签名跳转**（`STORAGE_BACKEND=s3`），由对象存储直出带宽
- S3 上传必须显式写对象元数据 `Content-Type`（boto3 不会按扩展名猜）与
  `Cache-Control: public, max-age=31536000, immutable`（`storage._s3_extra_args()`）；
  改存储相关代码后用 `scripts/verify_s3.py` 对着 MinIO 复跑（见 docs/DEPLOY_2C4G.md §6.5）
- 云端对象存储（腾讯 COS / 阿里 OSS）必须设 `S3_ADDRESSING_STYLE=virtual`：默认 `auto`
  走 path-style，COS 会 `PathStyleDomainForbidden`、预签名 URL 403；本机 MinIO 保持 `auto`。
  线上实测（COS）：媒体端点 307 预签名 → 虚拟主机域 → 200；AIGC 下载仍写 XMP。
- 在线预览响应头 `Cache-Control: public, max-age=31536000, immutable` + ETag/Last-Modified
  （`LocalStorageBackend.build_media_response`）；下载语义改 `private, must-revalidate`
- 上传时的 Pillow 变体生成与 S3 写入都在 `run_in_threadpool` 里执行，不占事件循环
- 模板走 S3 直传 + 预签名下载；预览由 LibreOffice headless 异步渲染

## 7. 检索

**已落地（默认零重依赖）**：

- 索引：PG `pg_trgm` + `tsvector('simple')`；中文用应用层**汉字二元组**
  （PG 函数 `sakura_search_tokens()` + trigger 维护 `photos.search_tokens`，
  生成列 `search_vector` 自动重算），不需要 jieba / torch
- `backend/app/services/lexical_search.py`：一条 CTE SQL 完成打分 + 过滤 + 分页
  （`ts_rank_cd` + `similarity` + ILIKE + 结构化加权），facet 一条聚合 SQL；
  测试用 SQLite 时降级 LIKE
- **Agent 搜索**（`backend/app/services/agent_search/`）：planner（1 次 `chat_json`）→ 意图/关键词/facet →
  词法必选 + facet 必选 + 向量可选（0.7/0.3 融合）→ explainer（1 次）；预算
  `AGENT_SEARCH_LATENCY_BUDGET_MS=3000`，超预算跳过 LLM 解释、用确定性中文兜底；
  任何异常降级 fast 模式、不 500；trace 落 `agent_search_traces`
- API：`GET /api/v1/search?q=&mode=agent|fast`、`/search/facets`、`/search/suggest`、
  `/search/traces/{trace_id}`（仅 admin）
- 实测：fast 端到端 21–50ms；agent「校园里春季开的花」2.2s（planner ≈2.0s，解释常被预算跳过）
- **Milvus / pgvector 本轮不做**（2c4g 装不下 Milvus standalone ≥8GB）；规模上来后加 pgvector + `text-embedding-v4` 回填

## 8. 设计系统

```
底 #fff6f9   卡面 #ffffff   墨 #4a2b35   次级 #63474f
主色 #c93a63（按钮/链接，4.9:1）   标题粉 #e8628c（大字，3.2:1）
四季淡底 春#ffd7e4 夏#d4f0e4 秋#ffdfd6 冬#d6e8f7（深墨字 9.5–10.3:1）
季相强调 春#e36089 夏#3b9c80 秋#b5703c 冬#5692c8
```

- 标题字 **站酷庆科黄油体**，正文 Noto Sans SC
- 圆角：卡 20px / 照片 16px / 控件全圆角；柔影 `0 6px 24px rgba(201,58,99,.10)`
- **CJK 行宽用 `em` 不用 `ch`**（`ch` 在中文下约半个汉字宽，会拆断词）
- 整块色域只承载大字，正文一律深墨
- 资产目录：`design/assets/{art,photo,ref}`，插画统一 WebP
- 品牌资产：`design/brand/` —— 顶栏用 `logo-combo-zh.png`（纯中文，h≥20 可读），
  深色底用 `logo-combo-reverse.png`，favicon 16/32/48 用实心简化版、大尺寸用细节版
- **标题字必须自托管**：`design/fonts/zcool/`（92 分片）。CDN 会静默回退；
  且 CSS 的 `url()` 相对 CSS 文件自身解析，路径写错会 404 而无报错

## 9. 本地开发

```bash
# 后端（Python 3.10+）
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # base + ai，不含 torch
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# 可选：requirements-vector.txt（Milvus/bge，默认不装）、requirements-worker.txt（Celery/Redis，默认不用）

# 前端
cd frontend && npm install && npm run dev
# 生产构建验收（dist + /api 代理到 8001，用来验证拆包/按需引入后的真实产物）
cd frontend && npm run build && npm run preview

# 测试（tests/conftest.py 自动切临时 SQLite，不碰本地 PG）
cd backend && pytest -q

# AI 渠道自检（文本 + 视觉各一次，打印模型/延迟/token/成本）
backend/.venv/bin/python scripts/check_ai.py

# 种子演示数据（幂等；读 NAS/本地清单，口令写 backend/.seed-demo-credentials.json，0600 且不入库）
backend/.venv/bin/python scripts/seed_demo.py --limit 63

# 视觉截图（CDP；必须 fromSurface=False，headless 自带 --screenshot 会丢图片层）
backend/.venv/bin/python scripts/shot.py <url> <out.png> --width 1440 --full --wait 3
```

依赖已分层：`requirements-base.txt` / `-ai.txt` / `-vector.txt` / `-worker.txt`，
外部贡献者不会被强制安装 torch。一键起用 `deploy/docker-compose.prod.yml`；
调研背景见 [`docs/research/2026-11-23-small-vps-deploy.md`](docs/research/2026-11-23-small-vps-deploy.md)。

**2c4g 性能约定（改代码时别破坏）**

- 前端：Naive UI 由 `unplugin-vue-components` + `NaiveUiResolver` 按需引入，
  **不要**在 `main.ts` 里 `app.use(naive)` 全量注册；vite 已把 echarts / naive 运行时 /
  vue 运行时拆成独立 vendor chunk（首屏 gzip 由 ~454KB 降到 ~227KB）。
- 后端：任何 Pillow 解码 / 变体生成 / boto3 上传这类阻塞调用都必须
  `await run_in_threadpool(...)` 或 `asyncio.to_thread(...)`，不要在 async 端点里裸跑。
- 数据库：连接池参数走 `DB_POOL_SIZE` / `DB_POOL_MAX_OVERFLOW` / `DB_POOL_RECYCLE`，
  `uvicorn --workers 2` 时真实连接数 = workers ×（pool_size + max_overflow）。
- 媒体：图片走长缓存 + 预签名跳转，不要新增加「Python 读文件再流式返回」的接口。
- 上传：图片处理受 `UPLOAD_PROCESS_CONCURRENCY`（每 worker 默认 1）信号量约束；
  24MP 单张峰值 RSS ≈ +190MB，`processing_result` 返回后由 `malloc_trim` 归还内存。
  不要去掉信号量或改成无界并发，否则 4G 机器上会被 cgroup OOM kill。
- nginx：`/api/v1/photos/public`（30s）、`/api/v1/search`（10s）、`/api/v1/collections`（30s）
  有匿名只读微缓存，响应带 `X-Cache-Status`；**不要**把带 Authorization 的私有接口加进缓存。
- 容量基线（cgroup 2 vCPU 模拟，见 `docs/DEPLOY_2C4G.md` §14）：
  混合读 49 req/s（无缓存）→ 301 req/s（开微缓存）；3 张 24MP 并发上传峰值 472MB。

## 10. AI 渠道（实测结论，不含 key）

**图像生成 — 阿里云百炼直连**

```
POST https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation
Header: X-DashScope-Async: enable
Body: {"model":"qwen-image-3.0-pro",
       "input":{"messages":[{"role":"user","content":[{"text":"..."}]}]},
       "parameters":{"size":"1664*928","n":1,"prompt_extend":true}}
→ output.task_id；轮询 GET /api/v1/tasks/{id}
→ 结果在 output.choices[0].message.content[0].image（字段名是 image，不是 url）
```
尺寸用 `*` 不用 `x`；单张约 53s。
`compatible-mode/v1/images/generations` 是 404，`text2image/image-synthesis` 是 400，别走错。

**NewAPI 代理渠道**：`z-image-turbo`(3.8s) 与 `qwen-image-2.0`(6.4s) 可用；
`*-pro` 与 `wan2.7-*` 全部 **502 且恰好 10.0s**，是代理上游 10 秒超时，不是模型问题。
慢模型一律走百炼直连异步接口。

**审核 VLM**：`qwen3-vl-plus` 两渠道均可用；`deepseek-v4.1-flash` 经实测**确认可读图**。

**审核 / Search-Agent 渠道（当前实现）**

- 渠道默认走 OpenAI 兼容中转（`OPENAI_COMPATIBLE_BASE_URL`，见 `backend/.env.example`，凭据不入库）；
  渠道不可用时由 `ai_client` 走 env fallback，可换本地 magpie 代理
- `AI_VISION_MODEL=qwen3-vl-plus`；`AI_TEXT_MODEL=deepseek-v4.1-flash-1017`
- 统一原语 `backend/app/services/ai_client.py::chat_json()`：渠道解析（DB provider 优先 → env fallback）、
  预算闸门、超时/429/5xx 重试、JSON 解析失败自动重试一次、用量与成本写 `ai_usage_events`
- 成本：`AI_MODEL_PRICES`（USD / 1M tokens，前缀匹配）。实测单张审核：快筛 ≈$0.00037、复核 ≈$0.00067；
  63 张种子图里 7 条 L2 审核合计 ≈$0.0047。官方报价 2.1 元/千张（快筛单层）
- **渠道是单点**：代理曾出现 `*-pro` / `wan2.7-*` 全部 502 且恰好 10.0s（上游 10s 超时）。
  因此审核必须异步、超时降级人工、并用 `MODERATION_DAILY_CALL_BUDGET` / `AGENT_SEARCH_DAILY_CALL_BUDGET`
  做日调用熔断（0 = 不限，当前开发期不限）。

## 11. 禁止事项

- 凭据、服务器 IP、SSH 账号、sudo 口令写入仓库任何文件
- 公开响应暴露学号、真实姓名、完整 EXIF、GPS
- 裁切用户原图构图
- AIGC 作品不带显式与隐式标识就放行
- 把 Milvus / torch 变成必装依赖
- 用 `{**model.__dict__}` 构造公开响应
- 在 async 端点/后台任务里直接执行 Pillow、boto3、同步文件 IO 等阻塞调用
- 在 `main.ts` 里 `app.use(naive)` 全量注册组件（会打爆首屏体积）

## 12. 路线图

分期时间表与验收标准见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。