<template>
  <section v-if="loading || works.length" class="related">
    <div class="related-head">
      <h2 class="related-title">相关作品</h2>
      <router-link class="related-more" :to="{ path: '/search', query: moreQuery }">
        查看更多
        <n-icon :component="ArrowForwardOutline" :size="14" />
      </router-link>
    </div>

    <div v-if="loading" class="related-track" aria-hidden="true">
      <div v-for="index in 5" :key="index" class="related-skeleton">
        <div class="related-skeleton-img" />
        <div class="related-skeleton-line" />
      </div>
    </div>

    <div v-else class="related-track">
      <router-link
        v-for="work in works"
        :key="work.id"
        class="related-card"
        :to="`/photo/${work.id}`"
      >
        <div class="related-thumb" :style="{ aspectRatio: work.aspectRatio || '4 / 3' }">
          <img :src="work.thumbUrl" :alt="work.author ? `${work.title} · ${work.author}` : work.title" loading="lazy" decoding="async" class="related-img" />
        </div>
        <span class="related-name">{{ work.title }}</span>
        <span v-if="work.meta" class="related-meta">{{ work.meta }}</span>
      </router-link>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NIcon } from 'naive-ui'
import { ArrowForwardOutline } from '@vicons/ionicons5'
import type { RelatedWork } from './workDetail'

const props = defineProps<{
  works: RelatedWork[]
  loading: boolean
  season?: string
  category?: string
}>()

const moreQuery = computed(() => {
  if (props.season) return { season: props.season }
  if (props.category) return { category: props.category }
  return {}
})
</script>

<style scoped>
.related {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.related-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.related-title {
  margin: 0;
  font-family: var(--display, 'Noto Sans SC', sans-serif);
  font-size: 18px;
  color: var(--ink, #4a2b35);
}

.related-more {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12.5px;
  color: var(--sakura-deep, #c93a63);
  text-decoration: none;
}

.related-more:hover {
  text-decoration: underline;
}

.related-track {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  padding: 4px 4px 12px;
  scroll-snap-type: x proximity;
  scrollbar-width: thin;
  scrollbar-color: #f0c6d4 transparent;
}

.related-track::-webkit-scrollbar {
  height: 6px;
}

.related-track::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: #f0c6d4;
}

.related-card {
  flex: 0 0 172px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 8px 10px;
  border-radius: 14px;
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  text-decoration: none;
  scroll-snap-align: start;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.related-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
}

.related-thumb {
  width: 100%;
  border-radius: 10px;
  overflow: hidden;
  background: #fdf3f7;
  display: flex;
  align-items: center;
  justify-content: center;
}

.related-img {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
}

.related-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.related-meta {
  font-size: 11px;
  color: #9a7f87;
}

.related-skeleton {
  flex: 0 0 172px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border-radius: 14px;
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
}

.related-skeleton-img,
.related-skeleton-line {
  border-radius: 10px;
  background: linear-gradient(90deg, #fbeef4 25%, #fff7fa 37%, #fbeef4 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}

.related-skeleton-img {
  width: 100%;
  aspect-ratio: 4 / 3;
}

.related-skeleton-line {
  height: 12px;
  width: 70%;
}

@keyframes shimmer {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}

@media (max-width: 768px) {
  .related-track {
    margin-right: -16px;
    padding-right: 16px;
  }

  .related-card,
  .related-skeleton {
    flex-basis: 148px;
  }
}
</style>
