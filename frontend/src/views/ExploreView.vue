<template>
  <div class="explore">
    <!-- 页头 -->
    <section class="explore-head wrap" aria-labelledby="explore-title">
      <p class="eyebrow">EXPLORE · 全部作品</p>
      <div class="head-row">
        <h1 id="explore-title" class="explore-title">探索</h1>
        <p class="head-count" aria-live="polite">
          <template v-if="initialLoading">正在索引…</template>
          <template v-else-if="total">{{ total }} 件作品</template>
          <template v-else>暂无作品</template>
        </p>
      </div>
      <p class="explore-desc">
        按季节、校区与景名筛选。每一张都保留原始构图与作者署名，十二番花信与八处景名是这套索引的坐标。
      </p>
      <p class="explore-now">
        <span class="now-dot" aria-hidden="true" />
        此刻 {{ nowTerm.name }} · {{ nowSeason.label }} ·
        下一番花信 {{ nextBloomInfo.text }}
      </p>
    </section>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="wrap filter-inner">
        <div class="filter-seasons" role="group" aria-label="按季节筛选">
          <TopicChip label="全部" :active="!season" @select="setSeason('')" />
          <TopicChip
            v-for="item in SEASONS"
            :key="item.key"
            :label="item.char"
            :season="item.key"
            :active="season === item.label"
            @select="setSeason(item.label)"
          />
        </div>

        <div class="filter-selects">
          <label class="select-wrap">
            <span class="sr-only">校区</span>
            <select v-model="campus" class="filter-select" @change="applyFilters">
              <option value="">全部校区</option>
              <option v-for="item in CAMPUSES" :key="item" :value="item">{{ item }}</option>
            </select>
            <svg class="select-chevron" width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="m4 6 4 4 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </label>

          <label class="select-wrap">
            <span class="sr-only">分类</span>
            <select v-model="category" class="filter-select" @change="applyFilters">
              <option value="">全部分类</option>
              <option v-for="item in CATEGORY_OPTIONS" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
            <svg class="select-chevron" width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="m4 6 4 4 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </label>

          <label class="select-wrap">
            <span class="sr-only">排序</span>
            <select v-model="sort" class="filter-select" @change="applyFilters">
              <option v-for="option in SORT_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
            <svg class="select-chevron" width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="m4 6 4 4 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </label>

          <button
            v-if="landscapeName"
            class="active-pill"
            type="button"
            :aria-label="`清除景名筛选：${landscapeName}`"
            @click="clearLandscape"
          >
            景名 · {{ landscapeName }} <span aria-hidden="true">×</span>
          </button>

          <button v-if="filtersActive" class="filter-reset" type="button" @click="resetFilters">
            清除筛选
          </button>
        </div>
      </div>
    </div>

    <!-- 结果 -->
    <section class="wrap results" aria-label="作品列表">
      <div v-if="error && items.length === 0" class="results-state">
        <EmptyState
          title="作品暂时没加载出来"
          :description="error"
          action-label="重新加载"
          error
          @action="reload"
        />
      </div>

      <EmptyState
        v-else-if="!initialLoading && items.length === 0"
        :title="landscapeEmpty ? '该景暂无作品' : filtersActive ? '没有符合条件的作品' : '还没有作品'"
        :description="landscapeEmpty ? '这个景名还没有对应的公开作品，后续会陆续收录。可以先去其它角落看看。' : filtersActive ? '换一个季节、校区或景名试试，也可以清除筛选看全部。' : '第一批照片正在路上，你也可以成为第一个把校园放进来的人。'"
        :action-label="landscapeEmpty ? '去看看其它作品' : filtersActive ? '清除筛选' : '去投稿'"
        @action="landscapeEmpty ? resetFilters() : filtersActive ? resetFilters() : $router.push('/upload')"
      />

      <MasonryGrid
        v-else
        :items="items"
        :loading="initialLoading"
        :max-columns="4"
        :skeleton-rows="3"
        eager
      />

      <div v-if="loading && items.length > 0" class="more-skeleton" aria-hidden="true">
        <SkeletonCard v-for="index in 3" :key="index" :aspect-ratio="index === 2 ? 1.3 : 0.75" />
      </div>

      <div v-if="error && items.length > 0" class="more-error" role="status">
        <span>加载更多失败，请稍后重试。</span>
        <button class="btn btn--ghost" type="button" @click="loadMore">重试</button>
      </div>

      <div v-if="!initialLoading && done && items.length > 0" class="results-end">
        <p>已看完 · 共 {{ total }} 件作品</p>
        <button class="btn btn--ghost" type="button" @click="backToTop">回到顶部 ↑</button>
      </div>

      <div ref="sentinel" class="sentinel" aria-hidden="true" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchPublicPhotos, type PublicPhoto } from '../api/public'
import {
  EIGHT_VIEWS,
  SEASONS,
  currentSeason,
  currentTerm,
  nextBloom,
} from '../constants/public'
import EmptyState from '../components/public/EmptyState.vue'
import MasonryGrid from '../components/public/MasonryGrid.vue'
import SkeletonCard from '../components/public/SkeletonCard.vue'
import TopicChip from '../components/public/TopicChip.vue'

const route = useRoute()
const router = useRouter()

const PAGE_SIZE = 24
const CAMPUSES = ['昌平校区', '朝阳校区', '海淀校区']
/** 后端 category 是英文枚举（Landscape / Documentary / Activity），展示用中文 */
const CATEGORY_OPTIONS = [
  { value: 'Landscape', label: '校园景观' },
  { value: 'Documentary', label: '校园纪实' },
  { value: 'Activity', label: '校园活动' },
] as const
const SORT_OPTIONS = [
  { value: 'new', label: '最新发布' },
  { value: 'uploaded', label: '最新上传' },
  { value: 'popular', label: '最多浏览' },
] as const
type SortKey = (typeof SORT_OPTIONS)[number]['value']

/* ---------- 「此刻」来自真实节气 ---------- */
const nowTerm = currentTerm()
const nowSeason = currentSeason()
const upcomingBloom = nextBloom()
const nextBloomInfo = { text: `${upcomingBloom.month}月${upcomingBloom.ten}的${upcomingBloom.name}` }

/* ---------- 筛选状态 ---------- */
const season = ref('')
const campus = ref('')
const category = ref('')
/** 景名目前只从 URL 进入（首页八景卡片），不占一个下拉位 */
const landscape = ref('')
const sort = ref<SortKey>('new')

const landscapeName = computed(
  () => EIGHT_VIEWS.find((view) => view.node === landscape.value)?.name || landscape.value,
)

const filtersActive = computed(() =>
  Boolean(season.value || campus.value || category.value || landscape.value),
)

/** 八景/景名筛选：目前后端种子数据尚未打 landscape 标签，空结果时给叙事化的空态而不是故障感 */
const landscapeEmpty = computed(() => Boolean(landscape.value))

/* ---------- 列表数据 ---------- */
const items = ref<PublicPhoto[]>([])
const total = ref(0)
const loading = ref(false)
const initialLoading = ref(true)
const error = ref('')

const done = computed(() => !initialLoading.value && items.value.length >= total.value)

function sortParams(): { sort_by: 'created_at' | 'views' | 'published_at'; sort_order: 'asc' | 'desc' } {
  if (sort.value === 'popular') return { sort_by: 'views', sort_order: 'desc' }
  if (sort.value === 'uploaded') return { sort_by: 'created_at', sort_order: 'desc' }
  return { sort_by: 'published_at', sort_order: 'desc' }
}

function baseQuery() {
  const { sort_by, sort_order } = sortParams()
  return {
    season: season.value || undefined,
    campus: campus.value || undefined,
    category: category.value || undefined,
    landscape: landscape.value || undefined,
    sort_by,
    sort_order,
  }
}

const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

function observeSentinel() {
  observer?.disconnect()
  if (!sentinel.value) return
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadMore()
    },
    { rootMargin: '600px 0px' },
  )
  observer.observe(sentinel.value)
}

async function loadPage(reset = false) {
  if (loading.value) return
  if (!reset && (done.value || Boolean(error.value))) return

  loading.value = true
  if (reset) {
    error.value = ''
    items.value = []
    total.value = 0
    initialLoading.value = true
  }

  try {
    const page = await fetchPublicPhotos({
      ...baseQuery(),
      skip: reset ? 0 : items.value.length,
      limit: PAGE_SIZE,
    })
    items.value = reset ? page.items : [...items.value, ...page.items]
    total.value = page.total
    error.value = ''
    await nextTick()
    observeSentinel()
  } catch (cause) {
    error.value = '网络或服务暂时不可用，请稍后再试。'
    console.warn('[explore] 作品加载失败', cause)
  } finally {
    loading.value = false
    initialLoading.value = false
  }
}

function loadMore() {
  if (!loading.value && !done.value && !error.value) void loadPage(false)
}

function reload() {
  void loadPage(true)
}

/* ---------- URL 同步：筛选变化写回 query，支持分享/回退 ---------- */
function syncQuery() {
  const query: Record<string, string> = {}
  if (season.value) query.season = season.value
  if (campus.value) query.campus = campus.value
  if (category.value) query.category = category.value
  if (landscape.value) query.landscape = landscape.value
  if (sort.value !== 'new') query.sort = sort.value
  void router.replace({ path: '/explore', query })
}

function clearLandscape() {
  landscape.value = ''
  applyFilters()
}

function applyFilters() {
  syncQuery()
  window.scrollTo({ top: 0, behavior: prefersReduced() ? 'auto' : 'smooth' })
  void loadPage(true)
}

function setSeason(label: string) {
  if (season.value === label) return
  season.value = label
  applyFilters()
}

function resetFilters() {
  season.value = ''
  campus.value = ''
  category.value = ''
  landscape.value = ''
  sort.value = 'new'
  applyFilters()
}

/* ---------- 从 URL 读取筛选 ---------- */
function readString(value: unknown): string {
  if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : ''
  return typeof value === 'string' ? value : ''
}

function applyQuery(): boolean {
  const nextSeason = readString(route.query.season)
  const nextCampus = readString(route.query.campus)
  const nextCategory = readString(route.query.category)
  const nextLandscape = readString(route.query.landscape)
  const nextSortRaw = readString(route.query.sort)
  const nextSort = (SORT_OPTIONS.some((option) => option.value === nextSortRaw)
    ? nextSortRaw
    : 'new') as SortKey

  const same =
    season.value === nextSeason &&
    campus.value === nextCampus &&
    category.value === nextCategory &&
    landscape.value === nextLandscape &&
    sort.value === nextSort

  season.value = SEASONS.some((item) => item.label === nextSeason) ? nextSeason : ''
  campus.value = CAMPUSES.includes(nextCampus) ? nextCampus : ''
  category.value = CATEGORY_OPTIONS.some((item) => item.value === nextCategory)
    ? nextCategory
    : ''
  landscape.value = EIGHT_VIEWS.some((view) => view.node === nextLandscape) ? nextLandscape : ''
  sort.value = nextSort
  return !same
}

function prefersReduced(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function backToTop() {
  window.scrollTo({ top: 0, behavior: prefersReduced() ? 'auto' : 'smooth' })
}

watch(
  () => route.query,
  () => {
    if (route.path !== '/explore') return
    if (applyQuery()) void loadPage(true)
  },
)

onMounted(() => {
  applyQuery()
  void loadPage(true)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<style scoped>
/* ---------- 页头 ---------- */
.explore-head {
  padding-block: clamp(36px, 4.6vw, 64px) clamp(24px, 3vw, 36px);
}

.head-row {
  display: flex;
  align-items: baseline;
  gap: 18px;
  margin-top: 10px;
}

.explore-title {
  font-family: var(--display);
  font-size: clamp(56px, 7vw, 84px);
  letter-spacing: 0.02em;
  line-height: 1;
}

.head-count {
  color: var(--faint);
  font-size: var(--fs-sm);
  font-variant-numeric: tabular-nums;
}

.explore-desc {
  max-width: 36em;
  margin-top: 14px;
  color: var(--muted);
  font-size: var(--fs-sm);
  line-height: 1.85;
}

.explore-now {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  color: var(--faint);
  font-size: var(--fs-xs);
}

.now-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--sakura);
  box-shadow: 0 0 0 4px rgba(232, 98, 140, 0.14);
}

/* ---------- 筛选栏：吸顶 + 不透明底，避免花哨玻璃 ---------- */
.filter-bar {
  position: sticky;
  top: var(--nav-h);
  z-index: var(--z-sticky);
  background: var(--ground);
  border-block: 1px solid var(--line);
}

.filter-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px 20px;
  padding-block: 12px;
}

.filter-seasons {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  scrollbar-width: none;
}

.filter-seasons::-webkit-scrollbar {
  display: none;
}

.filter-selects {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.select-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.filter-select {
  height: 40px;
  padding: 0 34px 0 16px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--ink);
  font-size: var(--fs-sm);
  line-height: 1;
  outline: none;
  appearance: none;
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out);
}

.filter-select:hover,
.filter-select:focus-visible {
  border-color: var(--sakura);
}

.select-chevron {
  position: absolute;
  right: 14px;
  color: var(--faint);
  pointer-events: none;
}

.filter-reset {
  height: 40px;
  padding: 0 14px;
  border-radius: var(--r-pill);
  color: var(--sakura-deep);
  font-size: var(--fs-sm);
}

.active-pill {
  height: 34px;
  padding: 0 14px;
  border-radius: var(--r-pill);
  background: var(--sakura-mist);
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  white-space: nowrap;
}

.active-pill:hover {
  background: var(--sakura-pale);
}

.filter-reset:hover {
  background: var(--sakura-mist);
}

/* ---------- 结果 ---------- */
.results {
  padding-block: clamp(24px, 3.4vw, 44px) var(--section-gap);
}

.results-state {
  padding-block: 24px;
}

.more-skeleton {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--gap);
  margin-top: var(--gap);
}

.sentinel {
  height: 1px;
}

.more-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding-block: 24px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.results-end {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 14px;
  padding-block: clamp(36px, 4.6vw, 60px) 0;
  color: var(--faint);
  font-size: var(--fs-sm);
  text-align: center;
}

@media (max-width: 900px) {
  .filter-inner {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-selects {
    justify-content: space-between;
  }

  .select-wrap {
    flex: 1;
  }

  .filter-select {
    width: 100%;
  }
}

@media (max-width: 720px) {
  .head-row {
    flex-wrap: wrap;
    gap: 8px;
  }

  .filter-bar {
    position: static;
  }

  .more-skeleton {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
