<template>
  <main class="spectrum-page">
    <div class="sp-shell wrap">
      <nav class="sp-crumb" aria-label="面包屑">
        <RouterLink class="sp-crumb-link" to="/">首页</RouterLink>
        <span class="sp-crumb-sep" aria-hidden="true">/</span>
        <span class="sp-crumb-current">樱色光谱</span>
      </nav>

      <header class="sp-head">
        <div class="sp-head-copy">
          <p class="eyebrow">SAKURA SPECTRUM</p>
          <h1 class="sp-title">樱色光谱</h1>
          <p class="sp-lead">
            按作品的主色自动策展——不是我们挑的，是颜色自己长出来的。
          </p>
          <p v-if="!loading && !error && bands.length" class="sp-head-meta">
            <span>{{ bands.length }} 个色卡</span>
            <span class="sp-meta-dot" aria-hidden="true">·</span>
            <span>{{ totalPhotos }} 件作品</span>
            <span class="sp-meta-dot" aria-hidden="true">·</span>
            <span>主色采样自缩略图，自动归入五色</span>
          </p>
        </div>

        <div v-if="!loading && !error && bands.length" class="sp-spectrum" aria-hidden="true">
          <button
            v-for="band in bands"
            :key="`bar-${band.key}`"
            type="button"
            class="sp-spectrum-seg"
            :style="{ '--band': band.hex, flexGrow: Math.max(band.photoCount, 1) }"
            :title="`${band.name} · ${band.photoCount} 件`"
            tabindex="-1"
            @click="jumpToBand(band.key)"
          />
        </div>
      </header>

      <div v-if="loading" class="sp-bands" aria-busy="true" aria-label="正在加载光谱">
        <section v-for="index in 3" :key="index" class="sp-band sp-band--skeleton">
          <div class="sp-skeleton-info">
            <div class="sp-skeleton-line sp-skeleton-line--swatch" />
            <div class="sp-skeleton-line" />
            <div class="sp-skeleton-line sp-skeleton-line--short" />
          </div>
          <div class="sp-skeleton-strip">
            <div v-for="item in 4" :key="item" class="sp-skeleton-thumb" />
          </div>
        </section>
      </div>

      <div v-else-if="error" class="sp-state">
        <EmptyState
          title="光谱暂时没有加载出来"
          :description="error"
          action-label="重新加载"
          error
          @action="load(true)"
        />
      </div>

      <div v-else-if="!bands.length" class="sp-state">
        <EmptyState
          title="光谱还没有颜色"
          description="等有作品入库后，主色会自己长成五张色卡。"
          action-label="去探索作品"
          @action="router.push('/explore')"
        />
      </div>

      <div v-else class="sp-bands">
        <section
          v-for="band in bands"
          :key="band.key"
          :id="`band-${band.key}`"
          class="sp-band"
          :style="{ '--band': band.hex }"
          :aria-labelledby="`band-title-${band.key}`"
        >
          <div class="sp-info">
            <div class="sp-swatch" :style="{ background: band.hex, color: readableInk(band.hex) }">
              <span class="sp-swatch-name">{{ band.name }}</span>
              <span class="sp-swatch-hex">{{ band.hex.toUpperCase() }}</span>
            </div>
            <h2 :id="`band-title-${band.key}`" class="sp-name">{{ band.name }}</h2>
            <p class="sp-desc">{{ band.description }}</p>
            <div class="sp-band-meta">
              <span class="sp-count">{{ band.photoCount }} 件</span>
              <RouterLink class="sp-more" :to="`/collections/${band.slug}`">查看专题 →</RouterLink>
            </div>
          </div>

          <div v-if="band.photos.length" class="sp-strip" role="list" tabindex="0" :aria-label="`${band.name} 的作品`">
            <RouterLink
              v-for="(photo, index) in band.photos"
              :key="photo.id"
              class="sp-item"
              role="listitem"
              :to="`/photo/${photo.id}`"
              :aria-label="`查看作品：${photo.title || '未命名作品'}`"
              :style="itemStyle(photo)"
            >
              <span class="sp-item-mat">
                <img
                  class="sp-item-img"
                  :src="photo.thumbUrl"
                  :srcset="itemSrcset(photo) || undefined"
                  :sizes="itemSizes(photo)"
                  :alt="itemAlt(photo)"
                  :width="photo.width || undefined"
                  :height="photo.height || undefined"
                  loading="lazy"
                  decoding="async"
                  @error="onImageError(photo.id)"
                />
                <span v-if="photo.aigc" class="sp-item-aigc">AI</span>
              </span>
              <span class="sp-item-title">
                <span class="sp-item-index" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
                {{ photo.title || '未命名作品' }}
              </span>
            </RouterLink>
          </div>
          <div v-else class="sp-strip-empty">
            这个颜色暂时没有可展示的作品。
          </div>
        </section>
      </div>

      <p class="sp-note">
        光谱由后端按缩略图主色自动归类，每 4 小时随新作品更新一次；色卡内作品按策展顺序排列。
      </p>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import EmptyState from '../components/public/EmptyState.vue'
import { buildSrcset, type PublicPhoto } from '../api/public'
import {
  fetchCollection,
  fetchSpectrum,
  type CollectionDetail,
  type SpectrumPalette,
} from '../api/collections'

interface SpectrumBand extends SpectrumPalette {
  photos: PublicPhoto[]
}

const router = useRouter()
const route = useRoute()

const palettes = ref<SpectrumPalette[]>([])
const details = ref<Record<string, CollectionDetail>>({})
const loading = ref(false)
const error = ref('')

const ITEM_SIZES = '(max-width: 640px) 46vw, (max-width: 1080px) 30vw, 240px'

const bands = computed<SpectrumBand[]>(() =>
  palettes.value
    .filter((item) => Boolean(item.slug))
    .map((item) => ({
      ...item,
      photos: item.slug ? details.value[item.slug]?.photos ?? [] : [],
    })),
)

const totalPhotos = computed(() =>
  palettes.value.reduce((sum, item) => sum + (item.photoCount || 0), 0),
)

function readableInk(hex: string): string {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!match) return 'var(--ink)'
  const value = Number.parseInt(match[1], 16)
  const r = (value >> 16) & 255
  const g = (value >> 8) & 255
  const b = value & 255
  const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
  return luminance > 0.66 ? '#3a2029' : '#ffffff'
}

function itemStyle(photo: PublicPhoto): Record<string, string> {
  const ratio = photo.width && photo.height ? photo.width / photo.height : 4 / 3
  const clamped = Math.min(Math.max(ratio, 0.62), 2.4)
  return { '--ar': String(Number(clamped.toFixed(3))) }
}

function itemSrcset(photo: PublicPhoto): string {
  return buildSrcset(photo.variants, 'webp') ? buildSrcset(photo.variants, 'jpeg') : ''
}

function itemSizes(photo: PublicPhoto): string {
  return itemSrcset(photo) ? ITEM_SIZES : ''
}

function itemAlt(photo: PublicPhoto): string {
  return photo.author ? `${photo.title || '未命名作品'} · ${photo.author}` : photo.title || '未命名作品'
}

const brokenIds = ref<Set<string>>(new Set())
function onImageError(id: string) {
  brokenIds.value = new Set(brokenIds.value).add(id)
}

async function load(silent = false) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const spectrum = await fetchSpectrum()
    palettes.value = spectrum.palettes
    const slugs = spectrum.palettes.map((item) => item.slug).filter((slug): slug is string => Boolean(slug))
    const results = await Promise.allSettled(slugs.map((slug) => fetchCollection(slug)))
    const next: Record<string, CollectionDetail> = {}
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') next[slugs[index]] = result.value
    })
    details.value = next
    if (!palettes.value.length) error.value = ''
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status
    error.value = status === 404 ? '光谱页暂时不可用。' : '网络连接失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

function jumpToBand(key: string) {
  const target = document.getElementById(`band-${key}`)
  if (!target) return
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
}

function scrollToHashBand() {
  const hash = String(route.hash || '').replace(/^#/, '')
  if (!hash.startsWith('band-')) return
  const target = document.getElementById(hash)
  if (!target) return
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
}

onMounted(async () => {
  document.title = '樱色光谱 · 视觉百花 Sakura Gallery'
  await load()
  if (route.hash) {
    window.requestAnimationFrame(() => window.setTimeout(scrollToHashBand, 80))
  }
})
</script>

<style scoped>
.spectrum-page {
  padding: clamp(18px, 3vw, 34px) 0 clamp(24px, 3vw, 40px);
  background:
    radial-gradient(1100px 520px at 78% -8%, rgba(232, 98, 140, 0.12), transparent 62%),
    radial-gradient(900px 480px at 4% 22%, rgba(91, 143, 192, 0.1), transparent 60%);
}

.sp-shell {
  display: block;
}

.sp-crumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
  color: var(--faint);
  font-size: var(--fs-xs);
}

.sp-crumb-link {
  color: var(--muted);
  text-decoration: none;
}

.sp-crumb-link:hover {
  color: var(--sakura-deep);
}

.sp-crumb-sep {
  color: var(--line-strong);
}

.sp-crumb-current {
  color: var(--ink);
  font-weight: 600;
}

.sp-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 28px;
  border-bottom: 1px solid var(--line);
}

.sp-head-copy {
  max-width: 46em;
}

.sp-title {
  margin: 8px 0 12px;
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(48px, 6vw, 84px);
  font-weight: 400;
  line-height: 1.06;
  letter-spacing: 0.02em;
}

.sp-lead {
  max-width: 30em;
  margin: 0;
  color: var(--muted);
  font-size: clamp(16px, 1.3vw, 19px);
  line-height: 1.85;
  letter-spacing: 0.01em;
}

.sp-head-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 16px 0 0;
  color: var(--faint);
  font-size: var(--fs-xs);
  letter-spacing: 0.02em;
}

.sp-meta-dot {
  color: var(--line-strong);
}

.sp-spectrum {
  display: flex;
  width: 260px;
  height: 62px;
  overflow: hidden;
  border-radius: var(--r-md);
  box-shadow: var(--shadow-soft);
}

.sp-spectrum-seg {
  flex: 1 1 0;
  min-width: 6px;
  border: 0;
  padding: 0;
  background: var(--band);
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out), filter var(--dur-fast) var(--ease-out);
}

.sp-spectrum-seg:hover {
  filter: saturate(1.15) brightness(1.04);
}

.sp-spectrum-seg:focus-visible {
  outline: 3px solid var(--ink);
  outline-offset: -3px;
}

.sp-bands {
  display: flex;
  flex-direction: column;
}

.sp-band {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: clamp(20px, 3vw, 40px);
  align-items: center;
  padding: clamp(26px, 3.6vw, 44px) 0;
  border-bottom: 1px solid var(--line);
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--band) 9%, transparent), transparent 58%);
}

.sp-band:last-child {
  border-bottom: 0;
}

.sp-info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}

.sp-swatch {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 2px;
  width: 128px;
  height: 128px;
  margin-bottom: 6px;
  padding: 14px;
  border-radius: var(--r-md);
  box-shadow: var(--shadow-soft), inset 0 0 0 1px rgba(255, 255, 255, 0.24);
  user-select: none;
}

.sp-swatch-name {
  font-family: var(--display);
  font-size: 34px;
  line-height: 1;
  letter-spacing: 0.04em;
}

.sp-swatch-hex {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  letter-spacing: 0.08em;
  opacity: 0.82;
}

.sp-name {
  margin: 0;
  color: var(--ink);
  font-family: var(--display);
  font-size: 26px;
  font-weight: 400;
  line-height: 1.2;
  letter-spacing: 0.03em;
}

.sp-desc {
  max-width: 22em;
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-sm);
  line-height: 1.8;
}

.sp-band-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  margin-top: 4px;
}

.sp-count {
  color: var(--ink-soft);
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
}

.sp-more {
  color: var(--sakura-deep);
  font-size: var(--fs-sm);
  font-weight: 600;
  text-decoration: none;
}

.sp-more:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.sp-strip {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  padding: 6px 2px 14px;
  scroll-snap-type: x proximity;
  scrollbar-width: none;
}

.sp-strip::-webkit-scrollbar {
  display: none;
}

.sp-strip:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 4px;
  border-radius: var(--r-sm);
}

.sp-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 0 0 auto;
  width: clamp(120px, calc(168px * var(--ar, 1.333)), 300px);
  text-decoration: none;
  scroll-snap-align: start;
}

.sp-item-mat {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 168px;
  padding: 8px;
  border-radius: var(--r-sm);
  background:
    color-mix(in srgb, var(--band) 14%, var(--surface));
  box-shadow: var(--shadow-soft);
  overflow: hidden;
}

.sp-item-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 6px;
  transition: transform 180ms var(--ease-out);
}

.sp-item:hover .sp-item-img,
.sp-item:focus-visible .sp-item-img {
  transform: scale(1.015);
}

.sp-item:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 3px;
  border-radius: var(--r-sm);
}

.sp-item-aigc {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 2px 6px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.92);
  color: var(--ink);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
}

.sp-item-title {
  display: flex;
  gap: 6px;
  color: var(--ink-soft);
  font-size: var(--fs-xs);
  line-height: 1.5;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
}

.sp-item-index {
  color: var(--faint);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.06em;
}

.sp-strip-empty {
  padding: 26px 0;
  color: var(--faint);
  font-size: var(--fs-sm);
}

.sp-note {
  margin: 22px 0 0;
  color: var(--faint);
  font-size: var(--fs-xs);
  line-height: 1.8;
}

.sp-state {
  padding: clamp(28px, 5vw, 56px) 0;
}

/* 骨架 */
.sp-band--skeleton {
  grid-template-columns: 300px minmax(0, 1fr);
}

.sp-skeleton-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sp-skeleton-line {
  height: 14px;
  width: 78%;
  border-radius: var(--r-sm);
  background: linear-gradient(90deg, var(--sakura-wash), var(--surface), var(--sakura-wash));
  background-size: 200% 100%;
  animation: sp-shimmer 1.4s ease-in-out infinite;
}

.sp-skeleton-line--swatch {
  width: 128px;
  height: 128px;
  border-radius: var(--r-md);
}

.sp-skeleton-line--short {
  width: 46%;
}

.sp-skeleton-strip {
  display: flex;
  gap: 16px;
  overflow: hidden;
}

.sp-skeleton-thumb {
  width: 168px;
  height: 168px;
  border-radius: var(--r-sm);
  background: linear-gradient(90deg, var(--sakura-wash), var(--surface), var(--sakura-wash));
  background-size: 200% 100%;
  animation: sp-shimmer 1.4s ease-in-out infinite;
}

@keyframes sp-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@media (max-width: 1080px) {
  .sp-band {
    grid-template-columns: 240px minmax(0, 1fr);
  }

  .sp-spectrum {
    width: 200px;
    height: 52px;
  }
}

@media (max-width: 860px) {
  .sp-band,
  .sp-band--skeleton {
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
    gap: 18px;
  }

  .sp-info {
    display: grid;
    grid-template-columns: 84px minmax(0, 1fr);
    grid-template-areas:
      'swatch name'
      'swatch desc'
      'swatch meta';
    column-gap: 16px;
    align-items: center;
    width: 100%;
  }

  .sp-swatch {
    grid-area: swatch;
    width: 84px;
    height: 84px;
    margin: 0;
    padding: 10px;
  }

  .sp-swatch-name {
    font-size: 22px;
  }

  .sp-swatch-hex {
    font-size: 9px;
  }

  .sp-name {
    grid-area: name;
    align-self: end;
  }

  .sp-desc {
    grid-area: desc;
  }

  .sp-band-meta {
    grid-area: meta;
  }
}

@media (max-width: 640px) {
  .sp-head {
    gap: 18px;
    padding-bottom: 22px;
  }

  .sp-title {
    font-size: clamp(44px, 12vw, 58px);
  }

  .sp-spectrum {
    width: 100%;
    height: 46px;
  }

  .sp-item {
    width: clamp(116px, calc(140px * var(--ar, 1.333)), 220px);
  }

  .sp-item-mat {
    height: 140px;
    padding: 6px;
  }

  .sp-item-title {
    font-size: 11px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sp-skeleton-line,
  .sp-skeleton-thumb {
    animation: none;
  }

  .sp-item-img {
    transition: none;
  }
}
</style>
