<template>
  <div class="home">
    <!-- ============ 首屏 ============ -->
    <section class="hero" aria-labelledby="hero-title">
      <div class="hero-noise" aria-hidden="true" />
      <div class="hero-petals" aria-hidden="true">
        <span
          v-for="(petal, index) in PETALS"
          :key="index"
          class="petal"
          :style="petal"
        />
      </div>

      <div class="wrap hero-grid">
        <div class="hero-copy">
          <p class="eyebrow hero-eyebrow hero-enter" style="--enter: 0ms">
            VISUAL BUCT · 北化学生自建开源平台
          </p>

          <h1 id="hero-title" class="hero-title hero-enter" style="--enter: 60ms">
            <span class="hero-title-ink">视觉</span><span class="hero-title-sakura">百花</span>
          </h1>

          <p class="hero-lead hero-enter" style="--enter: 120ms">
            北化学生自己的开源图像平台。<br />校园的一年，由十二番花信与八处景名索引。
          </p>

          <div class="hero-search hero-enter" style="--enter: 180ms">
            <SearchBar
              v-model="heroKeyword"
              size="lg"
              placeholder="搜花信、景名或作者"
              button-text="搜索"
              @submit="goSearch"
            />
          </div>

          <p class="hero-now hero-enter" style="--enter: 240ms">
            <span class="now-dot" aria-hidden="true" />
            此刻 <strong>{{ nowTerm.name }}</strong> · {{ nowSeason.label }} ·
            下一番花信 <strong>{{ nextBloomInfo.text }}</strong>
          </p>

          <p class="hero-stats hero-enter" style="--enter: 300ms">
            <a class="hero-stat-link" :href="`#feed`">{{ totalText }}</a>
            <span class="hero-stat-sep" aria-hidden="true">·</span>
            <span>十二番花信</span>
            <span class="hero-stat-sep" aria-hidden="true">·</span>
            <span>八处景名</span>
          </p>
        </div>

        <figure class="hero-figure hero-enter" style="--enter: 100ms">
          <img
            class="hero-img"
            src="/art/hero.webp"
            alt="樱花落在北化校园的插画：粉色花枝与教学楼"
            width="1440"
            height="810"
            fetchpriority="high"
            decoding="async"
          />
          <figcaption class="hero-credit">视觉百花 主视觉 · 项目自制</figcaption>
        </figure>
      </div>
    </section>

    <!-- ============ 最新作品 ============ -->
    <section id="feed" class="section feed-section" aria-labelledby="feed-title">
      <div class="wrap">
        <SectionHeader
          title-id="feed-title"
          eyebrow="LATEST"
          title="校园的样子"
          :description="`每一张都保留原始构图与作者署名。${activeSeason ? `${activeSeason.label}正在被看见。` : '从此刻的光开始。'}`"
          :count="feedCountText"
          more-label="全部作品"
          more-to="/explore"
        >
          <template #default>
            <div class="topic-row" role="group" aria-label="按季节筛选最新作品">
              <TopicChip label="全部" :active="!activeSeason" @select="selectSeason(null)" />
              <TopicChip
                v-for="season in SEASONS"
                :key="season.key"
                :label="season.char"
                :season="season.key"
                :active="activeSeason?.key === season.key"
                :count="seasonCounts[season.key] || undefined"
                @select="selectSeason(season)"
              />
            </div>
          </template>
        </SectionHeader>

        <div v-if="feedError" class="feed-state" role="status">
          <EmptyState
            :title="'作品暂时没加载出来'"
            :description="feedError"
            action-label="重试"
            error
            @action="loadFeed()"
          />
        </div>
        <EmptyState
          v-else-if="!feedLoading && latest.length === 0"
          title="这里还没有作品"
          description="第一批照片正在路上。你也可以成为第一个把校园放进来的人。"
          action-label="去投稿"
          @action="$router.push('/upload')"
        />
        <MasonryGrid
          v-else
          :items="latest"
          :loading="feedLoading"
          :max-columns="3"
          :skeleton-rows="3"
          eager
        />

        <div class="feed-foot">
          <RouterLink class="link-arrow" to="/explore">
            进入探索页
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M3 8h9M8.5 3.8 12.7 8l-4.2 4.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </RouterLink>
        </div>
      </div>
    </section>

    <!-- ============ 四季 ============ -->
    <section id="seasons" class="seasons" aria-labelledby="seasons-title">
      <div class="wrap seasons-head">
        <SectionHeader
          title-id="seasons-title"
          eyebrow="FOUR SEASONS"
          title="一年四时，各有各的颜色"
          description="以节气与花信为轴，校园的四季被拆成八个景名与十二番花期。"
        />
      </div>

      <SeasonBand
        v-for="(season, index) in SEASONS"
        :key="season.key"
        :season="season"
        :index="index + 1"
        :photos="seasonPhotos[season.key]"
        :count="seasonTotals[season.key]"
        :loading="seasonLoading[season.key]"
        :flip="index % 2 === 1"
      />
    </section>

    <!-- ============ 主题专题 ============ -->
    <section
      v-if="collections.length || collectionsLoading"
      id="collections"
      class="section collections-section"
      aria-labelledby="collections-title"
    >
      <div class="wrap">
        <SectionHeader
          title-id="collections-title"
          eyebrow="CURATED COLLECTIONS"
          title="主题专题"
          description="年度相册、校园四季，按作者原意策展——一条被认真排过序的观看路线。"
          more-label="全部专题"
          more-to="/collections"
        />

        <div
          v-if="collectionsLoading && !collections.length"
          class="collections-rail"
          aria-hidden="true"
        >
          <div
            v-for="index in 4"
            :key="index"
            class="collections-rail-cell"
          >
            <div class="collections-skeleton" />
          </div>
        </div>

        <ul v-else class="collections-rail" aria-label="主题专题列表" tabindex="0">
          <li
            v-for="collection in collections"
            :key="collection.slug"
            class="collections-rail-cell"
          >
            <CollectionCard :collection="collection" />
          </li>
        </ul>
      </div>
    </section>

    <!-- ============ 北化八景 ============ -->
    <section id="views" class="section views-section" aria-labelledby="views-title">
      <div class="wrap">
        <SectionHeader
          title-id="views-title"
          eyebrow="EIGHT SCENES"
          title="北化八景"
          description="八个景名，是几代北化人共同的坐标。点开任意一景，看它在不同季节的样子。"
          more-label="在探索页筛选"
          :more-to="{ path: '/explore', query: { landscape: EIGHT_VIEWS[0].node } }"
        />

        <ul class="views-grid">
          <li v-for="(view, index) in EIGHT_VIEWS" :key="view.node">
            <RouterLink class="view-card" :to="{ path: '/explore', query: { landscape: view.node } }">
              <span class="view-num" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
              <span class="view-body">
                <span class="view-name">{{ view.name }}</span>
                <span class="view-hint">看这一景的作品</span>
              </span>
              <svg class="view-arrow" width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
                <path d="M3.5 9h10M9.2 4.4 13.8 9l-4.6 4.6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </RouterLink>
          </li>
        </ul>
      </div>
    </section>

    <!-- ============ 投稿 CTA ============ -->
    <section id="join" class="section join-section" aria-labelledby="join-title">
      <div class="wrap">
        <div class="join-card">
          <div class="join-copy">
            <p class="eyebrow">JOIN IN</p>
            <h2 id="join-title" class="join-title">把你的校园<br />也放进来</h2>
            <p class="join-lead">
              投稿即发布。原图保留原始构图，署名与授权协议由你选择；AI 生成图像会自动带上显式标识。
            </p>
            <div class="join-actions">
              <RouterLink class="btn btn--primary btn--lg" to="/upload">开始投稿</RouterLink>
              <RouterLink class="btn btn--ghost btn--lg" to="/explore">先逛逛</RouterLink>
            </div>
            <p class="join-note">支持 JPG / PNG / WebP，单张不超过 50MB。</p>
          </div>

          <figure class="join-figure">
            <img
              v-if="joinPhoto"
              class="join-img"
              :src="joinPhoto.thumbUrl"
              :alt="joinPhoto.title"
              width="900"
              height="675"
              loading="lazy"
              decoding="async"
            />
            <img v-else class="join-img" src="/art/spring.webp" alt="春季季相插画" width="1472" height="1140" loading="lazy" decoding="async" />
            <figcaption class="join-credit">
              {{ joinPhoto ? `《${joinPhoto.title}》 · ${joinPhoto.author}` : '季相插画 · AI 生成' }}
            </figcaption>
          </figure>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchPublicPhotos, type PublicPhoto } from '../api/public'
import {
  EIGHT_VIEWS,
  SEASONS,
  currentSeason,
  currentTerm,
  nextBloom,
  type SeasonKey,
  type SeasonMeta,
} from '../constants/public'
import EmptyState from '../components/public/EmptyState.vue'
import CollectionCard from '../components/public/CollectionCard.vue'
import MasonryGrid from '../components/public/MasonryGrid.vue'
import SearchBar from '../components/public/SearchBar.vue'
import SeasonBand from '../components/public/SeasonBand.vue'
import SectionHeader from '../components/public/SectionHeader.vue'
import TopicChip from '../components/public/TopicChip.vue'
import { fetchCollections, type CollectionSummary } from '../api/collections'

const router = useRouter()

/* ---------- 首屏：此刻（真实节气历法） ---------- */
const nowTerm = currentTerm()
const nowSeason = currentSeason()
const upcomingBloom = nextBloom()
const nextBloomInfo = {
  text: `${upcomingBloom.month}月${upcomingBloom.ten}的${upcomingBloom.name}`,
}

const PETALS = Array.from({ length: window.innerWidth <= 720 ? 6 : 10 }, (_, index) => {
  const left = [6, 22, 37, 51, 64, 78, 90, 14, 46, 70][index % 10]
  const drift = [46, -38, 30, -52, 24, 38, -30, 58, -44, 20][index % 10]
  const spin = [320, -280, 360, -330, 260, -300, 340, -260, 300, -350][index % 10]
  return {
    left: `${left}%`,
    top: `${-6 - (index % 4) * 4}%`,
    '--drift': `${drift}px`,
    '--spin': `${spin}deg`,
    '--petal-opacity': index % 3 === 0 ? '0.5' : '0.32',
    '--travel': `${560 + (index % 5) * 46}px`,
    width: `${9 + (index % 4) * 2}px`,
    height: `${8 + (index % 4) * 2}px`,
    animationDuration: `${15 + (index % 5) * 1.6}s`,
    animationDelay: `${-index * 1.7}s`,
  } as Record<string, string>
})

const heroKeyword = ref('')
const total = ref(0)

const totalText = computed(() => (total.value ? `已收录 ${total.value} 件作品` : '正在收录校园的四季'))

function goSearch(keyword: string) {
  router.push(keyword ? { path: '/search', query: { q: keyword } } : { path: '/search' })
}

/* ---------- 最新作品（真实 API） ---------- */
const latest = ref<PublicPhoto[]>([])
const feedLoading = ref(true)
const feedError = ref('')
const activeSeason = ref<SeasonMeta | null>(null)
const seasonCounts = ref<Partial<Record<SeasonKey, number>>>({})

const feedCountText = computed(() => {
  const count = activeSeason.value ? seasonCounts.value[activeSeason.value.key] || 0 : total.value
  return count ? `共 ${count} 张` : '—'
})

async function loadFeed() {
  feedLoading.value = true
  feedError.value = ''
  try {
    const page = await fetchPublicPhotos({
      limit: 12,
      season: activeSeason.value?.label,
      sort_by: 'published_at',
      sort_order: 'desc',
    })
    latest.value = page.items
    if (!activeSeason.value) total.value = page.total
    else seasonCounts.value = { ...seasonCounts.value, [activeSeason.value.key]: page.total }
  } catch (error) {
    latest.value = []
    feedError.value = '网络或服务暂时不可用，请稍后重试。'
    console.warn('[home] 最新作品加载失败', error)
  } finally {
    feedLoading.value = false
  }
}

function selectSeason(season: SeasonMeta | null) {
  if (activeSeason.value?.key === season?.key) return
  activeSeason.value = season
  loadFeed()
}

/* ---------- 四季（每季取 4 张真实作品） ---------- */
const seasonPhotos = ref<Record<SeasonKey, PublicPhoto[]>>({
  spring: [],
  summer: [],
  autumn: [],
  winter: [],
})
const seasonTotals = ref<Partial<Record<SeasonKey, number>>>({})
const seasonLoading = ref<Record<SeasonKey, boolean>>({
  spring: true,
  summer: true,
  autumn: true,
  winter: true,
})

async function loadSeasons() {
  await Promise.allSettled(
    SEASONS.map(async (season) => {
      try {
        const page = await fetchPublicPhotos({
          season: season.label,
          limit: 4,
          sort_by: 'published_at',
          sort_order: 'desc',
        })
        seasonPhotos.value = { ...seasonPhotos.value, [season.key]: page.items }
        seasonTotals.value = { ...seasonTotals.value, [season.key]: page.total }
        seasonCounts.value = { ...seasonCounts.value, [season.key]: page.total }
      } catch (error) {
        console.warn(`[home] ${season.label}作品加载失败`, error)
      } finally {
        seasonLoading.value = { ...seasonLoading.value, [season.key]: false }
      }
    }),
  )
}

const joinPhoto = computed(() => latest.value[0] || null)

/* ---------- 主题专题（策展集合） ---------- */
const collections = ref<CollectionSummary[]>([])
const collectionsLoading = ref(true)

async function loadCollections() {
  collectionsLoading.value = true
  try {
    const data = await fetchCollections({ limit: 12 })
    collections.value = data.items
  } catch (error) {
    collections.value = []
    console.warn('[home] 主题专题加载失败', error)
  } finally {
    collectionsLoading.value = false
  }
}

onMounted(() => {
  loadFeed()
  loadSeasons()
  loadCollections()
})
</script>

<style scoped>
/* ============================================================
   首屏
   ============================================================ */
.hero {
  position: relative;
  overflow: hidden;
  padding-block: clamp(36px, 5.4vw, 74px) clamp(44px, 6vw, 84px);
}

.hero-noise {
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E");
  opacity: 0.022;
  mix-blend-mode: multiply;
  pointer-events: none;
}

.hero-grid {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 44fr) minmax(0, 56fr);
  gap: clamp(32px, 5vw, 76px);
  align-items: center;
}

.hero-copy {
  position: relative;
  z-index: 1;
  max-width: 34em;
}

.hero-eyebrow {
  color: var(--sakura-deep);
}

.hero-title {
  margin-top: 18px;
  font-family: var(--display);
  font-size: var(--fs-display);
  letter-spacing: 0.02em;
  line-height: 1.02;
}

.hero-title-ink {
  color: var(--ink);
}

.hero-title-sakura {
  color: var(--sakura);
}

.hero-lead {
  max-width: var(--measure-lead);
  margin-top: 22px;
  color: var(--muted);
  font-size: var(--fs-lead);
  line-height: var(--lh-lead);
}

.hero-search {
  margin-top: 28px;
  max-width: 560px;
}

.hero-now {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.hero-now strong {
  color: var(--ink);
  font-weight: 500;
}

.now-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--sakura);
  box-shadow: 0 0 0 4px rgba(232, 98, 140, 0.14);
}

.hero-stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
  color: var(--faint);
  font-size: var(--fs-xs);
}

.hero-stat-link {
  color: var(--muted);
  text-underline-offset: 4px;
}

.hero-stat-link:hover {
  color: var(--sakura-deep);
  text-decoration: underline;
}

.hero-stat-sep {
  opacity: 0.6;
}

/* 首屏主视觉：唯一允许 620ms 慢入场的地方 */
.hero-figure {
  position: relative;
  margin: 0;
  overflow: hidden;
  border-radius: var(--r-card);
  background: var(--sakura-mist);
  box-shadow: var(--shadow-soft);
}

.hero-img {
  width: 100%;
  aspect-ratio: 1440 / 810;
  object-fit: cover;
}

.hero-credit {
  position: absolute;
  right: 14px;
  bottom: 14px;
  padding: 6px 12px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.9);
  color: var(--ink);
  font-size: 11px;
  letter-spacing: 0.03em;
  backdrop-filter: blur(4px);
}

/* 入场：只作用于首屏，且只做透明度 + 轻微位移 */
.hero-enter {
  animation: hero-rise 620ms var(--ease-out) both;
  animation-delay: var(--enter, 0ms);
}

@keyframes hero-rise {
  from {
    opacity: 0;
    transform: translate3d(0, 16px, 0) scale(0.995);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

/* 花瓣：≤12，只飘在首屏内 */
.hero-petals {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.petal {
  position: absolute;
  top: 0;
  border-radius: 60% 0 60% 0;
  background: linear-gradient(135deg, var(--sakura-pale), var(--sakura));
  opacity: 0;
  animation-name: hero-petal;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
}

@keyframes hero-petal {
  0% {
    opacity: 0;
    transform: translate3d(0, -30px, 0) rotate(0deg);
  }
  8% {
    opacity: var(--petal-opacity, 0.4);
  }
  90% {
    opacity: var(--petal-opacity, 0.4);
  }
  100% {
    opacity: 0;
    transform: translate3d(var(--drift, 30px), var(--travel, 560px), 0) rotate(var(--spin, 320deg));
  }
}

/* ============================================================
   最新作品
   ============================================================ */
.feed-section {
  padding-top: clamp(40px, 5vw, 64px);
}

.topic-row {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  max-width: 100%;
  padding: 2px 2px 6px;
  scrollbar-width: none;
}

.topic-row::-webkit-scrollbar {
  display: none;
}

.feed-state {
  padding-block: 8px;
}

.feed-foot {
  display: flex;
  justify-content: center;
  margin-top: clamp(28px, 3.4vw, 44px);
}

/* ============================================================
   四季
   ============================================================ */
.seasons-head {
  padding-block: clamp(24px, 3vw, 40px) clamp(8px, 1.6vw, 18px);
}

/* ============================================================
   八景
   ============================================================ */
.views-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--gap-sm);
  margin-top: clamp(24px, 3vw, 36px);
}

.view-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  height: 100%;
  padding: 20px 18px;
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
  transition: border-color var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}

.view-card:hover {
  border-color: var(--sakura-pale);
  box-shadow: var(--shadow-soft);
  transform: translateY(-2px);
}

.view-num {
  color: var(--sakura);
  font-family: var(--display);
  font-size: 22px;
  line-height: 1;
  letter-spacing: 0.02em;
}

.view-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.view-name {
  color: var(--ink);
  font-family: var(--font);
  font-size: 21px;
  font-weight: 700;
  letter-spacing: 0.02em;
  line-height: 1.2;
}

.view-hint {
  color: var(--faint);
  font-size: var(--fs-xs);
  opacity: 0;
  transform: translateY(2px);
  transition: opacity var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}

.view-card:hover .view-hint,
.view-card:focus-visible .view-hint {
  opacity: 1;
  transform: translateY(0);
}

.view-arrow {
  margin-left: auto;
  align-self: center;
  color: var(--faint);
  transition: transform var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}

.view-card:hover .view-arrow {
  color: var(--sakura-deep);
  transform: translateX(3px);
}

/* ============================================================
   投稿 CTA
   ============================================================ */
.join-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.86fr);
  gap: clamp(24px, 4vw, 56px);
  align-items: center;
  padding: clamp(28px, 4.4vw, 56px);
  border-radius: var(--r-lg);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.join-title {
  margin-top: 14px;
  font-size: var(--fs-h2);
  letter-spacing: 0.03em;
  line-height: 1.16;
}

.join-lead {
  max-width: 26em;
  margin-top: 16px;
  color: var(--muted);
  font-size: var(--fs-sm);
  line-height: 1.85;
}

.join-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 24px;
}

.join-note {
  margin-top: 14px;
  color: var(--faint);
  font-size: var(--fs-xs);
}

.join-figure {
  position: relative;
  margin: 0;
  overflow: hidden;
  border-radius: var(--r-photo);
  background: var(--sakura-mist);
}

.join-img {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
}

.join-credit {
  position: absolute;
  left: 12px;
  bottom: 12px;
  max-width: calc(100% - 24px);
  overflow: hidden;
  padding: 6px 12px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.92);
  color: var(--ink);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
  backdrop-filter: blur(4px);
}

/* ============================================================
   响应式
   ============================================================ */
@media (max-width: 1100px) {
  .hero-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 36px;
  }

  .hero-copy {
    max-width: none;
  }

  .hero-figure {
    order: 2;
  }

  .views-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .join-card {
    grid-template-columns: minmax(0, 1fr);
  }

  .join-figure {
    order: -1;
  }
}

@media (max-width: 720px) {
  .hero {
    padding-top: 22px;
  }

  .hero-title {
    font-size: clamp(52px, 16vw, 76px);
  }

  .hero-lead {
    margin-top: 16px;
    font-size: var(--fs-body);
    line-height: 1.8;
  }

  .hero-search {
    margin-top: 20px;
  }

  .hero-petals {
    opacity: 0.7;
  }

  .hero-credit {
    right: 10px;
    bottom: 10px;
    font-size: 10px;
  }

  .views-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .view-card {
    padding: 14px 12px;
  }

  .view-name {
    font-size: 20px;
  }

  .view-arrow {
    display: none;
  }

  .join-card {
    padding: 22px 18px;
    border-radius: var(--r-card);
  }
}

/* 减弱动效：隐藏花瓣，取消首屏位移 */
@media (prefers-reduced-motion: reduce) {
  .hero-petals {
    display: none;
  }

  .hero-enter {
    animation: none;
  }
}

/* ============================================================
   主题专题
   ============================================================ */
.collections-section {
  overflow: hidden;
}

.collections-rail {
  display: flex;
  gap: var(--gap);
  margin: 0;
  padding: 4px 4px 12px;
  overflow-x: auto;
  list-style: none;
  scroll-snap-type: x proximity;
  scroll-padding-inline: 4px;
  scrollbar-width: none;
}

.collections-rail::-webkit-scrollbar {
  display: none;
}

.collections-rail::-webkit-scrollbar-thumb {
  border-radius: var(--r-pill);
  background: var(--sakura-pale);
}

.collections-rail-cell {
  flex: 0 0 clamp(280px, 27vw, 356px);
  min-width: 0;
  scroll-snap-align: start;
}

.collections-skeleton {
  height: 306px;
  border-radius: var(--r-card);
  background: linear-gradient(100deg, var(--sakura-wash) 20%, var(--sakura-mist) 42%, var(--sakura-wash) 62%);
  background-size: 220% 100%;
  animation: collections-shimmer 1.4s linear infinite;
}

@keyframes collections-shimmer {
  from {
    background-position: 120% 0;
  }
  to {
    background-position: -120% 0;
  }
}

@media (max-width: 720px) {
  .collections-rail-cell {
    flex-basis: 78vw;
  }

  .collections-skeleton {
    height: 264px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .collections-skeleton {
    animation: none;
  }
}
</style>
