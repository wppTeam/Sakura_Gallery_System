<template>
  <div class="workbench-page">
    <SiteHeader />

    <main class="workbench-main">
      <div class="wrap">
        <nav class="wb-crumb" aria-label="面包屑">
          <RouterLink class="wb-crumb-link" to="/">
            <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M12.4 4.6 7 10l5.4 5.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            首页
          </RouterLink>
          <span class="wb-crumb-sep" aria-hidden="true">/</span>
          <span class="wb-crumb-current">我的投稿</span>
        </nav>

        <header class="wb-hero">
          <div class="wb-hero-copy">
            <p class="eyebrow wb-hero-eyebrow">AUTHOR WORKBENCH · 我的投稿</p>
            <h1 class="wb-title">我的投稿</h1>
            <p class="wb-lead">从待审核、已通过到复核进度，你投出的每一张，都在这里。</p>
          </div>
          <RouterLink class="btn btn--primary wb-submit" to="/upload">
            投稿新作品
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M3.2 8h9.2M8.8 4.2 12.6 8l-3.8 3.8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </RouterLink>
        </header>

        <ul class="wb-stats" role="list" aria-label="投稿概览">
          <li v-for="card in statCards" :key="card.key" class="wb-stat-item">
            <button
              type="button"
              class="wb-stat"
              :class="[`wb-stat--${card.tone}`, { 'is-active': card.active }]"
              :aria-pressed="card.active"
              @click="onStatClick(card.key)"
            >
              <span class="wb-stat-label">{{ card.label }}</span>
              <span class="wb-stat-value">
                <template v-if="statsLoading && card.key !== 'appeal'">—</template>
                <template v-else>{{ formatCount(card.value) }}</template>
              </span>
              <span class="wb-stat-hint">{{ card.hint }}</span>
            </button>
          </li>
        </ul>
        <p v-if="statsError" class="wb-stats-error" role="status">
          {{ statsError }}
          <button type="button" class="wb-inline-link" @click="loadStats">重试</button>
        </p>

        <div class="wb-toolbar">
          <div class="wb-tabs" role="tablist" aria-label="按投稿状态筛选">
            <button
              v-for="(item, index) in TABS"
              :id="`wb-tab-${item.key}`"
              :key="item.key"
              type="button"
              role="tab"
              class="wb-tab"
              :class="{ 'is-active': tab === item.key }"
              :aria-selected="tab === item.key"
              :aria-controls="'wb-panel'"
              :tabindex="tab === item.key ? 0 : -1"
              @click="selectStatus(item.key)"
              @keydown="onTabKeydown($event, index)"
            >
              {{ item.label }}
              <span class="wb-tab-count">{{ formatCount(tabCount(item.key)) }}</span>
            </button>
          </div>

          <div class="wb-search">
            <n-icon :component="SearchOutline" :size="16" class="wb-search-icon" aria-hidden="true" />
            <label class="wb-search-label">
              <span class="sr-only">搜索投稿（标题或文件名）</span>
              <input
                v-model="searchInput"
                class="wb-search-input"
                type="search"
                placeholder="搜索标题或文件名"
                autocomplete="off"
                @compositionstart="composing = true"
                @compositionend="onCompositionEnd"
                @keydown.enter.prevent="applySearchNow"
              />
            </label>
            <button
              v-if="searchInput"
              type="button"
              class="wb-search-clear"
              aria-label="清空搜索"
              @click="clearSearch"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="m4.5 4.5 7 7m0-7-7 7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
              </svg>
            </button>
          </div>
        </div>

        <div
          id="wb-panel"
          class="wb-panel"
          role="tabpanel"
          :aria-labelledby="`wb-tab-${tab}`"
          :aria-busy="loading && !items.length"
        >
          <div v-if="error" class="wb-state">
            <EmptyState
              title="投稿列表暂时没有加载出来"
              :description="error"
              action-label="重新加载"
              error
              @action="load(true)"
            />
          </div>

          <div v-else-if="loading && !items.length" class="wb-grid" aria-hidden="true">
            <div v-for="n in 4" :key="`sk-${n}`" class="wb-card wb-card--skeleton">
              <div class="wb-thumb wb-thumb--skeleton"></div>
              <div class="wb-card-body">
                <span class="wb-skeleton-line wb-skeleton-line--title"></span>
                <span class="wb-skeleton-line"></span>
                <span class="wb-skeleton-line wb-skeleton-line--short"></span>
                <span class="wb-skeleton-line wb-skeleton-line--actions"></span>
              </div>
            </div>
          </div>

          <div v-else-if="!items.length" class="wb-state">
            <EmptyState
              :title="emptyState.title"
              :description="emptyState.description"
              :action-label="emptyState.actionLabel"
              @action="onEmptyAction"
            />
          </div>

          <template v-else>
            <div class="wb-grid">
              <article v-for="item in items" :key="item.id" class="wb-card">
                <div
                  class="wb-thumb"
                  :style="item.lqipColor ? { backgroundColor: item.lqipColor } : undefined"
                >
                  <img
                    v-if="thumbs[item.id]"
                    class="wb-thumb-img"
                    :src="thumbs[item.id]"
                    :alt="`${displayTitle(item)} · 我的投稿`"
                    loading="lazy"
                    decoding="async"
                  />
                  <div
                    v-else
                    class="wb-thumb-fallback"
                    :class="{ 'is-failed': thumbFailed[item.id] }"
                    aria-hidden="true"
                  >
                    <svg width="42" height="42" viewBox="0 0 64 64" fill="none">
                      <circle cx="32" cy="32" r="30" fill="var(--sakura-pale)" opacity="0.7" />
                      <g transform="translate(32 32)">
                        <path
                          v-for="rotate in [0, 72, 144, 216, 288]"
                          :key="rotate"
                          d="M0 -3.2c5.6 -6.2 6.2 -12.2 0 -15.4-6.2 3.2-5.6 9.2 0 15.4Z"
                          :transform="`rotate(${rotate})`"
                          fill="var(--sakura)"
                          opacity="0.55"
                        />
                        <circle r="3.1" fill="var(--sakura-deep)" />
                      </g>
                    </svg>
                  </div>

                  <div class="wb-badges">
                    <span class="wb-badge" :class="`wb-badge--${item.status}`">{{ statusLabel(item.status) }}</span>
                    <span v-if="appealBadge(item)" class="wb-badge" :class="appealBadgeClass(item)">
                      {{ appealBadge(item) }}
                    </span>
                  </div>
                  <span v-if="item.isAigc" class="wb-badge wb-badge--aigc wb-badge--aigc-corner">
                    {{ item.aigcLabel || 'AI 生成' }}
                  </span>
                </div>

                <div class="wb-card-body">
                  <h3 class="wb-card-title">
                    <RouterLink class="wb-card-link" :to="`/photo/${item.id}`">{{ displayTitle(item) }}</RouterLink>
                  </h3>
                  <p class="wb-card-meta">
                    <span>{{ kindLabel(item) }}</span>
                    <template v-if="seasonLabel(item)"><span class="wb-dot" aria-hidden="true">·</span><span>{{ seasonLabel(item) }}</span></template>
                    <template v-if="item.capturedAt"><span class="wb-dot" aria-hidden="true">·</span><span>拍摄 {{ formatDay(item.capturedAt) }}</span></template>
                  </p>
                  <p class="wb-card-sub">
                    投稿于 {{ formatDay(item.createdAt) || '—' }}
                    <template v-if="item.privacyLevel === 'sensitive'">
                      <span class="wb-dot" aria-hidden="true">·</span>
                      <span class="wb-privacy-tag">人像隐私保护</span>
                    </template>
                  </p>
                  <p v-if="appealNote(item)" class="wb-appeal-note" :title="appealNote(item)">
                    复核未通过：{{ appealNote(item) }}
                  </p>

                  <div class="wb-card-actions">
                    <RouterLink class="wb-btn wb-btn--quiet" :to="`/photo/${item.id}`">查看</RouterLink>
                    <button
                      v-if="canAppeal(item)"
                      type="button"
                      class="wb-btn wb-btn--appeal"
                      @click="openAppeal(item)"
                    >
                      申请复核
                    </button>
                    <span v-else-if="appealLoading(item)" class="wb-btn-note">复核状态读取中</span>
                    <span v-else-if="appealPending(item)" class="wb-btn-note">复核处理中</span>
                    <button
                      type="button"
                      class="wb-btn wb-btn--danger"
                      :aria-label="`删除投稿：${displayTitle(item)}`"
                      @click="askDelete(item)"
                    >
                      删除
                    </button>
                  </div>
                </div>
              </article>
            </div>

            <div class="wb-more">
              <button v-if="loadMoreError" type="button" class="btn" @click="loadMore">
                加载失败，点击重试
              </button>
              <button
                v-else-if="hasMore"
                type="button"
                class="btn btn--primary"
                :disabled="loadingMore"
                @click="loadMore"
              >
                {{ loadingMore ? '加载中…' : '加载更多' }}
              </button>
              <p v-else class="wb-end">没有更多了</p>
            </div>
          </template>
        </div>
      </div>
    </main>

    <n-modal
      v-model:show="appealOpen"
      preset="card"
      class="wb-modal"
      :bordered="false"
      :mask-closable="!appealSubmitting"
      :closable="!appealSubmitting"
      style="width: min(92vw, 540px)"
      @after-leave="onAppealClosed"
    >
      <template #header>
        <div class="wb-modal-head">
          <span class="wb-modal-seal" aria-hidden="true">!</span>
          <div>
            <b>申请复核</b>
            <span>{{ appealTarget ? `《${displayTitle(appealTarget)}》` : '' }}被驳回后有一次人工复核机会，请补充说明。</span>
          </div>
        </div>
      </template>

      <div class="wb-appeal-form">
        <p class="wb-appeal-hint">
          复核只针对「是否存在误判或可补充的合规信息」，请尽量说明拍摄 / 创作背景、授权情况或你认为审核有误的原因。
        </p>
        <label class="wb-field-label" for="wb-appeal-reason">复核理由（10–2000 字）</label>
        <textarea
          id="wb-appeal-reason"
          ref="appealTextarea"
          v-model="appealReason"
          class="wb-textarea"
          rows="5"
          maxlength="2000"
          :disabled="appealSubmitting"
          placeholder="例如：这是我本人拍摄的校园活动，已取得被摄同学同意；或画面中的人物为公共场所远景，不可识别……"
        ></textarea>
        <div class="wb-field-foot">
          <p v-if="appealReason.length && appealReasonLength < 10" class="wb-inline-error" role="alert">
            还需要 {{ 10 - appealReasonLength }} 个字才能提交。
          </p>
          <span v-else-if="appealReasonLength > 2000" class="wb-inline-error" role="alert">最多 2000 字。</span>
          <span class="wb-char-count" aria-hidden="true">{{ appealReasonLength }} / 2000</span>
        </div>
        <p v-if="appealError" class="wb-appeal-error" role="alert">{{ appealError }}</p>
        <p class="wb-appeal-legal">
          提交即表示你确认所述内容真实；恶意或虚假申诉可能影响账号信用。详见
          <RouterLink to="/terms">服务条款</RouterLink>。
        </p>
        <div class="wb-modal-actions">
          <button type="button" class="wb-btn" :disabled="appealSubmitting" @click="appealOpen = false">取消</button>
          <button
            type="button"
            class="wb-btn wb-btn--primary"
            :disabled="!appealCanSubmit"
            @click="submitAppeal"
          >
            {{ appealSubmitting ? '提交中…' : '提交复核申请' }}
          </button>
        </div>
      </div>
    </n-modal>

    <n-modal
      v-model:show="deleteOpen"
      preset="card"
      class="wb-modal"
      :bordered="false"
      :mask-closable="!deleting"
      :closable="!deleting"
      style="width: min(92vw, 460px)"
      @after-leave="onDeleteClosed"
    >
      <template #header>
        <div class="wb-modal-head">
          <span class="wb-modal-seal wb-modal-seal--danger" aria-hidden="true">×</span>
          <div>
            <b>删除这张投稿？</b>
            <span>{{ deleteTarget ? `《${displayTitle(deleteTarget)}》` : '' }}删除后不可恢复。</span>
          </div>
        </div>
      </template>

      <div class="wb-delete-body">
        <p class="wb-delete-copy">
          原图、缩略图、响应式变体与脱敏图会一并清理，相关复核记录也会失效。此操作不可撤销。
        </p>
        <p v-if="deleteError" class="wb-appeal-error" role="alert">{{ deleteError }}</p>
        <div class="wb-modal-actions">
          <button type="button" class="wb-btn" :disabled="deleting" @click="deleteOpen = false">取消</button>
          <button type="button" class="wb-btn wb-btn--danger-solid" :disabled="deleting" @click="confirmDelete">
            {{ deleting ? '删除中…' : '确认删除' }}
          </button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon, useMessage } from 'naive-ui'
import { SearchOutline } from '@vicons/ionicons5'
import SiteHeader from '../components/layout/SiteHeader.vue'
import EmptyState from '../components/public/EmptyState.vue'
import { formatDate } from '../utils/format'
import { fetchPhotoAppeal, submitPhotoAppeal, type PhotoAppeal } from '../api/appeals'
import {
  deleteMySubmission,
  fetchMySubmissionStats,
  fetchMySubmissions,
  fetchSubmissionThumbUrl,
  releaseSubmissionThumb,
  type MySubmissionItem,
  type MySubmissionStats,
  type SubmissionStatus,
} from '../api/submissions'

const PAGE_SIZE = 12
const STATUS_QUERY: SubmissionStatus[] = ['pending', 'approved', 'rejected']

type TabKey = 'all' | SubmissionStatus

const TABS: { key: TabKey; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待审核' },
  { key: 'approved', label: '已通过' },
  { key: 'rejected', label: '未通过' },
]

const STATUS_LABELS: Record<SubmissionStatus, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '未通过',
}

const SEASON_LABELS: Record<string, string> = {
  spring: '春',
  summer: '夏',
  autumn: '秋',
  winter: '冬',
  Spring: '春',
  Summer: '夏',
  Autumn: '秋',
  Winter: '冬',
  '春': '春',
  '夏': '夏',
  '秋': '秋',
  '冬': '冬',
}

const route = useRoute()
const router = useRouter()
const message = useMessage()

const stats = reactive<MySubmissionStats>({
  total: 0,
  pending: 0,
  approved: 0,
  rejected: 0,
  pendingAppeal: 0,
})
const statsLoading = ref(true)
const statsError = ref('')

const items = ref<MySubmissionItem[]>([])
const total = ref(0)
const tab = ref<TabKey>('all')
const searchInput = ref('')
const appliedSearch = ref('')
const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')
const loadMoreError = ref('')
const composing = ref(false)

const thumbs = reactive<Record<string, string>>({})
const thumbFailed = reactive<Record<string, boolean>>({})
const appealMap = reactive<Record<string, { loading: boolean; appeal: PhotoAppeal | null }>>({})

const appealOpen = ref(false)
const appealTarget = ref<MySubmissionItem | null>(null)
const appealReason = ref('')
const appealSubmitting = ref(false)
const appealError = ref('')
const appealTextarea = ref<HTMLTextAreaElement | null>(null)

const deleteOpen = ref(false)
const deleteTarget = ref<MySubmissionItem | null>(null)
const deleting = ref(false)
const deleteError = ref('')

let searchTimer: number | undefined

const hasMore = computed(() => items.value.length < total.value)

const appealReasonLength = computed(() => appealReason.value.trim().length)
const appealCanSubmit = computed(
  () => appealReasonLength.value >= 10 && appealReasonLength.value <= 2000 && !appealSubmitting.value,
)

const statCards = computed(() => [
  {
    key: 'all' as const,
    label: '全部作品',
    hint: '投稿总数',
    tone: 'all',
    value: stats.total,
    active: tab.value === 'all',
  },
  {
    key: 'pending' as const,
    label: '待审核',
    hint: '正在排队',
    tone: 'pending',
    value: stats.pending,
    active: tab.value === 'pending',
  },
  {
    key: 'approved' as const,
    label: '已通过',
    hint: '已公开发布',
    tone: 'approved',
    value: stats.approved,
    active: tab.value === 'approved',
  },
  {
    key: 'rejected' as const,
    label: '未通过',
    hint: '可申请复核',
    tone: 'rejected',
    value: stats.rejected,
    active: tab.value === 'rejected',
  },
  {
    key: 'appeal' as const,
    label: '复核中',
    hint: '等待人工受理',
    tone: 'appeal',
    value: stats.pendingAppeal,
    active: false,
  },
])

const emptyState = computed(() => {
  if (appliedSearch.value) {
    return {
      title: '没有找到匹配的投稿',
      description: `没有与「${appliedSearch.value}」匹配的作品，换个关键词或清空搜索试试。`,
      actionLabel: '清空搜索',
    }
  }
  if (tab.value === 'pending') {
    return {
      title: '没有待审核的作品',
      description: '新投稿会先进入 AI 快筛与人工审核，完成后结果会通过站内通知告诉你。',
      actionLabel: '去投稿',
    }
  }
  if (tab.value === 'approved') {
    return {
      title: '还没有通过审核的作品',
      description: '通过审核的作品会出现在这里；归档后也可以随时回到作品详情。',
      actionLabel: '查看全部投稿',
    }
  }
  if (tab.value === 'rejected') {
    return {
      title: '没有被驳回的作品',
      description: '如果作品未通过审核，会出现在这里，你可以补充说明后申请一次人工复核。',
      actionLabel: '查看全部投稿',
    }
  }
  return {
    title: '还没有投稿',
    description: '把第一张校园摄影或 AI 生成作品投上来吧，审核进度与结果都会在这里更新。',
    actionLabel: '投稿新作品',
  }
})

function normalizeTab(value: unknown): TabKey {
  const text = typeof value === 'string' ? value : ''
  return STATUS_QUERY.includes(text as SubmissionStatus) ? (text as SubmissionStatus) : 'all'
}

function queryText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function formatCount(value: number): string {
  return Number.isFinite(value) ? String(value) : '0'
}

function formatDay(value: string | null): string {
  if (!value) return ''
  const formatted = formatDate(value, 'YYYY-MM-DD')
  return formatted === '未知' ? value.slice(0, 10) : formatted
}

function displayTitle(item: MySubmissionItem): string {
  const title = item.title.trim()
  return title || item.filename || '未命名作品'
}

function statusLabel(status: SubmissionStatus): string {
  return STATUS_LABELS[status] || '待审核'
}

function kindLabel(item: MySubmissionItem): string {
  if (item.isAigc) return 'AI 生成'
  if (item.kind === 'template') return '模板素材'
  return '摄影作品'
}

function seasonLabel(item: MySubmissionItem): string {
  const raw = item.season?.trim()
  if (!raw) return ''
  return SEASON_LABELS[raw] ?? raw
}

function tabCount(key: TabKey): number {
  if (key === 'all') return stats.total
  return stats[key]
}

function onStatClick(key: 'all' | SubmissionStatus | 'appeal'): void {
  if (key === 'appeal') {
    selectStatus('rejected')
    return
  }
  selectStatus(key)
}

function describeError(cause: unknown): string {
  const status = (cause as { response?: { status?: number } } | undefined)?.response?.status
  const detail = (cause as { response?: { data?: { detail?: unknown } } } | undefined)?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (status === 401) return '登录状态已过期，请重新登录后再试。'
  if (status === 403) return '当前账号没有查看这些投稿的权限。'
  if (!status) return '网络连接失败，请检查网络后重试。'
  return `服务暂时不可用（${status}），请稍后重试。`
}

function applyThumbs(rows: MySubmissionItem[]): void {
  for (const item of rows) {
    if (thumbs[item.id] || thumbFailed[item.id]) continue
    void fetchSubmissionThumbUrl(item.id).then((url) => {
      if (url) thumbs[item.id] = url
      else thumbFailed[item.id] = true
    })
  }
}

function loadAppeal(item: MySubmissionItem): void {
  if (item.status !== 'rejected' || appealMap[item.id]) return
  appealMap[item.id] = { loading: true, appeal: null }
  void fetchPhotoAppeal(item.id)
    .then((appeal) => {
      const cell = appealMap[item.id]
      if (!cell) return
      cell.loading = false
      cell.appeal = appeal
    })
    .catch(() => {
      const cell = appealMap[item.id]
      if (cell) cell.loading = false
    })
}

function applyAppeals(rows: MySubmissionItem[]): void {
  for (const item of rows) loadAppeal(item)
}

function appealCell(item: MySubmissionItem): { loading: boolean; appeal: PhotoAppeal | null } | undefined {
  return appealMap[item.id]
}

function appealLoading(item: MySubmissionItem): boolean {
  const cell = appealCell(item)
  return item.status === 'rejected' && !!cell?.loading
}

function appealPending(item: MySubmissionItem): boolean {
  return appealCell(item)?.appeal?.status === 'pending'
}

function appealBadge(item: MySubmissionItem): string {
  const appeal = appealCell(item)?.appeal
  if (!appeal) return ''
  if (appeal.status === 'pending') return '复核中'
  if (appeal.status === 'accepted') return '复核通过'
  return '复核未通过'
}

function appealBadgeClass(item: MySubmissionItem): string {
  const appeal = appealCell(item)?.appeal
  return appeal?.status === 'rejected' ? 'wb-badge--appeal-rejected' : 'wb-badge--appeal'
}

function appealNote(item: MySubmissionItem): string {
  const appeal = appealCell(item)?.appeal
  if (!appeal || appeal.status !== 'rejected') return ''
  return appeal.note?.trim() || '维持原审核结果'
}

function canAppeal(item: MySubmissionItem): boolean {
  const cell = appealCell(item)
  return (
    item.status === 'rejected' &&
    !!cell &&
    !cell.loading &&
    cell.appeal === null
  )
}

async function loadStats(): Promise<void> {
  statsLoading.value = true
  statsError.value = ''
  try {
    const next = await fetchMySubmissionStats()
    Object.assign(stats, next)
  } catch (cause) {
    statsError.value = describeError(cause)
  } finally {
    statsLoading.value = false
  }
}

async function load(reset = false): Promise<void> {
  if (reset) {
    loading.value = true
    error.value = ''
    loadMoreError.value = ''
    items.value = []
    total.value = 0
  } else {
    loadingMore.value = true
    loadMoreError.value = ''
  }

  try {
    const page = await fetchMySubmissions({
      skip: reset ? 0 : items.value.length,
      limit: PAGE_SIZE,
      status: tab.value === 'all' ? undefined : tab.value,
      search: appliedSearch.value || undefined,
    })
    items.value = reset ? page.items : [...items.value, ...page.items]
    total.value = page.total
    applyThumbs(page.items)
    applyAppeals(page.items)
  } catch (cause) {
    if (reset || !items.value.length) {
      items.value = []
      total.value = 0
      error.value = describeError(cause)
    } else {
      loadMoreError.value = '加载更多失败，请重试。'
    }
    console.warn('[my-submissions] 投稿列表加载失败', cause)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function loadMore(): void {
  if (loadingMore.value || !hasMore.value) return
  void load(false)
}

function selectStatus(key: TabKey): void {
  if (key === tab.value) return
  tab.value = key
  void load(true)
  syncUrl()
}

function onTabKeydown(event: KeyboardEvent, index: number): void {
  const handled = ['ArrowRight', 'ArrowLeft', 'Home', 'End']
  if (!handled.includes(event.key)) return
  event.preventDefault()
  let next = index
  if (event.key === 'ArrowRight') next = (index + 1) % TABS.length
  else if (event.key === 'ArrowLeft') next = (index - 1 + TABS.length) % TABS.length
  else if (event.key === 'Home') next = 0
  else next = TABS.length - 1
  selectStatus(TABS[next].key)
  const tablist = (event.currentTarget as HTMLElement | null)?.closest('[role="tablist"]')
  const buttons = tablist?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
  buttons?.[next]?.focus()
}

function applySearchNow(): void {
  if (searchTimer !== undefined) {
    window.clearTimeout(searchTimer)
    searchTimer = undefined
  }
  const next = searchInput.value.trim()
  if (next === appliedSearch.value) return
  appliedSearch.value = next
  void load(true)
  syncUrl()
}

function onCompositionEnd(): void {
  composing.value = false
  if (searchTimer !== undefined) {
    window.clearTimeout(searchTimer)
    searchTimer = undefined
  }
  searchTimer = window.setTimeout(applySearchNow, 300)
}

function clearSearch(): void {
  searchInput.value = ''
  appliedSearch.value = ''
  void load(true)
  syncUrl()
}

watch(searchInput, () => {
  if (searchTimer !== undefined) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    searchTimer = undefined
    if (!composing.value) applySearchNow()
  }, 300)
})

function syncUrl(): void {
  const query: Record<string, string> = {}
  for (const [key, value] of Object.entries(route.query)) {
    if (key === 'status' || key === 'search') continue
    if (typeof value === 'string' && value) query[key] = value
  }
  if (tab.value !== 'all') query.status = tab.value
  if (appliedSearch.value) query.search = appliedSearch.value

  const current: Record<string, string> = {}
  for (const [key, value] of Object.entries(route.query)) {
    if (typeof value === 'string' && value) current[key] = value
  }
  if (JSON.stringify(current) === JSON.stringify(query)) return
  void router.replace({ query })
}

watch(
  () => [route.query.status, route.query.search],
  () => {
    const nextTab = normalizeTab(route.query.status)
    const nextSearch = queryText(route.query.search)
    if (nextTab === tab.value && nextSearch === appliedSearch.value) return
    tab.value = nextTab
    searchInput.value = nextSearch
    appliedSearch.value = nextSearch
    void load(true)
  },
)

function onEmptyAction(): void {
  if (appliedSearch.value) {
    clearSearch()
    return
  }
  if (tab.value !== 'all') {
    selectStatus('all')
    return
  }
  void router.push('/upload')
}

function openAppeal(item: MySubmissionItem): void {
  appealTarget.value = item
  appealReason.value = ''
  appealError.value = ''
  appealOpen.value = true
  void nextTick(() => {
    window.requestAnimationFrame(() => appealTextarea.value?.focus())
  })
}

function onAppealClosed(): void {
  if (appealSubmitting.value) return
  appealTarget.value = null
}

async function submitAppeal(): Promise<void> {
  const target = appealTarget.value
  if (!target || appealSubmitting.value) return
  const reason = appealReason.value.trim()
  if (reason.length < 10) {
    appealError.value = '复核理由至少需要 10 个字。'
    return
  }
  appealSubmitting.value = true
  appealError.value = ''
  try {
    const result = await submitPhotoAppeal(target.id, reason)
    appealMap[target.id] = {
      loading: false,
      appeal: {
        id: result.id,
        photoId: target.id,
        status: 'pending',
        reason,
        note: null,
        createdAt: new Date().toISOString(),
        handledAt: null,
        raw: {},
      },
    }
    appealOpen.value = false
    message.success('复核申请已提交，等待人工受理')
    void loadStats()
  } catch (cause) {
    const status = (cause as { response?: { status?: number } } | undefined)?.response?.status
    const detail = (cause as { response?: { data?: { detail?: unknown } } } | undefined)?.response?.data?.detail
    if (status === 409) {
      appealError.value = '该作品已有一条等待受理的复核申请，请等待处理结果。'
      void fetchPhotoAppeal(target.id).then((appeal) => {
        appealMap[target.id] = { loading: false, appeal }
        void loadStats()
      })
    } else if (status === 429) {
      appealError.value = '提交太频繁了，请稍后再试。'
    } else if (typeof detail === 'string' && detail.trim()) {
      appealError.value = detail
    } else {
      appealError.value = describeError(cause)
    }
  } finally {
    appealSubmitting.value = false
  }
}

function askDelete(item: MySubmissionItem): void {
  deleteTarget.value = item
  deleteError.value = ''
  deleteOpen.value = true
}

function onDeleteClosed(): void {
  if (deleting.value) return
  deleteTarget.value = null
}

async function confirmDelete(): Promise<void> {
  const target = deleteTarget.value
  if (!target || deleting.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    await deleteMySubmission(target.id)
    items.value = items.value.filter((row) => row.id !== target.id)
    total.value = Math.max(0, total.value - 1)
    stats.total = Math.max(0, stats.total - 1)
    stats[target.status] = Math.max(0, stats[target.status] - 1)
    if (appealPending(target)) stats.pendingAppeal = Math.max(0, stats.pendingAppeal - 1)
    delete delete appealMap[target.id]
    delete thumbs[target.id]
    delete thumbFailed[target.id]
    releaseSubmissionThumb(target.id)
    deleteOpen.value = false
    deleteTarget.value = null
    message.success('投稿已删除')
    void loadStats()
  } catch (cause) {
    deleteError.value = `删除失败：${describeError(cause)}`
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  tab.value = normalizeTab(route.query.status)
  const initialSearch = queryText(route.query.search)
  searchInput.value = initialSearch
  appliedSearch.value = initialSearch
  void loadStats()
  void load(true)
})

onBeforeUnmount(() => {
  if (searchTimer !== undefined) window.clearTimeout(searchTimer)
})
</script>

<style scoped>
.workbench-page {
  min-height: 100vh;
  background: var(--ground);
  /* 复核态用紫色，仅本页语义色（不新增全局 token） */
  --tone-pending-bg: #fff3d9;
  --tone-pending-ink: #8a5a00;
  --tone-approved-ink: #23624f;
  --tone-rejected-ink: #9c2f51;
  --tone-appeal-bg: #efe3fb;
  --tone-appeal-ink: #6b3fa0;
}

.workbench-main {
  padding: clamp(18px, 3vw, 34px) 0 clamp(56px, 7vw, 96px);
}

.wb-crumb {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: clamp(18px, 2.4vw, 28px);
  font-size: var(--fs-14);
  color: var(--muted);
}

.wb-crumb-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--muted);
  text-decoration: none;
}

.wb-crumb-link:hover {
  color: var(--sakura-deep);
}

.wb-crumb-sep {
  color: var(--line-strong);
}

.wb-crumb-current {
  color: var(--ink-soft);
}

.wb-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-6);
  margin-bottom: clamp(24px, 3vw, 36px);
}

.wb-hero-copy {
  min-width: 0;
}

.wb-hero-eyebrow {
  margin: 0 0 var(--sp-2);
}

.wb-title {
  margin: 0;
  font-family: var(--display);
  font-size: clamp(44px, 5.4vw, 64px);
  line-height: var(--lh-tight);
  color: var(--ink);
  letter-spacing: var(--tracking-wide);
}

.wb-lead {
  max-width: 34em;
  margin: var(--sp-3) 0 0;
  font-size: var(--fs-16);
  line-height: var(--lh-body);
  color: var(--muted);
}

.wb-submit {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 44px;
}

.wb-stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--sp-3);
  margin: 0 0 var(--sp-5);
  padding: 0;
  list-style: none;
}

.wb-stat-item {
  min-width: 0;
}

.wb-stat {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--dur-fast) var(--ease-soft),
    background-color var(--dur-fast) var(--ease-soft),
    box-shadow var(--dur-fast) var(--ease-soft);
}

.wb-stat:hover {
  border-color: var(--line-strong);
  background: var(--surface-warm);
}

.wb-stat.is-active {
  border-color: var(--sakura-deep);
  background: var(--sakura-mist);
  box-shadow: var(--shadow-soft);
}

.wb-stat-label {
  font-size: var(--fs-12);
  color: var(--muted);
  letter-spacing: var(--tracking-wide);
}

.wb-stat-value {
  font-family: var(--display);
  font-size: clamp(34px, 2.6vw, 44px);
  line-height: 1.1;
  color: var(--ink);
}

.wb-stat--pending .wb-stat-value {
  color: var(--tone-pending-ink);
}

.wb-stat--approved .wb-stat-value {
  color: var(--tone-approved-ink);
}

.wb-stat--rejected .wb-stat-value {
  color: var(--tone-rejected-ink);
}

.wb-stat--appeal .wb-stat-value {
  color: var(--tone-appeal-ink);
}

.wb-stat-hint {
  font-size: var(--fs-12);
  color: var(--faint);
}

.wb-stats-error {
  margin: calc(-1 * var(--sp-3)) 0 var(--sp-4);
  font-size: var(--fs-12);
  color: var(--autumn);
}

.wb-inline-link {
  padding: 0 2px;
  border: 0;
  background: none;
  color: var(--sakura-deep);
  font-size: inherit;
  cursor: pointer;
  text-decoration: underline;
}

.wb-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  margin-bottom: var(--sp-5);
}

.wb-tabs {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--surface-soft);
  max-width: 100%;
  overflow-x: auto;
  scrollbar-width: none;
}

.wb-tabs::-webkit-scrollbar {
  display: none;
}

.wb-tab {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 0 14px;
  border: 0;
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--muted);
  font-size: var(--fs-14);
  cursor: pointer;
  transition:
    background-color var(--dur-fast) var(--ease-soft),
    color var(--dur-fast) var(--ease-soft);
}

.wb-tab:hover {
  color: var(--sakura-deep);
  background: var(--sakura-wash);
}

.wb-tab.is-active {
  color: var(--on-accent);
  background: var(--sakura-deep);
}

.wb-tab-count {
  min-width: 1.4em;
  font-size: var(--fs-12);
  font-variant-numeric: tabular-nums;
  opacity: 0.8;
}

.wb-tab.is-active .wb-tab-count {
  opacity: 1;
}

.wb-search {
  position: relative;
  flex: 0 1 280px;
  display: flex;
  align-items: center;
  min-height: 40px;
  padding: 0 12px 0 38px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  transition:
    border-color var(--dur-fast) var(--ease-soft),
    box-shadow var(--dur-fast) var(--ease-soft);
}

.wb-search:focus-within {
  border-color: var(--sakura);
  box-shadow: var(--focus-ring);
}

.wb-search-icon {
  position: absolute;
  left: 14px;
  color: var(--faint);
  pointer-events: none;
}

.wb-search-label {
  flex: 1;
  min-width: 0;
  display: flex;
}

.wb-search-input {
  width: 100%;
  min-width: 0;
  padding: 9px 0;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-family: inherit;
  font-size: var(--fs-14);
  outline: none;
}

.wb-search-input::placeholder {
  color: var(--faint);
}

.wb-search-input::-webkit-search-cancel-button {
  display: none;
}

.wb-search-clear {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-left: 4px;
  border: 0;
  border-radius: 50%;
  background: var(--sakura-wash);
  color: var(--sakura-deep);
  cursor: pointer;
}

.wb-panel {
  min-height: 160px;
}

.wb-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: clamp(16px, 2vw, 24px);
}

.wb-card {
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.wb-thumb {
  position: relative;
  aspect-ratio: 4 / 3;
  width: 100%;
  overflow: hidden;
  background:
    radial-gradient(circle at 30% 20%, var(--sakura-wash), transparent 55%),
    linear-gradient(135deg, var(--surface-soft), var(--sakura-mist));
}

.wb-thumb-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  transition: transform var(--dur-slow) var(--ease-out);
}

.wb-card:hover .wb-thumb-img {
  transform: scale(1.015);
}

.wb-thumb-fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--sakura);
}

.wb-thumb-fallback::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    100deg,
    transparent 20%,
    rgba(255, 255, 255, 0.55) 46%,
    transparent 72%
  );
  transform: translateX(-100%);
  animation: wb-shimmer 1.4s var(--ease-soft) infinite;
}

.wb-thumb-fallback.is-failed::after {
  animation: none;
  background: none;
}

.wb-thumb--skeleton {
  border-bottom: 1px solid var(--line);
}

.wb-badges {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-width: calc(100% - 96px);
}

.wb-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: var(--r-pill);
  font-size: var(--fs-12);
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: 0.01em;
  white-space: nowrap;
}

.wb-badge--pending {
  background: var(--tone-pending-bg);
  color: var(--tone-pending-ink);
}

.wb-badge--approved {
  background: var(--summer-pale);
  color: var(--tone-approved-ink);
}

.wb-badge--rejected {
  background: var(--spring-pale);
  color: var(--tone-rejected-ink);
}

.wb-badge--appeal {
  background: var(--tone-appeal-bg);
  color: var(--tone-appeal-ink);
}

.wb-badge--appeal-rejected {
  background: var(--spring-pale);
  color: var(--tone-rejected-ink);
}

.wb-badge--aigc {
  background: rgba(74, 43, 53, 0.86);
  color: #ffffff;
}

.wb-badge--aigc-corner {
  position: absolute;
  top: 12px;
  right: 12px;
}

.wb-card-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 18px 16px;
}

.wb-card-title {
  margin: 0;
  font-size: var(--fs-16);
  line-height: var(--lh-snug);
  font-weight: 600;
  color: var(--ink);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.wb-card-link {
  color: inherit;
  text-decoration: none;
}

.wb-card-link:hover {
  color: var(--sakura-deep);
}

.wb-card-meta,
.wb-card-sub {
  margin: 0;
  font-size: var(--fs-12);
  color: var(--muted);
  line-height: 1.6;
}

.wb-card-sub {
  color: var(--faint);
}

.wb-dot {
  margin: 0 6px;
  color: var(--line-strong);
}

.wb-privacy-tag {
  color: var(--winter-accent);
}

.wb-appeal-note {
  margin: 2px 0 0;
  font-size: var(--fs-12);
  color: var(--tone-rejected-ink);
  line-height: 1.6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: help;
}

.wb-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
}

.wb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--ink-soft);
  font-family: inherit;
  font-size: var(--fs-12);
  text-decoration: none;
  cursor: pointer;
  transition:
    border-color var(--dur-fast) var(--ease-soft),
    background-color var(--dur-fast) var(--ease-soft),
    color var(--dur-fast) var(--ease-soft);
}

.wb-btn:hover {
  border-color: var(--sakura);
  background: var(--sakura-wash);
}

.wb-btn:disabled {
  opacity: 0.52;
  cursor: not-allowed;
}

.wb-btn--quiet {
  border-color: var(--line);
}

.wb-btn--appeal {
  border-color: var(--sakura);
  color: var(--sakura-deep);
  background: var(--sakura-wash);
}

.wb-btn--appeal:hover {
  background: var(--sakura-pale);
}

.wb-btn--danger {
  margin-left: auto;
  border-color: var(--spring-pale);
  color: var(--tone-rejected-ink);
}

.wb-btn--danger:hover {
  border-color: var(--spring);
  background: #fff4f7;
}

.wb-btn--primary {
  border-color: var(--sakura-deep);
  background: var(--sakura-deep);
  color: var(--on-accent);
}

.wb-btn--primary:hover {
  border-color: var(--sakura-deep-hover);
  background: var(--sakura-deep-hover);
}

.wb-btn--danger-solid {
  border-color: var(--sakura-deep);
  background: var(--sakura-deep);
  color: var(--on-accent);
}

.wb-btn--danger-solid:hover {
  border-color: var(--sakura-deep-hover);
  background: var(--sakura-deep-hover);
}

.wb-btn-note {
  font-size: var(--fs-12);
  color: var(--tone-appeal-ink);
}

.wb-end {
  margin: 0;
  padding: var(--sp-6) 0 0;
  text-align: center;
  font-size: var(--fs-12);
  color: var(--faint);
}

.wb-more {
  display: flex;
  justify-content: center;
  padding-top: var(--sp-8);
}

.wb-more .btn {
  min-height: 44px;
}

.wb-state {
  padding: var(--sp-6) 0;
}

.wb-skeleton-line {
  display: block;
  height: 12px;
  border-radius: var(--r-pill);
  background: linear-gradient(90deg, var(--sakura-mist), var(--ground-deep), var(--sakura-mist));
  background-size: 220% 100%;
  animation: wb-shimmer-bg 1.5s var(--ease-soft) infinite;
}

.wb-skeleton-line--title {
  width: 62%;
  height: 16px;
}

.wb-skeleton-line--short {
  width: 44%;
}

.wb-skeleton-line--actions {
  width: 100%;
  height: 34px;
  margin-top: 8px;
  border-radius: var(--r-pill);
}

.wb-card--skeleton .wb-card-body {
  gap: 10px;
}

/* ---------- 弹窗 ---------- */
.wb-modal-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.wb-modal-seal {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--sakura-pale);
  color: var(--sakura-deep);
  font-weight: 700;
}

.wb-modal-seal--danger {
  background: var(--spring-pale);
}

.wb-modal-head b {
  display: block;
  font-size: var(--fs-16);
  color: var(--ink);
}

.wb-modal-head > div > span {
  display: block;
  margin-top: 3px;
  font-size: var(--fs-12);
  line-height: 1.6;
  color: var(--muted);
}

.wb-modal-head .wb-modal-seal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--sakura-deep);
}

.wb-appeal-form,
.wb-delete-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wb-appeal-hint {
  margin: 0 0 2px;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: var(--sakura-wash);
  font-size: var(--fs-12);
  line-height: 1.7;
  color: var(--muted);
}

.wb-field-label {
  font-size: var(--fs-12);
  font-weight: 600;
  color: var(--ink-soft);
}

.wb-textarea {
  width: 100%;
  min-height: 120px;
  padding: 10px 12px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink);
  font-family: inherit;
  font-size: var(--fs-14);
  line-height: 1.7;
  resize: vertical;
  outline: none;
  transition:
    border-color var(--dur-fast) var(--ease-soft),
    box-shadow var(--dur-fast) var(--ease-soft);
}

.wb-textarea:focus {
  border-color: var(--sakura);
  box-shadow: var(--focus-ring);
}

.wb-textarea:disabled {
  background: var(--surface-soft);
  opacity: 0.7;
}

.wb-field-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}

.wb-char-count {
  margin-left: auto;
  font-size: var(--fs-12);
  color: var(--faint);
  font-variant-numeric: tabular-nums;
}

.wb-inline-error {
  margin: 0;
  font-size: var(--fs-12);
  color: var(--autumn);
}

.wb-appeal-error {
  margin: 0;
  padding: 8px 10px;
  border-radius: var(--r-sm);
  background: #fff4f0;
  color: #8a3b16;
  font-size: var(--fs-12);
  line-height: 1.6;
}

.wb-appeal-legal {
  margin: 0;
  font-size: var(--fs-12);
  line-height: 1.6;
  color: var(--faint);
}

.wb-appeal-legal a {
  color: var(--sakura-deep);
}

.wb-delete-copy {
  margin: 0;
  font-size: var(--fs-14);
  line-height: var(--lh-body);
  color: var(--muted);
}

.wb-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 6px;
}

.wb-modal-actions .wb-btn {
  min-height: 40px;
  padding: 0 18px;
  font-size: var(--fs-14);
}

:global(.wb-modal.n-card) {
  border-radius: var(--r-card);
  box-shadow: var(--shadow-lift);
  background: var(--surface);
}

:global(.wb-modal .n-card-header) {
  padding: 18px 20px 6px;
}

:global(.wb-modal .n-card__content) {
  padding: 6px 20px 20px;
}

@keyframes wb-shimmer {
  to {
    transform: translateX(100%);
  }
}

@keyframes wb-shimmer-bg {
  0% {
    background-position: 0% 50%;
  }
  100% {
    background-position: 100% 50%;
  }
}

@media (max-width: 1100px) {
  .wb-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .wb-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .wb-hero {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--sp-4);
  }

  .wb-submit {
    align-self: stretch;
    justify-content: center;
  }
}

@media (max-width: 760px) {
  .wb-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .wb-search {
    flex-basis: auto;
    width: 100%;
  }

  .wb-tabs {
    width: 100%;
  }
}

@media (max-width: 640px) {
  .wb-stats {
    display: flex;
    gap: var(--sp-2);
    overflow-x: auto;
    padding-bottom: 2px;
    scrollbar-width: none;
    scroll-snap-type: x proximity;
  }

  .wb-stats::-webkit-scrollbar {
    display: none;
  }

  .wb-stat-item {
    flex: 0 0 138px;
    scroll-snap-align: start;
  }

  .wb-card-body {
    padding: 12px 14px 14px;
  }
}

@media (pointer: coarse) {
  .wb-tab,
  .wb-stat,
  .wb-btn {
    min-height: 44px;
  }

  .wb-stat {
    min-height: 88px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .wb-thumb-img,
  .wb-card:hover .wb-thumb-img {
    transition: none;
    transform: none;
  }

  .wb-thumb-fallback::after,
  .wb-skeleton-line {
    animation: none;
  }
}
</style>
