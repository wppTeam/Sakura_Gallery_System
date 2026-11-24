# 视觉北化 API 手册

> 最后更新：2026-11-24
> 基础路径：`https://tkjs.buct.edu.cn/api/v1`（本地开发：`http://127.0.0.1:8000/api/v1`）

---

## 📋 目录

- [认证](#认证)
- [照片管理](#照片管理)
- [策展专题](#策展专题)
- [收藏](#收藏)
- [搜索](#搜索)
- [标签管理](#标签管理)
- [分类系统](#分类系统)
- [统计](#统计)
- [用户管理](#用户管理)

---

## 🔐 认证

### 登录

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "identifier": "username_or_email",
  "password": "your_password"
}
```

**响应**：
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "username",
    "role": "admin"
  }
}
```

### 注册

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "username": "newuser",
  "email": "user@example.com",
  "password": "password123"
}
```

### 邮箱验证码

```http
POST /api/v1/auth/email-code
Content-Type: application/json

{ "email": "user@example.com", "purpose": "register" }
# purpose: register | login | reset_password | verify_email（verify_email 需登录）
```

**响应**：`{ ok, message, expires_in, cooldown_seconds, delivered, dev_code }`
（`dev_code` 只在本地 `DEBUG=true` 且 `EMAIL_ENABLED=false` 时返回，生产不出现）。

### 邮箱验证码免密登录

```http
POST /api/v1/auth/login-with-code
Content-Type: application/json

{ "email": "user@example.com", "code": "123456" }
```

响应与 `/auth/login` 相同（`access_token` + `user`）。

### 注册（可选邮箱验证码）

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "student_id": "20260001",
  "username": "newuser",
  "email": "user@example.com",
  "email_code": "123456",
  "password": "Sakura2026!"
}
```

`REQUIRE_EMAIL_VERIFICATION=true` 时必须带 `email_code`，通过后 `email_verified=true`。

### 忘记 / 重置密码

```http
POST /api/v1/auth/password/forgot   # { "identifier": "邮箱/学号/用户名" }
POST /api/v1/auth/password/reset    # { "identifier": "...", "code": "123456", "new_password": "..." }
```

`forgot` 对未注册账号也返回同样提示（防枚举）；`reset` 成功后旧 token 全部失效。

### 登录后验证邮箱

```http
POST /api/v1/auth/email/send-verification   # 需 Bearer token
POST /api/v1/auth/email/verify              # { "code": "123456" }，返回 { detail, email_verified }
```

限流：email-code 5/min、register 5/min、login 10/min、forgot/reset 5/min（429 带 `Retry-After`）。

---

## 📷 照照管理

### 获取公开照片列表

```http
GET /api/v1/photos/public
```

**查询参数**：

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `page` | int | 页码 | `1` |
| `page_size` | int | 每页数量 | `30` |
| `season` | string | 季节筛选 | `秋季` |
| `period` | string | 拍摄时段：晨/昼/暮/夜（dawn/noon/dusk/night） | `黄昏` |
| `campus` | string | 校区筛选 | `昌平校区` |
| `building` | string | 楼宇筛选 | `图书馆` |
| `gallery_series` | string | 专题筛选 | `昌平校区摄影大赛` |
| `gallery_year` | string | 年份筛选 | `2025年第八届获奖作品` |
| `award_level` | string | 奖项筛选 | `特等奖` |
| `photo_type` | string | 照片类型 | `风光类` |
| `tag` | string | 标签筛选 | `银杏` |
| `search` | string | 关键词搜索 | `秋天` |
| `sort_by` | string | 排序字段 | `created_at` / `views` / `published_at` |

**响应**：
```json
{
  "items": [
    {
      "id": "photo-uuid",
      "filename": "银杏大道.jpg",
      "width": 4000,
      "height": 3000,
      "created_at": "2025-01-15T10:30:00",
      "classifications": {
        "season": {"node_name": "秋季"},
        "campus": {"node_name": "昌平校区"},
        "landmark": {"node_name": "图书馆"}
      }
    }
  ],
  "total": 542,
  "page": 1,
  "page_size": 30
}
```

### 获取单张照片详情

```http
GET /api/v1/photos/public/{photo_id}
```

### 获取照片缩略图

```http
GET /api/v1/photos/{photo_id}/image/thumbnail
```

**响应**：图片二进制数据（image/jpeg）

### 获取照片原图

```http
GET /api/v1/photos/{photo_id}/image/original
```

### 获取压缩图 / 响应式变体

```http
GET /api/v1/photos/{photo_id}/image/compressed
GET /api/v1/photos/{photo_id}/image/variant/{size}?format=webp|jpeg
```

`size` ∈ `320 / 640 / 1080 / 1600 / 2400`（只生成 ≤ 原图长边的档位，绝不放大）。
公开详情响应的 `variants` 字段直接给出各档 URL（含 width/height），前端据此生成
`<picture>` + `srcset`。缺档或老作品无变体时，该端点按
`thumbnail → compressed → original` 兜底返回 200，不会 404。

响应头：`Cache-Control: public, max-age=31536000, immutable`；
本地模式 `FileResponse`，S3 模式 307 预签名跳转，均不经 Python 转发字节。

### 上传照片

```http
POST /api/v1/photos/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data
```

**表单字段**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | file | ✅ | JPEG / PNG / WebP / GIF，≤ `MAX_UPLOAD_SIZE` |
| `title` | string | ❌ | 标题 |
| `description` | string | ❌ | 描述 |
| `aigc_declared` | bool | ✅ | **是否包含 AI 生成合成内容**（法定强制声明）。缺失返回 400 |
| `aigc_model` / `aigc_provider` | string | ❌ | 生成模型 / 渠道 |
| `aigc_prompt` | string | ❌ | 提示词（≤2000 字） |
| `aigc_prompt_public` | bool | ❌ | 是否公开提示词（默认 false） |
| `aigc_source_work_id` | uuid | ❌ | 图生图来源作品 |
| `aigc_face_swap` | bool | ❌ | 换脸 / 人脸替换类 |
| `consent_confirmed` | bool | ❌ | 图生图 / 换脸必须为 true，否则 400 |
| `enable_ai` | bool | ❌ | 是否触发 AI 打标（默认由运行时配置决定） |

上传成功后服务端：生成 320/640/1080/1600/2400 五档 WebP+JPEG 变体与 LQIP、
剥离 GPS、写 `photos.is_aigc/aigc_label/aigc_meta`、异步入审核队列（不阻塞响应）。
响应体 `PhotoUploadResponse` 含 `id`、`status`、`is_aigc`、`aigc_label`。

---

## 📚 策展专题

把同一主题 / 同一年度相册的作品组织成「专题」，公共端首页横滑卡与专题详情页消费。

### 樱色光谱（公开）

```http
GET /api/v1/collections/spectrum
```

返回固定的五个色卡（樱粉/金/绿/蓝/墨），每项含 `key`/`name`/`hex`/`description`/
`slug`（暂无作品的色卡为 `null`）/`photo_count`/`cover`。每个 `slug` 同时是普通专题，
可直接用 `GET /api/v1/collections/{slug}` 打开完整列表。作品由上传时采样缩略图主色自动归类
（`backend/app/services/spectrum.py`），不是人工挑选。

### 今日之光（公开）

```http
GET /api/v1/collections/light?per_period=4
```

按访问时刻把「光的一日」四个专题整理成固定结构，供首页 hero 与时段卡消费：

```json
{
  "periods": [
    {"key": "dawn", "slug": "light-dawn", "label": "晨", "time_range": "05:00–09:00",
     "title": "晨 · 还没醒的校园", "subtitle": "六点到九点，光比人先到",
     "intro": "…", "photo_count": 0, "photos": []},
    {"key": "noon", "slug": "light-noon", "label": "昼", "time_range": "09:00–15:00", "…": "…"},
    {"key": "dusk", "slug": "light-dusk", "label": "暮", "time_range": "15:00–19:00", "…": "…"},
    {"key": "night", "slug": "light-night", "label": "夜", "time_range": "19:00–05:00", "…": "…"}
  ],
  "total": 3
}
```

- 顺序固定为晨/昼/暮/夜；`photos` 是公开序列化的 `PhotoResponse`（`privacy_level=sensitive` 与未审核作品不出现），最多 `per_period` 张（1–8，默认 4）。
- 空时段 `photos=[]`、`photo_count=0`，`title` 回退为「{label} · 整理中」；`total` 是有作品的时段数。
- 时段划分单源在 `backend/app/services/light_of_day.py::period_for_hour`（05–09 晨、09–15 昼、15–19 暮、其余夜），策展种子脚本与前端选择逻辑都对齐它。
- 该接口在 nginx 有 30s 匿名只读微缓存（`/api/v1/collections` 前缀）。

### 作者手账（用户自建专辑，需登录）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/collections` | 新建专辑：`{title, subtitle?, description?}` → 201 `CollectionDetail`（`kind=user`、`status=published`） |
| GET | `/api/v1/collections/mine` | 我的专辑（含草稿），按最近更新排序 |
| GET | `/api/v1/collections/{id}/manage` | 编辑页读取（含未审核作品），仅作者或 admin |
| PATCH | `/api/v1/collections/{id}` | 改标题/副标题/引言/封面/发布状态（`published`/`draft`） |
| PUT | `/api/v1/collections/{id}/photos` | `{photo_ids:[...]}` 整体替换并保序（≤100，仅本人 approved 作品） |
| DELETE | `/api/v1/collections/{id}` | 删除专辑（同时删除条目，不删作品） |

权限：未登录 401；非作者 403（admin 可管理任意专辑）。封面只能取专辑内作品；
空专辑不进入公开列表。

### 专题列表（公开）

```http
GET /api/v1/collections/public?limit=12&offset=0
```

只返回 `status=published` 且 `visibility=public` 的专题，按 `sort_order` 升序。
`photo_count` 只统计 `approved` 作品；`cover` 是专题内排序最前的公开作品（完整
`PhotoResponse`，含 `variants`/`lqip`，无作品时为 `null`）。`limit` 上限 50。

### 专题详情（公开）

```http
GET /api/v1/collections/{slug}
```

返回叙事元信息 + `photos[]`（按 `position`，只含 approved）+ `prev_slug` / `next_slug`
（按 `sort_order` 相邻）。未发布或不存在返回 404「专题不存在或未发布」。

### 作品所属专题

```http
GET /api/v1/photos/{photo_id}/collections
```

返回 `{ items: [{ slug, title, kind }] }`，作品详情页「收录于」chips 用；
未收录返回空数组。

现有演示数据：12 个专题（「2024 · 七乐章」32 张、七个乐章单章 3–5 张、
「校园四季」8、「2023 · 年度精选」5、「2023 · 月度随笔」11、「2023 · 手机摄影」4），
由 `scripts/seed_collections.py` 幂等生成。

---

## 🖼 以图搜图（公开）

上传一张图，返回站内视觉相似作品（`results[]` 与文本检索同构，前端复用结果卡片）。
探针图**只在内存里**算 dhash + 光谱色卡，不落盘、不写库、不调用 AI 模型。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/search/visual` | `multipart/form-data`：`file`（JPEG / PNG / WebP，≤8MB，≤4000 万像素）+ 可选 `limit`（1–30，默认 12）。返回 `{results[], total, query_time_ms, mode:"visual", query:{filename,width,height,aspect_ratio,palette,palette_name,palette_hex}}`；非图片/过小 → 400，超过 8MB 或像素上限 → 413；与上传图近重复（汉明 ≤3）的作品不返回；按 IP 限流 10 次/分钟 |

## 👁 视觉相似（公开）

上传时记录 dhash 感知哈希 + 光谱色卡；按「构图 / 色调 / 标签 / 季节 / 校区」加权排序。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/photos/{photo_id}/similar?limit=8` | 返回 `{items:[PhotoResponse & {similarity,reasons}], total}`；候选只含已发布且非敏感作品；目标不存在/未公开 → 404 |

## 🚩 举报 / 侵权投诉

公开端（匿名可提交，登录后自动记录投诉人）：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/reports` | 提交投诉。body：`target_type`(photo/collection)、`target_id`、`reason_code`(copyright/portrait/illegal/misinformation/spam/other)、`reason_text`(≥5 字)、`contact`(可选)。201 → `{ok,id,status,message}`；404 对象不存在；422 字段非法；429 同 IP 24 小时内重复投诉 |

管理端（admin / auditor）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/reports?status=&target_type=&limit=&offset=` | 列表，待处理优先；返回 `items`（含 target_title/target_url/reason_label/contact/reporter）、`total` |
| GET | `/api/v1/admin/reports/stats?days=7` | 概览：total/pending/accepted/rejected/by_reason/last_7_days |
| POST | `/api/v1/admin/reports/{id}/resolve` | body `{decision: accept\|reject, note?, action: takedown\|none}`；accept+takedown 下架作品并通知上传者；已处理 → 409 |

## ❤️ 收藏

作品详情页的收藏按钮与「我的收藏」页消费这组接口（均需登录）。

### 切换收藏

```http
POST /api/v1/photos/{photo_id}/favorite
```

已收藏则取消、未收藏则收藏，返回 `{ favorited: bool, favorite_count: int }`。

### 收藏状态

```http
GET /api/v1/photos/{photo_id}/favorite
```

返回当前用户对该作品的状态：`{ favorited: bool, favorite_count: int }`。

### 我的收藏（分页）

```http
GET /api/v1/photos/favorites/my?skip=0&limit=20
```

```json
{
  "items": [ "…与 /photos/public 同构的公开安全 PhotoResponse…" ],
  "photo_ids": ["…"],
  "total": 2,
  "returned": 2
}
```

- `items` 已是公开安全序列化（可直接渲染卡片），含 `variants` / `lqip` / `thumb_path`；
- 只含 `approved` 作品（作品下架/退回后不再出现在收藏页），`total` 与 `items` 同口径；
- `photo_ids` 保留给旧前端兼容；`limit` 上限 100；
- 未登录返回 401。

---

## 🔍 搜索

### Agent 图片检索

```http
GET /api/v1/search?q={query}&mode=agent|fast
```

**查询参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `q` | string | 自然语言查询，如「校园里春季开的花」 |
| `mode` | string | `agent`（默认，意图分解 + 解释）或 `fast`（纯词法，21–50ms） |
| `limit` / `offset` | int | 分页，limit ≤ 100 |
| `season` / `category` / `campus` / `tag` | string | 结构化过滤 |
| `period` | string | 拍摄时段 `dawn` / `noon` / `dusk` / `night`（也接受 晨/昼/暮/夜、黄昏、清晨等口语） |

**响应**（节选）：

```json
{
  "results": [
    {
      "photo_id": "b25aee5d-...",
      "kind": "aigc",
      "score": 0.83,
      "title": "樱花小径 · AI 生成演示",
      "thumb_url": "/api/v1/photos/b25aee5d-.../image/thumbnail",
      "width": 1664, "height": 928, "aspect_ratio": 1.793,
      "is_aigc": true, "aigc_label": "AI 生成",
      "matched_fields": ["title"]
    }
  ],
  "total": 12,
  "query_time_ms": 2216,
  "search_mode": "agent",
  "intent": { "query": "校园里春季开的花", "keywords": ["花", "春季"], "filters": {...} },
  "steps": [ { "tool": "lexical", "result_count": 12, "latency_ms": 96, "status": "ok" } ],
  "clarify": false,
  "explanation": "找到 12 个结果……",
  "trace_id": "..."
}
```

- 实现：PG `pg_trgm` + `tsvector('simple')` + 汉字二元组（无需 jieba/torch）；
  planner 与 explainer 各 1 次 `chat_json`，解释超 `AGENT_SEARCH_LATENCY_BUDGET_MS` 时跳过并回退确定性文案。
- 任何模型异常都降级为 `mode=fast` 语义，不返回 5xx。

**辅助端点**：

```http
GET /api/v1/search/facets?q={query}        # 季节/类别/校区/标签计数
GET /api/v1/search/suggest?q={query}       # 搜索建议（taxonomy 名称）
GET /api/v1/search/traces/{trace_id}       # 仅 admin：单次 Agent 检索的完整 trace
```

**审核 API**（admin + auditor）见 [`docs/AI_PLATFORM.md`](./AI_PLATFORM.md)：
`/api/v1/admin/moderation/{queue,stats,{photo_id}}` 与 `POST .../run`、`POST .../decision`。

批量终判：`POST /api/v1/admin/moderation/batch-decision`，body `{"photo_ids": [..≤50], "decision": "approve|reject|hold", "reason?": "...", "final_tier?": "L0|L1|L2"}`，返回 `{ok, processed, succeeded, failed, items:[{photo_id, ok, decision, error}]}`；逐条独立提交，单张失败（不存在 / 已有终判 / 异常）不影响其它照片。

## 🏷️ 标签管理

### 获取所有标签

```http
GET /api/v1/tags
```

**响应**：
```json
[
  {
    "id": 1,
    "name": "银杏",
    "category": "object",
    "usage_count": 45
  }
]
```

### 创建标签

```http
POST /api/v1/tags
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "新标签",
  "category": "scene"
}
```

### 标签类别

| 类别 | 说明 | 示例 |
|------|------|------|
| `scene` | 场景 | 校园、图书馆 |
| `object` | 物体 | 银杏、红砖 |
| `mood` | 情绪 | 温馨、宁静 |
| `style` | 风格 | 航拍、夜景 |
| `color` | 色彩 | 金色、蓝色 |

---

## 📂 分类系统

### 获取分类体系

```http
GET /api/v1/taxonomy/public
```

### 获取分类引导

```http
GET /api/v1/taxonomy/public/guide
```

**响应**：
```json
{
  "primary": ["gallery_series", "campus", "photo_type"],
  "dependencies": {
    "gallery_series": {
      "昌平校区摄影大赛": ["season", "award_level"]
    }
  }
}
```

---

## 📊 统计

### 获取统计概览

```http
GET /api/v1/stats/overview
Authorization: Bearer {token}
```

**响应**：
```json
{
  "total_photos": 542,
  "total_tags": 1156,
  "total_users": 15,
  "photos_this_month": 23
}
```

---

## 👤 用户管理

### 获取当前用户

```http
GET /api/v1/auth/me
Authorization: Bearer {token}
```

### 修改密码

```http
POST /api/v1/auth/change-password
Authorization: Bearer {token}
Content-Type: application/json

{
  "old_password": "old_pass",
  "new_password": "new_pass"
}
```

---

## 🛠️ 管理员接口

### 用户管理

```http
GET    /api/v1/admin/users          # 用户列表：search / role / is_active / email_verified /
                                    # sort=created_at_desc|created_at_asc|last_login_desc|
                                    #      last_login_asc|login_count_desc|student_id_asc
GET    /api/v1/admin/users/stats    # 概览：total/active/inactive/admins/auditors/pending_approval/
                                    # email_unverified/new_last_7_days/recent_logins[8]
POST   /api/v1/admin/users/{id}/verify-email  # 管理员手动标记邮箱已验证（写审计日志）
PUT    /api/v1/admin/users/{id}     # 更新用户信息（含 email_verified）
DELETE /api/v1/admin/users/{id}     # 删除用户
```

### AI 成本与用量

```http
GET /api/v1/admin/ai/usage?days=7&recent_limit=20
```

聚合 `ai_usage_events`（只含调用元信息，不含 prompt/图片）。返回：

```json
{
  "days": 7,
  "since": "2026-11-17T12:00:00",
  "totals": {"calls": 42, "success": 40, "failed": 2, "prompt_tokens": 52000,
             "completion_tokens": 4100, "total_tokens": 56100,
             "cost_usd": 0.0421, "avg_latency_ms": 3210.5},
  "by_day": [{"key": "2026-11-24", "calls": 12, "total_tokens": 15200, "cost_usd": 0.011}],
  "by_operation": [{"key": "moderation.prefilter", "calls": 20, "total_tokens": 30000, "cost_usd": 0.028}],
  "by_model": [{"key": "qwen3-vl-plus", "calls": 20, "total_tokens": 30000, "cost_usd": 0.028}],
  "recent": [{"id": "…", "operation": "agent_search.plan", "model_id": "deepseek-v4.1-flash-1017",
              "ref_type": "search", "total_tokens": 1000, "cost_usd": 0.0002,
              "latency_ms": 1960, "success": true, "error": null, "created_at": "…"}]
}
```

仅 admin 可访问（auditor 403、匿名 401）；`days` ∈ [1, 90]、`recent_limit` ∈ [1, 100]。

### 系统设置

```http
GET    /api/v1/admin/settings       # 获取设置
PUT    /api/v1/admin/settings       # 更新设置
```

### AI Provider 管理

```http
GET    /api/v1/admin/ai-providers   # 获取 AI 供应商列表
POST   /api/v1/admin/ai-providers   # 添加 AI 供应商
PUT    /api/v1/admin/ai-providers/{id}  # 更新
DELETE /api/v1/admin/ai-providers/{id}  # 删除
```

### 打标任务

```http
GET    /api/v1/tagging-tasks        # 获取任务列表
POST   /api/v1/tagging-tasks        # 创建打标任务
GET    /api/v1/tagging-tasks/{id}   # 获取任务详情
```

---

## 📝 错误码

| 状态码 | 说明 |
|--------|------|
| `200` | 成功 |
| `201` | 创建成功 |
| `400` | 请求参数错误 |
| `401` | 未授权（需要登录） |
| `403` | 禁止访问（权限不足） |
| `404` | 资源不存在 |
| `422` | 数据验证失败 |
| `500` | 服务器内部错误 |

---

## 🔧 开发说明

### 环境

- **后端**：FastAPI + Uvicorn（端口 8000）
- **数据库**：PostgreSQL 18
- **向量数据库**：Milvus（端口 19530）
- **对象存储**：MinIO（端口 9000）

### 本地测试

```bash
# 测试搜索 API
curl -G "http://127.0.0.1:8000/api/v1/search" \
  --data-urlencode "q=秋天" \
  --data-urlencode "limit=5"

# 测试公开照片
curl "http://127.0.0.1:8000/api/v1/photos/public?page_size=5"
```

### 相关文档

- [项目 README](../README.md)
- [运维指南](./AGENTS.md)
- [部署流程](./docs/SOP.md)
- [向量搜索计划](../visual-buct-vector-search-plan-v2.md)

---

*本文档由 Hermes Agent 自动生成*


### 人像隐私分级（2026-11-24）

- `GET /api/v1/photos/public` 新增 `include_sensitive`（默认 false）；
  sensitive 作品默认不返回，显式开启且满足 `portrait_visibility` 时只给脱敏图。
- 作品对象新增 `privacy_level` / `is_redacted`。
- sensitive：匿名详情/媒体 404；登录非作者脱敏；原图与下载仅作者/审核员。
