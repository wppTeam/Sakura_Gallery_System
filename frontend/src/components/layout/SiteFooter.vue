<template>
  <footer class="site-footer">
    <div class="foot-noise" aria-hidden="true" />

    <div class="wrap foot-inner">
      <div class="foot-brand">
        <RouterLink class="wordmark" to="/" aria-label="视觉百花 · 回到首页">
          视觉<span class="wordmark-accent">百花</span>
        </RouterLink>
        <p class="foot-tag">北化学生自己的开源创作资源共享平台。<br />校园摄影、AI 生成图像与模板素材，保留作者署名与授权协议。</p>
      </div>

      <nav class="foot-grid" aria-label="页脚导航">
        <div class="foot-col">
          <h2 class="foot-head">校区</h2>
          <RouterLink v-for="campus in CAMPUSES" :key="campus" class="foot-link" :to="{ path: '/explore', query: { campus } }">
            {{ campus }}
          </RouterLink>
        </div>

        <div class="foot-col">
          <h2 class="foot-head">浏览</h2>
          <RouterLink class="foot-link" to="/explore">探索全部</RouterLink>
          <RouterLink class="foot-link" :to="{ path: '/', hash: '#seasons' }">四季</RouterLink>
          <RouterLink class="foot-link" :to="{ path: '/', hash: '#feed' }">最新作品</RouterLink>
          <RouterLink class="foot-link" :to="{ path: '/', hash: '#light' }">光的一日</RouterLink>
          <RouterLink class="foot-link" to="/creators">创作者</RouterLink>
        </div>

        <div class="foot-col">
          <h2 class="foot-head">参与</h2>
          <RouterLink class="foot-link" to="/upload">投稿</RouterLink>
          <a class="foot-link" :href="REPO_URL" target="_blank" rel="noopener noreferrer">开源仓库</a>
          <a class="foot-link" :href="`${REPO_URL}/blob/master/AGENTS.md`" target="_blank" rel="noopener noreferrer">开发指南</a>
        </div>

        <div class="foot-col">
          <h2 class="foot-head">项目</h2>
          <a class="foot-link" :href="REPO_URL" target="_blank" rel="noopener noreferrer">GitHub</a>
          <a class="foot-link" href="https://github.com/wppTeam" target="_blank" rel="noopener noreferrer">wppTeam</a>
          <button class="foot-link foot-top" type="button" @click="backToTop">回到顶部 ↑</button>
        </div>
      </nav>

      <div class="foot-credits">
        <p>
          照片按作者所选协议署名，完整署名与授权信息见作品详情页。四季节气与光的一日来自校园真实物候与光线，
          作为全站内容的索引方式；AIGC 作品均带显式标识。
        </p>
      </div>

      <div class="foot-last">
        <span>© 2026 视觉百花 · 北京化工大学学生自建开源项目</span>
        <span class="foot-last-right">
          <a :href="`${REPO_URL}#readme`" class="foot-last-link" target="_blank" rel="noopener noreferrer">关于</a>
          <span aria-hidden="true">·</span>
          <RouterLink class="foot-last-link" to="/terms">服务条款</RouterLink>
          <span aria-hidden="true">·</span>
          <RouterLink class="foot-last-link" to="/privacy">隐私政策</RouterLink>
          <span aria-hidden="true">·</span>
          <span>本站不收集非必要个人信息</span>
        </span>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
const REPO_URL = 'https://github.com/wppTeam/Sakura_Gallery_System'
const CAMPUSES = ['昌平校区', '朝阳校区', '海淀校区']

function backToTop() {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' })
}
</script>

<style scoped>
.site-footer {
  position: relative;
  overflow: hidden;
  padding-block: clamp(48px, 6vw, 84px) 26px;
  background: var(--sakura-pale);
}

/* 2.5% 噪点只铺页脚与首屏，其余保持纯净 */
.foot-noise {
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E");
  opacity: 0.025;
  mix-blend-mode: multiply;
  pointer-events: none;
}

.foot-inner {
  position: relative;
}

.foot-brand {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 12px 32px;
  justify-content: space-between;
  padding-bottom: clamp(28px, 4vw, 46px);
  border-bottom: 1px solid rgba(201, 58, 99, 0.16);
}

.wordmark {
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(56px, 12vw, 148px);
  letter-spacing: 0.03em;
  line-height: 0.95;
}

.wordmark:hover {
  color: var(--ink);
}

.wordmark-accent {
  color: var(--sakura);
}

.foot-tag {
  max-width: 30em;
  padding-bottom: 8px;
  color: var(--muted);
  font-size: var(--fs-xs);
  line-height: 1.9;
}

.foot-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 24px;
  padding-block: clamp(30px, 4vw, 48px);
}

.foot-head {
  margin-bottom: 12px;
  color: var(--ink);
  font-family: var(--font);
  font-size: var(--fs-xs);
  font-weight: 700;
  letter-spacing: var(--tracking-eyebrow);
}

.foot-col {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.foot-link {
  padding: 2px 0;
  color: var(--muted);
  font-size: var(--fs-sm);
  text-align: left;
  text-underline-offset: 4px;
}

.foot-link:hover {
  color: var(--sakura-deep);
  text-decoration: underline;
  text-decoration-thickness: 1px;
}

.foot-top {
  cursor: pointer;
}

.foot-credits {
  padding-top: 18px;
  border-top: 1px solid rgba(201, 58, 99, 0.16);
  color: var(--muted);
  font-size: var(--fs-xs);
  line-height: 1.9;
}

.foot-credits p {
  max-width: 62em;
}

.foot-last {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 24px;
  padding-top: 18px;
  padding-right: 72px;
  color: var(--faint);
  font-size: var(--fs-xs);
}

.foot-last-right {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.foot-last-link {
  color: var(--faint);
  text-underline-offset: 3px;
}

.foot-last-link:hover {
  color: var(--sakura-deep);
  text-decoration: underline;
}

@media (max-width: 900px) {
  .foot-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 26px 20px;
  }
}

@media (max-width: 720px) {
  .foot-credits {
    padding-right: 64px;
  }

  .foot-brand {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .foot-tag {
    padding-bottom: 0;
  }

  .wordmark {
    font-size: clamp(52px, 16vw, 72px);
  }
}
</style>
