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
        按季节、校区与取景地筛选。每一张都保留原始构图与作者署名，十二番花信与一日四光是这套索引的坐标。
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

        <div class="filter-periods" role="group" aria-label="按光线时段筛选">
          <span class="filter-periods-label">光</span>
          <div class="period-chips">
            <button
              type="button"
              class="period-chip period-chip--all"
              :class="{ 'is-active': !period }"
              :aria-pressed="!period"
              @click="setPeriod('')"
            >
              全部
            </button>
            <button
              v-for="option in PERIOD_OPTIONS"
              :key="option.key"
              type="button"
              class="period-chip"
              :class="[`period-chip--${option.key}`, { 'is-active': period === option.key }]"
              :aria-pressed="period === option.key"
              :aria-label="`${option.label} ${option.range}`"
              @click="setPeriod(option.key)"
            >
              <span class="period-dot" aria-hidden="true" />
              {{ option.label }}
            </button>
          </div>
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
            :aria-label="`清除取景地筛选：${landscapeName}`"
            @click="clearLandscape"
          >
            取景 · {{ landscapeName }} <span aria-hidden="true">×</span>
          </button>

          <button v-if="filtersActive" class="filter-reset" type="button" @click="resetFilters">
            清除筛选
          </button>
        </div>

        <div class="privacy-row">
          <label class="privacy-switch" :class="{ 'is-locked': !isAuthed }">
            <input
              type="checkbox"
              role="switch"
              class="privacy-input"
              :checked="includeSensitive"
              :aria-checked="includeSensitive"
              aria-label="显示人像作品（已脱敏）"
              @change="onToggleSensitive"
            />
            <span class="switch-track" aria-hidden="true"><span class="switch-thumb" /></span>
            <span class="switch-text">显示人像作品（已脱敏）</span>
            <svg v-if="authReady && !isAuthed" class="lock" width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect x="5" y="10.5" width="14" height="9" rx="2" stroke="currentColor" stroke-width="1.8" />
              <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" stroke="currentColor" stroke-width="1.8" />
            </svg>
          </label>
          <p class="privacy-hint">人像作品默认隐藏，展示的是脱敏图；原图仅作者与管理员可见。</p>
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
        :title="landscapeEmpty ? '该景暂无作品' : periodEmpty ? '这个时段还没有作品' : filtersActive ? '没有符合条件的作品' : '还没有作品'"
        :description="landscapeEmpty ? '这个取景地还没有对应的公开作品，后续会陆续收录。可以先去其它角落看看。' : periodEmpty ? '试试其他时段，也可以清除筛选，先看看全部作品。' : filtersActive ? '换一个季节、校区或取景地试试，也可以清除筛选看全部。' : '第一批照片正在路上，你也可以成为第一个把校园放进来的人。'"
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
import { useMessage } from 'naive-ui'
import { fetchPublicPhotos, type PublicPhoto } from '../api/public'
import { useAuthStore } from '../stores/auth'
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

/** 光线时段：与首页「光的一日」同一套区间（后端 light_of_day.py） */
const PERIOD_OPTIONS = [
  { key: 'dawn', label: '晨', range: '05:00–09:00' },
  { key: 'noon', label: '昼', range: '09:00–15:00' },
  { key: 'dusk', label: '暮', range: '15:00–19:00' },
  { key: 'night', label: '夜', range: '19:00–05:00' },
] as const
type PeriodKey = (typeof PERIOD_OPTIONS)[number]['key']

/* ---------- 「此刻」来自真实节气 ---------- */
const nowTerm = currentTerm()
const nowSeason = currentSeason()
const upcomingBloom = nextBloom()
const nextBloomInfo = { text: `${upcomingBloom.month}月${upcomingBloom.ten}的${upcomingBloom.name}` }

/* ---------- 筛选状态 ---------- */
const season = ref('')
const campus = ref('')
const category = ref('')
/** 取景地目前只从 URL 进入（专题/光谱深链），不占一个下拉位 */
const landscape = ref('')
/** 光线时段（晨/昼/暮/夜），空串表示全部 */
const period = ref<PeriodKey | ''>('')
const sort = ref<SortKey>('new')
/** 是否纳入人像作品（仅登录后生效；状态存 localStorage，刷新后保持） */
const includeSensitive = ref(false)
const INCLUDE_SENSITIVE_KEY = 'sakura:include-sensitive'
const PENDING_SENSITIVE_KEY = 'sakura:include-sensitive-pending'
const auth = useAuthStore()
const message = useMessage()
const isAuthed = computed(() => auth.isAuthenticated)
/** 登录态初始化完成前先不显示锁标，避免「一秒锁」闪烁 */
const authReady = ref(false)

const landscapeName = computed(
  () => EIGHT_VIEWS.find((view) => view.node === landscape.value)?.name || landscape.value,
)

const filtersActive = computed(() =>
  Boolean(season.value || campus.value || category.value || landscape.value || period.value),
)

/** 只选了光线时段或时段组合结果为空时，给更贴切的解释文案 */
const periodEmpty = computed(() => Boolean(period.value))

/** 取景地筛选：目前后端种子数据尚未打 landscape 标签，空结果时给叙事化的空态而不是故障感 */
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
    period: period.value || undefined,
    sort_by,
    sort_order,
    include_sensitive: includeSensitive.value && isAuthed.value ? true : undefined,
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
  if (period.value) query.period = period.value
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

function setPeriod(next: PeriodKey | '') {
  if (period.value === next) return
  period.value = next
  applyFilters()
}

function resetFilters() {
  season.value = ''
  campus.value = ''
  category.value = ''
  landscape.value = ''
  period.value = ''
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
  const nextPeriodRaw = readString(route.query.period)
  const nextPeriod = PERIOD_OPTIONS.some((option) => option.key === nextPeriodRaw)
    ? (nextPeriodRaw as PeriodKey)
    : ''
  const nextSortRaw = readString(route.query.sort)
  const nextSort = (SORT_OPTIONS.some((option) => option.value === nextSortRaw)
    ? nextSortRaw
    : 'new') as SortKey

  const same =
    season.value === nextSeason &&
    campus.value === nextCampus &&
    category.value === nextCategory &&
    landscape.value === nextLandscape &&
    period.value === nextPeriod &&
    sort.value === nextSort

  season.value = SEASONS.some((item) => item.label === nextSeason) ? nextSeason : ''
  campus.value = CAMPUSES.includes(nextCampus) ? nextCampus : ''
  category.value = CATEGORY_OPTIONS.some((item) => item.value === nextCategory)
    ? nextCategory
    : ''
  landscape.value = EIGHT_VIEWS.some((view) => view.node === nextLandscape) ? nextLandscape : ''
  period.value = nextPeriod
  sort.value = nextSort
  return !same
}

function prefersReduced(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function backToTop() {
  window.scrollTo({ top: 0, behavior: prefersReduced() ? 'auto' : 'smooth' })
}

/* ---------- 人像作品开关（登录后生效，localStorage 保持） ---------- */
function readStoredSensitive(): boolean {
  try {
    return localStorage.getItem(INCLUDE_SENSITIVE_KEY) === '1'
  } catch {
    return false
  }
}

function storeSensitive(value: boolean) {
  try {
    if (value) localStorage.setItem(INCLUDE_SENSITIVE_KEY, '1')
    else localStorage.removeItem(INCLUDE_SENSITIVE_KEY)
  } catch {
    // localStorage 不可用（隐私模式）时只影响记忆，不影响当前会话
  }
}

function onToggleSensitive(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  if (!checked) {
    includeSensitive.value = false
    storeSensitive(false)
    applyFilters()
    return
  }
  if (!isAuthed.value) {
    // 未登录：还原开关并引导登录，登录后回到探索页
    includeSensitive.value = false
    try {
      localStorage.setItem(PENDING_SENSITIVE_KEY, '1')
    } catch {
      // 忽略
    }
    message.info('登录后可以查看已脱敏的人像作品')
    void router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  includeSensitive.value = true
  storeSensitive(true)
  applyFilters()
}

/** 登录回来后自动恢复用户想看的开关 */
function syncSensitiveWithAuth() {
  if (!isAuthed.value) {
    if (includeSensitive.value) {
      includeSensitive.value = false
      storeSensitive(false)
      void loadPage(true)
    }
    return
  }
  let pending = false
  try {
    pending = localStorage.getItem(PENDING_SENSITIVE_KEY) === '1'
    if (pending) localStorage.removeItem(PENDING_SENSITIVE_KEY)
  } catch {
    // 忽略
  }
  if (pending) {
    includeSensitive.value = true
    storeSensitive(true)
    void loadPage(true)
  } else if (!includeSensitive.value) {
    includeSensitive.value = readStoredSensitive()
    if (includeSensitive.value) void loadPage(true)
  }
}

/* ---------- 滚动位置恢复：从详情页返回时回到原来的位置 ---------- */
const SCROLL_KEY = 'sakura:explore-scroll'
let restoringScroll = false

function saveScroll() {
  try {
    sessionStorage.setItem(SCROLL_KEY, JSON.stringify({ path: route.fullPath, y: window.scrollY }))
  } catch {
    // 忽略
  }
}

function restoreScroll() {
  if (restoringScroll) return
  let saved: { path?: string; y?: number } | null = null
  try {
    saved = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || 'null')
  } catch {
    saved = null
  }
  try {
    sessionStorage.removeItem(SCROLL_KEY)
  } catch {
    // 忽略
  }
  if (!saved || saved.path !== route.fullPath || !saved.y || saved.y < 80) return
  restoringScroll = true
  requestAnimationFrame(() => {
    const maxY = Math.max(0, document.documentElement.scrollHeight - window.innerHeight)
    window.scrollTo({ top: Math.min(saved?.y ? saved.y : 0, maxY), behavior: 'auto' })
    restoringScroll = false
  })
}

watch(
  () => route.query,
  () => {
    if (route.path !== '/explore') return
    if (applyQuery()) void loadPage(true).then(restoreScrollAfterLoad)
  },
)

watch(isAuthed, syncSensitiveWithAuth)

function restoreScrollAfterLoad() {
  // 首屏数据渲染后（Masonry 需要 measure）再恢复
  setTimeout(restoreScroll, 120)
}

onMounted(async () => {
  void auth.whenReady().finally(() => {
    authReady.value = true
  })
  // 登录状态决定是否恢复人像开关；登录跳转回来时消费「待开启」意图
  includeSensitive.value = isAuthed.value ? readStoredSensitive() : false
  if (isAuthed.value) {
    try {
      if (localStorage.getItem(PENDING_SENSITIVE_KEY) === '1') {
        localStorage.removeItem(PENDING_SENSITIVE_KEY)
        includeSensitive.value = true
        storeSensitive(true)
      }
    } catch {
      // 忽略
    }
  }
  applyQuery()
  await loadPage(true)
  restoreScrollAfterLoad()
})

onBeforeUnmount(() => {
  saveScroll()
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
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}

.filter-seasons::-webkit-scrollbar {
  display: none;
}

/* ---------- 按光浏览：晨 / 昼 / 暮 / 夜 ---------- */
.filter-periods {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-basis: 100%;
  min-width: 0;
}

.filter-periods-label {
  flex: none;
  color: var(--faint);
  font-size: var(--fs-xs);
  letter-spacing: 0.14em;
}

.period-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  overflow-x: auto;
  min-width: 0;
  padding-block: 2px;
  scrollbar-width: none;
}

.period-chips::-webkit-scrollbar {
  display: none;
}

.period-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex: none;
  height: 40px;
  padding: 0 18px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--muted);
  font-size: var(--fs-14);
  font-weight: 500;
  white-space: nowrap;
  transition: transform var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out);
}

.period-chip:hover {
  border-color: var(--period-accent, var(--sakura));
  color: var(--ink);
}

.period-chip.is-active {
  border-color: var(--period-accent, var(--sakura-deep));
  background: var(--period-pale, var(--sakura-pale));
  color: var(--ink);
}

.period-chip--all {
  --period-accent: var(--sakura);
  --period-pale: var(--sakura-pale);
}

.period-chip--all.is-active {
  border-color: var(--sakura-deep);
  background: var(--sakura-deep);
  color: var(--on-accent);
}

.period-chip--all.is-active .period-dot {
  background: var(--on-accent);
}

.period-chip--dawn {
  --period-accent: var(--autumn);
  --period-pale: var(--autumn-pale);
}

.period-chip--noon {
  --period-accent: var(--sakura);
  --period-pale: var(--sakura-pale);
}

.period-chip--dusk {
  --period-accent: color-mix(in srgb, var(--spring) 55%, var(--autumn) 45%);
  --period-pale: var(--spring-pale);
}

.period-chip--night {
  --period-accent: var(--winter);
  --period-pale: var(--winter-pale);
}

.period-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--period-accent, var(--sakura));
  opacity: 0.9;
}

.period-chip:active {
  transform: scale(0.97);
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

  /* 列向布局下显式撑满容器，避免内容 min-width 把页面顶出横向滚动 */
  .filter-seasons,
  .filter-periods,
  .filter-selects,
  .privacy-row {
    width: 100%;
    max-width: 100%;
    min-width: 0;
    box-sizing: border-box;
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

/* ---------- 人像作品开关（隐私分级） ---------- */
.privacy-row {
  flex-basis: 100%;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding-top: 2px;
}

.privacy-switch {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 5px 13px 5px 9px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--ink);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out), background-color var(--dur-fast) var(--ease-out);
}

.privacy-switch:hover {
  border-color: var(--sakura);
}

.privacy-switch:focus-within {
  border-color: var(--sakura-deep);
  box-shadow: 0 0 0 3px var(--sakura-mist);
}

.privacy-switch.is-locked {
  color: var(--muted);
}

.privacy-input {
  position: absolute;
  top: 50%;
  left: 0;
  width: 44px;
  height: 44px;
  padding: 0;
  margin: 0;
  transform: translateY(-50%);
  opacity: 0;
  cursor: pointer;
  white-space: nowrap;
  border: 0;
}

.switch-track {
  position: relative;
  flex: none;
  width: 34px;
  height: 20px;
  border-radius: var(--r-pill);
  background: var(--line-strong);
  transition: background-color var(--dur-fast) var(--ease-out);
}

.switch-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 4px rgba(74, 43, 53, 0.25);
  transition: transform var(--dur-fast) var(--ease-out);
}

.privacy-input:checked + .switch-track {
  background: var(--sakura-deep);
}

.privacy-input:checked + .switch-track .switch-thumb {
  transform: translateX(14px);
}

.privacy-input:focus-visible + .switch-track {
  outline: 3px solid var(--sakura);
  outline-offset: 2px;
}

.privacy-hint {
  color: var(--faint);
  font-size: var(--fs-xs);
  line-height: 1.6;
}

@media (prefers-reduced-motion: reduce) {
  .switch-track,
  .switch-thumb {
    transition: none;
  }
}

@media (max-width: 640px) {
  .privacy-switch {
    font-size: var(--fs-xs);
  }

  .privacy-hint {
    flex-basis: 100%;
    margin: 0;
  }
}
</style>