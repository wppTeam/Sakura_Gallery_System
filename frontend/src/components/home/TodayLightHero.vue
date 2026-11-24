<template>
  <figure
    ref="rootEl"
    class="today"
    :style="{ '--today-wash': washColor }"
    @mouseenter="paused = true"
    @mouseleave="paused = false"
    @focusin="paused = true"
    @focusout="paused = false"
  >
    <div class="today-glow" aria-hidden="true" />

    <div v-if="loading" class="today-stage is-loading" aria-hidden="true">
      <span class="today-loading-bar" />
    </div>

    <template v-else-if="slides.length">
      <div class="today-stage">
        <img
          v-for="slot in layers"
          :key="`${slot}-${slides[slot].id}`"
          class="today-img"
          :class="{
            'is-front': slot === index,
            'is-back': slot !== index,
            'is-kenburns': !reducedMotion && slot === index,
          }"
          :src="slideImageUrl(slides[slot])"
          :alt="slideAlt(slides[slot])"
          :width="slides[slot].width || undefined"
          :height="slides[slot].height || undefined"
          :fetchpriority="slot === 0 ? 'high' : 'low'"
          decoding="async"
        />
        <span class="today-tag">LIGHT OF DAY · {{ activeMeta.label }}</span>
        <span class="today-author">{{ activeAuthor }}</span>
      </div>

      <figcaption class="today-caption">
        <span class="today-title" :title="activePhoto?.title">
          {{ activePhoto?.title || '今日之光' }}
        </span>
        <span class="today-dots" role="group" aria-label="今日之光照片切换">
          <button
            v-for="(photo, dotIndex) in slides"
            :key="photo.id"
            type="button"
            class="today-dot"
            :class="{ 'is-active': dotIndex === index }"
            :aria-label="`查看第 ${dotIndex + 1} 张：${photo.title}`"
            :aria-current="dotIndex === index ? 'true' : undefined"
            @click="selectSlide(dotIndex)"
          />
        </span>
        <span class="today-caption-author" :title="activeAuthor">{{ activeAuthor }}</span>
        <span class="today-period">
          {{ activeMeta.label }} · {{ activeMeta.timeRange }} · {{ activePeriodText }}
        </span>
      </figcaption>
    </template>

    <template v-else>
      <div class="today-stage is-fallback">
        <img
          class="today-img is-front is-fallback-img"
          src="/art/hero.webp"
          alt="樱花落在北化校园的插画：粉色花枝与教学楼"
          width="1440"
          height="810"
          fetchpriority="high"
          decoding="async"
        />
        <span class="today-tag">LIGHT OF DAY</span>
      </div>
      <figcaption class="today-caption">
        <span class="today-title">视觉百花 主视觉</span>
        <span class="today-period">项目自制插画 · 今日之光整理中</span>
      </figcaption>
    </template>
  </figure>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { LightPeriod } from '../../api/collections'
import type { PublicPhoto } from '../../api/public'
import {
  LIGHT_PERIOD_META,
  currentLightKey,
  lightMeta,
  pickLightPeriod,
  type LightPeriodMeta,
} from './period'

const props = defineProps<{
  periods: LightPeriod[]
  loading?: boolean
}>()

const rootEl = ref<HTMLElement | null>(null)
const index = ref(0)
const prevIndex = ref(0)
const paused = ref(false)
const visible = ref(true)
const reducedMotion = ref(false)

const activePeriod = computed<LightPeriod | null>(() => pickLightPeriod(props.periods))
const slides = computed<PublicPhoto[]>(() => activePeriod.value?.photos.slice(0, 4) ?? [])
const activePhoto = computed<PublicPhoto | null>(() => slides.value[index.value] ?? null)

const activeMeta = computed<LightPeriodMeta>(() => {
  const key = activePeriod.value?.key || currentLightKey()
  const meta = lightMeta(key)
  return {
    key: meta.key,
    label: activePeriod.value?.label || meta.label,
    timeRange: activePeriod.value?.timeRange || meta.timeRange,
    washVar: meta.washVar,
  }
})

const activeAuthor = computed(() => activePhoto.value?.author || '北化创作者')
const activePeriodText = computed(() => {
  const period = activePeriod.value
  if (!period) return '今日之光'
  if (period.key === currentLightKey()) return '此刻'
  return period.title || period.label
})

const washColor = computed(() => {
  const color = activePhoto.value?.lqipColor
  return color || activeMeta.value.washVar
})

const layers = computed(() => Array.from(new Set([prevIndex.value, index.value])))

function variantUrl(photo: PublicPhoto, sizes: number[]): string {
  for (const size of sizes) {
    const variant = photo.variants.find((item) => item.size === size)
    if (variant?.webpUrl) return variant.webpUrl
  }
  return photo.imageUrl || photo.thumbUrl
}

function slideImageUrl(photo: PublicPhoto): string {
  return variantUrl(photo, [1080, 640, 320])
}

function preloadNext() {
  if (slides.value.length < 2) return
  const next = slides.value[(index.value + 1) % slides.value.length]
  if (!next) return
  const img = new Image()
  img.src = variantUrl(next, [640, 320])
}

function slideAlt(photo: PublicPhoto): string {
  const author = photo.author || '北化创作者'
  return `${photo.title || '今日之光'} · ${author}`
}

function selectSlide(next: number) {
  const count = slides.value.length
  if (!count || next === index.value) return
  prevIndex.value = index.value
  index.value = next
}

let timer: number | undefined
let observer: IntersectionObserver | null = null
let mediaQuery: MediaQueryList | null = null

function shouldAutoPlay(): boolean {
  return slides.value.length > 1 && !reducedMotion.value && !paused.value && visible.value
}

function stopAutoPlay() {
  if (timer !== undefined) {
    window.clearInterval(timer)
    timer = undefined
  }
}

function syncAutoPlay() {
  stopAutoPlay()
  if (!shouldAutoPlay()) return
  timer = window.setInterval(() => {
    if (!shouldAutoPlay()) return
    prevIndex.value = index.value
    index.value = (index.value + 1) % slides.value.length
  }, 6000)
}

watch(slides, () => {
  index.value = 0
  prevIndex.value = 0
  paused.value = false
  syncAutoPlay()
})
watch([paused, visible, reducedMotion], syncAutoPlay)

function onReducedMotionChange(event: MediaQueryListEvent) {
  reducedMotion.value = event.matches
}

onMounted(() => {
  mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.value = mediaQuery.matches
  mediaQuery.addEventListener('change', onReducedMotionChange)

  if (rootEl.value && 'IntersectionObserver' in window) {
    observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (entry) visible.value = entry.isIntersecting
      },
      { threshold: 0.15 },
    )
    observer.observe(rootEl.value)
  }

  window.addEventListener('load', preloadNext, { once: true })

  syncAutoPlay()
})

onBeforeUnmount(() => {
  stopAutoPlay()
  window.removeEventListener('load', preloadNext)
  observer?.disconnect()
  observer = null
  mediaQuery?.removeEventListener('change', onReducedMotionChange)
})
</script>

<style scoped>
.today {
  position: relative;
  margin: 0;
  isolation: isolate;
}

/* 氛围光：跟随当前照片 LQIP 主色，克制在右上角 */
.today-glow {
  position: absolute;
  inset: -12% -8% auto auto;
  width: min(78%, 520px);
  aspect-ratio: 1;
  border-radius: 50%;
  background: radial-gradient(circle at 62% 38%, var(--today-wash, var(--spring-pale)) 0%, transparent 68%);
  opacity: 0.14;
  filter: blur(6px);
  pointer-events: none;
  transition: background 800ms var(--ease-soft);
  z-index: -1;
}

.today-stage {
  position: relative;
  overflow: hidden;
  aspect-ratio: 4 / 3;
  border: 10px solid var(--surface);
  border-radius: var(--r-card);
  background: var(--sakura-mist);
  box-shadow: var(--shadow-lift);
}

.today-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  opacity: 0;
  transition: opacity 600ms var(--ease-soft);
}

.today-img.is-front {
  opacity: 1;
  z-index: 1;
}

.today-img.is-back {
  opacity: 0;
  z-index: 0;
}

.today-img.is-kenburns {
  animation: today-kenburns 12s linear forwards;
}

@keyframes today-kenburns {
  from {
    transform: scale(1);
  }
  to {
    transform: scale(1.035);
  }
}

.today-tag {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 11px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.92);
  color: var(--sakura-deep);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.today-author {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 2;
  max-width: 46%;
  overflow: hidden;
  padding: 6px 11px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.9);
  color: var(--ink);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.today-caption {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  padding-inline: 2px;
}

.today-title {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: var(--ink);
  font-size: var(--fs-sm);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.today-dots {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.today-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  cursor: pointer;
}

.today-dot::before {
  content: '';
  display: block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--line-strong);
  transition: background var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}

.today-dot.is-active::before {
  background: var(--sakura-deep);
  transform: scale(1.15);
}

.today-dot:hover::before {
  background: var(--sakura);
}

.today-dot:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: 1px;
}

.today-caption-author {
  flex: 0 1 auto;
  max-width: 9em;
  overflow: hidden;
  color: var(--muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.today-period {
  flex: none;
  color: var(--faint);
  font-size: 10.5px;
  letter-spacing: 0.03em;
  white-space: nowrap;
}

.today-stage.is-loading {
  display: flex;
  align-items: center;
  justify-content: center;
}

.today-loading-bar {
  width: 42%;
  height: 8px;
  border-radius: var(--r-pill);
  background: linear-gradient(100deg, var(--sakura-wash) 20%, var(--sakura-mist) 42%, var(--sakura-wash) 62%);
  background-size: 220% 100%;
  animation: today-shimmer 1.4s linear infinite;
}

@keyframes today-shimmer {
  from {
    background-position: 130% 0;
  }
  to {
    background-position: -130% 0;
  }
}

.today-stage.is-fallback {
  background: var(--ground-deep);
}

.today-img.is-fallback-img {
  position: absolute;
}

@media (pointer: coarse) {
  .today-dot {
    width: 44px;
    height: 44px;
  }
}

@media (max-width: 900px) {
  .today-stage {
    border-width: 8px;
  }

  .today-tag {
    top: 10px;
    left: 10px;
    font-size: 9.5px;
    padding: 5px 9px;
  }

  .today-author {
    top: 10px;
    right: 10px;
    max-width: 42%;
    padding: 5px 9px;
  }

  .today-caption {
    flex-wrap: wrap;
    gap: 6px 10px;
  }

  .today-title,
  .today-caption-author {
    flex-basis: 100%;
  }

  .today-caption-author {
    max-width: 60%;
  }

  .today-dot {
    width: 40px;
    height: 40px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .today-img.is-kenburns {
    animation: none;
  }

  .today-img {
    transition: none;
  }

  .today-loading-bar {
    animation: none;
  }
}
</style>
