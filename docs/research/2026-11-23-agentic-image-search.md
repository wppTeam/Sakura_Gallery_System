# Agent 化图像检索 + 向量后端调研（2026-11-23）

> 目标：把"关键词搜图"升级为"Agent 检索"（意图分解 → 多 facet 检索 → 结果解释 → 必要时追问），
> 同时满足两条硬约束：**部署目标 2c4g**、**Milvus/torch 不得成为必装依赖**（AGENTS.md §11）。
> 标签：**[官方]** 文档原话；**[本项目实测]** AGENTS.md / 本机实测；**[估算]** 推算未实测。

## 0. 结论先行

| 决策 | 方案 | 关键数字 | 理由 |
|---|---|---|---|
| **采用** | 第一阶段：PostgreSQL 内 `pg_trgm` + `tsvector('simple')` + 应用层 jieba 分词 | 0 新进程、0 新依赖；10 万条文本 GIN 索引几十 MB | 2c4g 上最省内存；现有 PG16 已装 `pg_trgm`（用户口述，本机未验证扩展清单） |
| **采用** | Agent 层手写 tool-calling loop（约 200 行）+ pydantic schema 校验 | ≤4 轮工具调用、总预算 8 s、1–2 次 LLM 调用 | 工具只有 4 个，框架收益 < 依赖成本；每多一层依赖都是 2c4g 上的内存与漏洞面 |
| **采用（第二阶段）** | 语料 >2 万条时上 `pgvector` + DashScope `text-embedding-v4` 外部 API | 512 维；**0.5 元/百万 token**（免费 100 万 token）；10 万条一次性约 1–3 元 | 不落本地模型（省 150–250 MB 常驻），向量与元数据同库，无第二套服务 |
| **不采用** | Milvus standalone | 官方最低 **RAM 8 GB / 4 核**，推荐 16 GB | 2c4g 上装不下，是硬性排除 |
| **不采用** | Qdrant | 额外常驻进程；向量仍需全量进内存 | 与 PG 方案重复（元数据在 PG、向量在 Qdrant 等于双写），运维面翻倍 |
| **不采用** | `sentence-transformers` + torch 本地 embedding | torch 数百 MB 依赖 | AGENTS.md §11 明令禁止把 torch 变必装；且 2 vCPU 上推理慢于一次 API 调用 |
| **不采用** | LangChain / LangGraph / LlamaIndex | 依赖树大（无法在受限网络下用 PyPI 量化，**[估算]** 单框架 20+ 传递依赖） | 只为一个 4 工具循环引入整套抽象，调试与升级成本高于手写 |
| **备选** | `pydantic-ai`（放进 `requirements-ai.txt`，不进 base） | 依赖以 pydantic/httpx 为主 | 若工具数 >8 或要做多 Agent 编排，它是最轻的选择；现在不需要 |

**一句话**：检索先"纯 PG 全文 + trigram"起跑，Agent 层手写 4 工具循环；
向量只在语料规模撑得住时作为**可选增强**加 `pgvector`，embedding 走外部 API 而非本地模型。

---

## 1. Agent 检索的形态选型

| 形态 | 说明 | 结论 |
|---|---|---|
| **tool-calling loop**（采用） | LLM 选工具/填参数 → 执行 → 观察 → 再决定；上限 4 轮 | 最贴合"跨 kind 多 facet 检索"，且每步可审计、可回放 |
| plan-then-execute | 先一次性出计划再批量执行 | 计划错则整轮废；对话式追问场景反而要多轮，**不采用**为默认 |
| 纯 query decomposition | 规则/一次 LLM 把查询拆成多 facet 关键词，再合并结果 | **采用**：把它做成 loop 的第 0 步（规则优先，LLM 兜底），不需要单独范式 |
| clarify（反问） | 低置信度时追问 | **采用为末路**：仅当结果数 <3 或 facet 冲突时问一句，不要频繁打断 |

**工具集（4 个，全部强制服务端过滤）**

1. `search_works(query, kind?, season?, bloom?, license?, aspect?, sort?, limit≤40)`
2. `get_work(id)` — 详情 + 相似作品 id 列表
3. `similar_works(id, limit≤20)` — 同色系/同场景/同 tag
4. `list_facets(dimension)` — 返回可筛选值及计数（把"有什么可选"交给模型，避免瞎猜）

**护栏（写进 loop，不交给模型自觉）**

- 每轮工具结果截断到 40 条 / 4 KB，总 token 预算 8 K；超过直接返回已有结果 + 说明。
- 工具参数用 pydantic 校验，非法直接报错回模型，不抛 500。
- 只暴露 `status=published AND visibility=public` 的行；**可见性过滤在 SQL 层，不靠 prompt**。
- 总超时 8 s（`asyncio.wait_for`）；LLM 超时 2.5 s 时降级为纯 SQL 检索，搜索页不能因 Agent 挂掉。
- 搜索 LLM 用**非推理型快速模型**；不要用 `deepseek-v4.1-flash`（本项目实测 4.7 s，交互场景太慢）。

**成本与延迟 [估算]**：一次搜索 1–2 次 LLM（约 300–800 token）+ 1–4 次 SQL。
按 1 元/百万 token 量级，单次 <0.001 元；1 万次/月约 5–10 元。
延迟构成：LLM 0.6–1.5 s + SQL/trgm 10–60 ms + 序列化；P95 目标 2 s 内。

## 2. 向量后端对比（2c4g 视角）

| 方案 | 常驻内存（10 万条 × 512d float32） | 运维面 | 结论 |
|---|---|---|---|
| **PG + pg_trgm/tsvector** | 索引几十 MB，随 PG 进程 | 无新增服务 | **采用（默认）** |
| **PG + pgvector HNSW** | 原始向量 100k×512×4 ≈ **205 MB**；HNSW 图约 1.2–1.4×（**[估算]** ≈250–290 MB），合计约 270 MB，需 PG 额外 shared_buffers/工作内存 | `CREATE EXTENSION vector`，需 superuser 或云厂商支持 | **采用（第二阶段，>2 万条再上）** |
| Milvus standalone | 官方最低 8 GB、推荐 16 GB | etcd + MinIO + 多容器 | **不采用** |
| Qdrant | 单进程基线 + 向量内存（10 万×512d 约 200 MB+） | 第二套服务 + 备份 | **不采用** |
| 外部向量 DB（Pinecone 等） | 0 | 出网依赖 + 费用 | **不采用**（数据出境/合规与成本都不划算） |

**pgvector 关键官方约束**（`github.com/pgvector/pgvector` README）：

- `vector` 最多 **2000 维**、`halfvec` 4000 维、`bit` 64000 维 → 512 维完全够用，可上 `halfvec` 省一半内存（102 MB）。
- HNSW "uses more memory" 且"better query performance than IVFFlat, slower build"。
- 建索引需要 `maintenance_work_mem` 能容纳整张图，否则报
  `hnsw graph no longer fits into maintenance_work_mem after N tuples`；README 示例给 8 GB，
  目标机应按"图大小 × 1.5"设（10 万条约 400 MB，构建完再调回）。
- 目标机未装该扩展（用户口述 PG16 无 pgvector）→ 上线前需 `apt install postgresql-16-pgvector`
  或云厂商控制台开启；**这是本方案唯一的安装前提，未实测**。

**索引规模对比**：10 万条 200 字中文 = 2000 万字。`pg_trgm` 的 GIN 索引通常是原文的 1–3 倍（**[估算]** 几十到上百 MB），
`pgvector` HNSW 约 270 MB。两者都在 PG 内，2c4g 上二选一即可，不需要同时全量建。

## 3. 中文检索的三种做法（易踩坑）

| 做法 | 原理 | 优点 | 缺点 |
|---|---|---|---|
| `pg_trgm` | 字符 3-gram，`%` 相似度 / `ILIKE` 加速 | 开箱即用（本机已有）、容错（错别字也能召回） | 对 1–2 字查询几乎无效；GIN 索引膨胀；无语义 |
| `tsvector('simple')` | 按空格切词 + 停用词，无中文分词 | 排序可用 `ts_rank` | 整句中文会被当成**一个 token**，必须应用层先分词 |
| `zhparser` 扩展 | SCWS 中文分词器，`to_tsvector('chinese', ...)` | 分词在库内，SQL 干净 | 需要编译安装扩展 + 词典；目标机没装，且升级 PG 要重编 → **不采用**（保持"零扩展"原则） |

**采用组合**：应用层 `jieba`（纯 Python，词典约几 MB）分词后用空格拼回，
写 `to_tsvector('simple', segmented)` 存生成列；同时保留 `title % query` 的 trigram 兜底。
排序：`ts_rank × 0.6 + similarity × 0.25 + 热度归一 × 0.15`（权重可调，别用未校准的 BM25）。

**来源**：PG 16 `pg_trgm` 文档 https://www.postgresql.org/docs/16/pgtrgm.html ；
zhparser https://github.com/amutu/zhparser 。

## 4. Embedding 选型：外部 API vs 本地小模型

| 方案 | 成本 | 常驻内存 | 延迟 | 结论 |
|---|---|---|---|---|
| **DashScope `text-embedding-v4`** | **0.5 元/百万 token**，新开通 100 万 token 免费；Batch 半价 | 0 | API 往返，**[估算]** 100–300 ms/次 | **采用** |
| DashScope `qwen3.7-text-embedding-flash` | **0.125 元/百万 token** | 0 | 同上 | 备选（更便宜，效果需自测） |
| 本地 `bge-small-zh-v1.5`（fastembed/onnxruntime） | 0 元/次 | **[估算]** 模型 int8 ≈24 MB / fp32 ≈95 MB + onnxruntime 与 tokenizer，进程 150–250 MB | 2 vCPU 上 **[估算]** 20–40 ms/条 | **不采用**（省 200 MB 比省几分钱重要） |
| `sentence-transformers` + torch | 0 元/次 | 数百 MB–1 GB | 更慢 | **不采用**（AGENTS.md §11） |

**用量估算 [估算]**：1 万条作品 × 平均 200 token（标题+标签+提示词+描述）= 200 万 token ≈ **1 元**；
重建全量索引也就几元。查询侧每次 ~20 token，可忽略。
`bge-small-zh-v1.5` 为 512 维 / 24M 参数（社区常见描述）；**HuggingFace 在本机网络不可达，文件大小与依赖未实测**。

## 5. 2c4g 内存预算（检索相关部分）

| 组件 | 常驻 RSS | 说明 |
|---|---|---|
| PG `shared_buffers=512MB` + 连接/工作内存 | 800 MB – 1.1 GB | 含 HNSW 索引时再加 270 MB（10 万条） |
| FastAPI 2 × uvicorn worker（含 SQLAlchemy 池） | 2 × 120 MB = 240 MB | 基于本项目实测全栈 import 峰值 **61 MB** + 运行时翻倍估算 |
| nginx | 15–20 MB | 反代 + 静态 |
| OS + 监控 | 300–400 MB | — |
| **合计（不含向量）** | **≈1.4–1.8 GB** | 4 GB 有余量，可再跑一个小 worker |
| **加 pgvector（10 万条）** | **≈1.7–2.1 GB** | 仍可行，但构建索引瞬间会顶到 400 MB 工作内存，需错峰 |

## 6. 落地顺序

1. **P0（2 天）**：PG 生成列 `tsv` + jieba 分词 + `pg_trgm` GIN；搜索 API 返回 facet 计数。
2. **P0（1 天）**：`search_works` / `list_facets` 两个工具 + 手写 loop（上限 4 轮、8 s 预算、降级纯 SQL）。
3. **P1（1 天）**：结果解释（用检索到的字段拼一句，不让模型编造）+ 低置信度追问。
4. **P1（1 天）**：`get_work` / `similar_works`（相似 = 同 tag/同季相/同色系，先不用向量）。
5. **P2（0.5 天，条件触发）**：作品数 >2 万或搜索满意度低 → 装 pgvector + `text-embedding-v4` 回填，
   用 RRF（Reciprocal Rank Fusion）把 BM25 与向量排名融合，不替换现有链路。
6. **依赖分层**：`requirements-base.txt`（无向量）/ `-ai.txt`（LLM 调用）/ `-vector.txt`（pgvector 客户端与回填脚本，不含 torch）。

## 7. 风险

- **R1｜扩展缺失**：目标机没有 `pgvector`，第二阶段可能装不上（无 PGDG 源/无 superuser）。对策：向量层默认关闭，装不上就停留阶段一；不要让检索依赖它。
- **R2｜分词质量**：jieba 对摄影/二次元专名（"八景""赛博朋克""景深"）会切错。对策：维护 200 词自定义词典，入库时同时把标签原文入索引。
- **R3｜索引膨胀**：`pg_trgm` GIN 在 10 万条量级可能上百 MB，写放大明显。对策：只对 `title + tags + prompt` 建，描述不建；定期 `REINDEX CONCURRENTLY`。
- **R4｜Agent 越权/幻觉**：模型可能编造筛选值或忽略可见性。对策：facet 值只从 `list_facets` 取、SQL 层强制过滤、结果解释只用检索字段。

## 8. 来源

- PostgreSQL 16 `pg_trgm`：https://www.postgresql.org/docs/16/pgtrgm.html
- pgvector（维度上限、HNSW 内存与 `maintenance_work_mem`）：https://github.com/pgvector/pgvector
- Milvus Docker 部署前置硬件要求（RAM 8 GB 最低 / 16 GB 推荐）：https://milvus.io/docs/prerequisite-docker.md
- Qdrant 安装与要求：https://qdrant.tech/documentation/guides/installation/
- 阿里云百炼文本向量价格（`text-embedding-v4` 0.5 元/百万 token）：https://help.aliyun.com/zh/model-studio/model-pricing
- pydantic-ai（备选 agent 框架）：https://pydantic.dev/docs/ai/core-concepts/agent/
- LangGraph：https://langchain-ai.github.io/langgraph/ ｜ LlamaIndex：https://docs.llamaindex.ai/en/stable/
- 中文分词扩展 zhparser：https://github.com/amutu/zhparser
- jieba（纯 Python 分词）：https://github.com/fxsjy/jieba
