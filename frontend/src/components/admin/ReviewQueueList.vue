<template>
  <section class="queue-list" aria-label="审核队列">
    <div v-if="loading && !items.length" class="queue-skeleton" aria-busy="true">
      <div v-for="index in 5" :key="index" class="queue-skeleton-item">
        <span class="sk-thumb" />
        <span class="sk-lines">
          <i class="sk-line sk-line-title" />
          <i class="sk-line sk-line-summary" />
          <i class="sk-line sk-line-meta" />
        </span>
      </div>
    </div>

    <div
      v-else-if="!items.length"
      class="queue-empty"
    >
      <n-icon :size="30" color="#c9a6b2"><ImagesOutline /></n-icon>
      <p class="queue-empty-title">{{ emptyTitle }}</p>
      <p class="queue-empty-hint">{{ emptyHint }}</p>
      <n-button size="small" secondary @click="emit('refresh')">刷新队列</n-button>
    </div>

    <div
      v-else
      class="queue-items"
      role="listbox"
      aria-label="待审照片列表"
      tabindex="0"
      @keydown="onKeydown"
    >
      <QueueItem
        v-for="review in items"
        :key="review.id || review.photoId"
        :review="review"
        :active="review.photoId === selectedPhotoId"
        :selected="selectedIds.includes(review.photoId)"
        :selectable="selectable"
        :data-photo-id="review.photoId"
        @select="emit('select', $event)"
        @toggle-select="emit('toggle-select', $event)"
      />
      <div v-if="loadingMore" class="queue-more-skeleton" aria-busy="true">
        <div v-for="index in 2" :key="index" class="queue-skeleton-item">
          <span class="sk-thumb" />
          <span class="sk-lines">
            <i class="sk-line sk-line-title" />
            <i class="sk-line sk-line-summary" />
          </span>
        </div>
      </div>
      <p v-if="loading && items.length" class="queue-loading-hint" aria-live="polite">正在刷新…</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick } from 'vue'
import { ImagesOutline } from '@vicons/ionicons5'
import type { ModerationReview } from '../../api/moderation'
import QueueItem from './QueueItem.vue'

const props = withDefaults(
  defineProps<{
    items: ModerationReview[]
    loading: boolean
    loadingMore?: boolean
    selectedPhotoId: string
    emptyTitle: string
    emptyHint: string
    selectable?: boolean
    selectedIds?: string[]
  }>(),
  { loadingMore: false, selectable: false, selectedIds: () => [] },
)

const emit = defineEmits<{
  select: [review: ModerationReview]
  refresh: []
  'toggle-select': [photoId: string]
}>()

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
  if (!props.items.length) return
  event.preventDefault()
  const currentIndex = props.items.findIndex((item) => item.photoId === props.selectedPhotoId)
  const delta = event.key === 'ArrowDown' ? 1 : -1
  const nextIndex = currentIndex < 0 ? 0 : Math.min(Math.max(currentIndex + delta, 0), props.items.length - 1)
  const target = props.items[nextIndex]
  if (!target) return
  emit('select', target)
  void nextTick(() => {
    const element = document.querySelector<HTMLElement>(`[data-photo-id="${target.photoId}"]`)
    element?.scrollIntoView({ block: 'nearest' })
  })
}
</script>

<style scoped>
.queue-list {
  min-height: 120px;
}

.queue-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  outline: none;
  border-radius: var(--r-md, 14px);
}

.queue-items:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 3px;
}

.queue-loading-hint {
  margin: 4px 0 0;
  text-align: center;
  font-size: 12px;
  color: var(--faint, #97808a);
}

.queue-skeleton,
.queue-more-skeleton {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.queue-more-skeleton {
  margin-top: 8px;
  opacity: 0.7;
}

.queue-skeleton-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: var(--r-md, 14px);
  border: 1px solid var(--line, #f3dde5);
  background: var(--surface, #fff);
}

.sk-thumb {
  width: 64px;
  height: 64px;
  flex: none;
  border-radius: var(--r-sm, 10px);
  background: var(--sakura-pale, #ffe9f0);
}

.sk-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sk-line {
  display: block;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--sakura-pale, #ffe9f0) 25%, #fff 50%, var(--sakura-pale, #ffe9f0) 75%);
  background-size: 200% 100%;
  animation: queue-shimmer 1.4s ease-in-out infinite;
}

.sk-line-title { width: 52%; height: 12px; }
.sk-line-summary { width: 78%; }
.sk-line-meta { width: 36%; }

@keyframes queue-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

.queue-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 44px 16px;
  text-align: center;
}

.queue-empty-title {
  margin: 6px 0 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.queue-empty-hint {
  margin: 0 0 8px;
  max-width: 26em;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--muted, #63474f);
}

@media (max-width: 768px) {
  .queue-items {
    gap: 6px;
  }

  .queue-skeleton-item {
    padding: 10px;
  }

  .sk-thumb {
    width: 54px;
    height: 54px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sk-line {
    animation: none;
  }
}
</style>
