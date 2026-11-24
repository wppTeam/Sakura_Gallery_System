# `works` 基表迁移方案（技术债清单 + 分阶段计划）

> 状态：**设计文档，未实施**。当前线上仍是 `photos` 单表承载全部作品（含 AIGC）。
> 本文回答三件事：为什么该迁、怎么迁、什么条件下才值得迁。

最后更新：2026-11-25

---

## 1. 为什么 AGENTS.md 要求 `works` 基表

`AGENTS.md` §3 的目标模型是：

```
works          id, kind, title, uploader_id, license, status, tier,
               visibility, aigc_label, views/likes/downloads, published_at
photo_meta     work_id, exif(脱敏), camera, width/height, captured_at, place, ...
aigc_meta      work_id, model, provider, prompt, prompt_public, params, seed, ...
template_meta  work_id, file_key, format, slides, ratio, fonts[], font_risk, ...
```

动机不是"表看起来更整齐"，而是三件具体的事：

1. **`kind` 判别**：`template`（PPT 模板）上线后，发布、审核、检索、收藏、分享卡全部要复用
   同一套公共逻辑。现在公共链路（`serialize_photo`、`lexical_search`、`collection_photos`、
   `favorites`、`sitemap`、分享卡）全部以 `photos` 为中心，塞第二种内容等于 fork 一遍。
2. **AIGC 字段位置**：`is_aigc / aigc_meta / label_written` 现在长在 `photos` 上（10 个列）。
   对普通摄影作品它们恒为 null/false，表宽和索引都浪费；对 `template` 更是完全无关。
3. **合规与检索的公共性**：`privacy_level`、`status`、`published_at`、`license`
   对所有 kind 语义相同，属于公共列；相机参数、EXIF 白名单只属于 photo。

## 2. 现状盘点（2026-11-25）

### 2.1 `photos` 表实际列（按归属分类）

| 归属 | 列 |
|------|-----|
| 公共 | `id, uploader_id, title, author, description, status, processing_status, views, created_at, updated_at, published_at` |
| 摄影 | `filename, original_path, processed_path, thumb_path, compressed_path, width, height, file_size, mime_type, exif_data, captured_at, category, campus, season` |
| AIGC | `is_aigc, aigc_label, aigc_meta, label_written` |
| 合规 | `privacy_level, redacted_path, redacted_thumb_path` |
| 检索 | `search_tokens, search_vector`（生成列 + trigger） |

- 表规模：生产 64 行，开发 64 行；年增长估计 10³–10⁴ 量级。
- 索引：`ix_photos_status_created`、`ix_photos_captured_at`、`ix_photos_privacy_level`、
  trgm GIN ×3、`ix_photos_search_vector`。
- 触发器：`sakura_photos_sync_search_tokens()` BEFORE INSERT OR UPDATE OF title, description。

### 2.2 外键依赖（迁移时必须一起处理）

有 9 处 `ForeignKey("photos.id")`：

- `collection_photos.photo_id`（CASCADE）
- `favorites.photo_id`（CASCADE）
- `photo_tags.photo_id`（CASCADE）
- `photo_classifications.photo_id`（CASCADE）
- `moderation_reviews.photo_id`（CASCADE）
- `collections.cover_photo_id`（SET NULL）
- `ai_analysis_tasks.photo_id`、`tagging_task_items.photo_id`、`task_photos.photo_id`
- 另有 `photos.uploader_id → users.id`

### 2.3 代码影响面

- `backend/app` 内引用 `Photo` 的模块 **40 个**（endpoints 15、crud 6、services 10、scripts 若干）。
- 公开 API 契约里已经带 `kind` 字段（`PhotoResponse.kind = photo|aigc`），前端按 `kind` 分支，
  所以**迁移对前端是透明的**。
- 检索 SQL（`lexical_search.py`）、sitemap、分享卡、专题、收藏都直接 join `photos`。

## 3. 三个候选方案

### 方案 A：彻底重建（works + 三张 meta，photos 删除）

- 新建 4 张表，PAID 迁移 9 个外键，40 个模块改引用。
- 成本：约 2–3 个整轮；风险最高（外键重建 + 触发器 + 索引 + 全量回归）。
- 只有在「template 内容马上要上线」或作品量级进入 10⁵ 时才值得。

### 方案 B：works 为公共基表，photos 退化为 1:1 扩展表（推荐路径）

- `works.id` 与 `photos.id` **同主键**（1:1），新增 `aigc_meta`、`template_meta`；
  公共列（title/description/status/uploader/privacy_level/计数/时间/AIGC 标识/search_tokens）
  迁到 `works`；photo 专有列留在 `photos`（改名 `photo_meta` 可选）。
- 9 个外键先继续指向 `photos.id`（因为 1:1 且同主键，语义等价）；Phase C 再切到 `works.id`。
- 公共链路逐步改读 `works`（列表/检索/专题/收藏/sitemap/分享卡），photo 详情再 join 扩展表。
- 成本：分 3 步，每步可独立上线与回滚，总计约 2 个整轮。

### 方案 C：不做表拆分，只做"伪 kind"（最小成本，当前状态）

- 新增 `photos.kind`（photo|aigc），AIGC 字段保留；
- 模板功能上线时单独建 `templates` 表，公共链路抽 service 层复用（不做 SQL 级统一）。
- 成本：≈0.5 轮；缺点是检索/收藏/专题无法跨 kind 聚合，长期仍要还债。

**推荐**：按 **C → B** 走。
- 现在（只有 photo/aigc，且 aigc 也是图片）做 C 的最小一步：加 `kind` 列并把 `is_aigc` 派生；
  同时**冻结**把新的 kind 专有字段加到 `photos` 上。
- 等 template 需求进排期（ROADMAP M6）或作品量 > 2 万，启动 B 的 Phase A。

## 4. 方案 B 的分阶段计划（实施时照此执行）

### Phase A：建表 + 双写（1 轮内可完成，可随时回滚）

1. 迁移 `works`（公共列 + `kind` + `legacy_photo_id` 可选）、`photo_meta`（从 photos 复制的摄影列）、
   `aigc_meta`（从 `photos.aigc_meta` 展开）。
2. 回填：`INSERT INTO works SELECT ... FROM photos`（同 id）；`photo_meta` / `aigc_meta` 同步回填。
3. 搜索：把 `search_tokens` 与 trigger 迁到 `works`（先在 works 上建，photos 的 trigger 保留到 Phase C 删）。
4. 双写：新增 `WorksRepository.create/update`，上传/审核/人工终判/隐私标记全部同时写
   `works` 与 `photos`（以 `works` 为准的字段以 works 写入，photos 仅镜像）。
5. 校准脚本 `scripts/verify_works_parity.py`：逐行 diff 公共列，CI 里跑（或 cron 每天跑）。
6. 回滚：直接停用双写、删 4 张新表，线上行为不变（photos 一直是主表）。

### Phase B：读路径切换（1 轮）

1. 公共列表/详情/检索/专题/收藏/sitemap/分享卡/审核队列改为读 `works`（photo 详情再 join `photo_meta`）。
2. `PhotoResponse` 保持字段不变（从 works + photo_meta 拼）。
3. 前端零改动；用现有 205 个测试 + 线上截图回归。
4. 回滚：路由层 switch（`settings.WORKS_READ_ENABLED`）切回 photos，表不用动。

### Phase C：写路径切换 + 外键迁移（1 轮，需停机窗口 < 2 分钟）

1. 上传/审核/终判/隐私/收藏/专题写入全部走 `works`。
2. 9 个外键改指 `works.id`（1:1 同主键，可在同一迁移里 `DROP CONSTRAINT` + `ADD CONSTRAINT`；
   64 行数据、秒级）。
3. `photos` 删公共列（或保留为视图兼容旧脚本），删旧 trigger。
4. 最终校验：pytest + 生产灰度 + 备份/恢复演练。

## 5. 风险与对策

| 风险 | 对策 |
|------|------|
| 双写不一致 | parity 脚本（逐行 diff）+ 每天 cron，不一致立刻告警 |
| 迁移卡住线上 | 每阶段独立迁移，可在 `alembic downgrade -1` 回滚；生产数据量小，备份 180KB |
| 检索 trigger 遗漏 | Phase A 就在 works 上建 trigger，Phase C 才删旧 trigger |
| 外键重建锁表 | 数据量小（64 行），且 Uvicorn 多 worker 下用迁移期间只读维护页（可选） |
| 收藏/专题/审核数据错位 | 同主键 1:1，所有 FK 值不变，无需数据搬运 |
| 测试覆盖不足 | 现有 205 个测试全绿 + 新增 parity/迁移测试 + 生产同一份 pg_dump 先在临时库演练 |

## 6. 触发条件（什么时候做）

满足任意一条即启动：

1. **template（PPT 模板）进入开发排期**（ROADMAP M6）——这是根本动机；
2. 作品量 > 2 万行，`photos` 表宽开始影响列表查询；
3. 需要跨 kind 的检索/收藏/专题聚合（例如"一周热门：照片 + AIGC + 模板混排"）。

在那之前：**不要**往 `photos` 增加新的 kind 专有列；新 kind 的需求先记在本文 §7。

## 7. 待记录的新 kind 需求（避免提前污染 photos）

- 模板：`file_key / format / slides / ratio / fonts[] / font_risk / previews[] / file_size`；
  下载走预签名，预览用 LibreOffice headless 异步渲染。
- 音频/插件等未来形态：暂不设计。

## 8. 本轮已做的低成本准备（不做表迁移）

- 公开 API 已有 `kind` 字段（photo|aigc）与 `is_aigc` 派生，前端按 kind 分支；
- AIGC 字段全部走 `_public_aigc_meta` 白名单，不直接暴露 `aigc_meta`；
- 检索/收藏/专题查询都集中在 `lexical_search.py` / `crud/favorite.py` / `collections.py` 三处，
  未来切 works 时改动点可控（已标注在本文 §2.3）。
