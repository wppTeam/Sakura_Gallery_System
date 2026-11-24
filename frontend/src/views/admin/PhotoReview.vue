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
              共 {{ formatInteger(total) }} 条 · 滚动加载（每批 {{ PAGE_SIZE }} 条）· 每张照片只显示最新一次 Agent 结论
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
          “只看待人工”只过滤已加载的记录；AI 排队/运行中的记录请用状态筛选查看。
        </p>

        <div class="queue-bulk" aria-label="批量操作">
          <label class="queue-select-all">
            <input
              type="checkbox"
              class="queue-check"
              :checked="allPageSelected"
              :aria-label="allPageSelected ? '取消全选当前列表' : '全选当前列表'"
              @change="toggleSelectAllPage"
            />
            <span class="queue-check-box" aria-hidden="true" />
            <span>全选本页</span>
          </label>
          <span class="queue-bulk-count">
            {{ selectedCount ? `已选 ${selectedCount} 张` : '勾选后可批量终判' }}
          </span>
          <div class="queue-bulk-actions">
            <n-button size="tiny" type="success" secondary :disabled="!selectedCount" @click="openBatch('approve', selectedIds)">
              批量通过
            </n-button>
            <n-button size="tiny" type="warning" secondary :disabled="!selectedCount" @click="openBatch('hold', selectedIds)">
              批量挂起
            </n-button>
            <n-button size="tiny" type="error" secondary :disabled="!selectedCount" @click="openBatch('reject', selectedIds)">
              批量驳回
            </n-button>
            <n-button v-if="selectedCount" size="tiny" quaternary @click="clearSelection">清空</n-button>
          </div>
        </div>

        <p class="queue-shortcuts">
          <span class="queue-shortcuts__keys">
            <kbd>J</kbd><kbd>K</kbd> 切换 · <kbd>A</kbd> 通过 · <kbd>R</kbd> 驳回 · <kbd>H</kbd> 挂起
          </span>
          <span class="queue-shortcuts__hint">输入框聚焦时不触发</span>
        </p>

        <ReviewQueueList
          :items="filteredQueue"
          :loading="queueLoading"
          :loading-more="loadingMore"
          :selectable="true"
          :selected-ids="selectedIds"
          :selected-photo-id="selectedPhotoId"
          :empty-title="emptyTitle"
          :empty-hint="emptyHint"
          @select="selectReview"
          @refresh="refreshQueue()"
          @toggle-select="toggleSelect"
        />

        <footer v-if="hasMoreQueue" ref="queueSentinel" class="queue-foot queue-sentinel">
          <span v-if="loadingMore" class="queue-sentinel__loading" aria-busy="true">正在加载更多…</span>
          <n-button v-else size="small" secondary @click="loadMoreQueue">加载更多</n-button>
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
            @preview="lightboxOpen = true"
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

    <AdminLightbox
      :show="lightboxOpen"
      :src="lightboxSrc"
      :title="lightboxTitle"
      :note="detail?.photo?.isRedacted ? '已脱敏图片 · 原图仅作者与管理员可见' : '原图只读，保持原始构图未裁切'"
      @close="lightboxOpen = false"
    />

    <n-modal
      v-model:show="batchDialog.open"
      preset="card"
      class="batch-modal"
      :title="`批量${BATCH_LABELS[batchDialog.decision]} · ${batchDialog.ids.length} 张照片`"
      style="width: 540px; max-width: 92vw"
      :mask-closable="!batchDialog.running"
      :close-on-esc="!batchDialog.running"
    >
      <n-space vertical size="medium">
        <n-alert type="warning" :bordered="false">
          将对已选 <strong>{{ batchDialog.ids.length }}</strong> 张照片批量<strong>{{ BATCH_LABELS[batchDialog.decision] }}</strong>。
          通过/驳回会给上传者发送通知，已有终判的照片会被自动跳过。
        </n-alert>

        <n-radio-group v-model:value="batchDialog.decision" name="batch-decision">
          <n-space>
            <n-radio value="approve">通过发布</n-radio>
            <n-radio value="reject">驳回</n-radio>
            <n-radio value="hold">挂起待补</n-radio>
          </n-space>
        </n-radio-group>

        <n-input
          v-model:value="batchDialog.reason"
          type="textarea"
          :rows="3"
          :maxlength="1000"
          show-count
          :placeholder="batchDialog.decision === 'reject' ? '请填写驳回理由（必填，会发给上传者）' : '批量操作理由（选填，会记录到审核日志）'"
          :status="batchDialog.error ? 'error' : undefined"
        />

        <n-alert v-if="batchDialog.error" type="error" :bordered="false">
          {{ batchDialog.error }}
        </n-alert>

        <n-alert v-if="batchFailures.length" type="warning" :bordered="false" class="batch-failures">
          <template #header>部分照片未处理成功（{{ batchFailures.length }} 张）</template>
          <ul class="batch-failures__list">
            <li v-for="failure in batchFailures" :key="failure.photoId">
              <span class="mono">{{ failure.photoId.slice(0, 8) }}</span>
              <span>{{ failure.error || '未知错误' }}</span>
            </li>
          </ul>
          <p class="batch-failures__hint">可修正后只重试失败的照片，其余已成功。</p>
        </n-alert>
      </n-space>

      <template #footer>
        <div class="batch-modal__foot">
          <n-button secondary :disabled="batchDialog.running" @click="closeBatch">取消</n-button>
          <n-button type="primary" :loading="batchDialog.running" @click="runBatch">
            确认{{ BATCH_LABELS[batchDialog.decision] }} {{ batchDialog.ids.length }} 张
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import '../../styles/admin-review.css'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { ReloadOutline } from '@vicons/ionicons5'
import {
  getModerationDetail,
  getModerationQueue,
  getModerationStats,
  isFinalized,
  runModeration,
  submitBatchDecision,
  submitModerationDecision,
  type BatchDecisionItem,
  type DecisionPayload,
  type ModerationDecision,
  type ModerationReview,
  type ModerationStats,
} from '../../api/moderation'
import { getPhotoUrl } from '../../utils/format'
import StatsBar from '../../components/admin/StatsBar.vue'
import ReviewQueueList from '../../components/admin/ReviewQueueList.vue'
import ReviewDetailPanel from '../../components/admin/ReviewDetailPanel.vue'
import AdminLightbox from '../../components/admin/AdminLightbox.vue'
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

const selectedIds = ref<string[]>([])
const loadingMore = ref(false)
const queueSentinel = ref<HTMLElement | null>(null)
const lightboxOpen = ref(false)

const BATCH_LIMIT = 50
const batchDialog = reactive({
  open: false,
  decision: 'approve' as ModerationDecision,
  reason: '',
  ids: [] as string[],
  running: false,
  error: '',
})
const batchFailures = ref<BatchDecisionItem[]>([])
let queueObserver: IntersectionObserver | undefined

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

const selectedCount = computed(() => selectedIds.value.length)
const allPageSelected = computed(
  () => filteredQueue.value.length > 0 && filteredQueue.value.every((review) => selectedIds.value.includes(review.photoId)),
)
const hasMoreQueue = computed(() => queue.value.length > 0 && queue.value.length < total.value)
const lightboxSrc = computed(() => (detail.value?.photo ? getPhotoUrl(detail.value.photo.id, 'original') : ''))
const lightboxTitle = computed(() => detail.value?.photo?.title || '审核图片')

const BATCH_LABELS: Record<ModerationDecision, string> = {
  approve: '通过',
  reject: '驳回',
  hold: '挂起',
}

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
      offset: 0,
    })
    queue.value = response.items
    total.value = response.total
    lastRefreshedAt.value = formatDateTime(new Date().toISOString())

    // 已不在当前列表中的选中项自动移除
    const present = new Set(response.items.map((item) => item.photoId))
    selectedIds.value = selectedIds.value.filter((id) => present.has(id))

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

async function loadMoreQueue() {
  if (queueLoading.value || loadingMore.value || !hasMoreQueue.value) return
  loadingMore.value = true
  try {
    const response = await getModerationQueue({
      status: statusFilter.value || undefined,
      tier: tierFilter.value || undefined,
      limit: PAGE_SIZE,
      offset: queue.value.length,
    })
    const seen = new Set(queue.value.map((item) => item.photoId))
    queue.value = [...queue.value, ...response.items.filter((item) => !seen.has(item.photoId))]
    total.value = Math.max(total.value, response.total)
  } catch (error) {
    message.error(extractError(error, '加载更多失败，请稍后重试'))
  } finally {
    loadingMore.value = false
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

// ────────────────────────────────────────────────────────────
// 选择 / 批量终判
// ────────────────────────────────────────────────────────────

function toggleSelect(photoId: string) {
  selectedIds.value = selectedIds.value.includes(photoId)
    ? selectedIds.value.filter((id) => id !== photoId)
    : [...selectedIds.value, photoId]
}

function toggleSelectAllPage() {
  if (allPageSelected.value) {
    const pageIds = new Set(filteredQueue.value.map((review) => review.photoId))
    selectedIds.value = selectedIds.value.filter((id) => !pageIds.has(id))
  } else {
    const merged = new Set([...selectedIds.value, ...filteredQueue.value.map((review) => review.photoId)])
    selectedIds.value = [...merged]
  }
}

function clearSelection() {
  selectedIds.value = []
}

function openBatch(decision: ModerationDecision, ids: string[]) {
  if (!ids.length) {
    message.info('请先勾选要处理的照片')
    return
  }
  const actionable = new Set(queue.value.filter((item) => !isFinalized(item)).map((item) => item.photoId))
  const valid = ids.filter((id) => actionable.has(id))
  if (!valid.length) {
    message.info('所选照片都已有终判，不能重复决策')
    return
  }
  if (valid.length < ids.length) {
    message.info(`已跳过 ${ids.length - valid.length} 张已有终判的照片`)
  }
  batchDialog.decision = decision
  batchDialog.ids = valid
  batchDialog.reason = ''
  batchDialog.error = ''
  batchFailures.value = []
  batchDialog.open = true
}

function closeBatch() {
  if (batchDialog.running) return
  batchDialog.open = false
}

async function runBatch() {
  if (batchDialog.running || !batchDialog.ids.length) return
  if (batchDialog.decision === 'reject' && !batchDialog.reason.trim()) {
    batchDialog.error = '驳回需要填写理由，便于上传者理解。'
    return
  }
  batchDialog.running = true
  batchDialog.error = ''
  batchFailures.value = []
  try {
    const chunks: string[][] = []
    for (let index = 0; index < batchDialog.ids.length; index += BATCH_LIMIT) {
      chunks.push(batchDialog.ids.slice(index, index + BATCH_LIMIT))
    }
    const outcomes: BatchDecisionItem[] = []
    let succeeded = 0
    for (const chunk of chunks) {
      const response = await submitBatchDecision({
        photoIds: chunk,
        decision: batchDialog.decision,
        reason: batchDialog.reason.trim() || undefined,
      })
      succeeded += response.succeeded
      outcomes.push(...response.items)
    }
    const failures = outcomes.filter((item) => !item.ok)
    batchFailures.value = failures
    // 部分失败时，把待处理范围收窄到失败项，避免「重试」重复提交已成功的照片
    if (failures.length > 0) batchDialog.ids = failures.map((item) => item.photoId)
    const failed = outcomes.length - succeeded
    const label = BATCH_LABELS[batchDialog.decision]
    if (failed === 0) {
      message.success(`已批量${label} ${succeeded} 张照片`)
      batchDialog.open = false
      batchDialog.ids = []
      clearSelection()
    } else {
      message.warning(`批量${label}完成：成功 ${succeeded} 张，失败 ${failed} 张`)
    }
    await Promise.all([refreshQueue(true), loadStats(true)])
    if (selectedPhotoId.value && batchDialog.ids.includes(selectedPhotoId.value)) {
      void loadDetail(selectedPhotoId.value)
    }
  } catch (error) {
    batchDialog.error = extractError(error, '批量终判失败，请稍后重试')
  } finally {
    batchDialog.running = false
  }
}

// ────────────────────────────────────────────────────────────
// 键盘快捷键：J/K 切换 · A 通过 · R 驳回 · H 挂起
// ────────────────────────────────────────────────────────────

function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  if (!element) return false
  return (
    element.tagName === 'INPUT' ||
    element.tagName === 'TEXTAREA' ||
    element.tagName === 'SELECT' ||
    element.isContentEditable ||
    Boolean(element.closest('[contenteditable="true"]'))
  )
}

function quickDecide(decision: ModerationDecision) {
  const review = queue.value.find((item) => item.photoId === selectedPhotoId.value)
  if (!review) {
    message.info('请先用 J / K 选中一条记录')
    return
  }
  if (isFinalized(review)) {
    message.info('这张照片已有终判，不能重复决策')
    return
  }
  if (decision === 'reject') {
    openBatch('reject', [review.photoId])
    return
  }
  void submitQuickDecision(decision)
}

async function submitQuickDecision(decision: ModerationDecision) {
  if (deciding.value) return
  deciding.value = true
  try {
    const review = await submitModerationDecision(selectedPhotoId.value, {
      decision,
      reason: decision === 'approve' ? '快捷键操作：通过' : '快捷键操作：挂起待补',
    })
    detail.value = review
    replaceQueueItem(review)
    message.success(`人工终判已提交：${BATCH_LABELS[decision]}`)
    void refreshQueue(true)
    void loadStats(true)
  } catch (error) {
    const text = extractError(error, '提交人工终判失败')
    if (/已有终判|409/.test(text)) {
      message.warning('该照片已有终判，不能重复决策，已为你刷新最新记录')
      void loadDetail(selectedPhotoId.value)
      void refreshQueue(true)
    } else {
      message.error(text)
    }
  } finally {
    deciding.value = false
  }
}

function moveCurrent(delta: 1 | -1) {
  const list = filteredQueue.value
  if (!list.length) return
  const currentIndex = list.findIndex((review) => review.photoId === selectedPhotoId.value)
  const nextIndex = currentIndex < 0 ? 0 : Math.min(Math.max(currentIndex + delta, 0), list.length - 1)
  const target = list[nextIndex]
  if (!target) return
  selectReview(target)
  queue.value.length // keep reactivity order
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
  if (event.key === 'Escape') {
    if (lightboxOpen.value) {
      lightboxOpen.value = false
      return
    }
    if (batchDialog.open) {
      closeBatch()
      return
    }
    if (isNarrow.value && drawerOpen.value) closeDrawer()
    return
  }
  if (batchDialog.open || lightboxOpen.value || isTypingTarget(event.target)) return
  if (event.metaKey || event.ctrlKey || event.altKey) return
  const key = event.key.toLowerCase()
  if (key === 'j') {
    event.preventDefault()
    moveCurrent(1)
  } else if (key === 'k') {
    event.preventDefault()
    moveCurrent(-1)
  } else if (key === 'a') {
    event.preventDefault()
    quickDecide('approve')
  } else if (key === 'r') {
    event.preventDefault()
    quickDecide('reject')
  } else if (key === 'h') {
    event.preventDefault()
    quickDecide('hold')
  }
}

watch([statusFilter, tierFilter], () => {
  clearSelection()
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
  queueObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadMoreQueue()
    },
    { rootMargin: '240px 0px 240px 0px' },
  )
  if (queueSentinel.value) queueObserver.observe(queueSentinel.value)
  void refreshQueue()
  void loadStats()
})

onBeforeUnmount(() => {
  stopPolling()
  if (autoTimer) clearInterval(autoTimer)
  mediaQuery?.removeEventListener('change', syncNarrow)
  queueObserver?.disconnect()
  window.removeEventListener('keydown', onGlobalKeydown)
  document.body.style.overflow = ''
  document.title = DEFAULT_TITLE
})
</script>
