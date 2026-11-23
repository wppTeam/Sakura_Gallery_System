# 调研汇总与建议（2026-11-23）

> 三条主线：AI 审核链路、Agent 化检索、2c4g 单机部署 + 对象存储。
> 每份详版见同目录：`2026-11-23-ai-review.md`、`2026-11-23-agentic-image-search.md`、`2026-11-23-small-vps-deploy.md`。
> 标签：**[官方]** 文档/定价页；**[实测]** 本项目实测（AGENTS.md / 本机）；**[估算]** 推算未实测。

## 0. 一页结论

| # | 主线 | 最终推荐 | 关键数字 | 结论 |
|---|---|---|---|---|
| 1 | AI 审核 | 规则前置 → `qwen3-vl-plus` 单层快筛 → `deepseek-v4.1-flash` 只跑 L2 → 人工终判；云审核只做涉政兜底 | 快筛 **2.1 元/千张**、1.9 s；复核 4.7 s；腾讯云审核 **2.5 元/千张** | **采用**（自建为主、云审核兜底） |
| 2 | 检索 | PG `pg_trgm` + 应用层 jieba + `tsvector('simple')`；Agent 层手写 4 工具循环；>2 万条再上 `pgvector` + 外部 embedding | embedding **0.5 元/百万 token**；Milvus 官方最低 **8 GB RAM** | **采用**（PG 优先、向量后置） |
| 3 | 部署 | nginx → 2×uvicorn worker + PG 512 MB + outbox worker + R2 预签名直传 + pyvips 预生成变体 | 常驻 **1.5–1.9 GB**、峰值 2.2–2.6 GB；R2 出网**免费**；libvips **0.57 s/94 MB** | **采用**（不跑 MinIO/Milvus/Celery） |

**月度增量成本 [估算]**：AI 审核约 3 元（1000 张量级）+ 检索约 5–10 元 + R2 约 $1.5 + 服务器（既有）。
真正的大头不是 AI，而是**图片出网流量**——所以对象存储选 R2、图片不经过 FastAPI 是省钱关键。

---

## 1. AI 审核链路

**采用**

| 层 | 方案 | 成本 | 延迟 | 依据 |
|---|---|---|---|---|
| 规则 | Pillow + pyexiftool + imagehash（pHash 64 bit，汉明 ≤6 判重） | 0 元 | 5–15 ms/张 | [实测] 全栈 import 峰值 61 MB |
| 快筛 | `qwen3-vl-plus`，固定 JSON 6 字段，20 s 超时、失败降级人工 | **2.1 元/千张**（输入 1 元/M、输出 10 元/M token） | **1.9 s / 57 token** [实测] | 能直接给 `suggested_tier`/`copyright_risk` |
| 复核 | `deepseek-v4.1-flash`，只接 L2/低置信度，`max_tokens ≥2048` | ≈0.005 元/次 | **4.7 s / 590 token** [实测] | 推理型，`max_tokens` 给少会被思维链吃光 |
| 终判 | 人工队列 + `review_tasks` 审计表（模型/令牌/成本/延迟/人工覆盖） | 人力 | — | 合规要求可追溯 |
| 兜底 | 腾讯云图片内容安全（`sensitive` 命中时才调） | **2.5 元/千张**（25 元/万张；套餐低至 1 元/千张） | 同步接口，未实测 | 涉政/暴恐是自建 VLM 的盲区 |

**不采用**

- 云内容审核做主链路：阿里国际站通用 0.6 USD/千次（≈4.3 元/千张）、大小模型融合 1.2 USD/千次（≈8.6 元/千张），
  比自建贵且只给通用标签，省不掉第二次判断。
- AIGC 鉴别 API 全量：腾讯 **0.1 元/张 = 100 元/千张**，是普通审核的 40 倍；合规靠"强制声明 + 元数据核验 + 隐式标识回写"。
- 开源 NSFW 模型（NudeNet/nsfw_model/CLIP 零样本）：多一套阈值与回归，无涉政能力。

**合规硬约束**（《人工智能生成合成内容标识办法》，**2025-09-01 已施行**）：
上传强制声明、图片显著角标、下载文件也须含显式标识、文件元数据写隐式标识（属性/服务提供者/内容编号）、
平台侧三态提示（生成合成 / 可能 / 疑似）、无显式标识版本日志留存 ≥6 个月、禁止用户删除标识。

## 2. Agent 化检索

**采用**

- **不动向量库**：PG 内 `pg_trgm`（容错）+ jieba 分词后 `tsvector('simple')`（相关性）；权重 `ts_rank 0.6 + similarity 0.25 + 热度 0.15`。
- **Agent = 手写 tool-calling loop**：4 个工具（`search_works` / `get_work` / `similar_works` / `list_facets`）、
  上限 4 轮、总预算 8 s、结果截断 40 条/4 KB、LLM 超时 2.5 s 即降级纯 SQL。
- **护栏写在代码里**：可见性过滤在 SQL 层、facet 值只从 `list_facets` 取、结果解释只用检索字段，防越权与幻觉。
- **第二阶段（作品 >2 万条）**：`pgvector` HNSW（512 维；10 万条约 270 MB 索引）+ `text-embedding-v4`
  （**0.5 元/百万 token**，1 万条回填约 1 元），RRF 融合，不替换现有链路。

**不采用**

- Milvus standalone：官方最低 **RAM 8 GB、4 核**，2c4g 硬性不可行。
- Qdrant / 外部向量 DB：第二套服务与元数据双写，运维面翻倍。
- `sentence-transformers`/torch 本地 embedding：AGENTS.md §11 禁止，且 2 vCPU 推理比一次 API 慢。
- LangChain / LangGraph / LlamaIndex：为 4 个工具引入整套抽象不划算（传递依赖无法在受限网络下量化，[估算] 20+）。

## 3. 2c4g 部署与对象存储

**采用**

| 项 | 参数 | 数字 |
|---|---|---|
| 进程 | nginx → `uvicorn --workers 2 --limit-max-requests 10000` | 2 vCPU 配 2 worker；不要 4 |
| PG | `shared_buffers=512MB`、`work_mem=8MB`、`max_connections=60` | PG RSS 800 MB–1.1 GB |
| 队列 | DB outbox 表 + 独立 asyncio worker（`FOR UPDATE SKIP LOCKED`）；复杂后再上 `dramatiq+Redis` | worker 120–180 MB |
| 对象存储 | Cloudflare R2（S3 API + boto3） | **$0.015/GB·月**，**egress 免费**，10 GB 免费额度 |
| 图片 | pyvips 5 档变体（320/640/1080/1600/2400）+ WebP + blurhash LQIP | **0.57 s / 94 MB** vs Pillow 1.8 s / 230 MB |
| 直传 | 预签名 PUT/GET，图片不经过 Python；`Cache-Control: immutable` | 省带宽、省内存 |

**不采用**

- Celery（prefork 每子进程重复加载应用，[估算] 150–250 MB/个）；arq（官方 "maintenance only mode"）。
- 同机自建 MinIO（抢内存、单点、自己运维）；OSS 作主存（存储 0.12 元/GB/月不贵，但外网流出流量不可控，未实测单价）。
- 图片实时转码 / FastAPI 流式转发图片。

**内存盘子 [估算]**：常驻 1.5–1.9 GB，峰值 2.2–2.6 GB / 4 GB；必须配 2–4 GB swap 防 OOM。

---

## 4. 分阶段落地

| 阶段 | 内容 | 预估 |
|---|---|---|
| P0（第 1–2 周） | 规则层 + 快筛 VLM + `review_tasks` 审计 + 成本护栏（日预算/配额/熔断）；AIGC 三态文案与 XMP 回写 | 3–4 天 |
| P0（并行） | PG 全文 + trigram + jieba；两个检索工具 + 手写 loop + 降级 | 3 天 |
| P1 | 复核模型只接 L2；结果解释与低置信度追问；outbox worker 接管变体生成 | 2–3 天 |
| P1 | R2 预签名直传/下载 + pyvips 管线 + 5 档变体 + nginx 反代 | 2 天 |
| P2（触发式） | `pgvector` + 外部 embedding 回填 + RRF；腾讯云审核兜底接入 | 各 0.5–1 天 |
| P2（触发式） | 队列换 dramatiq + Redis（当需要重试编排/多队列/看板） | 1 天 |

## 5. 风险最高的两点

1. **AI 渠道单点 + 降级缺失**（最高）。
   审核与检索都依赖同一个外部渠道；AGENTS.md 已记录 NewAPI 代理 `*-pro` 全部 502 且恰好 10.0 s（上游超时）。
   一旦主渠道抖动，若发布链路同步等待模型，就会出现"全站不能发图"。**必须**：审核异步化 + 超时降级人工 +
   日预算熔断 + 至少记住一个可用备用渠道（百炼直连为已验证通路）。
2. **2c4g 上的内存/扩展天花板**（次高）。
   PG + 2 worker + 图片处理同时峰值可到 2.6 GB，一次并发上传就可能 OOM 杀 PG；且目标机**没有 pgvector**，
   第二阶段可能装不上扩展，向量检索会直接落空。对策：swap、compose memory limit、图片任务并发限 1–2、
   向量层默认关闭（装不上就停在阶段一，不影响功能）。

其他需盯的：AIGC 元数据可被用户本地删除（靠服务端出图二次写入缓解）、
`pg_trgm` GIN 索引膨胀（只索引标题/标签/提示词，定期 `REINDEX CONCURRENTLY`）、
单机单点（图在 R2、PG 每日备份到 R2）。

## 6. 参考链接

- 阿里云百炼模型价格（qwen3-vl-plus / embedding）：https://help.aliyun.com/zh/model-studio/model-pricing
- 阿里云图片审核 2.0 计费（国际站）：https://www.alibabacloud.com/help/zh/content-moderation/latest/billing-description
- 腾讯云图片内容安全计费：https://cloud.tencent.com/document/product/1125/37108
- 腾讯云图片 AI 生成识别（0.1 元/张）：https://cloud.tencent.com/document/product/1125/121786
- 《人工智能生成合成内容标识办法》全文：https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm
- Milvus Docker 前置要求（8 GB RAM）：https://milvus.io/docs/prerequisite-docker.md
- pgvector（维度/内存/`maintenance_work_mem`）：https://github.com/pgvector/pgvector
- PostgreSQL 16 `pg_trgm`：https://www.postgresql.org/docs/16/pgtrgm.html
- Cloudflare R2 定价：https://developers.cloudflare.com/r2/pricing/
- 阿里云 OSS 计费概览：https://help.aliyun.com/zh/oss/product-overview/billing-overview
- libvips 性能与内存基准：https://github.com/libvips/libvips/wiki/Speed-and-memory-use
- FastAPI server workers：https://fastapi.tiangolo.com/deployment/server-workers/
- Docker Compose `deploy.resources`：https://docs.docker.com/compose/compose-file/deploy/
- dramatiq：https://github.com/Bogdanp/dramatiq/ ｜ arq 维护状态：https://github.com/python-arq/arq
