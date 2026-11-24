/**
 * 后台「审核复核（申诉）」处理页。
 *
 * 视觉与信息层级对齐 /admin/reports：概览卡 → 状态 tab → 列表 + 右侧详情；
 * 受理动作带二次确认与可选结论说明（会通知作者）。
 */
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NIcon, useDialog, useMessage } from 'naive-ui'
import {
  ChatbubbleEllipsesOutline,
  CheckmarkCircleOutline,
  CloseCircleOutline,
  DocumentTextOutline,
  OpenOutline,
  RefreshOutline,
  TimeOutline,
} from '@vicons/ionicons5'
import {
  APPEAL_STATUS_LABELS,
  fetchAdminAppeals,
  fetchAdminAppealStats,
  fetchAdminThumbUrl,
  resolveAdminAppeal,
  type AdminAppealItem,
  type AdminAppealStats,
  type AppealDecision,
  type AppealStatus,
} from '../../api/admin_appeals'

type TabKey = 'pending' | 'accepted' | 'rejected'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'pending', label: '待处理' },
  { key: 'accepted', label: '已受理' },
  { key: 'rejected', label: '已驳回' },
]

const PAGE_SIZE = 20
const STATUS_LABELS = APPEAL_STATUS_LABELS

// 被驳回作品的缩略图对匿名不可见：用带 token 的 fetch 拉 blob，<img> 无法带鉴权头。
const thumbMap = ref<Record<string, string>>({})
const thumbsPending = ref<Record<string, boolean>>({})

function thumbFor(item: AdminAppealItem): string | null {
  return item.thumbUrl ? thumbMap.value[item.id] ?? null : null
}

async function ensureThumbs(): Promise<void> {
  const targets = items.value.filter((item) => item.thumbUrl && !thumbMap.value[item.id] && !thumbsPending.value[item.id])
  if (!targets.length) return
  for (const item of targets) thumbsPending.value[item.id] = true
  await Promise.all(
    targets.map(async (item) => {
      const url = await fetchAdminThumbUrl(item.thumbUrl)
      if (url) thumbMap.value = { ...thumbMap.value, [item.id]: url }
      thumbsPending.value[item.id] = false
    }),
  )
}

const message = useMessage()
const dialog = useDialog()

const tab = ref<TabKey>('pending')
const items = ref<AdminAppealItem[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')

const stats = ref<AdminAppealStats | null>(null)
const statsLoading = ref(false)
const statsError = ref('')

const selectedId = ref('')
const decision = ref<AppealDecision>('accept')
const note = ref('')
const formError = ref('')
const submitting = ref(false)

const DEFAULT_NOTES: Record<AppealDecision, string> = {
  accept: '复核通过，作品已重新进入审核流程。',
  reject: '维持原审核结果。',
}

const selectedAppeal = computed(() => items.value.find((item) => item.id === selectedId.value) || null)
const finished = computed(() => items.value.length >= total.value)
const emptyTitle = computed(() => {
  if (tab.value === 'pending') return '当前没有待处理的复核申请'
  if (tab.value === 'accepted') return '还没有已受理的复核申请'
  return '还没有被驳回的复核申请'
})
const emptyHint = computed(() => {
  if (tab.value === 'pending') return '作者对被驳回作品提交复核后，会出现在这里。'
  if (tab.value === 'accepted') return '受理后会重新进入审核流程，并通知作者。'
  return '维持原判的复核申请会留档在这里。'
})

function parseDateValue(value: string | null): Date | null {
  if (!value) return null
  const normalized = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatDateTime(value: string | null): string {
  if (!value) return '—'
  const date = parseDateValue(value)
  if (!date) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function relativeTime(value: string | null): string {
  if (!value) return '—'
  const date = parseDateValue(value)
  if (!date) return value
  const diff = Date.now() - date.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 30 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return formatDateTime(value)
}

function uploaderLabel(item: AdminAppealItem): string {
  if (item.uploaderDisplayName && item.uploaderUsername) {
    return `${item.uploaderDisplayName} · @${item.uploaderUsername}`
  }
  if (item.uploaderUsername) return `@${item.uploaderUsername}`
  if (item.uploaderDisplayName) return item.uploaderDisplayName
  return '未知作者'
}

async function fetchList(reset = false) {
  if (reset) {
    loading.value = true
    offset.value = 0
  } else {
    loadingMore.value = true
  }
  error.value = ''
  try {
    const page = await fetchAdminAppeals({
      status: tab.value,
      limit: PAGE_SIZE,
      offset: offset.value,
    })
    items.value = reset ? page.items : [...items.value, ...page.items]
    total.value = page.total
    void ensureThumbs()
    offset.value = items.value.length
    if (selectedId.value && !items.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = ''
    }
  } catch (err) {
    const text = describeError(err)
    if (reset) error.value = text
    else message.error(text)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

async function fetchStats() {
  statsLoading.value = true
  statsError.value = ''
  try {
    stats.value = await fetchAdminAppealStats(7)
  } catch (err) {
    statsError.value = describeError(err)
  } finally {
    statsLoading.value = false
  }
}

function switchTab(next: TabKey) {
  if (tab.value === next) return
  tab.value = next
  selectedId.value = ''
  items.value = []
  total.value = 0
  void fetchList(true)
}

function selectItem(item: AdminAppealItem) {
  selectedId.value = item.id
}

function loadMore() {
  if (loading.value || loadingMore.value || finished.value) return
  void fetchList(false)
}

function refreshAll() {
  void fetchList(true)
  void fetchStats()
}

function extractDetail(err: unknown): string {
  const response = (err as { response?: { status?: number; data?: unknown } })?.response
  const data = response?.data
  if (typeof data === 'string') return data
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>
    if (typeof record.detail === 'string') return record.detail
    if (Array.isArray(record.detail)) {
      const first = record.detail[0] as { msg?: unknown } | undefined
      if (first && typeof first.msg === 'string') return first.msg
    }
    if (typeof record.message === 'string') return record.message
  }
  return ''
}

function describeError(err: unknown): string {
  const detail = extractDetail(err)
  if (detail) return detail
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return '登录已过期，请重新登录后再试'
  if (status === 403) return '当前账号没有处理复核申请的权限'
  if (status === 404) return '该复核申请或作品已不存在'
  if (status === 409) return '这条申请已被处理，不能重复受理'
  if (status === 429) return '操作过于频繁，请稍后再试'
  if (status && status >= 500) return '服务暂时不可用，请稍后重试'
  return '网络连接失败，请检查网络后重试'
}

function resetForm() {
  decision.value = 'accept'
  note.value = DEFAULT_NOTES.accept
  formError.value = ''
}

watch(selectedId, () => {
  resetForm()
})

function setDecision(next: AppealDecision) {
  if (decision.value === next) return
  decision.value = next
  note.value = DEFAULT_NOTES[next]
  formError.value = ''
}

function confirmResolve() {
  const appeal = selectedAppeal.value
  if (!appeal || submitting.value) return
  const isAccept = decision.value === 'accept'
  dialog.warning({
    title: isAccept ? '受理并重新审核' : '维持原判',
    content: isAccept
      ? '受理后作品会重新进入审核流程，并通知作者。确认继续？'
      : '维持原判会保留「已驳回」状态，并把结论通知作者。确认继续？',
    positiveText: '确认',
    negativeText: '再想想',
    onPositiveClick: () => {
      void submitResolve(appeal)
    },
  })
}

async function submitResolve(appeal: AdminAppealItem) {
  submitting.value = true
  formError.value = ''
  try {
    const result = await resolveAdminAppeal(appeal.id, {
      decision: decision.value,
      note: note.value.trim() || undefined,
    })
    const label = decision.value === 'accept' ? '已受理复核' : '已维持原判'
    message.success(`${label}：${appeal.photoTitle}`)
    selectedId.value = ''
    window.dispatchEvent(new CustomEvent('appeals:changed'))
    await Promise.all([fetchList(true), fetchStats()])
    if (result.message) message.info(result.message)
  } catch (err) {
    const text = describeError(err)
    formError.value = text
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 409 || status === 404) {
      message.warning(text)
      selectedId.value = ''
      void fetchList(true)
      void fetchStats()
    } else {
      message.error(text)
    }
  } finally {
    submitting.value = false
  }
}

function onGlobalKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  if (target && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)) return
  if (event.key === 'Escape' && selectedId.value) {
    selectedId.value = ''
  }
}

watch(statsError, (value) => {
  if (value) message.error(value)
})

onMounted(() => {
  document.title = '复核申诉 · 后台管理 · 视觉百花'
  window.addEventListener('keydown', onGlobalKeydown)
  void fetchList(true)
  void fetchStats()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  document.title = '后台管理 · 视觉百花'
})
</script>

<template>
  <div class="appeals-page">
    <header class="page-head">
      <div>
        <p class="eyebrow">MODERATION · APPEALS</p>
        <h1 class="page-title">复核申诉</h1>
        <p class="page-sub">受理作者对被驳回作品的复核申请：通过则重新进入审核，维持则保留驳回并通知作者。</p>
      </div>
      <n-button secondary :loading="loading || statsLoading" @click="refreshAll">
        <template #icon><n-icon :component="RefreshOutline" /></template>
        刷新
      </n-button>
    </header>

    <div class="stat-grid">
      <template v-if="statsLoading && !stats">
        <div v-for="n in 5" :key="'stat-sk-' + n" class="stat-card is-skeleton">
          <span class="sk-line sk-line--sm" />
          <span class="sk-line sk-line--lg" />
        </div>
      </template>
      <template v-else>
        <div class="stat-card">
          <p class="stat-label">申请总数</p>
          <p class="stat-value tabular">{{ stats?.total ?? '—' }}</p>
          <p class="stat-hint">全部复核记录</p>
        </div>
        <div class="stat-card stat-card--pending">
          <p class="stat-label">待处理</p>
          <p class="stat-value tabular">{{ stats?.pending ?? '—' }}</p>
          <p class="stat-hint">等待受理的申请</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">已受理</p>
          <p class="stat-value tabular">{{ stats?.accepted ?? '—' }}</p>
          <p class="stat-hint">重新进入审核</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">已驳回</p>
          <p class="stat-value tabular">{{ stats?.rejected ?? '—' }}</p>
          <p class="stat-hint">维持原判</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">近 7 天</p>
          <p class="stat-value tabular">{{ stats?.last7Days ?? '—' }}</p>
          <p class="stat-hint">近 7 天新增申请</p>
        </div>
      </template>
    </div>

    <div class="appeals-grid">
      <section class="panel list-panel" aria-label="复核申请列表">
        <div class="list-head">
          <div class="tabs" role="tablist" aria-label="申请状态筛选">
            <button
              v-for="item in TABS"
              :key="item.key"
              type="button"
              role="tab"
              class="tab"
              :class="{ 'is-active': tab === item.key }"
              :aria-selected="tab === item.key"
              @click="switchTab(item.key)"
            >
              {{ item.label }}
              <span v-if="item.key === 'pending' && stats" class="tab-count tabular">{{ stats.pending }}</span>
            </button>
          </div>
          <span class="list-total tabular">共 {{ total }} 条</span>
        </div>

        <n-alert v-if="error" type="error" closable class="list-alert" @close="error = ''">
          {{ error }}
          <template #action>
            <n-button size="small" secondary @click="fetchList(true)">重试</n-button>
          </template>
        </n-alert>

        <template v-if="loading && !items.length">
          <div v-for="n in 5" :key="'list-sk-' + n" class="appeal-item is-skeleton">
            <span class="sk-line sk-line--sm" />
            <span class="sk-line sk-line--md" />
            <span class="sk-line sk-line--lg" />
          </div>
        </template>

        <div v-else-if="!items.length" class="list-empty">
          <n-icon :component="CheckmarkCircleOutline" :size="34" class="empty-icon" />
          <p class="empty-title">{{ emptyTitle }}</p>
          <p class="empty-hint">{{ emptyHint }}</p>
        </div>

        <ul v-else class="appeal-list" role="listbox" aria-label="申诉条目">
          <li v-for="appeal in items" :key="appeal.id">
            <div
              role="option"
              tabindex="0"
              class="appeal-item"
              :data-appeal-id="appeal.id"
              :class="{ 'is-active': appeal.id === selectedId }"
              :aria-selected="appeal.id === selectedId"
              @click="selectItem(appeal)"
              @keydown.enter.prevent="selectItem(appeal)"
              @keydown.space.prevent="selectItem(appeal)"
            >
              <div class="appeal-thumb">
                <img
                  v-if="thumbFor(appeal)"
                  :src="thumbFor(appeal)!"
                  :alt="`${appeal.photoTitle} 缩略图`"
                  loading="lazy"
                  decoding="async"
                />
                <span v-else-if="thumbsPending[appeal.id]" class="thumb-loading" aria-hidden="true" />
                <n-icon v-else :component="DocumentTextOutline" :size="20" />
              </div>
              <div class="appeal-main">
                <div class="appeal-top">
                  <span class="status-tag" :class="'status-tag--' + appeal.status">{{ STATUS_LABELS[appeal.status] }}</span>
                  <span class="appeal-time">{{ relativeTime(appeal.createdAt) }}</span>
                </div>
                <p class="appeal-title">{{ appeal.photoTitle }}</p>
                <p class="appeal-uploader">{{ uploaderLabel(appeal) }}</p>
                <p class="appeal-reason">{{ appeal.reason }}</p>
              </div>
            </div>
          </li>
        </ul>

        <div v-if="items.length" class="list-foot">
          <n-button v-if="!finished" size="small" secondary :loading="loadingMore" @click="loadMore">
            加载更多
          </n-button>
          <span v-else class="list-end">已经到底啦</span>
        </div>
      </section>

      <aside class="panel detail-panel" aria-label="复核申请详情">
        <template v-if="selectedAppeal">
          <header class="detail-head">
            <div>
              <span class="status-tag" :class="'status-tag--' + selectedAppeal.status">
                {{ STATUS_LABELS[selectedAppeal.status] }}
              </span>
              <h2 class="detail-title">{{ selectedAppeal.photoTitle }}</h2>
              <p class="detail-sub">{{ uploaderLabel(selectedAppeal) }}</p>
            </div>
            <n-button size="small" quaternary circle aria-label="关闭详情" @click="selectedId = ''">
              <template #icon><n-icon :component="CloseCircleOutline" /></template>
            </n-button>
          </header>

          <div class="detail-meta">
            <p><span class="meta-label">作品</span><a class="detail-link" :href="`/photo/${selectedAppeal.photoId}`" target="_blank" rel="noopener noreferrer">查看作品页 <n-icon :component="OpenOutline" :size="13" /></a></p>
            <p><span class="meta-label">提交时间</span>{{ formatDateTime(selectedAppeal.createdAt) }}</p>
            <p><span class="meta-label">受理时间</span>{{ formatDateTime(selectedAppeal.handledAt) }}</p>
          </div>

          <section class="detail-block">
            <h3 class="block-title"><n-icon :component="ChatbubbleEllipsesOutline" :size="15" /> 作者申诉理由</h3>
            <p class="reason-full">{{ selectedAppeal.reason }}</p>
          </section>

          <section v-if="selectedAppeal.note" class="detail-block">
            <h3 class="block-title"><n-icon :component="DocumentTextOutline" :size="15" /> 受理结论</h3>
            <p class="note-full">{{ selectedAppeal.note }}</p>
          </section>

          <section v-if="selectedAppeal.status === 'pending'" class="resolve-block">
            <h3 class="block-title"><n-icon :component="TimeOutline" :size="15" /> 人工终判</h3>
            <div class="decision-group" role="radiogroup" aria-label="受理决定">
              <label class="decision-option" :class="{ 'is-active': decision === 'accept' }">
                <input type="radio" name="appeal-decision" value="accept" :checked="decision === 'accept'" @change="setDecision('accept')" />
                <span class="decision-dot" />
                <span>
                  <b>受理并重新审核</b>
                  <i>作品回到待审核，重新进入审核流程</i>
                </span>
              </label>
              <label class="decision-option" :class="{ 'is-active': decision === 'reject' }">
                <input type="radio" name="appeal-decision" value="reject" :checked="decision === 'reject'" @change="setDecision('reject')" />
                <span class="decision-dot" />
                <span>
                  <b>维持原判</b>
                  <i>作品保持已驳回，结论会通知作者</i>
                </span>
              </label>
            </div>

            <label class="resolve-label" for="appeal-note">结论说明（可选，会展示给作者）</label>
            <n-input
              id="appeal-note"
              v-model:value="note"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 6 }"
              maxlength="1000"
              show-count
              placeholder="说明复核结论，例如补交材料是否有效、维持原判的原因等"
            />
            <p v-if="formError" class="form-error">{{ formError }}</p>
            <div class="resolve-actions">
              <n-button secondary @click="resetForm">重置</n-button>
              <n-button type="primary" :loading="submitting" @click="confirmResolve">
                {{ decision === 'accept' ? '受理并重新审核' : '维持原判' }}
              </n-button>
            </div>
          </section>

          <n-alert v-else type="info" class="detail-alert">
            这条申请已处理（{{ STATUS_LABELS[selectedAppeal.status] }}），不能重复受理。
          </n-alert>
        </template>

        <div v-else class="detail-empty">
          <n-icon :component="DocumentTextOutline" :size="30" class="empty-icon" />
          <p class="empty-title">选择左侧一条复核申请</p>
          <p class="empty-hint">查看作者陈述、作品与提交时间，然后做受理决定。</p>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.appeals-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-bottom: 32px;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.eyebrow {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.16em;
  color: var(--faint, #a88a94);
  text-transform: uppercase;
}

.page-title {
  margin: 4px 0 0;
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: clamp(28px, 3vw, 36px);
  font-weight: 400;
  line-height: 1.15;
  letter-spacing: 0.02em;
  color: var(--ink, #4a2b35);
}

.page-sub {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--muted, #63474f);
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.stat-card {
  padding: 14px 16px;
  border-radius: var(--r-md, 14px);
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
}

.stat-card--pending {
  border-color: color-mix(in srgb, var(--sakura, #e8628c) 38%, var(--line, #f3dde5));
  background: linear-gradient(180deg, var(--sakura-wash, #fff0f5), var(--surface, #fff) 62%);
}

.stat-label {
  margin: 0;
  font-size: 12px;
  color: var(--muted, #63474f);
}

.stat-value {
  margin: 4px 0 0;
  font-size: 26px;
  line-height: 1.15;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.stat-hint {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--faint, #a88a94);
}

.stat-card.is-skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sk-line {
  display: block;
  border-radius: 6px;
  background: linear-gradient(90deg, #f7e9ef 25%, #fdf5f8 37%, #f7e9ef 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}

.sk-line--sm { height: 10px; width: 46%; }
.sk-line--lg { height: 18px; width: 92%; }

@keyframes shimmer {
  from { background-position: 100% 0; }
  to { background-position: 0 0; }
}

.appeals-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 440px;
  gap: 18px;
  align-items: start;
}

.panel {
  border-radius: var(--r-card, 20px);
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
}

.list-panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.tabs {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 14px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: 999px;
  background: var(--surface, #fff);
  color: var(--muted, #63474f);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: background 160ms ease, color 160ms ease, border-color 160ms ease;
}

.tab:hover { background: var(--sakura-wash, #fff0f5); }

.tab.is-active {
  background: var(--sakura-pale, #ffe9f0);
  border-color: color-mix(in srgb, var(--sakura, #e8628c) 36%, var(--line, #f3dde5));
  color: var(--sakura-deep, #c93a63);
  font-weight: 600;
}

.tab:focus-visible {
  outline: 3px solid var(--focus-ring, color-mix(in srgb, var(--sakura, #e8628c) 60%, transparent));
  outline-offset: 2px;
}

.tab-count {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--sakura-deep, #c93a63);
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.list-total {
  font-size: 12px;
  color: var(--muted, #63474f);
}

.appeal-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.appeal-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-md, 14px);
  background: var(--surface, #fff);
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease;
}

.appeal-item:hover { background: var(--sakura-wash, #fff0f5); }

.appeal-item.is-active {
  border-color: var(--sakura, #e8628c);
  box-shadow: inset 3px 0 0 var(--sakura-deep, #c93a63);
}

.appeal-item:focus-visible {
  outline: 3px solid var(--focus-ring, color-mix(in srgb, var(--sakura, #e8628c) 60%, transparent));
  outline-offset: 1px;
}

.appeal-thumb {
  flex-shrink: 0;
  width: 64px;
  height: 64px;
  border-radius: 10px;
  overflow: hidden;
  background: var(--sakura-50, #fff0f5);
  background: var(--sakura-wash, #fff0f5);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--faint, #a88a94);
}

.appeal-thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.appeal-main { flex: 1; min-width: 0; }

.thumb-loading {
  display: block;
  width: 100%;
  height: 100%;
  background: linear-gradient(100deg, #ffe3ee 20%, #fff6fa 40%, #ffe3ee 60%);
  background-size: 220% 100%;
  animation: thumb-shimmer 1.2s linear infinite;
}

@keyframes thumb-shimmer {
  from { background-position: 120% 0; }
  to { background-position: -20% 0; }
}

.appeal-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.appeal-time { font-size: 11px; color: var(--faint, #a88a94); }

.appeal-title {
  margin: 4px 0 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--ink, #4a2b35);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.appeal-uploader { margin: 2px 0 0; font-size: 12px; color: var(--muted, #63474f); }

.appeal-reason {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--muted, #63474f);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.status-tag {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background: var(--sakura-wash, #fff0f5);
  color: var(--sakura-deep, #c93a63);
}

.status-tag--accepted { background: #e8f5ee; color: #3b7a57; }
.status-tag--rejected { background: #f6ecec; color: #9c4a4a; }

.list-foot { display: flex; justify-content: center; padding-top: 4px; }
.list-end { font-size: 12px; color: var(--faint, #a88a94); }

.list-alert { margin: 0; }

.list-empty,
.detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 40px 16px;
  text-align: center;
}

.empty-icon { color: var(--sakura, #e8628c); }
.empty-title { margin: 4px 0 0; font-size: 14px; font-weight: 600; color: var(--ink, #4a2b35); }
.empty-hint { margin: 0; font-size: 12px; line-height: 1.7; color: var(--muted, #63474f); max-width: 34em; }

.detail-panel {
  padding: 16px;
  position: sticky;
  top: 86px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.detail-title {
  margin: 6px 0 0;
  font-size: 17px;
  line-height: 1.4;
  color: var(--ink, #4a2b35);
}

.detail-sub { margin: 2px 0 0; font-size: 12px; color: var(--muted, #63474f); }

.detail-meta { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted, #63474f); }
.detail-meta p { margin: 0; display: flex; gap: 8px; align-items: baseline; }
.meta-label { flex-shrink: 0; width: 64px; color: var(--faint, #a88a94); }

.detail-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--sakura-deep, #c93a63);
  text-decoration: none;
}

.detail-link:hover { text-decoration: underline; }

.detail-block { border-top: 1px dashed var(--line, #f3dde5); padding-top: 12px; }
.block-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.reason-full,
.note-full {
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: var(--ink, #4a2b35);
  white-space: pre-wrap;
  word-break: break-word;
}

.note-full { color: var(--muted, #63474f); }

.resolve-block { border-top: 1px dashed var(--line, #f3dde5); padding-top: 12px; display: flex; flex-direction: column; gap: 8px; }

.decision-group { display: grid; gap: 8px; }

.decision-option {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-md, 14px);
  cursor: pointer;
}

.decision-option.is-active {
  border-color: var(--sakura, #e8628c);
  background: var(--sakura-wash, #fff0f5);
}

.decision-option input { position: absolute; opacity: 0; pointer-events: none; }

.decision-dot {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  margin-top: 2px;
  border-radius: 50%;
  border: 2px solid var(--line-strong, #e6c9d4);
  background: var(--surface, #fff);
}

.decision-option.is-active .decision-dot {
  border-color: var(--sakura-deep, #c93a63);
  background: radial-gradient(circle, var(--sakura-deep, #c93a63) 0 45%, transparent 46%);
}

.decision-option b { display: block; font-size: 13px; color: var(--ink, #4a2b35); }
.decision-option i { display: block; margin-top: 2px; font-size: 11px; font-style: normal; line-height: 1.5; color: var(--muted, #63474f); }

.resolve-label { font-size: 12px; color: var(--muted, #63474f); }

.form-error { margin: 0; font-size: 12px; color: #b03a3a; }

.resolve-actions { display: flex; justify-content: flex-end; gap: 8px; }

.detail-alert { margin: 0; }

@media (max-width: 1180px) {
  .appeals-grid { grid-template-columns: minmax(0, 1fr) 380px; }
}

@media (max-width: 900px) {
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .appeals-grid { grid-template-columns: 1fr; }
  .detail-panel { position: static; }
}

@media (max-width: 560px) {
  .page-head { flex-direction: column; align-items: stretch; }
  .page-head :deep(.n-button) { width: 100%; }
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .stat-value { font-size: 22px; }
  .resolve-actions { flex-direction: column-reverse; }
  .resolve-actions :deep(.n-button) { width: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  .appeal-item,
  .tab,
  .sk-line { transition: none; animation: none; }
}
</style>
