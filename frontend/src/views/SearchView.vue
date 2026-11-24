<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NIcon, NInput, useMessage } from 'naive-ui'
import { onClickOutside, useDebounceFn } from '@vueuse/core'
import {
  ArrowUpOutline,
  FlashOutline,
  GitBranchOutline,
  ImageOutline,
  SearchOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import {
  getSearchFacets,
  getSearchSuggestions,
  searchWorks,
  type AgentSearchResult,
  type SearchFacets,
  type SearchMode,
  type SearchWork,
  type VisualSearchResponse,
} from '../api/search'
import SkeletonCard from '../components/public/SkeletonCard.vue'
import ClarifyCard from '../components/search/ClarifyCard.vue'
import FacetChips from '../components/search/FacetChips.vue'
import ImageSearchPanel from '../components/search/ImageSearchPanel.vue'
import ResultMasonry from '../components/search/ResultMasonry.vue'
import SearchEmptyState from '../components/search/SearchEmptyState.vue'
import SearchStepsTimeline from '../components/search/SearchStepsTimeline.vue'
import '../styles/search.css'

const PAGE_SIZE = 24
const CONTEXT_LIMIT = 3
const IDLE_SUGGESTIONS = ['樱花大道的春天', '操场夜景', '图书馆里的人', '秋天的银杏']
const HISTORY_KEY = 'sakura:search-history'
const HISTORY_LIMIT = 8
const SKELETON_SHAPES = [4 / 3, 3 / 4, 1, 3 / 4, 4 / 3, 1, 3 / 4, 4 / 3]

const MODE_LABELS: Record<string, string> = {
  agent: 'Agent 智能检索',
  fast: '快速检索',
  keyword: '关键词检索',
  vector: '语义检索',
  hybrid: '混合检索',
  lexical: '关键词检索',
}

const FALLBACK_LABELS: Record<string, string> = {
  fast_mode: '当前为快速检索模式',
  ai_disabled: 'Agent 模型未启用，已降级为关键词检索',
  planner_failed: '意图解析失败，已降级为关键词检索',
  agent_search_disabled: 'Agent 检索已关闭，已降级为关键词检索',
  disabled: 'Agent 检索已关闭，已降级为关键词检索',
}

interface RouteState {
  q: string
  mode: SearchMode
  season: string
  category: string
  campus: string
}

const route = useRoute()
const router = useRouter()
const message = useMessage()

const queryInput = ref('')
const q = ref('')
const mode = ref<SearchMode>('agent')
const season = ref('')
const category = ref('')
const campus = ref('')

const works = ref<SearchWork[]>([])
const total = ref(0)
const result = ref<AgentSearchResult | null>(null)
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')
const errorKind = ref<'error' | 'timeout'>('error')
const searched = ref(false)
const retrying = ref(false)

const facets = ref<SearchFacets>({ season: [], category: [], tag: [], campus: [] })
const facetsLoading = ref(false)

const fallbackDismissed = ref(false)
const suggestions = ref<string[]>([])
const suggestionsOpen = ref(false)
const activeSuggestion = ref(-1)
const searchBox = ref<HTMLElement | null>(null)
const searchInput = ref<InstanceType<typeof NInput> | null>(null)
const showBackToTop = ref(false)
const history = ref<string[]>(readHistory())
const emptySuggestions = ref<string[]>([])
const activeResultIndex = ref(-1)

// 多轮追问上下文：最近 3 条上一轮提问（不含当前，不写 URL，仅 agent 文本检索生效）
const contextHistory = ref<string[]>([])

// 以图搜图（独立于文本检索的模式，不写入 URL）
const imagePanelOpen = ref(false)
const visualResult = ref<VisualSearchResponse | null>(null)
const imageTrigger = ref<HTMLElement | null>(null)

let searchSeq = 0
let suggestSeq = 0
let appliedKey = ''
// 由 URL / facet 程序化写入输入框时，不自动弹出联想面板
let programmaticQuery = false

onClickOutside(searchBox, () => closeSuggestions())

const hasActiveFilters = computed(() => Boolean(season.value || category.value || campus.value))
const hasFacets = computed(
  () =>
    facets.value.season.length > 0 ||
    facets.value.category.length > 0 ||
    facets.value.campus.length > 0,
)
const hasMore = computed(() => works.value.length > 0 && works.value.length < total.value)

const showSkeleton = computed(() => loading.value && works.value.length === 0)
const hasHistory = computed(() => history.value.length > 0)

const totalText = computed(() => {
  if (loading.value && !works.value.length) return '正在检索…'
  if (!total.value) return `${works.value.length} 件`
  return `共 ${total.value} 件`
})

function shortModeLabel(): string {
  const searchMode = result.value?.searchMode || mode.value
  if (searchMode === 'fast') return '快速'
  if (searchMode === 'agent') return 'Agent'
  return MODE_LABELS[searchMode] || '检索'
}

const resultMeta = computed(() => {
  if (!result.value) return ''
  const ms = Math.round(result.value.queryTimeMs)
  const parts = [`共 ${formatCount(total.value)} 件`, `用时 ${ms} ms`, shortModeLabel()]
  return parts.join(' · ')
})

const latestContext = computed(() => contextHistory.value[contextHistory.value.length - 1] || '')

const assumedContext = computed(() => {
  const assumed = result.value?.intent?.assumed ?? []
  return assumed.find((item) => item.includes('承接')) || ''
})

// 仅当「上文非空 + agent 模式 + 有结果（或正在载入）」时显示上下文条
const showContextBar = computed(() => {
  if (!contextHistory.value.length) return false
  if (mode.value !== 'agent') return false
  if (visualResult.value || imagePanelOpen.value) return false
  if (loading.value) return true
  if (error.value || !result.value) return false
  return total.value > 0 || Boolean(result.value.clarify)
})

function formatCount(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value ?? 0)
}

const fallbackNotice = computed(() => {
  const reason = result.value?.fallbackReason
  if (!reason) return ''
  return FALLBACK_LABELS[reason] || `检索已降级（${reason}）`
})

const fallbackTone = computed<'info' | 'warning'>(() =>
  result.value?.searchMode === 'fast' || result.value?.fallbackReason === 'fast_mode' ? 'info' : 'warning',
)

// ────────────────────────────────────────────────────────────
// URL 同步
// ────────────────────────────────────────────────────────────

function stringQuery(key: string): string {
  const value = route.query[key]
  return typeof value === 'string' ? value.trim() : ''
}

function currentState(): RouteState {
  return {
    q: q.value,
    mode: mode.value,
    season: season.value,
    category: category.value,
    campus: campus.value,
  }
}

function pushUrl() {
  const state = currentState()
  appliedKey = JSON.stringify(state)
  const query: Record<string, string> = {}
  if (state.q) query.q = state.q
  if (state.mode === 'fast') query.mode = 'fast'
  if (state.season) query.season = state.season
  if (state.category) query.category = state.category
  if (state.campus) query.campus = state.campus
  void router.replace({ path: '/search', query })
}

function applyRoute(force = false) {
  const state: RouteState = {
    q: stringQuery('q'),
    mode: stringQuery('mode') === 'fast' ? 'fast' : 'agent',
    season: stringQuery('season'),
    category: stringQuery('category'),
    campus: stringQuery('campus'),
  }
  const key = JSON.stringify(state)
  if (!force && key === appliedKey) return
  appliedKey = key

  q.value = state.q
  programmaticQuery = true
  queryInput.value = state.q
  void nextTick(() => {
    programmaticQuery = false
  })
  mode.value = state.mode
  season.value = state.season
  category.value = state.category
  campus.value = state.campus

  if (state.q) {
    void performSearch()
  } else {
    resetToIdle()
  }
}

watch(
  () => route.query,
  () => applyRoute(),
  { deep: true },
)

// ────────────────────────────────────────────────────────────
// 检索
// ────────────────────────────────────────────────────────────

/** 组装发给后端的 history：仅 agent 模式且确有上文时发送，最多 3 条（只发上一轮提问，当前 query 由 q 参数承担） */
function agentHistory(): string[] | undefined {
  if (mode.value !== 'agent' || !contextHistory.value.length) return undefined
  return contextHistory.value.filter((item) => item.trim().length > 0).slice(-CONTEXT_LIMIT)
}

function facetParams() {
  return {
    season: season.value || null,
    category: category.value || null,
    campus: campus.value || null,
  }
}

function hasFacetItems(value: SearchFacets): boolean {
  return value.season.length > 0 || value.category.length > 0 || value.campus.length > 0 || value.tag.length > 0
}

function describeError(raw: unknown): { message: string; kind: 'error' | 'timeout' } {
  const record = (raw ?? {}) as Record<string, unknown>
  const code = String(record.code ?? '')
  const response = record.response as Record<string, unknown> | undefined
  const status = Number(record.status ?? response?.status ?? 0)
  const message = String(record.message ?? '')

  if (code === 'ECONNABORTED' || code === 'ETIMEDOUT' || /timeout/i.test(message)) {
    return { message: '本次检索耗时过长。可以稍后重试，或切换到「快速检索」先看结果。', kind: 'timeout' }
  }
  if (!status || code === 'ERR_NETWORK') {
    return { message: '网络连接失败，请检查网络后重试。', kind: 'error' }
  }
  if (status === 429) {
    return { message: '检索请求太频繁了，请稍等片刻再试。', kind: 'error' }
  }
  if (status >= 500) {
    return { message: `检索服务暂时不可用（${status}），请稍后重试。`, kind: 'error' }
  }
  if (status === 400) {
    return { message: '检索条件有误，请调整关键词后重试。', kind: 'error' }
  }
  return { message: '检索失败，请稍后重试。', kind: 'error' }
}

async function performSearch() {
  const query = q.value.trim()
  if (!query) {
    resetToIdle()
    return
  }
  visualResult.value = null
  const seq = ++searchSeq
  loading.value = true
  loadingMore.value = false
  error.value = ''
  fallbackDismissed.value = false
  works.value = []
  total.value = 0
  result.value = null
  emptySuggestions.value = []
  activeResultIndex.value = -1
  searched.value = true
  closeSuggestions()

  try {
    const response = await searchWorks({
      q: query,
      mode: mode.value,
      limit: PAGE_SIZE,
      offset: 0,
      ...facetParams(),
      history: agentHistory(),
    })
    if (seq !== searchSeq) return
    result.value = response
    works.value = response.works
    total.value = response.total
    if (hasFacetItems(response.facets)) facets.value = response.facets
    if (!response.works.length && !response.total) void loadEmptySuggestions(query)
  } catch (raw) {
    if (seq !== searchSeq) return
    const described = describeError(raw)
    error.value = described.message
    errorKind.value = described.kind
  } finally {
    if (seq === searchSeq) {
      loading.value = false
      retrying.value = false
    }
  }
}

function resetToIdle() {
  searchSeq += 1
  contextHistory.value = []
  visualResult.value = null
  activeResultIndex.value = -1
  emptySuggestions.value = []
  loading.value = false
  loadingMore.value = false
  retrying.value = false
  works.value = []
  total.value = 0
  result.value = null
  error.value = ''
  searched.value = false
  void loadFacets()
}

async function loadMore() {
  if (loading.value || loadingMore.value || !hasMore.value) return
  const seq = searchSeq
  loadingMore.value = true
  try {
    const response = await searchWorks({
      q: q.value,
      mode: mode.value,
      limit: PAGE_SIZE,
      offset: works.value.length,
      ...facetParams(),
      history: agentHistory(),
    })
    if (seq !== searchSeq) return
    const seen = new Set(works.value.map((work) => work.id))
    works.value = [...works.value, ...response.works.filter((work) => !seen.has(work.id))]
    total.value = Math.max(total.value, response.total)
  } catch (raw) {
    if (seq !== searchSeq) return
    const described = describeError(raw)
    message.error(described.message)
  } finally {
    if (seq === searchSeq) loadingMore.value = false
  }
}

function retry() {
  retrying.value = true
  void performSearch()
}

async function loadEmptySuggestions(query: string) {
  let list: string[] = []
  try {
    list = await getSearchSuggestions(query)
  } catch {
    list = []
  }
  const cleaned = list.filter((item) => item && item.trim()).slice(0, 6)
  // 建议接口没命中时给一组通用换词方向，保证空态始终可执行
  emptySuggestions.value = cleaned.length ? cleaned : IDLE_SUGGESTIONS
}

async function loadFacets() {
  facetsLoading.value = true
  try {
    const data = await getSearchFacets({ q: q.value || undefined })
    if (hasFacetItems(data)) facets.value = data
  } catch {
    // facet 只是辅助筛选，失败时静默降级为不显示
  } finally {
    facetsLoading.value = false
  }
}

// ────────────────────────────────────────────────────────────
// 搜索历史 / 键盘快捷操作
// ────────────────────────────────────────────────────────────

function readHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is string => typeof item === 'string' && item.trim().length > 0).slice(0, HISTORY_LIMIT)
  } catch {
    return []
  }
}

function persistHistory() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value))
  } catch {
    // localStorage 不可用时静默降级
  }
}

function recordHistory(keyword: string) {
  const text = keyword.trim()
  if (!text) return
  history.value = [text, ...history.value.filter((item) => item !== text)].slice(0, HISTORY_LIMIT)
  persistHistory()
}

function removeHistory(keyword: string) {
  history.value = history.value.filter((item) => item !== keyword)
  persistHistory()
}

function clearHistory() {
  history.value = []
  persistHistory()
}

function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  if (!element) return false
  const tag = element.tagName
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    element.isContentEditable ||
    Boolean(element.closest('[contenteditable="true"]'))
  )
}

function focusSearch() {
  searchInput.value?.focus()
  closeSuggestions()
}

function blurSearch() {
  const element = document.activeElement as HTMLElement | null
  if (element && searchBox.value?.contains(element)) element.blur()
  closeSuggestions()
}

function resultCards(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('.search-results .work-card'))
}

function focusResult(index: number) {
  const cards = resultCards()
  if (!cards.length) return
  const next = Math.min(Math.max(index, 0), cards.length - 1)
  activeResultIndex.value = next
  const card = cards[next]
  card?.focus({ preventScroll: true })
  card?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
}

function onGlobalKeydown(event: KeyboardEvent) {
  if (event.defaultPrevented) return
  const typing = isTypingTarget(event.target)

  if (event.key === '/' && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) {
    event.preventDefault()
    focusSearch()
    return
  }

  if (event.key === 'Escape' && typing) {
    blurSearch()
    return
  }

  if (typing) return

  if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && works.value.length && !loading.value) {
    event.preventDefault()
    const cardIsFocused = document.activeElement?.classList.contains('work-card')
    const base = activeResultIndex.value >= 0 ? activeResultIndex.value : cardIsFocused ? 0 : -1
    focusResult(event.key === 'ArrowDown' ? base + (base < 0 ? 0 : 1) : Math.max(base - 1, 0))
  }
}

// ────────────────────────────────────────────────────────────
// 交互
// ────────────────────────────────────────────────────────────

function submitSearch(raw?: string) {
  const next = (raw ?? queryInput.value).trim()
  const previous = q.value.trim()
  queryInput.value = next
  if (!next) {
    contextHistory.value = []
    q.value = ''
    pushUrl()
    resetToIdle()
    return
  }
  if (mode.value === 'agent' && previous && previous !== next) {
    contextHistory.value = [...contextHistory.value.filter((item) => item !== previous), previous].slice(-CONTEXT_LIMIT)
  }
  q.value = next
  recordHistory(next)
  pushUrl()
  void performSearch()
}

/** 清除上文后，立即用当前关键词重新检索（不带 history） */
function clearContext() {
  if (!contextHistory.value.length) return
  contextHistory.value = []
  if (q.value) {
    message.info('已清除上文，按当前关键词重新检索')
    void performSearch()
  }
}

function setMode(next: SearchMode) {
  if (mode.value === next) return
  if (next === 'fast') contextHistory.value = []
  mode.value = next
  pushUrl()
  if (q.value) void performSearch()
}

function setFacet(key: 'season' | 'category' | 'campus', value: string) {
  const current = key === 'season' ? season.value : key === 'category' ? category.value : campus.value
  const next = current === value ? '' : value
  if (!q.value) {
    if (!next) return
    q.value = next
    programmaticQuery = true
    queryInput.value = next
    void nextTick(() => {
      programmaticQuery = false
    })
  }
  if (key === 'season') season.value = next
  else if (key === 'category') category.value = next
  else campus.value = next
  pushUrl()
  void performSearch()
}

function clearFilters() {
  contextHistory.value = []
  season.value = ''
  category.value = ''
  campus.value = ''
  pushUrl()
  if (q.value) void performSearch()
}

function closeSuggestions() {
  suggestionsOpen.value = false
  activeSuggestion.value = -1
}

function onFocus() {
  if (queryInput.value.trim() && suggestions.value.length) suggestionsOpen.value = true
}

function pickSuggestion(value: string) {
  submitSearch(value)
}

function moveSuggestion(direction: 1 | -1) {
  if (!suggestions.value.length) return
  suggestionsOpen.value = true
  const next = activeSuggestion.value + direction
  if (next < 0) activeSuggestion.value = suggestions.value.length - 1
  else if (next >= suggestions.value.length) activeSuggestion.value = -1
  else activeSuggestion.value = next
}

function onInputEnter() {
  if (suggestionsOpen.value && activeSuggestion.value >= 0 && suggestions.value[activeSuggestion.value]) {
    pickSuggestion(suggestions.value[activeSuggestion.value])
    return
  }
  submitSearch()
}

const fetchSuggestions = useDebounceFn(async (text: string) => {
  const seq = ++suggestSeq
  try {
    const list = await getSearchSuggestions(text)
    if (seq !== suggestSeq) return
    suggestions.value = list.slice(0, 8)
    activeSuggestion.value = -1
  } catch {
    if (seq === suggestSeq) suggestions.value = []
  }
}, 260)

watch(queryInput, (value) => {
  if (programmaticQuery) return
  if (!value.trim()) {
    contextHistory.value = []
    suggestions.value = []
    suggestionsOpen.value = false
    return
  }
  suggestionsOpen.value = true
  void fetchSuggestions(value)
})

// ────────────────────────────────────────────────────────────
// 生命周期
// ────────────────────────────────────────────────────────────

// ────────────────────────────────────────────────────────────
// 以图搜图
// ────────────────────────────────────────────────────────────

const visualQueryText = computed(() => {
  const query = visualResult.value?.query
  if (!query) return ''
  const parts: string[] = []
  if (query.paletteName) {
    const palette = query.paletteName
    parts.push(palette.endsWith('色') ? `${palette}调` : `${palette}色调`)
  }
  if (query.width > 0 && query.height > 0) parts.push(`${query.width}×${query.height}`)
  return parts.length ? ` · ${parts.join(' · ')}` : ''
})

const visualTotalText = computed(() => {
  const total = visualResult.value?.total ?? 0
  return `找到 ${formatCount(total)} 件相近作品`
})

function openImageSearch() {
  contextHistory.value = []
  closeSuggestions()
  imagePanelOpen.value = true
}

function onImageResult(response: VisualSearchResponse) {
  visualResult.value = response
  imagePanelOpen.value = false
  void nextTick(() => {
    document.querySelector('.visual-summary')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

function clearVisualSearch() {
  visualResult.value = null
  void nextTick(() => imageTrigger.value?.focus())
}

function retryImageSearch() {
  imagePanelOpen.value = true
}

function onScroll() {
  showBackToTop.value = window.scrollY > window.innerHeight * 2
}

function backToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

onMounted(() => {
  document.title = 'Agent 检索 · 视觉百花 Sakura Gallery'
  applyRoute(true)
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('keydown', onGlobalKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('keydown', onGlobalKeydown)
  document.title = '视觉百花 Sakura Gallery'
})
</script>

<template>
  <div class="search-page">
    <div class="search-shell">
      <header class="search-hero">
        <p class="search-eyebrow">
          <n-icon :component="SparklesOutline" :size="13" />
          Agent 检索 · 视觉百花
        </p>
        <h1 class="search-title">描述你想要的画面</h1>
        <p class="search-lead">
          一句话就够了。Agent 会拆解意图、多步检索，并解释这些作品为什么与你的描述相关。
        </p>

        <div ref="searchBox" class="search-box">
          <form class="search-form" @submit.prevent="onInputEnter">
            <n-input
              ref="searchInput"
              v-model:value="queryInput"
              class="search-input"
              size="large"
              round
              clearable
              placeholder="例如：春天的樱花树下，暖光人像"
              aria-label="检索关键词"
              @keydown.enter.prevent="onInputEnter"
              @keydown.down.prevent="moveSuggestion(1)"
              @keydown.up.prevent="moveSuggestion(-1)"
              @keydown.esc="closeSuggestions"
              @focus="onFocus"
            >
              <template #prefix>
                <n-icon :component="SearchOutline" :size="18" />
              </template>
            </n-input>
            <button type="submit" class="search-submit">检索</button>
            <button
              ref="imageTrigger"
              type="button"
              class="image-search-trigger"
              :aria-expanded="imagePanelOpen"
              aria-haspopup="dialog"
              title="上传一张图，找站内视觉相似的作品"
              @click="openImageSearch"
            >
              <n-icon :component="ImageOutline" :size="16" />
              <span>以图搜图</span>
            </button>
          </form>
          <span class="search-kbd" aria-hidden="true"><kbd>/</kbd> 按 / 搜索</span>
          <button type="button" class="image-search-trigger image-search-trigger--mobile" @click="openImageSearch">
            <n-icon :component="ImageOutline" :size="16" />
            <span>以图搜图</span>
          </button>

          <ul
            v-if="suggestionsOpen && suggestions.length"
            class="search-suggest"
            role="listbox"
            aria-label="搜索建议"
          >
            <li v-for="(suggestion, index) in suggestions" :key="suggestion">
              <button
                type="button"
                class="search-suggest__item"
                :class="{ 'is-active': index === activeSuggestion }"
                role="option"
                :aria-selected="index === activeSuggestion"
                @mousedown.prevent="pickSuggestion(suggestion)"
              >
                <n-icon :component="SearchOutline" :size="13" />
                {{ suggestion }}
              </button>
            </li>
          </ul>
        </div>

        <div class="mode-switch" role="group" aria-label="检索模式">
          <button
            type="button"
            class="mode-option"
            :class="{ 'is-active': mode === 'agent' }"
            :aria-pressed="mode === 'agent'"
            @click="setMode('agent')"
          >
            <n-icon :component="SparklesOutline" :size="16" />
            <span class="mode-option__text">
              <strong>Agent 智能检索</strong>
              <small>理解意图 · 多步检索 · 给出解释</small>
            </span>
          </button>
          <button
            type="button"
            class="mode-option"
            :class="{ 'is-active': mode === 'fast' }"
            :aria-pressed="mode === 'fast'"
            @click="setMode('fast')"
          >
            <n-icon :component="FlashOutline" :size="16" />
            <span class="mode-option__text">
              <strong>快速检索</strong>
              <small>直接关键词 / 语义匹配，响应更快</small>
            </span>
          </button>
        </div>
      </header>

      <FacetChips
        v-if="hasFacets && !visualResult"
        :facets="facets"
        :season="season"
        :category="category"
        :campus="campus"
        :loading="facetsLoading"
        @update:season="(value) => setFacet('season', value)"
        @update:category="(value) => setFacet('category', value)"
        @update:campus="(value) => setFacet('campus', value)"
        @clear="clearFilters"
      />

      <SearchStepsTimeline v-if="result && !loading && !visualResult" :result="result" />

      <ClarifyCard
        v-if="result?.clarify && !loading && !visualResult"
        :question="result.clarify"
        :options="result.clarifyOptions"
        :has-results="total > 0"
        @pick="submitSearch"
      />

      <n-alert
        v-if="fallbackNotice && !loading && !fallbackDismissed && !visualResult"
        class="search-fallback"
        :type="fallbackTone"
        :bordered="false"
        closable
        @close="fallbackDismissed = true"
      >
        {{ fallbackNotice }}
      </n-alert>

      <div v-if="showContextBar" class="context-bar" role="status">
        <n-icon :component="GitBranchOutline" :size="14" />
        <span class="context-bar__text">结合上文：<strong>{{ latestContext }}</strong></span>
        <button type="button" class="context-bar__clear" @click="clearContext">清除上下文</button>
        <span v-if="assumedContext" class="context-bar__assumed">{{ assumedContext }}</span>
      </div>

      <section class="search-results" :aria-label="visualResult ? '以图搜图结果' : '检索结果'">
        <div v-if="visualResult" class="visual-summary" role="status">
          <span
            class="visual-summary__dot"
            :style="visualResult.query?.paletteHex ? { background: visualResult.query.paletteHex } : undefined"
            aria-hidden="true"
          />
          <div class="visual-summary__text">
            <p class="visual-summary__title">以图找图{{ visualQueryText }}</p>
            <p class="visual-summary__meta">
              {{ visualTotalText }}
              <span v-if="visualResult.queryTimeMs > 0"> · 用时 {{ Math.round(visualResult.queryTimeMs) }} ms</span>
            </p>
          </div>
          <button type="button" class="visual-summary__clear" @click="clearVisualSearch">
            清除以图搜图
          </button>
        </div>

        <div v-if="!visualResult && (loading || (searched && works.length))" class="results-head">
          <div class="results-summary" role="status">
            <span class="results-count">{{ totalText }}</span>
            <span v-if="result && !loading" class="results-meta">{{ resultMeta }}</span>
          </div>
          <button v-if="hasActiveFilters" type="button" class="results-clear" @click="clearFilters">
            清除筛选
          </button>
        </div>

        <div v-if="showSkeleton && !visualResult" class="search-skeleton" aria-busy="true" aria-label="正在检索">
          <SkeletonCard
            v-for="(shape, index) in SKELETON_SHAPES"
            :key="index"
            :aspect-ratio="shape"
          />
        </div>

        <SearchEmptyState
          v-if="error && !loading && !visualResult"
          :variant="errorKind"
          :message="error"
          :retrying="retrying"
          @retry="retry"
        />

        <SearchEmptyState
          v-else-if="!visualResult && !loading && searched && works.length === 0"
          variant="empty"
          :query="q"
          :can-clear="hasActiveFilters"
          :suggestions="emptySuggestions"
          @pick="submitSearch"
          :retrying="retrying"
          @retry="retry"
          @clear="clearFilters"
        />

        <section
          v-if="!visualResult && !loading && !searched && hasHistory"
          class="search-history"
          aria-label="最近搜索"
        >
          <div class="search-history__head">
            <span class="search-history__label">最近搜索</span>
            <button type="button" class="search-history__clear" @click="clearHistory">清空</button>
          </div>
          <div class="search-history__chips">
            <span v-for="item in history" :key="item" class="history-chip">
              <button type="button" class="history-chip__main" @click="submitSearch(item)">
                {{ item }}
              </button>
              <button
                type="button"
                class="history-chip__remove"
                :aria-label="`删除搜索历史 ${item}`"
                @click.stop="removeHistory(item)"
              >
                ×
              </button>
            </span>
          </div>
        </section>

        <SearchEmptyState
          v-else-if="!visualResult && !loading && !searched"
          variant="idle"
          :suggestions="IDLE_SUGGESTIONS"
          @pick="submitSearch"
        />

        <SearchEmptyState
          v-else-if="visualResult && visualResult.works.length === 0"
          variant="empty"
          message="没有找到足够相近的作品"
          action-label="换一张试试"
          @retry="retryImageSearch"
        />

        <ResultMasonry
          v-if="visualResult ? visualResult.works.length > 0 : works.length > 0"
          :works="visualResult ? visualResult.works : works"
          :loading="visualResult ? false : loading"
          :loading-more="visualResult ? false : loadingMore"
          :skeleton-count="8"
          :score-hint="visualResult ? '与上传图的视觉相似度' : undefined"
        />

        <div v-if="!visualResult && works.length && !loading" class="results-foot">
          <button
            v-if="hasMore"
            type="button"
            class="load-more"
            :disabled="loadingMore"
            @click="loadMore"
          >
            {{ loadingMore ? '正在加载…' : '加载更多作品' }}
          </button>
          <p v-else class="results-end">已经到底啦 · 共 {{ works.length }} 个结果</p>
        </div>
      </section>
    </div>

    <ImageSearchPanel v-model:show="imagePanelOpen" @result="onImageResult" />

    <Transition name="backtop">
      <button
        v-if="showBackToTop"
        type="button"
        class="back-to-top"
        aria-label="回到顶部"
        @click="backToTop"
      >
        <n-icon :component="ArrowUpOutline" :size="18" />
      </button>
    </Transition>
  </div>
</template>

<style scoped>
.context-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 16px 0 4px;
  padding: 8px 14px;
  border-radius: 999px;
  background: var(--sakura-wash, #ffe9f0);
  color: var(--ink, #4a2b35);
  font-size: var(--fs-sm, 14px);
  line-height: 1.5;
}

.context-bar :deep(.n-icon) {
  flex: none;
  color: var(--sakura-deep, #c93a63);
}

.context-bar__text strong {
  font-weight: 600;
  color: var(--sakura-deep, #c93a63);
}

.context-bar__clear {
  min-height: 36px;
  padding: 0 16px;
  border: 1px solid color-mix(in srgb, var(--sakura-deep, #c93a63) 24%, transparent);
  border-radius: 999px;
  background: var(--surface, #fff);
  color: var(--sakura-deep, #c93a63);
  font-size: var(--fs-sm, 14px);
  cursor: pointer;
  transition: background var(--dur-fast, 160ms) ease;
}

.context-bar__clear:hover {
  background: var(--sakura-pale, #ffe9f0);
}

.context-bar__clear:focus-visible {
  outline: 3px solid var(--sakura-deep, #c93a63);
  outline-offset: 2px;
}

.context-bar__assumed {
  color: var(--muted, #63474f);
  font-size: var(--fs-xs, 12.5px);
}

@media (pointer: coarse) {
  .context-bar__clear {
    min-height: 44px;
    min-width: 44px;
  }
}

@media (max-width: 640px) {
  .context-bar {
    border-radius: 18px;
    padding: 12px 14px;
  }

  .context-bar__clear {
    min-height: 44px;
  }
}

/* 以图搜图入口：桌面在搜索框内右侧，移动端单独一行 */
.image-search-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: none;
  height: 46px;
  padding: 0 16px;
  border: 1px solid var(--line-strong, #e6c6d2);
  border-radius: var(--r-pill, 999px);
  background: var(--surface, #fff);
  color: var(--sakura-deep, #c93a63);
  font-family: var(--font, 'Noto Sans SC', sans-serif);
  font-size: var(--fs-sm, 14px);
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition:
    border-color 160ms var(--ease-out, ease),
    background 160ms var(--ease-out, ease),
    color 160ms var(--ease-out, ease);
}

.image-search-trigger:hover {
  border-color: var(--sakura, #e8628c);
  background: var(--sakura-wash, #fff0f5);
}

.image-search-trigger:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 2px;
}

.image-search-trigger--mobile {
  display: none;
  margin-top: 10px;
}

/* 以图搜图结果摘要 */
.visual-summary {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 4px 0 20px;
  padding: 14px 18px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-card, 20px);
  background:
    radial-gradient(120% 140% at 0% 0%, var(--sakura-wash, #fff0f5) 0%, transparent 62%),
    var(--surface, #fff);
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
}

.visual-summary__dot {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--sakura, #e8628c);
  box-shadow: 0 0 0 4px var(--sakura-mist, #fff2f7);
}

.visual-summary__text {
  min-width: 0;
  flex: 1;
}

.visual-summary__title {
  margin: 0;
  font-size: var(--fs-body, 16px);
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.visual-summary__meta {
  margin: 2px 0 0;
  font-size: var(--fs-sm, 14px);
  color: var(--muted, #63474f);
  font-variant-numeric: tabular-nums;
}

.visual-summary__clear {
  flex: none;
  min-height: 38px;
  padding: 0 14px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-pill, 999px);
  background: var(--surface, #fff);
  color: var(--muted, #63474f);
  font-size: var(--fs-sm, 14px);
  cursor: pointer;
  transition:
    border-color 160ms var(--ease-out, ease),
    color 160ms var(--ease-out, ease);
}

.visual-summary__clear:hover {
  border-color: var(--sakura, #e8628c);
  color: var(--sakura-deep, #c93a63);
}

.visual-summary__clear:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 2px;
}

@media (max-width: 900px) {
  .image-search-trigger:not(.image-search-trigger--mobile) {
    display: none;
  }

  .image-search-trigger--mobile {
    display: inline-flex;
    width: 100%;
  }

  .visual-summary {
    flex-wrap: wrap;
    gap: 10px;
    padding: 12px 14px;
  }

  .visual-summary__clear {
    width: 100%;
  }
}

@media (pointer: coarse) {
  .image-search-trigger,
  .visual-summary__clear {
    min-height: 44px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .image-search-trigger,
  .visual-summary__clear {
    transition: none;
  }
}
</style>
