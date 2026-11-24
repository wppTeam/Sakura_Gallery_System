<template>
  <component
    :is="linked ? RouterLink : 'div'"
    class="light-card"
    :class="{ 'is-pending': !linked, 'is-current': current && linked }"
    :to="linked ? `/collections/${period.slug}` : undefined"
    :aria-disabled="linked ? undefined : 'true'"
  >
    <span class="lc-rail" aria-hidden="true">
      <span class="lc-rail-dot" />
      <span class="lc-rail-line" />
    </span>

    <span class="lc-main">
      <span class="lc-head">
        <span class="lc-time">{{ period.timeRange }}</span>
        <span v-if="current && linked" class="lc-now">此刻</span>
      </span>

      <span class="lc-cover" :style="coverStyle">
        <img
          v-if="coverUrl"
          class="lc-cover-img"
          :src="coverUrl"
          :alt="`${period.title} 封面`"
          width="640"
          height="480"
          loading="lazy"
          decoding="async"
        />
        <span v-else class="lc-cover-token" aria-hidden="true">{{ period.label }}</span>
        <span class="lc-token" aria-hidden="true">{{ period.label }}</span>
      </span>

      <span class="lc-body">
        <span class="lc-title">{{ period.title }}</span>
        <span class="lc-sub">{{ period.subtitle }}</span>
        <span class="lc-meta">
          <template v-if="linked">{{ period.photoCount }} 件作品</template>
          <template v-else>整理中 · 暂无作品</template>
        </span>
      </span>
    </span>
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { LightPeriod } from '../../api/collections'
import type { PublicPhoto } from '../../api/public'

const props = defineProps<{
  period: LightPeriod
  current?: boolean
}>()

const linked = computed(() => Boolean(props.period.slug) && props.period.photoCount > 0)
const cover = computed<PublicPhoto | null>(() => props.period.photos[0] ?? null)

const coverUrl = computed(() => {
  const photo = cover.value
  if (!photo) return ''
  for (const size of [640, 320, 1080]) {
    const variant = photo.variants.find((item) => item.size === size)
    if (variant?.webpUrl) return variant.webpUrl
  }
  return photo.thumbUrl
})

/** 封面加载前先用 LQIP 铺底（20px WebP，cover 铺满），避免粉色空框跳动 */
const coverStyle = computed(() => {
  const lqip = cover.value?.lqip
  if (!lqip) return undefined
  return {
    backgroundImage: `url(${lqip})`,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    backgroundRepeat: 'no-repeat',
  }
})
</script>

<style scoped>
.light-card {
  position: relative;
  display: flex;
  height: 100%;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
  color: inherit;
  text-decoration: none;
  transition:
    border-color var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out);
}

.light-card:not(.is-pending):hover {
  border-color: var(--sakura-pale);
  box-shadow: var(--shadow-soft);
  transform: translateY(-2px);
}

.light-card:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: 3px;
}

.lc-rail {
  position: relative;
  flex: none;
  width: 26px;
}

.lc-rail-dot {
  position: absolute;
  top: 18px;
  left: 11px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--sakura);
  box-shadow: 0 0 0 4px var(--sakura-wash);
}

.lc-rail-line {
  position: absolute;
  top: 31px;
  bottom: 14px;
  left: 14px;
  width: 1px;
  background: linear-gradient(var(--line-strong), transparent);
}

.lc-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  padding: 14px 14px 14px 0;
}

.lc-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lc-time {
  color: var(--muted);
  font-family: var(--font);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.05em;
}

.lc-now {
  padding: 2px 8px;
  border-radius: var(--r-pill);
  background: var(--sakura-pale);
  color: var(--sakura-deep);
  font-size: 10px;
  font-weight: 600;
}

.lc-cover {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 10px;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border-radius: var(--r-md);
  background: var(--sakura-wash);
}

.lc-cover-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  transition: transform 180ms var(--ease-out);
}

.light-card:not(.is-pending):hover .lc-cover-img,
.light-card:not(.is-pending):focus-visible .lc-cover-img {
  transform: scale(1.015);
}

.lc-cover-token {
  color: var(--sakura);
  font-family: var(--display);
  font-size: 52px;
  line-height: 1;
  opacity: 0.68;
}

.lc-token {
  position: absolute;
  top: 8px;
  left: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.9);
  color: var(--sakura-deep);
  font-family: var(--display);
  font-size: 14px;
  line-height: 1;
}

.lc-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 11px;
}

.lc-title {
  overflow: hidden;
  color: var(--ink);
  font-size: 16px;
  font-weight: 700;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lc-sub {
  display: -webkit-box;
  overflow: hidden;
  color: var(--muted);
  font-size: var(--fs-xs);
  line-height: 1.55;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.lc-meta {
  color: var(--faint);
  font-size: 11px;
  letter-spacing: 0.02em;
}

.light-card.is-pending {
  border-style: dashed;
  background: color-mix(in srgb, var(--surface) 72%, var(--ground));
}

.light-card.is-pending .lc-cover {
  background: var(--ground-deep);
}

.light-card.is-pending .lc-rail-dot {
  background: var(--line-strong);
  box-shadow: 0 0 0 4px var(--ground-deep);
}

@media (max-width: 720px) {
  .lc-main {
    padding: 12px 12px 12px 0;
  }

  .lc-title {
    font-size: 15px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .light-card,
  .lc-cover-img {
    transition: none;
  }
}
</style>
