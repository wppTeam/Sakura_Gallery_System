# 视觉百花 · Sakura Gallery

**北化学生自己的开源创作资源共享平台。**

校园的一年，由十二番花信与八处景名索引。每张作品保留拍摄者署名与授权协议，
照片按原始构图呈现，不裁切。

> 前身是内部校园媒体资产管理系统「视觉北化 / Visual BUCT」。
> 现重定位为面向学生**自助发布**的开放平台：从"审核前置的资产库"变成"自由投稿的创作社区"。

---

## 这是什么

不是一个图库，是**创作资源共享站**。三类内容共用一套发布、检索、互动与授权机制：

| 类型 | 内容 | 状态 |
|------|------|------|
| **摄影** | 校园摄影作品，按季节 / 花信 / 校区 / 景名索引 | 后端已有，公共端重建中 |
| **AIGC** | AI 生成图像，带法定显式与隐式标识，可公开提示词与参数 | 规划中（M2） |
| **模板** | PPT 等模板素材，自动预览、字体清单与风险标注 | 规划中（M6） |

### 与旧版的区别：自由度

- **三级发布**：原创内容免审即发；进精选才需评审；涉可识别人物与疑似侵权强制前审
- **Agent 辅助审核**：规则前置过滤 + VLM 快筛 + 推理模型复核难例，人做终判
- 用户自助建专辑、自定义标签、装修个人主页，**不需要管理员批准**
- 开放 API、可自部署

---

## 现状（诚实说明）

- **后端**：FastAPI + SQLAlchemy + PostgreSQL，已具备上传、AI 打标、审核、taxonomy 多维分类、
  语义检索、RBAC、审计日志、通知、收藏。仍是单类型（摄影）模型。
- **公共端新设计**：目前是 `design/` 下的**静态原型**，已通过 1440 / 768 / 390 三宽度实测门禁。
  尚未落进 `frontend/src`。
- **重构进行中**：统一 `works` 基表 + kind 判别、资产管线、隐私白名单修复见路线图 M0。

打开 **[design/index.html](design/index.html)** 可直接看到新公共端设计（纯静态，无需构建）。

---

## 快速开始

### 后端

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

创建管理员（口令从环境变量读，未提供则随机生成并打印一次）：

```bash
ADMIN_EMAIL=you@example.edu.cn ADMIN_PASSWORD='your-strong-password' \
  python3 scripts/create_admin.py
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

- 前端 http://localhost:5173
- API 文档 http://localhost:8000/docs

### 配置

复制 `backend/.env.example` 为 `backend/.env`，`deploy/.env.production.example` 为部署用模板。
**真实凭据不提交仓库**，脚本通过环境变量读取：

| 变量 | 用途 |
|------|------|
| `SECRET_KEY` | JWT 签名（生产必须自定义） |
| `DATABASE_URL` | PostgreSQL 连接 |
| `S3_ENDPOINT` / `S3_BUCKET` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` | 对象存储 |
| `DEPLOY_SERVER` / `DEPLOY_USER` / `DEPLOY_HOST` / `SUDO_PASS` | 部署脚本 |
| `S3_SSH_FALLBACK_HOST` / `S3_SSH_FALLBACK_USER` | 本地开发绕过防火墙的可选兜底，生产不用 |

---

## 设计系统

樱花粉柔色系 + 二次元取向。全部对比度为脚本实测，非目测。

```
底 #fff6f9   卡面 #ffffff   墨 #4a2b35   次级 #63474f
主色 #c93a63（按钮/链接 4.9:1）   标题粉 #e8628c（大字 3.2:1）
四季淡底 春#ffd7e4 夏#d4f0e4 秋#ffdfd6 冬#d6e8f7（深墨字 9.5–10.3:1）
```

- 标题字 **站酷庆科黄油体**（自托管，92 个 unicode-range 分片），正文 Noto Sans SC
- 圆角：卡 20px / 照片 16px / 控件全圆角
- **照片保留原始宽高比，禁止裁切**；瀑布流按真实比例做最短列分配
- CJK 行宽用 `em` 不用 `ch`

详见 [design/DIRECTION.md](design/DIRECTION.md)。

### 品牌资产

`design/brand/` 提供组合标、纯中文版（顶栏用）、反色版（深色底用）、图形标、
「北化创作者」认证徽章、1200×630 社交分享图，以及 favicon 全套
（16/32/48 用实心简化版，180/192/512 用细节版）。均为透明 PNG。

---

## 项目结构

```
backend/          FastAPI 应用
  app/api/v1/     路由与端点
  app/models/     SQLAlchemy 模型
  app/services/   业务逻辑（存储、图像处理、AI、检索）
  alembic/        数据库迁移
frontend/         Vue 3 + Vite + TS + Naive UI + Tailwind 4
design/           公共端设计原型与品牌资产
  index.html      可交互原型
  DIRECTION.md    设计方向、色板实测值、踩坑记录
  brand/          标识与 favicon
  assets/         art 插画 / photo 摄影素材 / ref 参考
docs/             ROADMAP.md 分期时间表，API.md 等
deploy/           部署脚本与配置模板（无凭据）
scripts/          运维与初始化脚本
```

---

## 路线图

八个里程碑，每项带可验收判据：**[docs/ROADMAP.md](docs/ROADMAP.md)**

| | 主题 |
|---|---|
| M0 | 数据模型（works + kind）、资产管线、隐私修复 |
| M1 | 品牌资产、公共端骨架、探索页 |
| M2 | AIGC 专区（法定标识链路） |
| M3 | Agent 审核（规则 + 快筛 + 复核） |
| M4 | 检索与 Agent 搜索 |
| M5 | 详情页、摄影师主页、社区互动 |
| M6 | 模板专区 |
| M7 | 开源发布 v1.0 |

开发约定见 **[AGENTS.md](AGENTS.md)**。

---

## 合规

- **AIGC 标识**：依《人工智能生成合成内容标识办法》（2025-09-01 施行），
  AI 生成内容须带显式标识（角标与说明）与隐式标识（下载文件元数据）
- **个人信息**：公开响应不含学号、真实姓名、完整 EXIF；GPS 入库即剥离；学号永不公开
- **肖像权**：涉可识别人物需被摄者同意
- **字体授权**：模板会抽取字体清单并标注风险等级，不硬拦；非商用**不豁免**著作权，
  推荐使用思源 / 霞鹜 / 站酷等开源免费商用字体

## 安全

**本仓库工作区已脱敏**，不含服务器地址、账号、口令或密钥。

⚠️ **但 git 历史中仍存有早期提交的真实凭据**，且本仓库曾公开。
如果你 fork 或克隆过 2026-11 之前的版本，请视为凭据已泄露：
**轮换是唯一有效补救**，清洗历史只是卫生。相关处置见路线图 M7。

发现漏洞请勿公开提 Issue，先私下联系维护者。

---

## 第三方素材

`design/assets/photo/` 中的摄影作品来自 Wikimedia Commons，依各自 CC 协议使用，
作者与协议见 `design/assets/credits.json` 与原型页脚署名。
它们**不是北化学生投稿**，是设计占位，接入真实作品后须替换。

`design/assets/art/` 的插画为 AI 生成（阿里云百炼 qwen-image-3.0-pro），
页面明确标注，不冒充摄影作品。首屏主视觉为项目自制。

字体：站酷庆科黄油体与 Noto Sans SC 依 SIL Open Font License 使用。

---

## 贡献

欢迎贡献。Commit 标题用简短英文命令句概括改动（与现有历史一致），例如
`Return clear taxonomy node validation errors`；需要展开时写在正文。

提交前请确认：
- 不含任何凭据、服务器地址或账号
- 不在公开响应中暴露学号、真实姓名、完整 EXIF
- 不裁切用户原图构图
- AIGC 内容带显式与隐式标识

## 许可

代码许可证待定（见路线图 M7）。摄影与插画素材依各自作者所选协议，见上方署名。