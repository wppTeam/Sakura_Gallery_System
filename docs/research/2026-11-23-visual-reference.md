# 前端「惊艳」视觉参考与落地技法（2026-11-23）

> 用途：直接指导 `frontend/src` 的 fe-shell / fe-pages 落地，对应原型 `design/index.html` + `design/sakura.css`，
> token 以 `frontend/src/styles/tokens.css`（已读）与 `frontend/src/styles/motion.css`（已读）为准。
> 标签：**[官方]** 规范/文档；**[社区]** 业界经验/基准；**[本项目]** 原型与 token 现状。所有参考站点 2026-11-23 用 curl 验证可达。

## 0. 结论先行：TOP 10 提升点

| # | 动作 | 参数 | 为什么惊艳 | 风险 |
|---|---|---|---|---|
| 1 | **首屏一图一文**，不堆卡片：主视觉占 44%，右侧 92px 大标题 + 21px 副文 + 单一 CTA | 标题 `clamp(56,7.2vw,92)`、行高 1.1；副文 21/1.85 `--muted`；下留白 `--section-gap` | 影像优先站点的"贵感"来自第一屏的**比例与留白**，不是装饰 | 首屏过高会挤掉首图；≤1440 高 780 内必须露出下一节标题 |
| 2 | 瀑布流**保真比例 + 密度节奏**：列宽固定、行高随图；限制极端比例 | 列数 3/4/5（断点 768/1200）；`--gap: 20px`；宽高比限 `[0.55, 2.2]` | 真实比例混排是 Unsplash 与 Pinterest 的分水岭，也避免"长条图破坏节奏" | 比例极端多时列高差过大；用"最短列优先"分配 |
| 3 | 图片三件套：**`aspect-ratio` + `width/height` + LQIP + 渐显** | `420ms` opacity + `scale(1.02→1)` `--ease-out`；LQIP 20px base64 ≈300–600B | CLS=0 且不闪白，是"高级感"的地基 | LQIP 未生成时退化为占位色，不能留白 |
| 4 | 入场动效**收窄**：现 `--dur-reveal:700ms` + `stagger 70ms` 改 `420ms` / `40ms`，且**只作用于首屏与首屏列表**，后续直接显示 | `threshold 0.12`、`rootMargin 0 0 -8% 0`、`once` | 舞台感只应出现在"第一眼"；全站 reveal 是廉价动画的第一特征 | 改小后首屏显平；用首图 620ms 单独拉长补节奏 |
| 5 | hover 只做**图微缩放 + 操作条滑入**，禁止整卡上浮 | 图 `scale(1.015)` 180ms；操作条 `opacity 0→1, translateY(6px→0)` 180ms；`focus-within` 同步 | 克制的手感差异，最容易被感知为"精细" | 移动端无 hover；必须靠 `focus-within` + 常显作者名兜底 |
| 6 | 页面转场用 **View Transitions（同文档）**，360ms | `document.startViewTransition`；缓动 `--ease-out`；无支持则直接切换 | SPA 路由跳转的白闪是最伤"完成度"的细节 | Firefox 144+/Safari 18+ 才支持（2025-10 起 newly available）；须 feature-detect |
| 7 | 标题字体**只在 ≥44px 用**站酷庆科黄油体，字距 0.02em、行高 1.1 | 正文 16/1.75；行宽 `--measure: 24em`（CJK 用 em） | 圆体小字会糊；大字号才能展示圆润字形 | 92 分片 1.82MB 字体；首屏只预载 1–2 个分片 |
| 8 | 粉色**只做强调与极淡底**：70% 底 / 25% 白面 / ≤5% 樱粉 | 主按钮 `--sakura-deep #c93a63`；阴影 alpha ≤0.10；禁粉紫渐变 | 大面积亮粉 = 廉价；"樱花"的高级表达是**白与留白里的一点粉** | 粉太少会失去主题；靠四季淡底与角标补 |
| 9 | 质感只加一处：**2–3% 噪点**（首屏/页脚）+ 顶栏玻璃，其余纯净 | `feTurbulence` overlay `opacity:.025`；`backdrop-filter: blur(12px)` 仅顶栏 | 噪点消除"屏幕塑料感"；玻璃只做一层是精致，做满屏是 2019 | 噪点图会增加一次请求；用 SVG data-URI 内联 |
| 10 | 细节系统：focus ring 3px、`::selection` 樱粉、空态插画、错误态人话、键盘 ←→、toast「已保存」 | 见 §6 的 18 条 | 用户说"惊艳"，往往来自**交互细节的密度**而非大图 | 逐条验收成本高；按 §8 的 10 条截图检查即可 |

---

## 1. 参考站点 12 个（URL 均已验证可达）

| # | 站点 | 借鉴什么（具体机制） | 不要学什么 |
|---|---|---|---|
| 1 | **Unsplash** https://unsplash.com | 真实比例网格（`aspect-ratio: var(--w)/var(--h)`）、hover 才显操作、占位色+脉冲不用骨架闪、横向话题 chip | 商业下载堆叠、无终点的无限流、通栏黑白无品牌色 |
| 2 | **Cosmos** https://www.cosmos.so | "contact sheet"式密集策展、**元数据只在 hover 出现**、窄 gutter 的高级感、整页几乎无 chrome | 暗色底（与樱花白冲突）、密到没有呼吸 |
| 3 | **Are.na** https://www.are.na | 频道(channel)=天然对应"专辑"、图片与**文字块混排**、内容即界面 | 工具感的纯链接风、零动效 |
| 4 | **Savee** https://savee.it | 收藏动作的轻量反馈、tag pill 在 hover 时出现 | 高密度信息、卡片化过度 |
| 5 | **Layers** https://layers.to | 作者 chip 与头像的层级处理、精选大图行打破网格 | 卡片阴影堆叠、阴影颜色花 |
| 6 | **Magnum Photos** https://www.magnumphotos.com | 摄影集式编排：全宽图 → 大量留白 → 小字图注；图注排版严谨 | 黑白极简（与粉白方向冲突） |
| 7 | **Ignant** https://www.ignant.com | 超大标题 + 窄栏正文 + 编辑式留白；图片直接贴边 | 依赖极高质量原片，缺图时立刻塌 |
| 8 | **This Is Colossal** https://www.thisiscolossal.com | 图文混排的节奏（大图/双图/引语交替），不靠动效 | 广告位与侧栏、老式博客感 |
| 9 | **Apple 中国** https://www.apple.com/cn/ | 分节节奏、精确字距与大字号、sticky 视觉、滚动驱动的分镜 | 长滚动堆砌、文案过密 |
| 10 | **Readymag** https://readymag.com | 网格系统与字号对比的展示方式、作品集排版 | 过度装饰性动效 |
| 11 | **京都动画** https://www.kyotoanimation.co.jp | 日系留白的比例、细线分隔、克制的单色体系 | 信息量过少；我们仍需瀑布流承载内容 |
| 12 | **原神官网** https://ys.mihoyo.com | 二次元的**装饰克制用法**：细描边、小装饰件、大字+副标层级、立绘与底色关系 | 满屏漂浮粒子、金粉描边过多、重动画首屏 |

> 补充：Pinterest / Behance / 500px / Flickr 在本机网络不可达（curl 000/403），**未作为依据**；
> 任务里要求的"Pinterest 类"以 Cosmos + Savee 的密集策展机制替代参考。

## 2. 瀑布流与图片呈现

**实现方式（重要）**：原生 masonry `display: grid-lanes` 目前**只有 Safari 27.2 支持，Chrome/Firefox 均不支持**
（[官方] web-features explorer: Grid lanes = *Limited availability*）。因此继续用原型已验证的**列式 flex 分配**：
按"当前最短列"依次放卡，阅读顺序天然按列，比 CSS `columns` 更适合键盘/读屏。

```css
.masonry { display: flex; gap: var(--gap); align-items: flex-start; }
.masonry-col { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; gap: var(--gap); }
/* 卡片：宽高比来自真实图片，绝不裁切 */
.shot-media { aspect-ratio: var(--w) / var(--h); border-radius: var(--r-photo); background: var(--surface-soft); overflow: hidden; }
.shot-media img { width: 100%; height: 100%; object-fit: cover; display: block; } /* cover 仅用于同比例容器 */
```

**节奏与边界**：单列宽约 `(1320 - 24×2 - 20×(n-1)) / n`（n=3/4/5）；建议比例分布 ≈ 竖 2:3 30%、方 1:1 10%、横 3:2 40%、16:9 20%。
超出 `[0.55, 2.2]` 的极端图**限宽并留白居中**（不裁切、不拉伸）——这是"不土"的关键。

**避免 CLS 的具体做法**（[官方] Core Web Vitals：CLS 良好 < 0.1）：

1. 每张图给 `width`/`height` 属性 + CSS `aspect-ratio`，二者一致；
2. 容器底色 `--surface-soft`，LQIP 作为 `background-image` 或 `img` 的底层；
3. 顶栏固定 `--nav-h: 64px`（sticky 不改变文档流）；字体 `font-display: swap` 但标题先预留行高；
4. 首屏 2 张图 `fetchpriority="high"`，其余 `loading="lazy" decoding="async"`。

**渐进加载**：优先 **20px base64 LQIP**（≈300–600B、零 JS 解码成本）；
blurhash（https://blurha.sh/，[社区] 广泛使用）需 JS 解码 32×32，适合"氛围色块"；
thumbhash（https://evanw.github.io/thumbhash/，[社区]）约 25B 更省，但同样需要 JS。**采用 LQIP 为主、blurhash 备选**。

**渐显曲线**（与 `motion.css` 的 token 对齐）：

```css
.shot-media img { opacity: 0; transform: scale(1.02); transition: opacity 420ms var(--ease-out), transform 620ms var(--ease-out); }
.shot-media img.is-loaded { opacity: 1; transform: scale(1); }
```

**无限滚动边界**：哨兵 + `IntersectionObserver`（`rootMargin: '600px'`），24 条/页；
到底必须显示「已看完 · 共 N 张」+「回到顶部」；加载失败给重试按钮而不是静默重试。
长列表可加 `content-visibility: auto` + `contain-intrinsic-size`（[官方] MDN），但会与 reveal 动画轻微打架，谨慎启用。

## 3. 克制版动效系统

| 场景 | 时长 | 缓动 | 说明 |
|---|---|---|---|
| hover / 按下 | 120–180ms | `--ease-out` | 按下 `scale(0.985)` 90ms |
| 展开/收起、toast | 240ms | `--ease-soft` | 现有 `--dur` |
| 入场 reveal | **420ms**（原 700ms） | `--ease-out` | stagger **40ms**（原 70ms），同屏 ≤6 个元素 |
| 首屏主视觉 | 620ms | `--ease-out` | 唯一允许"慢"的地方 |
| 页面转场 | 360ms | `--ease-out` | 用 View Transitions |
| 花瓣飘落 | 12–22s linear | linear | 循环动画只允许 linear |

[官方] M3 动效 token 的时长分组：short 50–200ms / medium 250–400ms / long 450–600ms / extra-long 700–1000ms。
我们的系统应**整体落在 short–medium**，只有 hero 与花瓣进入 long —— 这就是"克制"的量化定义。

**入场（IntersectionObserver）参数**：`threshold: 0.12`、`rootMargin: '0px 0px -8% 0px'`、`once`；
`--reveal-i` 由 JS 写 0–5，超过 5 不再延迟（防止长列表末尾延迟 2s）。

**页面转场**（Vue Router 内）：

```ts
const go = async () => {
  if (!document.startViewTransition) return router.push(to);
  await document.startViewTransition(() => flushSync(() => router.push(to))).finished;
};
// CSS: ::view-transition-old(root){animation: fade-out 240ms} ::view-transition-new(root){animation: fade-in 360ms}
```

[官方] View Transitions 自 2025-10-14 起 "Newly available"（Chrome 111 / Safari 18 / Firefox 144 起），
仍非 "Widely available"（预计 2028-04），**必须 feature-detect**，无支持时直接切换。

**视差**：只允许 hero 一处，`translate3d(0, scrollY * 0.06, 0)` 且 `Math.min(40px)`，rAF 节流；
**禁止** `background-attachment: fixed`（移动端掉帧）。[官方] scroll-driven animations 自 2026-10-27 "Newly available"
（Chrome 115 / Safari 26 / Firefox 159），可作渐进增强，但别作为唯一实现。

**花瓣/光斑性能上限** [社区]：CSS transform 动画在合成线程，12–20 个元素 ≈ 0 主线程成本；
超过 ~30 个或要物理碰撞再上 canvas（2D 300 粒子 ≈ 3–6ms/帧，估算）。移动端 ≤6 个，`prefers-reduced-motion` 下 0 个。
**禁止**：scroll-jacking、鼠标跟随大位移、每张卡独立 animation、`will-change` 常驻。

**reduced-motion**：现有 `motion.css` 已全局降级，补一条——保留 opacity 变化（信息性），
去掉位移/缩放/视差/花瓣；`.petals` 已 `display:none`，保持。

## 4. 字体与排版

**站酷庆科黄油体用法**：只用于 **≥44px** 的标题与数字；字距 `0.02em`（不要更大，中文会散）；行高 1.1；
禁用于正文/按钮/小字（圆体小字笔画粘连）；**不要合成粗体**（faux bold 会糊边），靠字号与字重天然对比。
字体自托管见 `design/fonts/zcool/`（92 分片、1.82MB），首屏仅 `preload` 用到的 1–2 个分片。

**三组「大标题 + 副文」组合**（token 引用自 `tokens.css`）：

| 场景 | 大标题 | 副文 | 备注 |
|---|---|---|---|
| 首屏 | `--fs-display` `clamp(56,7.2vw,92)` / `--lh-tight 1.1` / `--ink` 庆科 | `--fs-lead 21` / `--lh-lead 1.85` / `--muted`，`max-width: var(--measure-lead) 21em` | eyebrow `12px/0.16em` `--sakura-deep` |
| 区块标题 | `--fs-h2` `clamp(28,3.2vw,44)` / `--lh-title 1.22` / `--ink` | `--fs-body 16` / `--lh-body 1.75` / `--muted`，`max-width: var(--measure) 24em` | 标题与正文间 12–16px |
| 详情页 | 44 庆科 / 1.22 / `--ink` | meta `14/1.5` `--muted`；图注 `12` 前加 2px `--sakura-pale` 竖线 | 正文 `24em` 行宽 |

**CJK 排版**：[官方] W3C《中文排版需求》(clreq) 对行宽与标点的约定；本项目实测坑：
`ch` 在中文下 ≈ 半个汉字宽，**行宽一律 `em`**（`--measure: 24em` ≈ 24 字，舒适区 20–32 字）。
数字/日期用 `font-variant-numeric: tabular-nums`；中英混排加 `text-spacing-trim`（渐进）或手工空格。

## 5. 色彩与质感：让粉色不廉价

**廉价粉的三个来源**：① 大面积高饱和粉填充 ② 粉→紫渐变 ③ 粉字配白底小字号。
规则：樱粉只出现在 **① ≥44px 大字 ② 小面积强调（≤5% 面积）③ 极淡底**；主按钮一律 `--sakura-deep #c93a63`（4.9:1）。

| 项 | 规则 | 现状 |
|---|---|---|
| 配比 | **70% 底 `#fff6f9` / 25% 白面 / ≤5% 樱粉** | token 已有；靠控制 hero/CTA 面积落地 |
| 饱和度 | 粉的 HSV S ≤ 70% / OKLCH chroma ≤ 0.16（[社区] 经验阈值）；禁 `#ff69b4` 大块 | `--sakura #e8628c` 已达标 |
| 阴影 | **只用一种**粉影，alpha ≤0.10；hover 才升 `--shadow-lift` | token 已分 soft/lift/card，页面只许用 soft 与 lift |
| 对比度 | 正文 ≥4.5:1（本项目实际 7.8–11.7:1）；大字 ≥3:1（[官方] WCAG 1.4.3） | 达标 |
| 玻璃拟态 | **只用于 sticky 顶栏**：`backdrop-filter: blur(12px) saturate(1.1)` + 88% 白底；卡片一律不用 | 待落地 |
| 噪点 | SVG `feTurbulence` overlay，`opacity: .025`，只铺首屏与页脚；`pointer-events:none` | 待落地 |
| 四季 | 只做**整块色域**（banner/区块底），文字深墨；强调色只用于 eyebrow/线/图标；禁止四季间渐变 | 规则已定 |
| 深色模式 | **不做**（粉白是品牌资产），避免半成品 | 明确不做 |

## 6. 交互细节清单（18 条，可勾选）

| # | 触发 | 表现 | 参数 |
|---|---|---|---|
| 1 | 首屏主视觉加载 | 620ms 渐显 + 1.04→1 缩放 | `--ease-out` |
| 2 | 卡片 hover | 图 `scale(1.015)`；操作条滑入 | 180ms |
| 3 | 卡片键盘 focus | focus ring + 显示操作条（`focus-within`） | 3px ring |
| 4 | 收藏 | 心形 1→1.2→1，计数 +1，按钮 aria-pressed | 180ms |
| 5 | 下载 | 按钮 loading → toast「已保存 · 文件名」 | 3s |
| 6 | 搜索框 focus | 容器 ring + 建议面板 8px 上滑淡入 | 160ms |
| 7 | 搜索建议 | ↑↓ 选择、Enter 进入、Esc 关闭、`aria-activedescendant` | — |
| 8 | 空态 | 插画 + 一句可执行建议 + 「清除筛选」 | 插画 ≤120KB WebP |
| 9 | 错误态 | 人话 + 重试按钮；不暴露 stack | — |
| 10 | 图片查看器开关 | 320ms 开 / 240ms 关，背景 `rgba(74,43,53,.72)` | — |
| 11 | 图片键盘 | Esc 关、←→ 切换、`+/-` 缩放、`0` 复位 | — |
| 12 | 移动端 | 双击缩放、左右滑切换、下滑关闭 | 手势阈值 30% |
| 13 | 回到顶部 | 滚动 >2 屏淡入，点击平滑回顶 | 180ms |
| 14 | 加载更多 | 3 张骨架卡（脉冲），不用 spinner | 现有 `ph-pulse` |
| 15 | 复制引用 | 文案变「已复制」+ 图标切换 | 1.5s |
| 16 | 筛选 chip | 背景 120ms 过渡 + `scale(.97)` 按下 | — |
| 17 | 页脚署名 | 下划线 3px offset（原型已有） | — |
| 18 | toast 统一 | 底部 12px 滑入、240ms、3s 消失、可手动关闭、`role=status` | — |

## 7. 反向清单：12 条"土/廉价/AI 味"做法

| 做法 | 为什么廉价 | 替代 |
|---|---|---|
| 粉→紫渐变按钮 | 典型 AI 生成审美 | 纯色 `--sakura-deep` + 1px 内描边 |
| 满屏飘落花瓣（>30） | 廉价且掉帧 | ≤12 个 CSS 花瓣，移动端 ≤6 |
| emoji 当图标 | 平台不一致、幼齿 | 统一 1.6px stroke SVG（原型已用） |
| 全站玻璃卡片 | 2019 味 + 低端机卡 | 只在顶栏 |
| 彩色/彩虹阴影 | 玩具感 | 单色 10% 樱影 |
| 卡片整卡上浮+大阴影+描边三件套 | 堆砌 | 只做图片 1.5% 微缩放 |
| 每个元素都 fade-up | 舞台感、慢 | 只首屏与首屏列表 |
| 圆角随机（12/18/20/28 混用） | 无系统感 | 只用 token 四档 |
| 纯黑 `#000` 正文 | 过硬 | `--ink #4a2b35` |
| 小字用庆科圆体 | 糊、不可读 | 正文 Noto Sans SC |
| 标题渐变文字 | AI 味 | 纯色 + 字距 0.02em |
| 自动轮播/自动播放视频 | 打断、耗电 | 静态首图 + 手动播放 |

## 8. 「惊艳」验收清单（10 条，可截图对照）

1. **1440 首屏**：标题 ≥84px，首屏可见 ≥4 张图，无横向滚动，主标题到副文留白 ≥24px。
2. **390 移动首屏**：标题不超 3 行，CTA 在首屏内，花瓣 ≤6 或关闭。
3. **瀑布流**：任意两卡同宽不同高；随机取 3 张与后端原图对比，**构图零裁切**。
4. **CLS**：DevTools Performance 录屏，CLS < 0.1（目标是 0），图片无跳动。
5. **hover 截图**：操作条仅 hover 出现，作者名不遮主体，按钮对比度可读。
6. **动效录制**：入场 stagger 总时长 ≤600ms，单元素位移 ≤20px，无回弹。
7. **reduced-motion 截图**：开系统减弱动效后，无位移/无花瓣/内容全部可见。
8. **对比度**：正文 ≥4.5:1（实为 7.8+）、大字 ≥3:1，DevTools 取色各截一张。
9. **键盘**：Tab 依次走完首屏可交互元素，focus ring 全程可见且不被 overflow 裁掉。
10. **性能**：Lighthouse 移动端 Performance ≥90，LCP ≤2.5s，CLS <0.1（[官方] CWV 阈值）。

## 9. 来源

- [官方] 原生 masonry（`display: grid-lanes`）仅 Safari 27.2 支持：https://web-platform-dx.github.io/web-features-explorer/features/grid-lanes/
- [官方] View Transitions 支持矩阵（2025-10-14 newly available）：https://web-platform-dx.github.io/web-features-explorer/features/view-transitions/
- [官方] Scroll-driven animations（2026-10-27 newly available）：https://web-platform-dx.github.io/web-features-explorer/features/scroll-driven-animations/
- [官方] MDN `prefers-reduced-motion`：https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion
- [官方] MDN `IntersectionObserver`：https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API
- [官方] MDN `content-visibility`：https://developer.mozilla.org/en-US/docs/Web/CSS/content-visibility
- [官方] WCAG 2.2 焦点外观（≥2px、对比 3:1）：https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html
- [官方] WCAG 2.2 对比度（正文 4.5:1 / 大字 3:1）：https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- [官方] W3C 中文排版需求 clreq：https://www.w3.org/TR/clreq/
- [官方] Material 3 动效时长/缓动 token：https://m3.material.io/styles/motion/easing-and-duration/tokens-specs
- [官方] 站酷庆科黄油体（Google Fonts）：https://fonts.google.com/specimen/ZCOOL+QingKe+HuangYou
- [社区] NN/g 响应时间三档（0.1s / 1s / 10s）：https://www.nngroup.com/articles/response-times-3-important-limits/
- [社区] NN/g 骨架屏：https://www.nngroup.com/articles/skeleton-screens/
- [社区] blurhash：https://blurha.sh/ ｜ thumbhash：https://evanw.github.io/thumbhash/
- [社区] CSS masonry 现状与列式方案：https://css-tricks.com/piecing-together-approaches-for-a-css-masonry-layout/
- [注] `web.dev`（CLS/CWV 正文）在本机网络不可达，以上 CWV 阈值（CLS<0.1、LCP≤2.5s、INP≤200ms）为公开通行值，未抓正文复核。
