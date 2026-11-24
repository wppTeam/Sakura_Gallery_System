<template>
  <div class="auth-page">
    <div class="auth-decor" aria-hidden="true">
      <span class="petal petal--1"></span>
      <span class="petal petal--2"></span>
      <span class="petal petal--3"></span>
      <span class="petal petal--4"></span>
      <span class="glow glow--a"></span>
      <span class="glow glow--b"></span>
    </div>

    <div class="auth-shell">
      <aside class="auth-aside" aria-hidden="true">
        <RouterLink class="auth-brand" to="/" tabindex="-1">
          <img
            class="auth-brand-logo"
            src="/brand/logo-combo-zh.png"
            alt="视觉百花"
            width="360"
            height="90"
          />
        </RouterLink>

        <p class="auth-aside-eyebrow">VISUAL BUCT · 视觉百花</p>
        <p class="auth-display">
          把校园的<br />
          每一次快门<br />
          留给后来的人
        </p>
        <p class="auth-aside-lead">
          北化学生自建的开源创作资源共享平台。摄影、AI 生成、模板素材，
          同一套发布、检索与授权机制。
        </p>

        <ul class="auth-points">
          <li>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M3 10.5 7.5 15 17 5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            原图只读、保留原始构图，不裁切
          </li>
          <li>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M10 2.5 3.5 5v5c0 3.6 2.7 6.4 6.5 7.5 3.8-1.1 6.5-3.9 6.5-7.5V5L10 2.5Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
              <path d="M7.4 10.2 9.3 12l3.4-3.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            人像默认脱敏，原图仅作者与管理员可见
          </li>
          <li>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <circle cx="10" cy="10" r="7.2" stroke="currentColor" stroke-width="1.6" />
              <path d="M10 6.4v3.9l2.6 1.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
            发布免审即发，精选由人与社区共同决定
          </li>
        </ul>

        <div class="auth-seasons" aria-hidden="true">
          <span class="auth-season is-spring">春 · 花信</span>
          <span class="auth-season is-summer">夏 · 绿荫</span>
          <span class="auth-season is-autumn">秋 · 银杏</span>
          <span class="auth-season is-winter">冬 · 初雪</span>
        </div>

        <p class="auth-quote">「十二番花信，一日四光，都是这套索引的坐标。」</p>
      </aside>

      <main class="auth-main">
        <div class="auth-main-top">
          <RouterLink class="auth-home" to="/">
            <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M12.5 4.5 7 10l5.5 5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            返回首页
          </RouterLink>
          <RouterLink class="auth-mobile-brand" to="/" aria-label="视觉百花 · 回到首页">
            <img src="/brand/logo-combo-zh.png" alt="视觉百花" width="360" height="90" />
          </RouterLink>
        </div>

        <div class="auth-card">
          <p v-if="eyebrow" class="auth-card-eyebrow">{{ eyebrow }}</p>
          <h1 class="auth-title">{{ title }}</h1>
          <p v-if="subtitle" class="auth-subtitle">{{ subtitle }}</p>

          <slot name="alert" />
          <slot />
          <slot name="footer" />
        </div>

        <p class="auth-legal">北京化工大学学生自建 · 开源创作资源共享平台</p>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  eyebrow?: string
  title: string
  subtitle?: string
}>()
</script>

<style scoped>
.auth-page {
  position: relative;
  min-height: 100dvh;
  overflow: hidden;
  background:
    radial-gradient(1100px 620px at 8% -10%, var(--sakura-pale, #ffe9f0) 0%, transparent 62%),
    radial-gradient(900px 560px at 106% 8%, var(--spring-tint, #ffeef4) 0%, transparent 58%),
    var(--ground, #fff6f9);
  color: var(--ink, #4a2b35);
}

.auth-decor {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.petal {
  position: absolute;
  width: 120px;
  height: 120px;
  border-radius: 62% 38% 58% 42% / 48% 56% 44% 52%;
  background: linear-gradient(140deg, rgba(232, 98, 140, 0.16), rgba(232, 98, 140, 0.03));
  filter: blur(1px);
}
.petal--1 { top: -34px; left: 4%; transform: rotate(24deg); }
.petal--2 { top: 16%; right: -30px; width: 180px; height: 180px; transform: rotate(-18deg); }
.petal--3 { bottom: 8%; left: -36px; width: 160px; height: 160px; transform: rotate(12deg); }
.petal--4 { bottom: -46px; right: 18%; width: 110px; height: 110px; transform: rotate(40deg); }

.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(4px);
  opacity: 0.5;
}
.glow--a {
  top: 8%;
  left: 34%;
  width: 220px;
  height: 220px;
  background: radial-gradient(circle, var(--spring-pale, #ffd7e4) 0%, transparent 70%);
}
.glow--b {
  bottom: 4%;
  right: 8%;
  width: 260px;
  height: 260px;
  background: radial-gradient(circle, var(--winter-pale, #d6e8f7) 0%, transparent 72%);
}

.auth-shell {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(420px, 480px);
  gap: clamp(32px, 5vw, 88px);
  align-items: center;
  width: min(1180px, 100%);
  min-height: 100dvh;
  margin-inline: auto;
  padding: clamp(24px, 4vw, 56px) var(--margin, 24px);
}

/* ── 左侧品牌区 ─────────────────────────────────────── */
.auth-aside {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: clamp(8px, 2vw, 24px) 0;
}

.auth-brand {
  display: inline-flex;
  width: fit-content;
  border-radius: 14px;
}
.auth-brand-logo {
  width: clamp(160px, 15vw, 196px);
  height: auto;
  display: block;
}

.auth-aside-eyebrow {
  margin: 6px 0 0;
  font-family: var(--font, 'Noto Sans SC', sans-serif);
  font-size: var(--fs-xs, 12px);
  font-weight: 600;
  letter-spacing: 0.22em;
  color: var(--sakura-deep, #c93a63);
}

.auth-display {
  margin: 0;
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: clamp(44px, 4.6vw, 60px);
  font-weight: 400;
  line-height: 1.08;
  letter-spacing: 0.02em;
  color: var(--ink, #4a2b35);
}

.auth-aside-lead {
  margin: 0;
  max-width: 21em;
  font-size: 16px;
  line-height: 1.85;
  color: var(--muted, #63474f);
}

.auth-points {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 2px 0 0;
  padding: 0;
  list-style: none;
}
.auth-points li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: var(--fs-sm, 14px);
  line-height: 1.7;
  color: var(--ink, #4a2b35);
}
.auth-points svg {
  flex: none;
  margin-top: 3px;
  color: var(--sakura-deep, #c93a63);
}

.auth-seasons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}
.auth-season {
  padding: 5px 12px;
  border-radius: var(--r-pill, 999px);
  font-size: var(--fs-xs, 12px);
  font-weight: 600;
  letter-spacing: 0.04em;
}
.auth-season.is-spring { background: var(--spring-pale, #ffd7e4); color: var(--spring, #e36089); }
.auth-season.is-summer { background: var(--summer-pale, #d4f0e4); color: var(--summer, #3b9c80); }
.auth-season.is-autumn { background: var(--autumn-pale, #ffdfd6); color: var(--autumn, #b5703c); }
.auth-season.is-winter { background: var(--winter-pale, #d6e8f7); color: var(--winter, #5692c8); }

.auth-quote {
  margin: 6px 0 0;
  padding-left: 14px;
  border-left: 3px solid var(--sakura, #e8628c);
  font-size: var(--fs-sm, 14px);
  line-height: 1.8;
  color: var(--muted, #63474f);
}

/* ── 右侧表单区 ─────────────────────────────────────── */
.auth-main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
}

.auth-main-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
}

.auth-home {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: var(--r-pill, 999px);
  font-size: var(--fs-sm, 14px);
  font-weight: 500;
  color: var(--muted, #63474f);
  text-decoration: none;
  transition: color var(--dur-fast, 160ms) var(--ease-out, ease), background var(--dur-fast, 160ms) var(--ease-out, ease);
}
.auth-home:hover {
  color: var(--sakura-deep, #c93a63);
  background: var(--sakura-wash, rgba(232, 98, 140, 0.08));
}
.auth-home:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring, 0 0 0 3px rgba(201, 58, 99, 0.35));
}

.auth-mobile-brand { display: none; }
.auth-mobile-brand img { width: 136px; height: auto; display: block; }

.auth-card {
  width: 100%;
  padding: clamp(22px, 3.4vw, 36px);
  border-radius: var(--r-card, 20px);
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  box-shadow: var(--shadow-lift, 0 12px 32px rgba(201, 58, 99, 0.16));
}

.auth-card-eyebrow {
  margin: 0 0 8px;
  font-size: var(--fs-xs, 12px);
  font-weight: 600;
  letter-spacing: 0.18em;
  color: var(--sakura-deep, #c93a63);
}

.auth-title {
  margin: 0;
  font-family: var(--font, 'Noto Sans SC', sans-serif);
  font-size: clamp(26px, 2.4vw, 32px);
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: 0.01em;
  color: var(--ink, #4a2b35);
}

.auth-subtitle {
  margin: 10px 0 0;
  font-size: var(--fs-sm, 14px);
  line-height: 1.75;
  color: var(--muted, #63474f);
}

.auth-legal {
  margin: 2px 0 0;
  text-align: center;
  font-size: var(--fs-xs, 12px);
  color: var(--faint, #9a8088);
}

/* ── 响应式 ─────────────────────────────────────────── */
@media (max-width: 980px) {
  .auth-shell {
    grid-template-columns: minmax(0, 1fr);
    max-width: 520px;
    min-height: auto;
    padding: 20px var(--margin, 24px) 40px;
    gap: 18px;
  }
  .auth-aside { display: none; }
  .auth-mobile-brand { display: inline-flex; }
  .auth-main { gap: 12px; }
  .auth-legal { margin-top: 8px; }
}

@media (max-width: 560px) {
  .auth-page { min-height: 100dvh; }
  .auth-shell { padding: 14px 16px 28px; }
  .auth-card { padding: 20px 16px; border-radius: var(--r-md, 14px); }
  .auth-home { padding: 6px 8px; }
}

@media (prefers-reduced-motion: reduce) {
  .auth-home { transition: none; }
}

/* 支持系统主题最小化动效偏好外的轻量入场：仅首次渲染的淡入 */
.auth-card {
  animation: auth-card-in var(--dur-slow, 420ms) var(--ease-out, cubic-bezier(0.22, 1, 0.36, 1)) both;
}
@keyframes auth-card-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .auth-card { animation: none; }
}
</style>
