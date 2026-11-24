<template>
  <div class="reports-page">
    <header class="page-head">
      <div>
        <p class="eyebrow">MODERATION · REPORTS</p>
        <h1 class="page-title">举报处理</h1>
        <p class="page-sub">受理公开站点的侵权 / 违规投诉，按「通知—删除」规则处理并留存记录。</p>
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
          <p class="stat-label">投诉总数</p>
          <p class="stat-value tabular">{{ stats?.total ?? '—' }}</p>
          <p class="stat-hint">全部投诉记录</p>
        </div>
        <div class="stat-card stat-card--pending">
          <p class="stat-label">待处理</p>
          <p class="stat-value tabular">{{ stats?.pending ?? '—' }}</p>
          <p class="stat-hint">等待受理的投诉</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">已受理</p>
          <p class="stat-value tabular">{{ stats?.accepted ?? '—' }}</p>
          <p class="stat-hint">通过并处理的投诉</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">已驳回</p>
          <p class="stat-value tabular">{{ stats?.rejected ?? '—' }}</p>
          <p class="stat-hint">不成立的投诉</p>
        </div>
        <div class="stat-card">
          <p class="stat-label">近 7 天</p>
          <p class="stat-value tabular">{{ stats?.last7Days ?? '—' }}</p>
          <p class="stat-hint">近 7 天新增投诉</p>
        </div>
      </template>
    </div>

    <div class="reports-grid">
      <section class="panel list-panel" aria-label="举报列表">
        <div class="list-head">
          <div class="tabs" role="tablist" aria-label="举报状态筛选">
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

        <template v-if="loading && !reports.length">
          <div v-for="n in 5" :key="'list-sk-' + n" class="report-item is-skeleton">
            <span class="sk-line sk-line--sm" />
            <span class="sk-line sk-line--md" />
            <span class="sk-line sk-line--lg" />
          </div>
        </template>

        <div v-else-if="!reports.length" class="list-empty">
          <n-icon :component="CheckmarkCircleOutline" :size="34" class="empty-icon" />
          <p class="empty-title">{{ emptyTitle }}</p>
          <p class="empty-hint">{{ emptyHint }}</p>
        </div>

        <ul v-else class="report-list" role="listbox" aria-label="举报条目">
          <li v-for="report in reports" :key="report.id">
            <div
              role="option"
              tabindex="0"
              class="report-item"
              :data-report-id="report.id"
              :class="{ 'is-active': report.id === selectedId }"
              :aria-selected="report.id === selectedId"
              @click="selectReport(report)"
              @keydown.enter.prevent="selectReport(report)"
              @keydown.space.prevent="selectReport(report)"
            >
              <div class="report-top">
                <span class="reason-tag" :class="'reason-tag--' + report.reasonCode">{{ report.reasonLabel }}</span>
                <span class="target-kind">{{ TARGET_LABELS[report.targetType] }}</span>
                <span class="report-time">{{ relativeTime(report.createdAt) }}</span>
                <span class="status-tag" :class="'status-tag--' + report.status">{{ STATUS_LABELS[report.status] }}</span>
              </div>
              <p class="report-target">
                <a
                  v-if="report.targetUrl"
                  class="target-link target-link--list"
                  :href="report.targetUrl"
                  target="_blank"
                  rel="noopener noreferrer"
                  @click.stop
                >
                  {{ report.targetTitle }}
                  <n-icon :component="OpenOutline" :size="12" />
                </a>
                <span v-else>{{ report.targetTitle }}</span>
              </p>
              <p class="report-text">{{ report.reasonText }}</p>
              <p class="report-meta">
                <span>{{ reporterText(report) }}</span>
                <span v-if="report.reporterIp" class="dot">·</span>
                <span v-if="report.reporterIp">IP {{ maskedIp(report.reporterIp) }}</span>
                <span v-if="report.contact" class="dot">·</span>
                <span v-if="report.contact">{{ report.contact }}</span>
              </p>
            </div>
          </li>
        </ul>

        <div v-if="reports.length" class="list-foot">
          <n-button v-if="reports.length < total" secondary :loading="loadingMore" @click="loadMore">加载更多</n-button>
          <span v-else class="list-end">已经到底啦</span>
        </div>
      </section>

      <section ref="detailPanel" class="panel detail-panel" aria-label="举报详情">
        <template v-if="!selectedReport">
          <div class="detail-empty">
            <n-icon :component="FlagOutline" :size="34" class="empty-icon" />
            <p class="empty-title">选择一条投诉</p>
            <p class="empty-hint">左侧列表点选后，可以查看完整说明并提交处理结果。</p>
          </div>
        </template>
        <template v-else>
          <header class="detail-head">
            <div class="detail-tags">
              <span class="status-tag" :class="'status-tag--' + selectedReport.status">{{ STATUS_LABELS[selectedReport.status] }}</span>
              <span class="reason-tag" :class="'reason-tag--' + selectedReport.reasonCode">{{ selectedReport.reasonLabel }}</span>
            </div>
            <p class="detail-time">提交于 {{ absoluteTime(selectedReport.createdAt) }}</p>
          </header>

          <div class="detail-block">
            <p class="block-label">投诉对象</p>
            <p class="detail-target">
              <span class="target-kind">{{ TARGET_LABELS[selectedReport.targetType] }}</span>
              <a
                v-if="selectedReport.targetUrl"
                class="target-link"
                :href="selectedReport.targetUrl"
                target="_blank"
                rel="noopener noreferrer"
              >
                {{ selectedReport.targetTitle }}
                <n-icon :component="OpenOutline" :size="13" />
              </a>
              <span v-else>{{ selectedReport.targetTitle }}</span>
            </p>
          </div>

          <div class="detail-block">
            <p class="block-label">投诉说明</p>
            <p class="detail-text">{{ selectedReport.reasonText }}</p>
          </div>

          <div class="detail-block">
            <p class="block-label">投诉人</p>
            <dl class="meta-list">
              <div class="meta-row">
                <dt>身份</dt>
                <dd>{{ reporterText(selectedReport) }}</dd>
              </div>
              <div v-if="selectedReport.contact" class="meta-row">
                <dt>联系方式</dt>
                <dd>{{ selectedReport.contact }}</dd>
              </div>
              <div v-if="selectedReport.reporterIp" class="meta-row">
                <dt>来源 IP</dt>
                <dd class="mono-cell">{{ selectedReport.reporterIp }}</dd>
              </div>
            </dl>
          </div>

          <div class="detail-block">
            <p class="block-label">时间线</p>
            <dl class="meta-list">
              <div class="meta-row">
                <dt>提交</dt>
                <dd>{{ absoluteTime(selectedReport.createdAt) }}</dd>
              </div>
              <div v-if="selectedReport.handledAt" class="meta-row">
                <dt>处理</dt>
                <dd>{{ absoluteTime(selectedReport.handledAt) }}</dd>
              </div>
              <div v-if="selectedReport.actionTaken" class="meta-row">
                <dt>处置</dt>
                <dd>{{ actionLabel(selectedReport.actionTaken) }}</dd>
              </div>
              <div v-if="selectedReport.handledBy" class="meta-row">
                <dt>处理人</dt>
                <dd class="mono-cell">{{ shortId(selectedReport.handledBy) }}</dd>
              </div>
            </dl>
          </div>

          <template v-if="selectedReport.status === 'pending'">
            <div class="resolve-block">
              <p class="block-label">处理结果</p>
              <n-radio-group v-model:value="decision" class="decision-group" :disabled="submitting">
                <n-radio value="accept">受理投诉</n-radio>
                <n-radio value="reject">驳回投诉</n-radio>
              </n-radio-group>
              <label class="takedown-row" :class="{ 'is-disabled': decision !== 'accept' || selectedReport.targetType !== 'photo' }">
                <n-checkbox
                  v-model:checked="takedown"
                  :disabled="decision !== 'accept' || selectedReport.targetType !== 'photo' || submitting"
                />
                <span>
                  通过时下架作品
                  <span class="takedown-hint">（作品状态改为已驳回，并通知上传者；专题会转为草稿）</span>
                </span>
              </label>
              <label class="note-label" for="report-resolution-note">处理备注（可选）</label>
              <n-input
                id="report-resolution-note"
                v-model:value="note"
                type="textarea"
                :rows="3"
                maxlength="1000"
                show-count
                placeholder="记录处理依据、通知情况等，便于后续追溯"
                :disabled="submitting"
              />
              <n-alert v-if="formError" type="error" closable class="form-alert" @close="formError = ''">{{ formError }}</n-alert>
              <div class="resolve-actions">
                <n-button type="primary" :loading="submitting" :disabled="submitting" @click="confirmResolve">
                  {{ decision === 'accept' ? '确认受理' : '确认驳回' }}
                </n-button>
                <span class="resolve-hint">处理后将记录处理人与时间，且不能重复处理。</span>
              </div>
            </div>
          </template>
          <template v-else>
            <div class="handled-block">
              <n-alert type="info" :show-icon="false">该投诉已处理，不能重复提交处理结果。</n-alert>
              <p v-if="selectedReport.resolutionNote" class="handled-note">{{ selectedReport.resolutionNote }}</p>
            </div>
          </template>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NAlert, NButton, NCheckbox, NIcon, NInput, NRadio, NRadioGroup, useDialog, useMessage } from 'naive-ui'
import {
  CheckmarkCircleOutline,
  FlagOutline,
  OpenOutline,
  RefreshOutline,
} from '@vicons/ionicons5'
import {
  REPORT_REASON_LABELS,
  REPORT_STATUS_LABELS,
  REPORT_TARGET_LABELS,
  fetchReportStats,
  fetchReports,
  resolveReport,
  type AdminReportItem,
  type AdminReportStats,
  type ReportStatus,
} from '../../api/admin_reports'
import { formatDate, formatRelativeTime } from '../../utils/format'

type TabKey = 'pending' | 'accepted' | 'rejected'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'pending', label: '待处理' },
  { key: 'accepted', label: '已受理' },
  { key: 'rejected', label: '已驳回' },
]

const STATUS_LABELS = REPORT_STATUS_LABELS
const TARGET_LABELS = REPORT_TARGET_LABELS
const PAGE_SIZE = 20

const message = useMessage()
const dialog = useDialog()

const tab = ref<TabKey>('pending')
const reports = ref<AdminReportItem[]>([])
const total = ref(0)
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')

const stats = ref<AdminReportStats | null>(null)
const statsLoading = ref(false)
const statsError = ref('')

const selectedId = ref('')
const selectedReport = computed(() => reports.value.find((item) => item.id === selectedId.value) || null)
const detailPanel = ref<HTMLElement | null>(null)

const decision = ref<'accept' | 'reject'>('accept')
const takedown = ref(false)
const note = ref('')
const submitting = ref(false)
const formError = ref('')

const emptyTitle = computed(() => {
  if (tab.value === 'pending') return '没有待处理的投诉'
  if (tab.value === 'accepted') return '还没有已受理的投诉'
  return '还没有已驳回的投诉'
})
const emptyHint = computed(() =>
  tab.value === 'pending' ? '公示站点暂时没有新的侵权 / 违规投诉。' : '切换到「待处理」查看需要处理的投诉。',
)

let narrowMedia: MediaQueryList | null = null

function isNarrowNow() {
  return narrowMedia?.matches ?? false
}

function tabStatus(): ReportStatus {
  return tab.value
}

async function fetchList(reset = false) {
  if (loading.value || loadingMore.value) return
  const nextOffset = reset ? 0 : reports.value.length
  if (reset) {
    loading.value = true
    error.value = ''
  } else {
    loadingMore.value = true
  }
  try {
    const page = await fetchReports({ status: tabStatus(), limit: PAGE_SIZE, offset: nextOffset })
    if (reset) {
      reports.value = page.items
      total.value = page.total
      if (!page.items.some((item) => item.id === selectedId.value)) selectedId.value = ''
    } else {
      reports.value = reports.value.concat(page.items)
      total.value = page.total
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
    stats.value = await fetchReportStats(7)
  } catch (err) {
    statsError.value = describeError(err)
  } finally {
    statsLoading.value = false
  }
}

function refreshAll() {
  void fetchList(true)
  void fetchStats()
}

function switchTab(next: TabKey) {
  if (tab.value === next) return
  tab.value = next
  selectedId.value = ''
  void fetchList(true)
}

function loadMore() {
  if (reports.value.length >= total.value) return
  void fetchList(false)
}

function selectReport(report: AdminReportItem) {
  selectedId.value = report.id
  if (isNarrowNow()) {
    void nextTick(() => detailPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }
}

function reporterText(report: AdminReportItem) {
  const reporter = report.reporter
  if (!reporter) return '匿名访客'
  const name = reporter.displayName || reporter.username
  if (!name) return '匿名访客'
  return reporter.username && reporter.username !== name ? `${name}（@${reporter.username}）` : name
}

function relativeTime(value: string | null) {
  if (!value) return '未知时间'
  return formatRelativeTime(value)
}

function absoluteTime(value: string | null) {
  if (!value) return '—'
  return formatDate(value, 'YYYY-MM-DD HH:mm:ss')
}

function maskedIp(value: string) {
  if (value.includes(':')) {
    const parts = value.split(':')
    return parts.slice(0, 2).join(':') + ':…'
  }
  const parts = value.split('.')
  if (parts.length === 4) return `${parts[0]}.${parts[1]}.*.*`
  return value.length > 6 ? `${value.slice(0, 4)}…` : value
}

function shortId(value: string) {
  return value.length > 12 ? `${value.slice(0, 8)}…` : value
}

function actionLabel(value: string) {
  if (value === 'takedown') return '已下架'
  if (value === 'none') return '未下架'
  return value
}

function resetForm() {
  decision.value = 'accept'
  takedown.value = false
  note.value = ''
  formError.value = ''
}

watch(selectedId, () => resetForm())

function extractDetail(err: unknown): string {
  const response = (err as { response?: { status?: number; data?: unknown; statusText?: string } })?.response
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
  if (status === 403) return '当前账号没有处理举报的权限'
  if (status === 404) return '该投诉或作品已不存在'
  if (status === 409) return '该投诉已处理，不能重复提交'
  if (status === 429) return '操作过于频繁，请稍后再试'
  if (status && status >= 500) return '服务暂时不可用，请稍后重试'
  return '网络连接失败，请检查网络后重试'
}

function confirmResolve() {
  const report = selectedReport.value
  if (!report || submitting.value) return
  const isAccept = decision.value === 'accept'
  const willTakedown = isAccept && report.targetType === 'photo' && takedown.value
  const confirmText = isAccept
    ? willTakedown
      ? '受理后将下架该作品，并通知上传者。确认继续？'
      : '确认受理该投诉？'
    : '确认驳回该投诉？'
  dialog.warning({
    title: isAccept ? '确认受理投诉' : '确认驳回投诉',
    content: confirmText,
    positiveText: '确认',
    negativeText: '再想想',
    onPositiveClick: () => {
      void submitResolve(report)
    },
  })
}

async function submitResolve(report: AdminReportItem) {
  submitting.value = true
  formError.value = ''
  try {
    const result = await resolveReport(report.id, {
      decision: decision.value,
      note: note.value.trim() || undefined,
      action: decision.value === 'accept' && report.targetType === 'photo' && takedown.value ? 'takedown' : 'none',
    })
    const label = decision.value === 'accept' ? '已受理' : '已驳回'
    message.success(`${label}：${report.targetTitle}${result.actionTaken === 'takedown' ? '（已下架）' : ''}`)
    selectedId.value = ''
    window.dispatchEvent(new CustomEvent('reports:changed'))
    await Promise.all([fetchList(true), fetchStats()])
  } catch (err) {
    const text = describeError(err)
    formError.value = text
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 409 || status === 404) {
      message.warning(text)
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

onMounted(() => {
  narrowMedia = window.matchMedia('(max-width: 900px)')
  document.title = '举报处理 · 后台管理 · 视觉百花'
  window.addEventListener('keydown', onGlobalKeydown)
  void fetchList(true)
  void fetchStats()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  document.title = '后台管理 · 视觉百花'
})

// 供模板 tab count 使用
watch(statsError, (value) => {
  if (value) message.error(value)
})
</script>

<style scoped>
.reports-page {
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
.sk-line--md { height: 14px; width: 72%; }
.sk-line--lg { height: 18px; width: 92%; }

@keyframes shimmer {
  from { background-position: 100% 0; }
  to { background-position: 0 0; }
}

.reports-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
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
  gap: 6px;
  padding: 4px;
  border-radius: 999px;
  background: var(--sakura-wash, #fff0f5);
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 14px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--muted, #63474f);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 120ms ease, color 120ms ease;
}

.tab:hover { color: var(--sakura-deep, #c93a63); }
.tab.is-active { background: var(--surface, #fff); color: var(--sakura-deep, #c93a63); box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1)); }

.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--sakura, #e8628c);
  color: #fff;
  font-size: 11px;
}

.list-total {
  font-size: 12px;
  color: var(--faint, #a88a94);
}

.list-alert { margin-bottom: 2px; }

.report-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.report-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  padding: 12px 14px;
  border-radius: var(--r-sm, 10px);
  border: 1px solid transparent;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 140ms ease, border-color 140ms ease;
}

.report-item:hover { background: var(--sakura-wash, #fff0f5); }
.report-item.is-active { background: var(--sakura-wash, #fff0f5); border-color: var(--sakura-pale, #ffe9f0); }
.report-item.is-skeleton { pointer-events: none; gap: 8px; background: var(--surface-soft, #fff9fb); }
.report-item:focus-visible { outline: 3px solid var(--focus-ring, #e8628c); outline-offset: 2px; }

.target-link--list {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  border-bottom: 1px dashed transparent;
}

.target-link--list:hover { color: var(--sakura-deep, #c93a63); border-color: currentColor; }

.report-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.reason-tag {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--sakura-wash, #fff0f5);
  color: var(--sakura-deep, #c93a63);
  font-size: 11px;
  line-height: 18px;
}

.reason-tag--illegal { background: #fff1ec; color: #b5533a; }
.reason-tag--copyright { background: #f2f4ff; color: #4f5fa8; }
.reason-tag--portrait { background: #fff6e8; color: #a87726; }

.target-kind {
  font-size: 11px;
  color: var(--faint, #a88a94);
}

.report-time {
  margin-left: auto;
  font-size: 11px;
  color: var(--faint, #a88a94);
}

.status-tag {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 18px;
}

.status-tag--pending { background: #fff4e5; color: #a5651b; }
.status-tag--accepted { background: var(--spring-pale, #ffd7e4); color: var(--spring, #e36089); }
.status-tag--rejected { background: var(--line, #f3dde5); color: var(--muted, #63474f); }

.report-target {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.report-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--muted, #63474f);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.report-meta {
  margin: 0;
  font-size: 11px;
  color: var(--faint, #a88a94);
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.dot { opacity: 0.7; }

.list-empty,
.detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 44px 16px;
  text-align: center;
}

.empty-icon { color: var(--sakura, #e8628c); }
.empty-title { margin: 0; font-size: 15px; font-weight: 600; color: var(--ink, #4a2b35); }
.empty-hint { margin: 0; font-size: 12px; line-height: 1.7; color: var(--muted, #63474f); max-width: 30em; }

.list-foot {
  display: flex;
  justify-content: center;
  padding: 6px 0 2px;
}

.list-end { font-size: 12px; color: var(--faint, #a88a94); }

.detail-panel {
  padding: 18px;
  position: sticky;
  top: 18px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  scrollbar-width: thin;
}

.detail-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--line-strong, #e9cad5);
}

.detail-tags { display: flex; gap: 8px; flex-wrap: wrap; }
.detail-time { margin: 0; font-size: 11px; color: var(--faint, #a88a94); }

.detail-block {
  padding: 12px 0;
  border-bottom: 1px dashed var(--line, #f3dde5);
}

.block-label {
  margin: 0 0 6px;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--faint, #a88a94);
  text-transform: uppercase;
}

.detail-target {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 14px;
  color: var(--ink, #4a2b35);
}

.target-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--sakura-deep, #c93a63);
  text-decoration: none;
  border-bottom: 1px solid transparent;
}

.target-link:hover { border-color: currentColor; }
.target-link:focus-visible { outline: 3px solid var(--focus-ring, #e8628c); outline-offset: 2px; border-radius: 4px; }

.detail-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink, #4a2b35);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.meta-list { margin: 0; display: flex; flex-direction: column; gap: 5px; }
.meta-row { display: flex; gap: 10px; font-size: 12px; }
.meta-row dt { flex: none; width: 5em; color: var(--faint, #a88a94); }
.meta-row dd { margin: 0; color: var(--muted, #63474f); overflow-wrap: anywhere; }
.mono-cell { font-family: var(--mono, ui-monospace, SFMono-Regular, Menlo, monospace); font-size: 11px; }

.resolve-block {
  padding-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.decision-group { display: flex; gap: 16px; }

.takedown-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--r-sm, 10px);
  background: var(--surface-warm, #fffaf6);
  border: 1px solid var(--line, #f3dde5);
  font-size: 13px;
  color: var(--ink, #4a2b35);
  line-height: 1.5;
  cursor: pointer;
}

.takedown-row.is-disabled { opacity: 0.55; cursor: not-allowed; }
.takedown-hint { display: block; font-size: 11px; color: var(--faint, #a88a94); margin-top: 2px; }

.note-label { font-size: 12px; color: var(--muted, #63474f); }

.form-alert { margin: 2px 0; }

.resolve-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding-top: 2px;
}

.resolve-hint { font-size: 11px; color: var(--faint, #a88a94); }

.handled-block {
  padding-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.handled-note {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--r-sm, 10px);
  background: var(--surface-soft, #fff9fb);
  font-size: 12px;
  line-height: 1.7;
  color: var(--muted, #63474f);
  white-space: pre-wrap;
}

@media (max-width: 1180px) {
  .reports-grid { grid-template-columns: minmax(0, 1fr) 380px; }
}

@media (max-width: 1080px) {
  .reports-grid { grid-template-columns: minmax(0, 1fr); }
  .detail-panel { position: static; max-height: none; }
}

@media (max-width: 1180px) {
  .stat-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
  .stat-value { font-size: 22px; }
}

@media (max-width: 900px) {
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stat-value { font-size: 26px; }
}

@media (max-width: 640px) {
  .page-head { flex-direction: column; align-items: stretch; }
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .stat-value { font-size: 24px; }
  .tabs { width: 100%; }
  .tab { flex: 1; justify-content: center; padding: 0 8px; }
  .list-head { gap: 8px; }
  .detail-panel { padding: 14px; }
}

@media (pointer: coarse) {
  .tab, .report-item { min-height: 44px; }
}

@media (prefers-reduced-motion: reduce) {
  .stat-card.is-skeleton .sk-line { animation: none; }
  .report-item, .tab { transition: none; }
}
</style>
