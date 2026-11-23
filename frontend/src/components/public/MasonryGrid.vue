<template>
  <div
    ref="container"
    class="masonry"
    :class="{ 'is-loading': loading }"
    :aria-busy="loading ? 'true' : 'false'"
  >
    <div v-for="(column, columnIndex) in displayColumns" :key="columnIndex" class="masonry-col">
      <div v-for="item in column" :key="item.key" class="masonry-item">
        <SkeletonCard
          v-if="item.skeleton"
          :aspect-ratio="item.ratio"
          :show-caption="showCaption"
        />
        <PhotoCard
          v-else
          :photo="item.photo"
          :show-caption="showCaption"
          :show-author="showAuthor"
          :variant="variant"
          :eager="eager && item.index < 2"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { PublicPhoto } from '../../api/public'
import PhotoCard from './PhotoCard.vue'
import SkeletonCard from './SkeletonCard.vue'

const props = withDefaults(
  defineProps<{
    items: PublicPhoto[]
    /** 列数上限：首页信息流 3，探索页 5 */
    maxColumns?: number
    /** 加载中且列表为空时显示骨架卡的列数倍率（每列张数） */
    skeletonRows?: number
    showCaption?: boolean
    showAuthor?: boolean
    variant?: 'default' | 'compact'
    /** 首屏图片优先加载 */
    eager?: boolean
    loading?: boolean
  }>(),
  {
    maxColumns: 5,
    skeletonRows: 3,
    showCaption: true,
    showAuthor: true,
    variant: 'default',
    eager: false,
    loading: false,
  },
)

/* 骨架卡的预设比例，模拟真实混排节奏（不与真实数据混淆：仅占位） */
const SKELETON_RATIOS = [0.72, 1.32, 1, 0.66, 1.48, 0.82, 1.18, 0.75, 1.5, 1.02, 0.7, 1.26]

interface MasonryItem {
  key: string
  skeleton: boolean
  ratio: number
  photo: PublicPhoto
  index: number
}

const container = ref<HTMLElement | null>(null)
const width = ref(0)
const gap = ref(20)

const columnCount = computed(() => {
  const w = width.value
  if (!w) return 3
  let cols = 4
  if (w < 720) cols = 2
  else if (w < 1000) cols = 3
  else if (w < 1600) cols = 4
  else cols = 5
  return Math.max(1, Math.min(cols, props.maxColumns))
})

/** 最短列优先分配：保持瀑布流列高均衡，阅读顺序天然按列 */
function distribute<T>(
  items: T[],
  ratioOf: (item: T) => number,
  columnWidth: number,
  gapPx: number,
  count: number,
  extraHeight: number,
): T[][] {
  const columns: T[][] = Array.from({ length: count }, () => [])
  const heights = new Array<number>(count).fill(0)
  for (const item of items) {
    let target = 0
    for (let i = 1; i < count; i += 1) {
      if (heights[i] < heights[target] - 0.5) target = i
    }
    columns[target].push(item)
    heights[target] += columnWidth / ratioOf(item) + extraHeight + gapPx
  }
  return columns
}

const displayColumns = computed<MasonryItem[][]>(() => {
  const cols = columnCount.value
  const gapPx = gap.value
  const budget = Math.max(320, width.value) - gapPx * (cols - 1)
  const columnWidth = budget / cols
  /* 说明文字高度影响列高估算：约 55px（标题 + 副行 + 间距） */
  const captionHeight = props.showCaption ? 55 : 0

  if (props.loading && props.items.length === 0) {
    const skeletons: MasonryItem[] = Array.from({ length: cols * props.skeletonRows }, (_, i) => ({
      key: `skeleton-${i}`,
      skeleton: true,
      ratio: SKELETON_RATIOS[i % SKELETON_RATIOS.length],
      photo: null as unknown as PublicPhoto,
      index: i,
    }))
    return distribute(skeletons, (item) => item.ratio, columnWidth, gapPx, cols, captionHeight)
  }

  const real: MasonryItem[] = props.items.map((photo, index) => ({
    key: `${photo.id}-${index}`,
    skeleton: false,
    ratio: photo.aspectRatio,
    photo,
    index,
  }))
  return distribute(real, (item) => item.ratio, columnWidth, gapPx, cols, captionHeight)
})

let resizeObserver: ResizeObserver | null = null

function measure() {
  const el = container.value
  if (!el) return
  width.value = el.clientWidth
  const gapValue = getComputedStyle(el).getPropertyValue('--gap').trim()
  const parsed = Number.parseFloat(gapValue)
  if (Number.isFinite(parsed) && parsed > 0) gap.value = parsed
}

onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined' && container.value) {
    resizeObserver = new ResizeObserver(measure)
    resizeObserver.observe(container.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})
</script>

<style scoped>
.masonry {
  display: flex;
  align-items: flex-start;
  gap: var(--gap);
  width: 100%;
}

.masonry-col {
  display: flex;
  flex: 1 1 0;
  flex-direction: column;
  gap: var(--gap);
  min-width: 0;
}

.masonry-item {
  min-width: 0;
}
</style>
