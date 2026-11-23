# 视觉百花 Sakura Gallery · 公共端设计方向（樱花粉 / 二次元）

> 现行方向。制定 2026-11-23。
> 前两版（`prev/` 暗色后台版、`prev/annual/` 骨白年刊版）已废弃，仅留作对照。

---

## 1. 方向来源

用户明确指定：**粉嫩、二次元，因为是 Sakura BUCT**；结构上综合 Unsplash 的影像优先，
但不照搬 Unsplash / 视觉中国的配色。

从 Unsplash 实际 CSS 提取并采用的结构事实：
- 顶栏 56px（移动）/ 64px（桌面）
- 内容最大宽 1296px + 24px 侧边距（本项目用 1320 / 24）
- 照片网格用 `aspect-ratio: var(--width)/var(--height)` —— **真实宽高比，不裁切**
- 悬停才显操作按钮（`opacity 0 → 1`）
- 横向可滚动话题导航
- 占位底色 + 脉冲，不用骨架闪动渐变

**没有采用**：Unsplash 的 64px 图标侧栏（公开浏览面不需要）、VCG 红 `#e60012`
（虽然项目旧 CSS 里有，但与樱花粉方向冲突）。

---

## 2. 概念（沿用，来自项目自身数据）

> **北化的十二番花信与八处景名，成为信息流的组织轴。**

- `taxonomy.py` `CHANGPING_NATURAL_ECOLOGY.植物` 正好十二种花：迎春、杏、连翘、芍药、
  郁金香、二月兰、桃、牡丹、紫花地丁、海棠、樱花、玉兰
- 同文件 `CHANGPING_LANDSCAPE_MAINTENANCE` 的**北化八景**：化彩三台、馆声凫影、镜湖书柳、
  小荷听书、花海晴光、平湖跃金、花海聆淙、烟雨玉屏
- 宿舍区以花命名（樱花苑、玉兰苑、紫竹苑、杏坛苑）——「百花」有实指
- 「此刻」行由真实节气计算：2026-11-23 → 小雪已过 → 冬季 → 下一番花信 3 月上旬迎春

---

## 3. 色板（全部脚本实测，非目测）

| 角色 | 值 | 对比度 |
|------|-----|--------|
| 底色 樱花白 | `#fff6f9` | — |
| 卡面 | `#ffffff` | — |
| 墨色 深梅 | `#4a2b35` | 11.7:1（底）/ 12.4:1（白） |
| 次级文字 | `#63474f` | 7.8:1（底）/ 8.3:1（白） |
| 主色 深樱（按钮/链接） | `#c93a63` | 4.9:1，白字其上 4.9:1 |
| 标题 樱粉（大字） | `#e8628c` | 3.2:1（白，满足大字 3:1） |
| 页脚名 | `#c93a63` on `#ffe9f0` | 4.26:1 |

四季淡色域（深墨字其上 9.5–10.3:1）与季相强调色（大字 ≥3.1:1）：

| 季 | 淡底 | 强调 |
|----|------|------|
| 春 | `#ffd7e4` | `#e36089` |
| 夏 | `#d4f0e4` | `#3b9c80` |
| 秋 | `#ffdfd6` | `#b5703c` |
| 冬 | `#d6e8f7` | `#5692c8` |

**规则**：整块色域只承载大字；正文一律用深墨。秋季淡底原为 `#ffe4cc`，被检测判为
「米色+陶土」的典型 AI 配色，改为桃色 `#ffdfd6` 并把强调色压到 `#b5703c` 以过 3:1。

## 4. 字体

- 标题：**站酷庆科黄油体**（ZCOOL QingKe HuangYou）—— 圆润，二次元取向
- 正文：Noto Sans SC 400/500/700
- 字号六级：12（头像首字母）/ 16（正文与细print）/ 22 / 44 / 84 / 92
- **CJK 排版注意**：`ch` 单位在中文下约为半个汉字宽，用 `em` 设定行宽，否则「平台」「花信」
  会被拆断。行宽一律 `em`。

## 5. 圆角与柔影（申述保留）

用户明确要求二次元语言，故保留：卡片 20px、照片 16px、控件全圆角、
柔影 `0 6px 24px rgba(201,58,99,.10)`。

这三条与 design-taste skill 的 house rules 冲突，已显式放行并记录理由：

| 放行项 | 理由 |
|--------|------|
| `shadow` | 用户明确要二次元柔影；粉色柔影是风格的一部分，非通用装饰 |
| `font-not-dealt` | 方向表抽的是 Switzer，无中文字形；用户要圆润中文标题 |
| `name-only-title` | 首屏 h1 下方有 22px 说明句「北化学生自己的开源图像平台」，检测器未计入 |

最终门禁：**0 FAIL / 0 WARN**（1440 / 768 / 390 三宽度）。

---

## 6. 资产组织

```
design/assets/
  art/      hero.webp spring.webp summer.webp autumn.webp winter.webp
            four-seasons-mosaic.jpg   ← 项目原始自绘四季马赛克
  photo/    9 张真实 CC 摄影作品 + nevicata-svizzera.webm（落雪影像）
  ref/      library-reference.jpg     ← 用户提供的图书馆实景参考
            hero-user-original.png    ← 用户自制首屏主视觉原件
  credits.json
```

- 插画统一转 WebP（长边 1600，q82）：**12.9MB PNG → 1.26MB WebP，约 10 倍**
- 整个 assets 目录 **41MB → 14MB**
- 淘汰的生成版本（turbo 全套、pro-hero、lib-b、ab-*）已删除，共 13 个文件

### 图书馆形态修正与首屏主视觉定稿（重要）

首版插画把图书馆画成方盒子灰石玻璃楼，**与真实建筑不符**。用户提供实景参考后核实：
北化昌平图书馆是 **S 形曲面立面 + 深红横向色带与青绿玻璃错层交替**，约七层，
前有草坪与石砌矮墙。

据参考重出两版（`lib-a` / `lib-b`）后，**用户自行重做了首屏主视觉并定为最终版**。
现 `art/hero.webp` 为用户自制版本：粉紫天空过渡更柔、花瓣层次更好，与页面樱花底色更协调。
原件保留在 `ref/hero-user-original.png`（1672×941 PNG，2.68MB），
上线版转 WebP q90 后 343KB，分辨率不变。

四季插画仍为 AI 生成（`qwen-image-3.0-pro`），图书馆形态依同一实景参考。

---

## 7. 图像生成：实测可用模型表

用户提供的两个渠道实测结果（同题同参数）：

**NewAPI 渠道 `152.136.121.153:26102`**

| 模型 | 结果 |
|------|------|
| `z-image-turbo` | 200 · 3.8s ✓ |
| `qwen-image-2.0` | 200 · 6.4s ✓ |
| `qwen-image` / `-plus` / `-max` / `wanx2.1-*` | 429 配额限流 |
| `qwen-image-2.0-pro` / `3.0-pro` / `wan2.7-image(-pro)` | **502，恰好 10.0s** |
| `wan2.6-image` | 400 参数结构不符 |
| `/v1/images/edits`（multipart） | 400 unexpected EOF |

→ 502 全部卡在恰好 10 秒，是**代理上游 10 秒超时**，不是模型或参数问题。

**阿里云百炼直连**

- `compatible-mode/v1/images/generations` → 404（不提供）
- `api/v1/services/aigc/text2image/image-synthesis` → 400 url error
- `api/v1/services/aigc/multimodal-generation/generation` + 异步头 → 403 不支持异步；同步挂起 249s
- **`api/v1/services/aigc/image-generation/generation` + `X-DashScope-Async: enable` → 200 ✓**

正确用法：
```
POST https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation
Header: X-DashScope-Async: enable
Body: {"model":"qwen-image-3.0-pro",
       "input":{"messages":[{"role":"user","content":[{"text":"..."}]}]},
       "parameters":{"size":"1664*928","n":1,"prompt_extend":true}}
→ output.task_id，轮询 GET /api/v1/tasks/{id}
→ 结果在 output.choices[0].message.content[0].image（字段名是 image，不是 url）
```
尺寸用 `*` 而非 `x`。单张约 53 秒。`qwen-image-3.0-pro` 出图质量明显优于 `z-image-turbo`。

**凭据处理**：两个 key 只在命令环境变量中临时使用，**未写入仓库任何文件**。

---

## 8. 图片来源与署名

九张摄影作品来自 Wikimedia Commons，真实 CC 授权，作者与协议不可改写，
**不是北化学生投稿**，接入真实作品后须替换。其中 4 张确为北化校园。

| 作品 | 作者 | 协议 |
|------|------|------|
| 校名石前 | HoweyYuan | CC BY-SA 4.0 |
| 逆光樱花 | Paul Colin Hennig | CC BY-SA 4.0 |
| 静水（天鹅） | Olha Mozok | CC BY 3.0 |
| 母校之光 | Song.li | CC BY-SA 3.0 |
| 晚霞落在教学楼 | Nhrjmhll | CC0 |
| 三蒂莲 | Buchio Takano | CC BY-SA 3.0 |
| 南门冬日 | N509FZ | CC BY-SA 4.0 |
| 厚德榜 | Song.li | CC BY-SA 3.0 |
| 初雪覆顶 | Globetrotter19 | CC BY-SA 3.0 |
| 落雪影像 Nevicata, Svizzera | Jo-Jo Eumerus | CC BY-SA 4.0 |

首屏主视觉为项目自制（用户提供），标注「主视觉 · 项目自制」；四季插画为 AI 生成，
标注「季相插画 · AI 生成」。两者均不冒充摄影作品。署名集中在页脚 credits 与每张卡片的协议 chip。

拍摄参数由 PIL 从文件 EXIF 实读；读不到即为短横，不编造。
`母校之光` 与 `厚德榜` 读出 Canon PowerShot S50 / 7.1mm / f/5.6，真实拍摄日 2006-11-22 与 2006-11-30。

搜索中丢弃 4 张：两张 `G-BUCT` 实为英国飞机注册号（字符串误匹配），
两张 ESO 沙漠天文台与校园题材无关。

---

## 9. 已建 / 未建

**已建**：`design/index.html` —— 顶栏、首屏、四季话题筛选、真瀑布流、
四季色域（插画横幅 + 作品瀑布流）、北化八景、投稿 CTA、页脚署名、飘落樱花动效。

**未建（规格已定，沿用同一套 token）**：
- 作品详情页：原图舞台 + 拍摄者 + 授权与可复制引用 + 拍摄参数（空态给一句话而非六行短横）
- 投稿页：拖拽队列 + 逐文件进度 + **未选协议不能提交** + 引用格式实时预览
- 摄影师主页 `/@username`：认证徽章、作品网格、公开专辑。**学号永不公开**
- 专辑页：策展人署名 + 说明 + 真瀑布流

**上线前须替换**：九张占位照片、作品标题（按画面所拟，需作者确认）、
`place` 字段（依画面判断，需核实）、八景与花信链接目前指向锚点、投稿按钮未接后端。

---

## 10. 落地顺序

1. token 与外壳落进 `frontend/src`：替换失效的 `tailwind.config.js` 为 CSS-first `@theme`
2. **图像管线必须先于瀑布流上线**：保留原比例的多尺寸 WebP 变体 + LQIP，
   否则真瀑布流没有素材可排（现状 `image_processing.py:44-62` 强制中心裁切）
3. 修 `GalleryView.vue:538` 的 `getItemRatio = () => 1`
4. 删死代码：`Gallery.vue`(1106行)、`SearchView.vue`、`UniformGrid.vue`
5. 接 `vue-tsc`（现状 `.vue` 完全不做类型检查）、eslint、vitest、Playwright

---

## 11. 品牌标识（自制，非第三方设计服务）

全部用 **百炼 qwen-image-3.0-pro** 生成，纯白底出图后程序抠成透明 PNG。
中文字标逐字核对无错字：「视觉百花」「Sakura Gallery」「北化创作者」均正确。

```
design/brand/
  logo-combo.png              组合标（图形+中文+英文），1140×335
  logo-combo-zh.png           纯中文版（去英文副行），顶栏用
  logo-combo-reverse.png      反色版（墨色→骨白），深色底用
  logo-combo-zh-reverse.png   纯中文反色版
  logo-symbol.png             图形标细节版，大尺寸用
  badge-verified.png          北化创作者徽章
  og-share.png / .webp        1200×630 社交分享图
  favicon/                    icon-16/32/48（实心版）+ 180/192/512（细节版）+ favicon.ico
  raw/                        生成原图，保留出处
```

### 三个实测发现与处理

| 发现 | 处理 |
|------|------|
| 图形标 16px 糊成粉团（花瓣细白缝 + 花蕊细节过多） | 形态学闭运算合并花瓣、填洞、去花蕊，得**实心版**专供 16/32/48px；大尺寸保留细节版 |
| 组合标 h=20px 时英文副行不可读 | 按色相分离墨色（中文）与深樱（英文），程序抹除英文带，得**纯中文版**；顶栏用它，h=20 即可读 |
| 深色底上墨色中文完全消失 | 墨色像素映射为骨白 `#fff6f9`，得**反色版**；粉色保留 |

三项都是程序化处理，未额外消耗生成额度。

### 抠图方法（可复用）

生图模型不产出真 alpha。做法：让模型在纯白底出图 →
`scipy.ndimage.label` 找近白连通域 → **只删触边的那块**（避免吃掉徽章的淡樱填充 `#ffd7e4`，
其最暗通道 215，简单阈值会误删）→ 边界 0.6px 高斯羽化，内部与远背景保持硬值 → 裁 bbox。

## 12. 字体自托管（踩过的坑）

**站酷庆科黄油体必须自托管，不能依赖 Google Fonts CDN。**

- CDN 声明成功但实际未加载，inspector 一开始只报「声明的字体族」，视觉上标题回退成细体 Noto Sans SC，
  与顶栏 logo 的粗圆中文明显不一致才发现
- `fonts.gstatic.com` 用 Python 3.9 的 urllib 下载报 SSL EOF；**curl 直连正常**，改用 curl 批量下载
- 该字体被切成 **92 个 unicode-range 分片，共 1.82MB**，全部自托管于 `design/fonts/zcool/`
- **关键坑**：CSS 里的 `url()` 相对 **CSS 文件自身**解析，不是相对 HTML。
  `design/fonts/zcool.css` 里必须写 `zcool/zcool-XX.woff2`，写成 `fonts/zcool/...` 会 404 且静默回退
- 修好后 `font-fallback` 警告消失，标题与 logo 字形一致
