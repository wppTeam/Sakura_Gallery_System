# AI 能力说明：审核链路与 Agent 检索

本文档描述视觉百花 Sakura Gallery 的 AI 能力实现：**图片审核**与 **Agent 驱动的图片检索**。
内容与代码同步维护，涉及文件、契约、配置、成本与降级行为。所有 AI 调用统一走
`backend/app/services/ai_client.py`，任何模块不要自己拼 HTTP 请求。

> 合规红线见 `AGENTS.md` §5：AIGC 显式/隐式标识、隐私白名单、肖像权。本文档只讲实现，
> 不放松那些约束。

---

## 1. 总体结构

```
上传请求 ──> photos.upload ──(BackgroundTasks/Celery)──> moderation_worker.run_moderation
                                                              │
                                                              ├─ moderation_rules（0 成本）
                                                              ├─ qwen3-vl-plus 快筛（1 次视觉调用）
                                                              ├─ deepseek-v4.1-flash 复核（仅 L2/低置信）
                                                              └─ 写 moderation_reviews + ai_usage_events

搜索请求 ──> /api/v1/search?mode=agent ──> agent_search.service.run_agent_search
                                              ├─ planner：deepseek 解析意图（1 次）
                                              ├─ retriever：lexical_search 一条 SQL（必选）+ facets + 可选向量
                                              ├─ explainer：deepseek 生成说明（预算内才调）
                                              └─ 写 agent_search_traces + ai_usage_events
```

- 模型渠道：OpenAI 兼容中转站（`backend/.env` 的 `OPENAI_COMPATIBLE_BASE_URL`），
  视觉 `AI_VISION_MODEL=qwen3-vl-plus`，文本 `AI_TEXT_MODEL=deepseek-v4.1-flash-1017`。
- 重依赖纪律：`torch`/`sentence-transformers`/`pymilvus` 只允许函数内延迟 import；
  默认安装集合（`requirements-base.txt` + `requirements-ai.txt`）不含它们。
  无向量依赖时检索与审核都必须正常降级，不得启动失败。

## 2. 共享原语 `services/ai_client.py`

```python
async def chat_json(db, *, operation, user, system=None, model=None,
                    image_base64=None, image_mime="image/jpeg",
                    max_tokens=1200, temperature=0.1, timeout=None,
                    ref_type=None, ref_id=None, fallback_models=None) -> AIJSONResult
```

- `db` 可为 `None`（此时跳过渠道表查找、预算校验与用量落库，供脚本自检用）。
- 模型选择：显式 `model` > `MODERATION_*_MODEL`/`AGENT_SEARCH_MODEL` 等调用方传入 >
  `AI_VISION_MODEL`（有图）/`AI_TEXT_MODEL`（纯文本）。
- 渠道优先级：数据库 `ai_provider_configs`（启用项）> `.env` 的 `AI_PROVIDER` 配置。
- 预算：`MODERATION_DAILY_CALL_BUDGET` / `AGENT_SEARCH_DAILY_CALL_BUDGET`，`0` 表示不限。
  一轮部署建议先设 `1000` 左右，作为渠道扣费失控的熔断（默认值 0，仅因当前用户拍板「无限流」）。
- 重试：超时、429、5xx 重试 `max_retries+1` 次，指数退避上限 4s；4xx 立即失败。
- JSON 容错：解析失败自动追加「只输出 JSON」再要一次；空内容/截断时 `max_tokens` 翻倍（上限 8192）。
- 用量：每次调用写一条 `ai_usage_events`（operation/provider/model/tokens/cost/latency/success），
  随调用方事务提交，失败不影响主流程。**不记录 prompt、图片与密钥。**
- 图片编码：`encode_image_base64(path, max_edge=1024, quality=85)`，等比缩小、EXIF 方向纠正、
  **绝不裁切**（Pillow 在函数内 import）。

## 3. 图片审核链路

### 3.1 三层处理

| 层 | 实现 | 成本 | 说明 |
|----|------|------|------|
| 规则前置 | `services/moderation_rules.py` | 0 | 文件存在/体积/格式/可解码/最小长边/极端宽高比；EXIF GPS block；隐私字段 warn；AIGC 软件指纹；16×16 dhash 近重复（回看最近 200 张，汉明距离阈值 `MODERATION_DUPLICATE_HAMMING=5`） |
| 快筛 VLM | `moderation._run_prefilter` | qwen3-vl-plus，约 2.1 元/千张 | 长边 1024 JPEG → 结构化 JSON：`has_identifiable_person / likely_aigc / sensitive_content / copyright_risk / watermark / text_in_image / suggested_tier(L0/L1/L2) / confidence / reason` |
| 复核推理 | `moderation._run_escalation` | deepseek-v4.1-flash，仅 L2 或 `confidence<0.6` | 输出 `final_tier / decision(approve/reject/hold) / risk_points / needs_human / reason`；`max_tokens≥3072`，否则思维链吃掉可见输出 |

规则命中 `block`（当前为 EXIF GPS）时**直接** tier=L2、status=completed，不花模型钱。

### 3.2 状态与自动放行

- `ModerationReview.status`：`queued → running → completed|failed`；`tier` 为最终档位。
- 自动放行条件：规则无 block + 合并后 tier=L0 + 快筛置信度 ≥ `MODERATION_AUTO_APPROVE_CONFIDENCE=0.8`
  + `MODERATION_AUTO_APPROVE_L0=True` → `photo.status=approved` 并写 `published_at`。
- 其余情况 photo 保持 `pending` 并进入人工队列；`final_decision` 由人工 `approve|reject|hold` 写入。
- 任何 AI 异常：review.status=failed、tier 至少 L1、photo 保持 pending，**绝不把异常抛回上传请求**。

### 3.3 管理端 API（前缀 `/api/v1/admin/moderation`）

鉴权：`get_current_auditor_user`（admin 或 auditor；普通用户 403、匿名 401）。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/queue?status=&tier=&limit=&offset=` | 每 photo 取最新 review（窗口函数），`limit≤100` |
| GET | `/{photo_id}` | 完整 review（rules/prefilter/escalation/用量） |
| POST | `/{photo_id}/run` | 重跑审核，202，返回 review |
| POST | `/{photo_id}/decision` | body `{decision: approve\|reject\|hold, reason?, final_tier?}`；写 AuditLog + Notification；重复决策 409；hold 保持 pending |
| GET | `/stats?days=` | 各 tier/status 数量、平均延迟、token、成本、当日调用与预算 |

队列契约（前端使用）：

```jsonc
{
  "items": [{
    "id": "...", "photo_id": "...", "status": "completed", "tier": "L2",
    "suggested_tier": "L2", "final_decision": null,
    "rules": {"hits": [{"code": "exif_gps_present", "severity": "block", "detail": "..."}]},
    "prefilter": {"has_identifiable_person": true, "confidence": 0.85, "reason": "..."},
    "escalation": {"decision": "hold", "needs_human": true, "reason": "..."},
    "provider": "openai_compatible", "model_id": "deepseek-v4.1-flash-1017",
    "latency_ms": 7151, "prompt_tokens": 2322, "completion_tokens": 560, "cost_usd": 0.00064,
    "photo": {
      "id": "...", "title": "...", "status": "pending",
      "thumb_url": "/api/v1/photos/{id}/image/thumbnail",
      "uploader": {"username": "jackwpp", "display_name": "王海翔"},
      "width": 2924, "height": 4444
    }
  }],
  "total": 1, "limit": 20, "offset": 0
}
```

- `uploader` 只含 `username`/`display_name`（公开身份），**永不返回学号与真实姓名**。
- 缩略图端点对 `pending` 照片要求鉴权，`<img>` 需自行拼 `?access_token=`（前端 `getPhotoUrl` 已处理）。
- 状态徽章：L0 免审直发 / L1 精选需评审 / L2 强制前审（涉可识别人物、疑似侵权或深伪）。

### 3.4 实测（本地中转站，2026-11-23）

| 样本 | 结果 | 耗时 | 用量 | 成本 |
|------|------|------|------|------|
| clean 图（无 EXIF 问题） | 快筛 L1、confidence 0.85，不触发复核 | 4.04s | 1431 + 123 tok | $0.000374 |
| 带 GPS 图 | 规则 block → L2 completed，0 次模型调用 | <0.1s | 0 | $0 |
| 多人可辨图（seed 演示） | 快筛 L2 人像 → 复核 hold/needs_human | 7.15s（含复核） | 2322 + 560 tok | $0.00064 |

结论：大多数 L0/L1 样本 1 次视觉调用（约 4s）；只对 L2/低置信付第二次推理调用。
1000 张混合样本按 15% 走复核估算约 **2.1 元**（快筛 1.4 元 + 复核 0.6 元，估算值）。

## 4. Agent 驱动检索

### 4.1 流程（`services/agent_search/`）

1. **planner**：`chat_json(operation="agent_search.plan")` 把自然语言解析成
   `{keywords, filters{season,category,campus,...}, semantic_query, needs_clarification,
   clarify_question, expected_facets}`；失败回退为关键词直检（heuristic）。
2. **retriever**：`lexical_search` 一条 SQL 完成过滤+打分+分页（PG：`tsvector ts_rank_cd`
   + `pg_trgm similarity` + `ILIKE` + 结构化过滤；SQLite 降级为 `LIKE`），另加 facet 聚合。
   向量检索可选：仅当 `pymilvus`/`sentence-transformers` 可 import 时执行，否则 step 标
   `skipped:no_vector_dep`。融合按 0.7 词法 / 0.3 向量加权去重。
3. **explainer**：有结果且 `AGENT_SEARCH_EXPLAIN=true` 时生成 1–3 句中文说明；
   `AGENT_SEARCH_LATENCY_BUDGET_MS=3000` 预算内才调用，否则用确定性兜底文案，
   step 标 `skipped:latency_budget`。
4. **trace**：`AGENT_SEARCH_TRACE_ENABLED=true` 时落 `agent_search_traces`
   （query/intent/facets/steps/result_count/clarify/explanation/用量），供排障。
5. 全程 try/except 降级到纯词法 `fast`，**绝不 500**。

### 4.2 API（前缀 `/api/v1/search`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/search?q=&mode=agent\|fast&limit=&offset=&season=&category=&campus=&tag=` | 默认 agent；`AGENT_SEARCH_ENABLED=false` 时强制 fast；limit≤100；兼容旧字段 |
| GET | `/search/facets?q=&season=&campus=&category=&tag=` | 命中集合的 season/category/campus/tag 计数 |
| GET | `/search/suggest?q=&limit=` | 标签/标题/taxonomy 补全（`pg_trgm`，limit≤10） |
| GET | `/search/traces/{trace_id}` | 检索轨迹，仅管理员 |

`/search` 返回要点：`results[]`（photo_id/id/kind/score/tags/classifications/matched_fields/
match_reason/title/author/thumb_url/width/height/aspect_ratio/season/category/campus/is_aigc/
blurhash/created_at/published_at）、`total`、`query_time_ms`、`search_mode`、
`fallback_reason`、`index_version`、`explanation`、`steps[]`、`intent`、`facets`、
`clarify`/`clarify_options`、`trace_id`。

### 4.3 实测（PG 63 张 / approved 57，本地 uvicorn）

- `mode=fast`：端到端 **21–50ms**（query_time_ms 17–49ms），`index_version="pg_trgm+tsvector"`。
- `mode=agent`（"校园里春季开的花"）：HTTP 200，端到端 **2.2s**；
  planner ≈1.96s、lexical ≈96ms、facets ≈29ms、vector skipped、explainer 因预算跳过。
- 未做延迟预算时 agent 约 5.0s（planner 2.0s + explainer 2.85s 串行）；
  如需要 LLM 说明可调大 `AGENT_SEARCH_LATENCY_BUDGET_MS`，代价约 +3s。
- 数据集无「樱花」tag 时返回 0 + 澄清建议（suggest 给出 taxonomy 樱花/樱花苑），属预期行为。

## 5. 数据表

| 表 | 用途 | 关键字段 |
|----|------|----------|
| `moderation_reviews` | 每张照片的审核记录（可多次） | photo_id, status, tier, suggested_tier, rules/prefilter/escalation(JSON), final_decision, final_tier, reviewer_id, provider, model_id, latency_ms, tokens, cost_usd, error |
| `ai_usage_events` | 所有 AI 调用的用量与成本 | operation, provider, model_id, source, ref_type/ref_id, prompt/completion/total_tokens, cost_usd, latency_ms, success, error |
| `agent_search_traces` | Agent 检索轨迹 | trace_id(unique), query, intent/facets/steps(JSON), result_count, clarify, explanation, model_id, latency_ms, total_tokens, cost_usd, error |

迁移：`d8e9f0a1b2c3`（三表 + PG `pg_trgm` + photos.search_tokens/search_vector + GIN 索引）、
`e9f0a1b2c3d4`（`sakura_search_tokens()` 函数 + `photos` BEFORE INSERT/UPDATE 触发器，
自动维护 `search_tokens`，中文按汉字二元组分词）、`f0a1b2c3d4e5`（users 增加
username/display_name 公开身份列）。

## 6. 配置项（`backend/.env` / `core/config.py`）

```ini
# 渠道
AI_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_BASE_URL=http://<relay>/v1
OPENAI_COMPATIBLE_API_KEY=<key>
AI_VISION_MODEL=qwen3-vl-plus
AI_TEXT_MODEL=deepseek-v4.1-flash-1017
AI_TIMEOUT=60
AI_MAX_RETRIES=2

# 审核
MODERATION_ENABLED=true
MODERATION_AUTO_APPROVE_L0=true          # L0 高置信免审
MODERATION_AUTO_APPROVE_CONFIDENCE=0.8
MODERATION_ESCALATION_CONFIDENCE=0.6     # 低于该置信度才复核
MODERATION_DAILY_CALL_BUDGET=0           # 0=不限；建议线上设上限做熔断
MODERATION_DUPLICATE_HAMMING=5

# 检索
AGENT_SEARCH_ENABLED=true
AGENT_SEARCH_MODEL=                      # 空=AI_TEXT_MODEL
AGENT_SEARCH_EXPLAIN=true
AGENT_SEARCH_LATENCY_BUDGET_MS=3000
AGENT_SEARCH_TRACE_ENABLED=true
AGENT_SEARCH_DAILY_CALL_BUDGET=0
```

完整清单见 `backend/.env.example`。旧 Ollama 兼容项保留但不再推荐。

## 7. 降级矩阵

| 故障 | 审核行为 | 检索行为 |
|------|----------|----------|
| 渠道超时/5xx | 重试后失败 → review.failed，photo 保持 pending 进人工 | 降级 fast 词法检索，`fallback_reason` 说明 |
| 429/限流 | 同上，不阻塞上传 | 同上 |
| JSON 解析失败 | 自动重试一次；仍失败按 failed 处理 | planner 回退 heuristic，仍可返回结果 |
| 超预算 | 抛 `AIBudgetExceeded`，按 failed 进人工 | 跳过 planner/explainer，走 fast |
| 无 torch/pymilvus | 无影响 | vector step `skipped:no_vector_dep` |
| 数据库异常 | worker 内捕获，不抛出到请求 | 返回 503/空结果，不 500 泄漏栈 |

## 8. 本地验证

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/python scripts/check_ai.py          # 渠道自检：文本 + 视觉各一次
.venv/bin/python -m pytest -q                 # 全量测试
.venv/bin/uvicorn app.main:app --port 8001    # 真机
curl 'http://127.0.0.1:8001/api/v1/search?q=花&mode=fast&limit=2'
# 审核队列（需 admin/auditor 登录 token）
curl -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8001/api/v1/admin/moderation/queue?limit=5'
```

后台执行：本地默认 `TASK_QUEUE_BACKEND=background`（FastAPI BackgroundTasks）。
2c4g 生产建议由独立 worker 进程消费（`scripts/worker.py` 或 Celery，见
`docs/research/2026-11-23-small-vps-deploy.md`），避免拖慢上传请求所在进程。

## 9. 已知限制与后续

1. **AIGC 法定标识**：本轮只做「疑似 AIGC」证据留存与审核提示；强制声明字段、
   显式角标、下载文件隐式 XMP 标识仍未落库（ROADMAP M2）。
2. 规则层目前不自动通知上传者「GPS 已剥离/请移除 EXIF」，只在审核结果里提示。
3. 公开照片响应暂无 `uploader` 对象（详情页作者用 `author` 字段）；公开身份列已就绪，
   后续在列表/详情序列化中补 `uploader:{username,display_name}`（注意 N+1，建议 join）。
4. 向量检索默认关闭；作品量 >2 万条再评估 pgvector HNSW + embedding API
   （见 `docs/research/2026-11-23-agentic-image-search.md`）。
5. 前端审核队列的批量通过、Agent 意见与人工终判分层已交付（`frontend/src/views/admin/PhotoReview.vue`），
   批量通过暂只对 L0 高置信度样本开放；更细的操作体验仍可继续打磨。

## 10. 2c4g 性能与部署约束

AI 链路不得破坏小机器假设（详细部署见 [`docs/DEPLOY_2C4G.md`](DEPLOY_2C4G.md)）：

- **审核后台执行、不阻塞上传**：上传端点只做一次 `enqueue_moderation()`；AI 调用走异步 httpx，
  规则层的 Pillow 解码 + dHash 用 `asyncio.to_thread` 丢线程池；客户端断开/渠道超时都只降级，不抛回上传。
- **检索有延迟预算**：`AGENT_SEARCH_LATENCY_BUDGET_MS=3000`，评分/解释超预算就跳过 LLM 解释、
  用确定性中文兜底；任何 AI 异常降级 `mode=fast` 纯 SQL 检索，绝不 500。
- **渠道单点熔断**：`MODERATION_DAILY_CALL_BUDGET` / `AGENT_SEARCH_DAILY_CALL_BUDGET`
  按 operation 前缀做日调用闸门（0 = 不限），渠道抖动时先保上传与浏览可用。
- **没有额外常驻服务**：不引入 Redis/Celery/Milvus/torch 作为必装依赖；
  审核 worker 与 uvicorn 同进程（可换独立 worker），检索只依赖 PG `pg_trgm` + `tsvector`。
- **成本可见**：每次调用写 `ai_usage_events`，管理端 `GET /api/v1/admin/moderation/stats`
  可看各 tier 数量、平均延迟、tokens 与 USD 成本。
