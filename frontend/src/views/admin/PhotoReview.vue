<template>
  <div class="review-page">
    <header class="review-page-head">
      <div class="review-page-title-wrap">
        <p class="review-eyebrow">管理后台 · AI 审核</p>
        <h1 class="review-page-title">AI 审核队列</h1>
        <p class="review-page-desc">
          Agent 用规则前置、VLM 快筛与复核推理解释风险、过滤低风险样本；<strong>发布与否由人终判</strong>。
        </p>
      </div>
      <div class="review-page-actions">
        <label class="auto-refresh">
          <n-switch v-model:value="autoRefresh" size="small" />
          <span>自动刷新 20s</span>
        </label>
        <n-button secondary :loading="queueLoading || statsLoading" @click="refreshAll">
          <template #icon>
            <n-icon><ReloadOutline /></n-icon>
          </template>
          刷新
        </n-button>
      </div>
    </header>

    <StatsBar
      :stats="stats"
      :loading="statsLoading"
      :error="statsError"
      :days="statsDays"
      @refresh="loadStats()"
      @update:days="onStatsDaysChange"
    />

    <div class="review-workspace">
      <section class="queue-panel" aria-label="待审队列">
        <header class="queue-panel-head">
          <div>
            <h2 class="queue-panel-title">待审队列</h2>
            <p class="queue-panel-sub">
              共 {{ formatInteger(total) }} 条 · 每页 {{ PAGE_SIZE }} 条 · 每张照片只显示最新一次 Agent 结论
              <span v-if="lastRefreshedAt"> · 更新于 {{ lastRefreshedAt }}</span>
            </p>
          </div>
          <n-tag v-if="pendingHumanCount" size="small" type="warning" :bordered="false" round>
            待人工 {{ pendingHumanCount }}
          </n-tag>
        </header>

        <div class="queue-filters">
          <n-select
            v-model:value="statusFilter"
            size="small"
            :options="statusOptions"
            class="filter-select"
            :consistent-menu-width="false"
          />
          <n-select
            v-model:value="tierFilter"
            size="small"
            :options="tierOptions"
            class="filter-select"
            :consistent-menu-width="false"
          />
          <label class="pending-toggle">
            <n-switch v-model:value="pendingOnly" size="small" />
            <span>只看待人工</span>
          </label>
        </div>

        <n-alert v-if="queueError" type="error" :bordered="false" class="queue-alert">
          {{ queueError }}
          <template #action>
            <n-button size="tiny" quaternary @click="refreshQueue()">重试</n-button>
          </template>
        </n-alert>

        <p v-if="pendingOnly" class="pending-note">
          “只看待人工”只过滤当前页；AI 排队/运行中的记录请用状态筛选查看。
        </p>

        <ReviewQueueList
          :items="filteredQueue"
          :loading="queueLoading"
          :selected-photo-id="selectedPhotoId"
          :empty-title="emptyTitle"
          :empty-hint="emptyHint"
          @select="selectReview"
          @refresh="refreshQueue()"
        />

        <footer v-if="total > PAGE_SIZE" class="queue-foot">
          <n-pagination
            :page="page"
            :page-size="PAGE_SIZE"
            :item-count="total"
            :page-slot="5"
            size="small"
            @update:page="onPageChange"
          />
        </footer>
      </section>

      <Teleport to="body" :disabled="!isNarrow">
        <div
          v-show="!isNarrow || drawerOpen"
          class="review-detail-col"
          :class="{ 'is-drawer': isNarrow && drawerOpen }"
        >
          <ReviewDetailPanel
            :review="detail"
            :loading="detailLoading"
            :error="detailError"
            :running="runPending"
            :deciding="deciding"
            :dismissible="isNarrow"
            @run="runReview"
            @retry="retryDetail"
            @close="closeDrawer"
            @submit-decision="handleDecision"
          />
        </div>
      </Teleport>

      <div
        v-if="isNarrow && drawerOpen"
        class="review-drawer-backdrop"
        aria-hidden="true"
        @click="closeDrawer"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../styles/admin-review.css'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { ReloadOutline } from '@vicons/ionicons5'
import {
  getModerationDetail,
  getModerationQueue,
  getModerationStats,
  isFinalized,
  runModeration,
  submitModerationDecision,
  type DecisionPayload,
  type ModerationReview,
  type ModerationStats,
} from '../../api/moderation'
import StatsBar from '../../components/admin/StatsBar.vue'
import ReviewQueueList from '../../components/admin/ReviewQueueList.vue'
import ReviewDetailPanel from '../../components/admin/ReviewDetailPanel.vue'
import { formatInteger, formatDateTime } from '../../components/admin/reviewDisplay'

const PAGE_SIZE = 20
const DEFAULT_TITLE = '视觉百花 Sakura Gallery'

const message = useMessage()

const queue = ref<ModerationReview[]>([])
const total = ref(0)
const queueLoading = ref(false)
const queueError = ref('')
const statusFilter = ref('')
const tierFilter = ref('')
const pendingOnly = ref(false)
const page = ref(1)

const selectedPhotoId = ref('')
const detail = ref<ModerationReview | null>(null)
const detailLoading = ref(false)
const detailError = ref('')

const runPending = ref(false)
const deciding = ref(false)

const stats = ref<ModerationStats | null>(null)
const statsLoading = ref(false)
const statsError = ref('')
const statsDays = ref(7)

const autoRefresh = ref(false)
const isNarrow = ref(false)
const drawerOpen = ref(false)
const lastRefreshedAt = ref('')

let autoTimer: ReturnType<typeof setInterval> | undefined
let pollTimer: ReturnType<typeof setInterval> | undefined
let pollTries = 0
let mediaQuery: MediaQueryList | undefined

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '排队中', value: 'queued' },
  { label: 'AI 审核中', value: 'running' },
  { label: 'AI 已完成', value: 'completed' },
  { label: 'AI 失败', value: 'failed' },
]

const tierOptions = [
  { label: '全部等级', value: '' },
  { label: 'L0 免审即发', value: 'L0' },
  { label: 'L1 人工精选', value: 'L1' },
  { label: 'L2 强制前审', value: 'L2' },
]

const pendingHumanCount = computed(() => stats.value?.pendingHuman ?? 0)

const filteredQueue = computed(() => {
  if (!pendingOnly.value) return queue.value
  return queue.value.filter(
    (review) => !isFinalized(review) && review.status !== 'queued' && review.status !== 'running',
  )
})

const emptyTitle = computed(() => {
  if (pendingOnly.value) return '本页没有待人工的记录'
  if (statusFilter.value || tierFilter.value) return '当前筛选下没有记录'
  return '审核队列是空的'
})

const emptyHint = computed(() => {
  if (pendingOnly.value) return '可以翻到上一页，或关闭“只看待人工”查看全部记录，也可以点刷新。'
  if (statusFilter.value || tierFilter.value) return '试试放宽状态或等级筛选，或点刷新获取最新队列。'
  return '新投稿入队后会出现在这里；也可以点刷新确认后台 worker 是否在运行。'
})

function extractError(error: unknown, fallback: string): string {
  const candidate = error as {
    response?: { data?: { detail?: unknown }; status?: number }
    message?: string
  }
  const detail = candidate?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: unknown }
    if (first && typeof first.msg === 'string') return first.msg
  }
  if (typeof candidate?.message === 'string' && candidate.message.trim()) return candidate.message
  return fallback
}

function replaceQueueItem(review: ModerationReview) {
  const index = queue.value.findIndex((item) => item.photoId === review.photoId)
  if (index >= 0) queue.value[index] = review
}

async function refreshQueue(silent = false) {
  if (!silent) queueLoading.value = true
  queueError.value = ''
  try {
    const response = await getModerationQueue({
      status: statusFilter.value || undefined,
      tier: tierFilter.value || undefined,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    queue.value = response.items
    total.value = response.total
    lastRefreshedAt.value = formatDateTime(new Date().toISOString())

    if (!response.items.length && page.value > 1) {
      page.value = Math.max(1, page.value - 1)
      return
    }

    const nextSelected = response.items.find((item) => item.photoId === selectedPhotoId.value)
    if (nextSelected) {
      replaceQueueItem(nextSelected)
    } else if (!isNarrow.value && !selectedPhotoId.value && response.items[0]) {
      selectReview(response.items[0])
    }
  } catch (error) {
    queueError.value = extractError(error, '审核队列加载失败，请稍后重试')
  } finally {
    queueLoading.value = false
  }
}

async function loadStats(silent = false) {
  if (!silent) statsLoading.value = true
  statsError.value = ''
  try {
    stats.value = await getModerationStats(statsDays.value)
  } catch (error) {
    statsError.value = extractError(error, '审核统计加载失败')
  } finally {
    statsLoading.value = false
  }
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = undefined
  pollTries = 0
}

function startPolling(photoId: string) {
  stopPolling()
  pollTimer = setInterval(() => {
    pollTries += 1
    if (pollTries > 20) {
      stopPolling()
      message.info('AI 仍在后台审核，稍后可手动刷新查看')
      return
    }
    void getModerationDetail(photoId)
      .then((review) => {
        if (selectedPhotoId.value === photoId) detail.value = review
        replaceQueueItem(review)
        if (review.status !== 'queued' && review.status !== 'running') {
          stopPolling()
          void refreshQueue(true)
          void loadStats(true)
        }
      })
      .catch(() => {
        // 轮询失败不打断，下一轮继续
      })
  }, 3000)
}

async function loadDetail(photoId: string) {
  detailLoading.value = true
  detailError.value = ''
  stopPolling()
  try {
    const review = await getModerationDetail(photoId)
    if (selectedPhotoId.value !== photoId) return
    detail.value = review
    replaceQueueItem(review)
    if (review.status === 'queued' || review.status === 'running') startPolling(photoId)
  } catch (error) {
    if (selectedPhotoId.value !== photoId) return
    detailError.value = extractError(error, '获取审核详情失败')
  } finally {
    if (selectedPhotoId.value === photoId) detailLoading.value = false
  }
}

function selectReview(review: ModerationReview) {
  selectedPhotoId.value = review.photoId
  detail.value = review
  detailError.value = ''
  if (isNarrow.value) drawerOpen.value = true
  void loadDetail(review.photoId)
}

function retryDetail() {
  if (selectedPhotoId.value) void loadDetail(selectedPhotoId.value)
}

function closeDrawer() {
  drawerOpen.value = false
}

async function runReview() {
  const photoId = selectedPhotoId.value
  if (!photoId || runPending.value) return
  runPending.value = true
  try {
    const response = await runModeration(photoId)
    message.success(response.message || '审核任务已入队')
    startPolling(photoId)
    void refreshQueue(true)
  } catch (error) {
    const text = extractError(error, '重新审核失败')
    if (/409|未启用|MODERATION_ENABLED/i.test(text)) {
      message.warning(text)
    } else {
      message.error(text)
    }
  } finally {
    runPending.value = false
  }
}

async function handleDecision(payload: DecisionPayload) {
  const photoId = selectedPhotoId.value
  if (!photoId || deciding.value) return
  deciding.value = true
  try {
    const review = await submitModerationDecision(photoId, payload)
    detail.value = review
    replaceQueueItem(review)
    const label = payload.decision === 'approve' ? '通过' : payload.decision === 'reject' ? '驳回' : '挂起'
    message.success(`人工终判已提交：${label}`)
    void refreshQueue(true)
    void loadStats(true)
  } catch (error) {
    const text = extractError(error, '提交人工终判失败')
    if (/已有终判|409/.test(text)) {
      message.warning('该照片已有终判，不能重复决策，已为你刷新最新记录')
      void loadDetail(photoId)
      void refreshQueue(true)
    } else {
      message.error(text)
    }
  } finally {
    deciding.value = false
  }
}

function onPageChange(nextPage: number) {
  page.value = nextPage
  void refreshQueue()
}

function onStatsDaysChange(days: number) {
  statsDays.value = days
  void loadStats()
}

function refreshAll() {
  void refreshQueue()
  void loadStats()
  if (selectedPhotoId.value && !isNarrow.value) void loadDetail(selectedPhotoId.value)
}

function applyAutoRefresh(enabled: boolean) {
  if (autoTimer) clearInterval(autoTimer)
  autoTimer = undefined
  if (enabled) {
    autoTimer = setInterval(() => {
      void refreshQueue(true)
      void loadStats(true)
    }, 20000)
  }
}

function syncNarrow() {
  isNarrow.value = mediaQuery?.matches ?? false
  if (!isNarrow.value) drawerOpen.value = false
}

function onGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && isNarrow.value && drawerOpen.value) closeDrawer()
}

watch([statusFilter, tierFilter], () => {
  page.value = 1
  void refreshQueue()
})

watch(page, () => {
  void refreshQueue()
})

watch(autoRefresh, (enabled) => applyAutoRefresh(enabled))

watch(
  () => isNarrow.value && drawerOpen.value,
  (open) => {
    document.body.style.overflow = open ? 'hidden' : ''
  },
)

onMounted(() => {
  document.title = 'AI 审核队列 · 视觉百花管理后台'
  mediaQuery = window.matchMedia('(max-width: 900px)')
  syncNarrow()
  mediaQuery.addEventListener('change', syncNarrow)
  window.addEventListener('keydown', onGlobalKeydown)
  void refreshQueue()
  void loadStats()
})

onBeforeUnmount(() => {
  stopPolling()
  if (autoTimer) clearInterval(autoTimer)
  mediaQuery?.removeEventListener('change', syncNarrow)
  window.removeEventListener('keydown', onGlobalKeydown)
  document.body.style.overflow = ''
  document.title = DEFAULT_TITLE
})
</script>
