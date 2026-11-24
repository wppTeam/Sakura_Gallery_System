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
AI 成本观测（admin）：`GET /api/v1/admin/ai/usage?days=7` 聚合 `ai_usage_events`
（总量/按日/按 operation/按 model 的 calls·tokens·USD + 最近事件），用于核对单价与失败率；
实现 `backend/app/api/v1/endpoints/admin_ai.py`。

架构、配置项与降级矩阵见 [`docs/AI_PLATFORM.md`](docs/AI_PLATFORM.md)。

**策展专题（collections，已落地）**：`collections` + `collection_photos` 两张表
（`backend/app/models/collection.py`）。`kind` 区分三类策展：

- `editorial`（编辑策展）：年度相册、校园四季、手机摄影等，用 `scripts/seed_collections.py` 种。
- `editorial`（自动策展）：**光的一日**按 `captured_at` 归入 晨/昼/暮/夜、**樱色光谱**
  按作品主色归入 樱粉/金/绿/蓝/墨（`app/services/spectrum.py`，采样缩略图 64×64 的 HSV）。
  两者都由 `scripts/seed_curation.py` 幂等生成，不需要人工选图。
  **成员自动归档（审核链路内）**：`backend/app/services/curation.py` —— 作品过审
  （人工终判 `_apply_decision` 与快筛自动放行两条路径）、被驳回或被举报下架时，
  自动加入/移出「光的一日」「樱色光谱」的对应专题；只动 `light-*` / `spectrum-*`
  两个前缀，不碰人工 editorial 与作者手账，成员追加到末尾不重排既有顺序。
  存量校正用 `scripts/sync_curation_membership.py [--dry-run]`（幂等，可反复跑，
  容器内 `docker exec -w /app -e PYTHONPATH=/app` 执行）；专题文案/顺序以
  `seed_curation.py` 为准，标题与引言单源在 `curation.py`（seed 直接 import）。
- `user`（作者手账）：用户自建专辑，**不需要管理员批准**（落 AGENTS.md §4 的「自助」原则）。
  CRUD 接口：`POST /api/v1/collections`、`GET /mine`、`GET /{id}/manage`、`PATCH /{id}`、
  `PUT /{id}/photos`（整体替换并保序）、`DELETE /{id}`；只能收录自己的 approved 作品，
  一次 ≤100 件、每人 ≤50 个专辑。
- **AI 策展助手**（`POST /api/v1/collections/assistant`，需登录）：作者写一句话主题
  （≤200 字），模型只从**本人 approved 且非 sensitive** 的作品里挑 3–24 张、按观展节奏
  排序，返回标题/副标题/简介/每张的挑选理由（`picks[].reason`），**只出提案、不落库**，
  前端在编辑页确认后才调 `POST /collections` 创建。候选上限 60 张（按发布时间倒序），
  目录行格式 `P01 | 标题 | 季节·时段·校区 | 标签 | 画面描述`，模型用编号引用；不认识的
  编号/重复编号会被丢弃。实现 `backend/app/services/curation_assistant.py`，
  每次调用约 3.7k prompt + 0.5–1.6k completion tokens（≈$0.001）、6–10 秒；
  推理型模型必须给足 `max_tokens`（当前 8192，给小了可见输出会被思维链吃光）。
  限流 5 次/分钟/IP；AI 不可用返回 503、没有可策展作品返回 400。

### AI 创作台（站内 AI 生图）

作者写一句提示词 → 后台调百炼直连异步接口（`qwen-image-3.0-pro`，单张约 50–60s）
生成草稿图 → 作者预览满意后，走**普通上传接口**（`aigc_declared=true` + prompt/model）
发布为待审 AIGC 作品。审核、显式角标、隐式标识、变体全部复用既有链路，
创作台本身**不直接创建作品**。

- 接口（前缀 `/api/v1`，均需登录）：
  `GET /aigc/config`（开关、尺寸档位、每日额度）、`POST /aigc/generations`
  （202 + 后台任务，3 次/分钟）、`GET /aigc/generations`（我的记录）、
  `GET /aigc/generations/{id}`（前端轮询状态）、`GET /aigc/generations/{id}/image`
  （草稿图，仅本人/管理员）、`DELETE /aigc/generations/{id}`。
- 草稿图只落本地 `uploads/generated/`，不进作品表、不对外公开；
- 每日额度 `AIGC_IMAGE_DAILY_LIMIT`（默认 5，失败不计），开关
  `AIGC_GENERATION_ENABLED`，未配 `DASHSCOPE_API_KEY` 时接口返回 503；
- 用量记 `ai_usage_events(operation="aigc.generate")`，按张成本用
  `AIGC_IMAGE_PRICE_USD` 估算（默认 0，按实际渠道价填写）；
- 生成图大小上限 `AIGC_IMAGE_MAX_BYTES`（默认 20MB），尺寸档位
  `AIGC_IMAGE_SIZES`（方图 1328*1328 / 横图 1664*928 / 竖图 928*1664，百炼用 `*` 分隔）；
- 服务重启导致卡在 queued/running 的任务，由状态接口按超时自动标 failed；
- 迁移 `a7b8c9d0e1f2`（表 `aigc_generations`）。

公开接口：`GET /api/v1/collections/public`（只返回至少 1 张公开作品的专题）、
`GET /api/v1/collections/{slug}`（含 `owner{username,display_name}`）、
`GET /api/v1/collections/spectrum`（五色卡 + 封面）、
`GET /api/v1/collections/light?per_period=4`（今日之光：固定返回 晨/昼/暮/夜 四个时段，
每段最多 `per_period` 张公开作品，空时段 `photos=[]` 且标题回退「{label} · 整理中」，
供首页 hero 按访问时刻选段；时段定义单源在 `app/services/light_of_day.py`，
`scripts/seed_curation.py` 也用同一套 `period_for_hour()` 分桶）、
`GET /api/v1/photos/{photo_id}/collections`（详情页「收录于」）。
约定：专题只展示 `status=approved` 且非 `sensitive` 的作品；`photo_count` 与实际可见条目一致；
封面**不裁切**（前端 `object-fit: contain`）；专题内顺序用 `position` 显式维护；
用户专辑的公开身份只用 `username/display_name`，绝不带学号/真实姓名。

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
    `label_written=true`；JPEG / PNG / **WebP（RIFF `XMP ` chunk）** 均支持写入，GIF 暂不支持（降级 `unsupported-format`）。
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

### 内容举报与「通知—删除」（2026-11-25 落地）

公开站点必须有侵权投诉渠道（《信息网络传播权保护条例》/《民法典》第 1195 条），实现：

- **匿名可投诉**：`POST /api/v1/reports`，body `{target_type: photo|collection, target_id, reason_code, reason_text(≥5 字), contact?}`；
  reason_code ∈ `copyright / portrait / illegal / misinformation / spam / other`；限流 10 次/小时/IP；
  同一 IP 对同一对象 24h 内重复提交返回 429。
- **管理端受理**：`GET /api/v1/admin/reports`（待处理优先）、`GET /api/v1/admin/reports/stats`、
  `POST /api/v1/admin/reports/{id}/resolve`（`decision: accept|reject`，accept 可选 `action: takedown`）。
  accept + takedown 对作品置 `photos.status = rejected` 并站内通知上传者；对专题置 `status = draft`。
  所有受理写 `audit_logs`（`report.accept` / `report.reject`）。已处理过再提交 → 409。
- **前端**：作品详情页「举报 / 侵权投诉」入口（服务条款 `/terms`、隐私政策 `/privacy` 页脚可达）；
  管理后台 `/admin/reports` 举报处理页。
- 约定：举报记录只存投诉文本与联系方式，不存证据文件；公开响应不返回投诉人联系方式（仅管理端可见）。

### 审核复核（申诉）通道（2026-11-25 落地）

被驳回的作品，作者有**一次**申诉机会，形成「驳回 → 申诉 → 人工复核 → 回到审核队列 / 维持驳回」闭环：

- **作者提交**：`POST /api/v1/photos/{photo_id}/appeal`，body `{reason: 10–2000 字}`；
  仅作者本人（403）、仅 `status=rejected` 的作品（400）、同一作品只允许一条 `pending`
  申请（PG 部分唯一索引 + 代码 409）、限流 5 次/小时/IP。
  `GET /api/v1/photos/{photo_id}/appeal` 返回最近一条申请（没有则 `null`），作者本人或 admin/auditor 可读。
- **管理端受理**：`GET /api/v1/admin/appeals`（待处理优先）、`GET /api/v1/admin/appeals/stats`、
  `POST /api/v1/admin/appeals/{id}/resolve`（`decision: accept|reject`，`note` 会展示给作者）。
  `accept` → 作品 `status = pending` 并 `enqueue_moderation(force=True)` 重新进审核队列，
  作者收 `photo_appeal_accepted` 通知；`reject` → 保持 rejected，作者收 `photo_appeal_rejected`。
  受理写 `audit_logs`（`appeal.accept` / `appeal.reject`）；重复受理 409。
- 实现：`backend/app/models/appeal.py`、`backend/app/api/v1/endpoints/appeals.py`（管理端）、
  `backend/app/api/v1/endpoints/photos.py`（作者端点）、迁移 `b8c9d0e1f2a3`；
  前端：详情页作者视角的驳回横幅 + 申诉弹窗，后台 `/admin/appeals` 复核处理页。

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
- **多轮追问（history 上下文）**：`GET /api/v1/search` 支持重复参数
  `history=上一轮提问`（最多 3 条、每条 ≤200 字，按时间顺序）。planner 的 user 消息
  会带上「对话上下文」，模型只在当前问题是省略式追问（如「那黄昏呢」「还有春天的吗」）时
  借上文补全 keywords/filters，新话题忽略上文；模型不可用时规则兜底
  `heuristic_intent(query, history)` 仅对「那/还有/再/换成…」或句末「呢/吗」的追问合并
  上一轮关键词，并识别时段口语（「黄昏」→ `period=dusk`）。前端在连续搜索时携带，
  并对用户显示「结合上文 · 清除」；上下文不落库（trace 里只记 `history` 条数）
- **按光找图（`period` 过滤）**：`/search` 与 `/photos/public` 都接受
  `period=dawn|noon|dusk|night`（也接受 晨/昼/暮/夜、清晨、黄昏、傍晚、夜晚 等口语）；
  小时区间与「光的一日」策展共用 `backend/app/services/light_of_day.py` 的
  `PERIOD_HOUR_RANGES`（夜跨零点按 `>=19 或 <5`），SQL 用 PG `EXTRACT(HOUR …)`、
  SQLite `strftime('%H')`；planner 的 filters 白名单含 `period`，用户说「黄昏的校园」
  会自动落成 `period=dusk`，无需前端额外传参
- **视觉相似**（`backend/app/services/visual_similarity.py`）：上传时对缩略图算 16×16 dhash
  写入 `exif_data["_dhash"]`，与光谱色卡 / 构图比例 / 标签 / 季节 / 校区加权（缺 dhash 的老图按可用
  信号归一化权重）；候选集只含已发布且非敏感作品，Python 内打分（`MAX_CANDIDATES=800`），
  近重复（汉明 ≤3）不推荐；`GET /api/v1/photos/{id}/similar?limit=` 返回 `similarity + reasons`
  供前端「视觉相似」区展示。存量回填：`scripts/backfill_visual_signatures.py`
- **以图搜图**（`POST /api/v1/search/visual`，multipart `file`）：上传图只在内存算签名
  （`backend/app/services/visual_probe.py`：dhash + 光谱色卡，不落盘、不写库、无 AI 成本），
  复用视觉相似打分对公开作品排序，返回与文本检索同构的 `results[]`（score / match_reason /
  thumb_url / author…），前端直接复用结果卡片；与上传图近重复（汉明 ≤3）的作品不返回；
  限 8MB / 4000 万像素 / JPEG·PNG·WebP，公开端点按 IP 10 次/分钟限流（slowapi）
- **详情页导航（上一张 / 下一张）**：`GET /api/v1/photos/{id}/neighbors?context=latest|collection:<slug>`
  返回当前作品所处的序列（`latest` 按 `coalesce(published_at, created_at)` 倒序；`collection:<slug>`
  按 `collection_photos.position`），以及 `position/total`、前后邻居 id 与一个含当前作品的紧凑窗口
  （`items[]` 只带 id/标题/宽高/AIGC 角标/LQIP 色/thumbnail URL，避免胶片条传完整 EXIF）。候选只含已发布
  且非人像敏感作品；专题不存在或作品不在专题内时自动退回最新流；目标不可访问时 404。实现
  `backend/app/services/photo_navigation.py`（latest 用 keyset 四条小 SQL，不把全站 id 拉进内存）。
  前端：`frontend/src/layouts/PublicLayout.vue` 对 `route.name === 'PhotoDetail'` 使用固定 `key`，
  翻页时复用同一个组件实例（`PhotoDetailView.load(true)` 保留当前帧与邻居序列，等新详情到达后原地替换），
  因此灯箱在 ←/→ 切换作品时不关闭、不重挂载；其它路由仍按 `route.path` 重挂载以保留页面转场。
  频道页（collection）进入作品时补 `?from=collection:<slug>`，详情页翻页沿用同一序列。
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
- **可访问性契约（改公共端组件别破坏）**：
  · 键盘焦点 `:focus-visible` 3px 轮廓（`styles/base.css`），Skip link 指向 `#main`；
  · 触屏（`@media (pointer: coarse)`）可点元素 ≥44×44，桌面 fine pointer 可保留紧凑尺寸；
  · 灯箱/抽屉/对话框：Esc 关闭、Tab 焦点陷阱、打开时聚焦容器、关闭后焦点归还触发元素；
  · 图片 alt 用「标题 · 作者」（装饰性缩略图才允许空 alt），表单 label 与控件 `for/id` 关联；
  · `prefers-reduced-motion: reduce` 下停花瓣与位移动画，图片渐显 420ms，骨架与卡片同比例防 CLS。

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

# 视觉截图（CDP；截图必须 fromSurface=True，否则淡入 / Ken Burns 这类合成层会缺层）
# headless 自带 --screenshot 也会丢图片层；动画 hero 可先 emulate prefers-reduced-motion 再截
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
- nginx：`/api/v1/photos/public` 列表（30s）、`/api/v1/photos/public/{id}` 详情（30s）、
  `/api/v1/search`（10s）、`/api/v1/collections`（30s）有匿名只读微缓存，响应带
  `X-Cache-Status`；带 `Authorization` 的请求 `BYPASS`，**不要**把私有鉴权接口加进缓存。
  新增缓存点必须用 `^~` 前缀（`^~ /api/` 会跳过正则 location）。
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
- 在图片 sitemap 里放会过期的预签名 URL（用稳定的媒体端点）
- 裁切用户原图构图
- AIGC 作品不带显式与隐式标识就放行
- 把 Milvus / torch 变成必装依赖
- 用 `{**model.__dict__}` 构造公开响应
- 生产备份只留在与站点同一块磁盘上（必须异地对象存储；恢复演练见 `docs/DEPLOY_2C4G.md` §17）
- 巡检/告警静默失败（监控必须能发出异常与恢复通知）
- 在 async 端点/后台任务里直接执行 Pillow、boto3、同步文件 IO 等阻塞调用
- 在 `main.ts` 里 `app.use(naive)` 全量注册组件（会打爆首屏体积）

## 12. 路线图

分期时间表与验收标准见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。