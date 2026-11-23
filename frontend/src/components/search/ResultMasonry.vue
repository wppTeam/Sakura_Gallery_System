<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { SearchWork } from '../../api/search'
import WorkCard from './WorkCard.vue'

const props = withDefaults(
  defineProps<{
    works: SearchWork[]
    loading?: boolean
    loadingMore?: boolean
    skeletonCount?: number
  }>(),
  { loading: false, loadingMore: false, skeletonCount: 8 },
)

const GAP = 20
const root = ref<HTMLElement | null>(null)
const containerWidth = ref(
  typeof window === 'undefined' ? 1200 : Math.min(Math.max(window.innerWidth - 48, 320), 1272),
)

function measure() {
  if (root.value && root.value.clientWidth > 0) containerWidth.value = root.value.clientWidth
}

let observer: ResizeObserver | null = null

onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined' && root.value) {
    observer = new ResizeObserver(measure)
    observer.observe(root.value)
  } else {
    window.addEventListener('resize', measure)
  }
})

onBeforeUnmount(() => {
  if (observer) observer.disconnect()
  observer = null
  window.removeEventListener('resize', measure)
})

const columnCount = computed(() => {
  const width = containerWidth.value
  if (width < 520) return 1
  if (width < 900) return 2
  if (width < 1280) return 3
  return 4
})

const gap = computed(() => (columnCount.value === 1 ? 12 : GAP))

/** 估算卡片高度（图高 + 文字区），用于「最短列优先」分配 */
function ratioOf(work: SearchWork): number {
  if (work.width > 0 && work.height > 0) {
    return Math.min(2.6, Math.max(0.4, work.height / work.width))
  }
  const match = String(work.aspectRatio || '').match(/^(\d+(?:\.\d+)?)\s*[/:×]\s*(\d+(?:\.\d+)?)$/)
  if (match) {
    const w = Number(match[1])
    const h = Number(match[2])
    if (w > 0 && h > 0) return Math.min(2.6, Math.max(0.4, h / w))
  }
  return 0.75
}

interface ColumnEntry {
  key: string
  work?: SearchWork
  variant?: number
}

const displayColumns = computed<ColumnEntry[][]>(() => {
  const count = columnCount.value
  if (count <= 0) return []
  const isInitialLoading = props.loading && props.works.length === 0

  if (isInitialLoading) {
    const perColumn = Math.max(1, Math.ceil(props.skeletonCount / count))
    return Array.from({ length: count }, (_, columnIndex) =>
      Array.from({ length: perColumn }, (_, itemIndex) => ({
        key: `skeleton-${columnIndex}-${itemIndex}`,
        variant: ((columnIndex + itemIndex) % 4) + 1,
      })),
    )
  }

  const columns: ColumnEntry[][] = Array.from({ length: count }, () => [])
  const heights = new Array<number>(count).fill(0)
  const columnWidth = Math.max(120, (containerWidth.value - GAP * (count - 1)) / count)

  for (const work of props.works) {
    let target = 0
    for (let index = 1; index < count; index += 1) {
      if (heights[index] < heights[target] - 1) target = index
    }
    columns[target].push({ key: work.id, work })
    heights[target] += columnWidth * ratioOf(work) + 104
  }

  if (props.loadingMore) {
    for (let index = 0; index < 3 && index < count; index += 1) {
      columns[index].push({ key: `loading-more-${index}`, variant: ((index + 2) % 4) + 1 })
    }
  }

  return columns
})
</script>

<template>
  <div
    ref="root"
    class="result-masonry"
    :aria-busy="loading || loadingMore"
    :aria-label="loading ? '检索结果加载中' : '检索结果'"
  >
    <div v-for="(column, columnIndex) in displayColumns" :key="`col-${columnIndex}`" class="masonry-col">
      <template v-for="entry in column" :key="entry.key">
        <WorkCard v-if="entry.work" :work="entry.work" />
        <div v-else class="masonry-item skeleton-card" :class="`skeleton-card--${entry.variant}`" aria-hidden="true">
          <div class="skeleton-media" />
          <div class="skeleton-body">
            <span class="skeleton-line skeleton-line--title" />
            <span class="skeleton-line skeleton-line--short" />
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.result-masonry {
  display: flex;
  align-items: flex-start;
  gap: var(--gap, 20px);
}

.masonry-col {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--gap, 20px);
}

.masonry-item {
  min-width: 0;
}

.skeleton-card {
  border-radius: var(--r-card, 20px);
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  overflow: hidden;
}

.skeleton-media {
  width: 100%;
  background: linear-gradient(100deg, #ffeef4 20%, #fff7fa 40%, #ffeef4 60%);
  background-size: 220% 100%;
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton-card--1 .skeleton-media {
  aspect-ratio: 4 / 3;
}

.skeleton-card--2 .skeleton-media {
  aspect-ratio: 3 / 4;
}

.skeleton-card--3 .skeleton-media {
  aspect-ratio: 16 / 10;
}

.skeleton-card--4 .skeleton-media {
  aspect-ratio: 1 / 1;
}

.skeleton-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 13px 14px 16px;
}

.skeleton-line {
  height: 11px;
  border-radius: 6px;
  background: linear-gradient(100deg, #fbe7ee 20%, #fff7fa 40%, #fbe7ee 60%);
  background-size: 220% 100%;
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton-line--title {
  width: 72%;
}

.skeleton-line--short {
  width: 42%;
  height: 9px;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.62;
  }
}

@media (max-width: 560px) {
  .result-masonry,
  .masonry-col {
    gap: 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton-media,
  .skeleton-line {
    animation: none;
  }
}
</style>
