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
前端 Vue 3 + Vite + TS + Naive UI + Tailwind 4
   │
   └── Nginx ── FastAPI (uvicorn) ── PostgreSQL
                    │                  │
                    ├── MinIO (S3)     └── Alembic 迁移
                    ├── Redis / Celery（可选，默认 BackgroundTasks）
                    ├── Milvus + bge-small-zh（可选，语义检索增强）
                    └── AI 渠道（审核 VLM / 打标 / 查询改写 / 生图）
```

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

**Agent 审核链路（三层，模型与延迟为实测值）**：

1. **规则前置**（不花模型钱）：GPS 存在性、感知哈希查重、AIGC 元数据探测、
   pptx `fontTable` 字体清单抽取、文件类型与体积校验
2. **快筛 VLM**：`qwen3-vl-plus` —— 实测 **1.9s / 57 输出 tokens**，
   输出结构化 JSON：`has_identifiable_person / likely_aigc / sensitive /
   copyright_risk / suggested_tier / reason`
3. **复核推理**：`deepseek-v4.1-flash` —— 实测 **4.7s / 590 输出 tokens**（推理型，
   `max_tokens` 必须给够，否则可见输出被思维链吃光而截断）。
   **只处理快筛判为 L2 或置信度低的样本**，不要全量走它。

后台常驻 worker 消费审核队列；人工队列 UI 展示 agent 意见与依据，人做终判。
初期由项目所有者自审，agent 与规则负责过滤与提速。

## 5. 合规约定（不可省）

- **AIGC 标识是法定要求**（《人工智能生成合成内容标识办法》，2025-09-01 施行）：
  ① 上传强制声明 ② 展示显式角标 + 详情说明 ③ **下载文件写入隐式标识（XMP/EXIF）**
  ④ 图生图换脸类额外限制。四件都要做，不是加个 tag。
- **个人信息白名单**：公开响应**不得**包含 `uploader_student_id`、`uploader_name`、
  完整 `exif_data`。学号永不公开，公开身份用 `username` / `display_name`。
  GPS 在入库时剥离。
  ⚠️ 现状 `backend/app/api/v1/endpoints/photos.py:150-163` 的 `serialize_photo`
  用 `{**photo.__dict__}` 并显式塞入学号与真实姓名，且被未鉴权的 `/photos/public` 使用——**必修**。
- **字体授权**：非商用**不豁免**著作权，分发行为本身即需授权。策略是
  **抽清单 + 标风险等级 + 详情页明示，不硬拦不拒收**，把判断交给下载者。
  推荐开源免费商用字体：思源系列、霞鹜系列、站酷系列。
- **肖像权**：涉可识别人物需被摄者同意，走 L2。

## 6. 图像与资产管线

**原图只读、保留原始构图，禁止裁切。**
⚠️ 现状 `backend/app/services/image_processing.py:44-62` 强制中心裁切成 3:2 / 2:3，
16:9 全景损失 44% 画面——**必修**。

- 变体长边 `320 / 640 / 1080 / 1600 / 2400`，WebP 主用 + JPEG 兜底
- LQIP（blurhash 或 20px 内联）消除加载跳动
- 图片不经 Python 流式转发：nginx 反代 MinIO 或预签名 URL
- `Cache-Control: public, max-age=31536000, immutable` + ETag
- 模板走 S3 直传 + 预签名下载；预览由 LibreOffice headless 异步渲染

## 7. 检索

- **默认**：PostgreSQL `pg_trgm` + `tsvector` 跨 kind 全文（去掉 Milvus 硬依赖）
- **可选增强**：Milvus + `bge-small-zh-v1.5`（现有 `vector_search_service.py`）
- AIGC 提示词、模板文本一并入索引
- **Agent 搜索**：意图分解 → 多 facet 检索 → 结果解释 → 必要时澄清追问。
  复用现有 `search_interpreter.py` 的查询改写，扩到跨 kind。

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
# 后端
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev

# 测试
cd backend && pytest
```

依赖将分层为 `requirements-base.txt` / `-ai.txt` / `-vector.txt`，
避免外部贡献者被迫安装 torch。目标是 `docker compose up` 一键起。

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

## 11. 禁止事项

- 凭据、服务器 IP、SSH 账号、sudo 口令写入仓库任何文件
- 公开响应暴露学号、真实姓名、完整 EXIF、GPS
- 裁切用户原图构图
- AIGC 作品不带显式与隐式标识就放行
- 把 Milvus / torch 变成必装依赖
- 用 `{**model.__dict__}` 构造公开响应

## 12. 路线图

分期时间表与验收标准见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。