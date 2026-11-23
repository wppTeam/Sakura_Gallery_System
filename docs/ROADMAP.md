# 视觉百花 Sakura Gallery — 分期时间表

> 制定 2026-11-23。开发指南与约定见 [`AGENTS.md`](../AGENTS.md)，设计方向见 [`design/DIRECTION.md`](../design/DIRECTION.md)。
>
> 范围决策：三类内容全做，**摄影与 AIGC 为主，模板排后**；三级发布 + Agent 审核一步到位；
> 字体不硬拦只标风险；品牌资产四件全做，透明 PNG 即可不要求 SVG。

---

## 总览

| 里程碑 | 日期 | 主题 | 依赖 |
|--------|------|------|------|
| **M0** | 11/24 – 11/30 | 地基：数据模型 + 资产管线 + 隐私修复 | — |
| **M1** | 12/01 – 12/07 | 品牌资产 + 公共端骨架 + 探索页 | M0 |
| **M2** | 12/08 – 12/14 | AIGC 专区（含法定标识链路） | M0 |
| **M3** | 12/15 – 12/21 | Agent 审核（规则 + 快筛 + 复核） | M0, M2 |
| **M4** | 12/22 – 12/28 | 检索与 Agent 搜索 | M0, M2 |
| **M5** | 12/29 – 01/04 | 详情页 + 摄影师主页 + 社区互动 | M1, M3 |
| **M6** | 01/05 – 01/11 | 模板专区 | M0, M3 |
| **M7** | 01/12 – 01/18 | 开源发布 v1.0 | 全部 |

**关键路径**：M0 → M1 → M5。资产管线不先做完，真瀑布流没有素材可排。
**可并行**：M2 与 M1；M4 与 M3。

---

## M0 · 地基（11/24 – 11/30）

先把地基改对，否则后面全是返工。

- [ ] **works 基表 + kind 判别 + 三张元数据表** Alembic 迁移；存量 photos 数据平移，保留旧 id
- [ ] **隐私修复**：`serialize_photo` 改白名单 schema，公开响应剔除学号 / 真实姓名 / 完整 EXIF
      （`backend/app/api/v1/endpoints/photos.py:150-163`）
- [ ] **废除强制裁切**：`image_processing.py:44-62` 改为保留原始宽高比
- [ ] **多尺寸变体**：长边 320/640/1080/1600/2400，WebP + JPEG 兜底，LQIP blurhash
- [ ] **GPS 剥离**：入库即去除，公开变体不含定位
- [ ] **回填脚本** `scripts/regenerate_variants.py --dry-run`，可断点续跑
- [ ] **图片交付改道**：nginx 反代 MinIO 或预签名 URL，不再经 Python 流式转发
- [ ] `Cache-Control: immutable` + ETag
- [ ] 删掉 `storage.py:198-244` 里硬编码 SSH + `mc pipe` 的 S3 写入兜底
- [ ] 分页硬上限、配置 TTL 缓存、PG 连接池参数

**验收**：迁移可 upgrade/downgrade；同一张 16:9 全景在列表与详情均完整不裁切；
未登录请求 `/photos/public` 的响应里 grep 不到学号与 exif_data；回填 dry-run 报告出体积估算。

---

## M1 · 品牌与公共端骨架（12/01 – 12/07）

- [ ] **品牌四件**（品牌设计师）：组合标、单独图形标、北化创作者徽章、OG 分享图
- [ ] 图形标导出多尺寸 PNG：32 / 48 / 180 / 192 / 512 + favicon
- [ ] 四季插画重做以匹配用户自制 hero 画风；三专区封面；空态插画 4 张；默认头像与专辑封面
- [ ] **token 落进 frontend/src**：替换失效的 `tailwind.config.js` 为 CSS-first `@theme`；
      Naive `themeOverrides` 统一；亮色为默认
- [ ] **应用壳**：真导航（探索/四季/八景/专区）+ 桌面常驻搜索 + 移动抽屉 + 用户菜单
- [ ] **探索页真瀑布流**：修 `GalleryView.vue:538` 的 `getItemRatio = () => 1`，
      改真实 aspect_ratio + 虚拟化 + srcset + LQIP + 骨架屏
- [ ] 首页去掉摄影大赛硬编码（`HomeView.vue:140`）
- [ ] **删死代码**：`Gallery.vue`(1106行)、`SearchView.vue`、`UniformGrid.vue`
- [ ] 接 `vue-tsc`（现状 `.vue` 完全不做类型检查）、eslint、prettier
- [ ] 接通全局错误提示（`api/index.ts:24` 的 `setGlobalErrorHandler` 从未被调用）
- [ ] 修路由 default-deny 导致未登录访问错误 URL 被踢到登录页的 bug

**验收**：新探索页在 1440/768/390 三宽度可用；`npm run build` 含 vue-tsc 且通过；
死代码已删；favicon 在 16px 下可辨。

---

## M2 · AIGC 专区（12/08 – 12/14）

**法定标识四件套必须齐，缺一不可放行。**

- [ ] `aigc_meta` 落地：model / provider / prompt / prompt_public / params / seed / source_work_id
- [ ] **上传强制声明**：不声明 AIGC 不能进 aigc kind；摄影流里探测到 AIGC 元数据则提示改投
- [ ] **显式标识**：列表角标 + 详情页说明区，文案明确「AI 生成」
- [ ] **隐式标识**：下载文件写入 XMP/EXIF 标识字段，`label_written` 落库
- [ ] 图生图 / 换脸类额外限制与 L2 强制前审
- [ ] AIGC 上传流：模型与参数可选公开，提示词可分享
- [ ] kind facet 接入检索与筛选
- [ ] AIGC 专区页：按题材 / 模型 / 是否可复现浏览

**验收**：投一张 AIGC → 列表有角标 → 详情有说明 → 下载文件用 exiftool 能读到标识；
未声明的 AIGC 无法进 aigc kind。

---

## M3 · Agent 审核（12/15 – 12/21）

三层，模型与延迟已实测（见 AGENTS.md §10）。

- [ ] **规则前置层**：GPS 存在性、感知哈希查重、AIGC 元数据探测、
      pptx `fontTable` 字体清单抽取、类型与体积校验
- [ ] **快筛**：`qwen3-vl-plus`（1.9s / 57 tokens），输出结构化 JSON 判定 + suggested_tier
- [ ] **复核**：`deepseek-v4.1-flash`（4.7s / 590 tokens，`max_tokens` 给足 ≥2000），
      **仅 L2 或低置信样本**
- [ ] 常驻 worker 消费队列；失败重试与死信；每步耗时与 token 计数入库
- [ ] **人工队列 UI**：展示 agent 判定、依据、原图与规则命中项，人做终判
- [ ] 三级发布判定落库：L0 自动放行、L1 待推荐评审、L2 前审阻塞
- [ ] 审计日志埋点复用现有 `AuditLog`
- [ ] 成本护栏：日预算 + 超预算降级为纯规则 + 人工

**验收**：L0 样本全自动放行且耗时 < 5s；L2 样本进人工队列并带 agent 意见；
断网或超预算时系统降级不崩；审核结论可追溯到模型版本与规则命中。

---

## M4 · 检索与 Agent 搜索（12/22 – 12/28）

- [ ] **pg_trgm + tsvector** 跨 kind 全文索引，去掉 Milvus 硬依赖
- [ ] AIGC 提示词、模板文本入索引
- [ ] Milvus 降为可选增强，缺失时优雅降级
- [ ] **Agent 搜索**：意图分解 → 多 facet 检索 → 结果解释 → 必要时澄清追问；
      复用 `search_interpreter.py` 扩到跨 kind
- [ ] 搜索建议 typeahead、拍摄时间范围筛选
- [ ] 搜索结果按 kind 分组，AIGC 与摄影视觉区分明确

**验收**：无 Milvus 环境下中文搜索可用；「找昌平下雪的照片」能命中 kind=photo + 校区 + 雪；
「适合答辩的模板」能命中 kind=template + 用途 facet。

---

## M5 · 详情页与社区（12/29 – 01/04）

- [ ] **作品详情页**：原图舞台（缩放/手势/键盘）+ 拍摄者 + 授权与可复制引用 + 参数（空态一句话）
- [ ] **摄影师主页** `/@username`：认证徽章、作品网格、公开专辑、关注
- [ ] User 改造：`student_id` 改 nullable，新增 username/display_name/avatar/bio；
      存量用户生成中性 username，**不用学号生成**
- [ ] 开放注册 + 邮箱验证 + 北化认证（校园邮箱或学号人工核）
- [ ] Like / Comment / Follow / Collection（+CollectionItem）/ Report
- [ ] 通知扩展：点赞/评论/关注/收录/举报结果
- [ ] 我的作品从 `n-data-table` 改卡片网格 + 状态标识
- [ ] 八景专辑页

**验收**：浏览 → 投稿 → 互动闭环可走通；公开主页 grep 不到学号；
被拒作品能看到原因并重投。

---

## M6 · 模板专区（01/05 – 01/11）

- [ ] `template_meta` + S3 直传 + 预签名下载
- [ ] **LibreOffice headless** 容器内异步渲染 pptx → 预览图
- [ ] **字体清单解析** + 风险等级标注 + 详情页明示（**不硬拦不拒收**）
- [ ] 模板 facet：用途（答辩/组会/招新/课程汇报）、风格、比例、页数
- [ ] 首批示例模板：用开源字体（思源/霞鹜/站酷）生成一批，避免空架子
- [ ] 下载计数与授权提示

**验收**：投一个 pptx → 自动出预览 → 字体清单与风险等级可见 → 可下载；
含商业字体的模板不被拒收但风险明示。

---

## M7 · 开源发布 v1.0（01/12 – 01/18）

**发布前必过项，不可跳。**

- [ ] **凭据轮换**：旧 AGENTS.md 曾明文记录服务器 IP / SSH 账号 / sudo 口令 / SECRET_KEY /
      PG 与 MinIO 密钥，且仓库已公开。先确认这些是否在线上栈复用；复用则按泄露处置
- [ ] `SECRET_KEY` 轮换需先重加密 `ai_provider_configs`（Fernet 由 SECRET_KEY 派生），
      长期拆成 `DATA_ENCRYPTION_KEY` / `SECRET_KEY` 双密钥
- [ ] **git 历史清洗**：`git filter-repo` 移除凭据文件；三个公开副本都要处理
      （源头 `JackWPP/BUCT_Media_System`、fork `wppTeam/Sakura_Gallery_System`、
      第三方 fork 不在控制内）；断开 fork 关系；force-push 前通知协作者
- [ ] 装 `gitleaks` pre-commit + 开 GitHub Secret Scanning 与 Push Protection
- [ ] **LICENSE**（待定：代码 AGPL-3.0 或 MIT；照片依作者所选协议）
- [ ] 依赖分层 base / ai / vector；Docker Compose 一键起
- [ ] CI：lint + vue-tsc + pytest + build
- [ ] README 中英双语、CONTRIBUTING、SECURITY.md、Issue/PR 模板
- [ ] 机构耦合配置化：taxonomy 种子、AI 提示词里的校名与楼宇词表抽成可替换文件
- [ ] 示例种子数据（不含北化真实学生肖像）

**验收**：全新环境 `docker compose up` 可访问；仓库 grep 不到任何凭据；
CI 全绿；README 能让陌生人在 5 分钟内跑起来。

---

## 风险与降级

| 风险 | 影响 | 应对 |
|------|------|------|
| 8 周到 v1.0 偏激进 | 延期 |  slipping 时先砍 M6 模板专区，保 M0–M5 的摄影 + AIGC 闭环 |
| 审核人力只有项目所有者 | L2 积压 | Agent 快筛 + 规则前置把 L2 压到最小；必要时 temporarily 关闭 L2 类投稿 |
| 模板首批无内容 | 专区空架子 | M6 自带开源字体示例模板生成 |
| AI 渠道限流或超时 | 审核/生图阻塞 | 双渠道互备；慢模型走百炼异步；超预算降级纯规则 |
| 第三方 fork 无法清除凭据 | 泄露不可回收 | 以轮换为唯一有效补救，清洗只是卫生 |
| 变体回填耗时与存储膨胀 | 磁盘带宽 | 分批后台跑，dry-run 先估体积，旧变体延迟清理 |

## 待定

- LICENSE 选型（AGPL-3.0 vs MIT）
- 域名（沿用还是新域名）
- 「视觉百花」与英文「Sakura Gallery」意象是否需要统一
- 首批模板来源（自制 / 同学投稿 / 代码生成示例）