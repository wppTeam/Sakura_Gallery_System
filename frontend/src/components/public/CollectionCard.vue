<template>
  <RouterLink class="collection-card" :to="`/collections/${collection.slug}`">
    <div
      class="cc-cover"
      :style="coverStyle"
      :class="{ 'is-empty': !collection.cover }"
      aria-hidden="true"
    >
      <img
        v-if="collection.cover"
        class="cc-cover-img"
        :class="{ 'is-loaded': loaded }"
        :src="coverImageSrc"
        :srcset="coverSrcset || undefined"
        :sizes="COVER_SIZES"
        :alt="''"
        :width="collection.cover.width || undefined"
        :height="collection.cover.height || undefined"
        loading="lazy"
        decoding="async"
        @load="loaded = true"
      />
      <svg v-else class="cc-cover-mark" width="56" height="56" viewBox="0 0 56 56" fill="none">
        <circle cx="28" cy="28" r="26" fill="var(--sakura-pale)" />
        <g transform="translate(28 28)">
          <path
            v-for="rotate in [0, 72, 144, 216, 288]"
            :key="rotate"
            d="M0 -3c5 -5.6 5.6 -11 0 -13.8-5.6 2.8-5 8.2 0 13.8Z"
            :transform="`rotate(${rotate})`"
            fill="var(--sakura)"
            opacity="0.55"
          />
          <circle r="2.8" fill="var(--sakura-deep)" />
        </g>
      </svg>
      <span class="cc-count">{{ collection.photoCount }} 张</span>
    </div>

    <div class="cc-body">
      <h3 class="cc-title">{{ collection.title }}</h3>
      <p v-if="collection.subtitle" class="cc-sub">{{ collection.subtitle }}</p>
      <p class="cc-foot">
        <span class="cc-foot-text">{{ collection.photoCount }} 张作品</span>
        <span class="cc-arrow" aria-hidden="true">
          查看
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path
              d="M3.2 8h9.2M8.8 4.2 12.6 8l-3.8 3.8"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </span>
      </p>
    </div>
  </RouterLink>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { buildSrcset, type PublicPhoto } from '../../api/public'
import type { CollectionSummary } from '../../api/collections'

const props = defineProps<{
  collection: CollectionSummary
}>()

const COVER_SIZES = '(max-width: 560px) 92vw, (max-width: 900px) 46vw, (max-width: 1280px) 30vw, 23vw'

const loaded = ref(false)
watch(
  () => props.collection.cover?.id,
  () => {
    loaded.value = false
  },
)

const cover = computed<PublicPhoto | null>(() => props.collection.cover)

/** 封面主图：优先 compressed（1600 JPEG），保留原始比例，contain 不裁切 */
const coverImageSrc = computed(() => cover.value?.imageUrl || cover.value?.thumbUrl || '')
const coverSrcset = computed(() => buildSrcset(cover.value?.variants || [], 'jpeg'))

const coverStyle = computed(() => {
  const style: Record<string, string> = {}
  const lqip = cover.value?.lqip
  if (lqip) {
    style.backgroundImage = `url("${lqip}")`
    style.backgroundSize = 'cover'
  }
  return style
})
</script>

<style scoped>
.collection-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
  color: var(--ink);
  text-decoration: none;
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}

.collection-card:hover {
  border-color: var(--sakura-pale);
  box-shadow: var(--shadow-lift);
}

.collection-card:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 3px;
}

.cc-cover {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 4 / 3;
  padding: 14px;
  background-color: var(--sakura-wash);
  background-position: center;
  background-size: cover;
  overflow: hidden;
}

.cc-cover.is-empty {
  background-image: radial-gradient(circle at 30% 20%, var(--sakura-mist), transparent 62%);
}

.cc-cover-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  opacity: 0;
  transform: scale(1.015);
  transition: opacity var(--dur-slow) var(--ease-out), transform var(--dur-slow) var(--ease-out);
}

.cc-cover-img.is-loaded {
  opacity: 1;
  transform: scale(1);
}

.collection-card:hover .cc-cover-img.is-loaded,
.collection-card:focus-visible .cc-cover-img.is-loaded {
  transform: scale(1.015);
}

.cc-cover-mark {
  opacity: 0.8;
}

.cc-count {
  position: absolute;
  right: 12px;
  bottom: 12px;
  padding: 4px 10px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.92);
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.cc-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 18px 18px;
}

.cc-title {
  font-family: var(--display);
  font-size: 23px;
  font-weight: 400;
  line-height: var(--lh-tight);
  letter-spacing: 0.02em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cc-sub {
  overflow: hidden;
  color: var(--muted);
  font-size: var(--fs-sm);
  line-height: 1.6;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cc-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 2px;
  color: var(--muted);
  font-size: var(--fs-xs);
}

.cc-foot-text {
  font-variant-numeric: tabular-nums;
}

.cc-arrow {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--sakura-deep);
  font-weight: 600;
  transition: gap var(--dur-fast) var(--ease-out);
}

.collection-card:hover .cc-arrow,
.collection-card:focus-visible .cc-arrow {
  gap: 8px;
}

@media (prefers-reduced-motion: reduce) {
  .cc-cover-img,
  .cc-arrow {
    transition: none;
  }
}
</style>
