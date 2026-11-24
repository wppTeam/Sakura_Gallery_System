<template>
  <div class="admin-ai">
    <header class="page-head">
      <div class="head-text">
        <p class="eyebrow">AI OBSERVABILITY</p>
        <h1 class="page-title">AI 成本</h1>
        <p class="page-sub">
          按日、链路与模型核对调用量、token 与花费。数据来自 ai_usage_events，仅含模型调用元信息，不含提示词与图片内容。
        </p>
      </div>
      <div class="head-actions">
        <n-radio-group :value="days" size="small" @update:value="onDaysChange">
          <n-radio-button v-for="option in DAY_OPTIONS" :key="option" :value="option">{{ option }} 天</n-radio-button>
        </n-radio-group>
        <n-button secondary :loading="loading" @click="load()">刷新</n-button>
      </div>
    </header>

    <p v-if="generatedLabel" class="generated-at">{{ generatedLabel }}</p>

    <n-result
      v-if="error && !usage"
      class="error-panel"
      status="error"
      title="AI 用量加载失败"
      :description="error"
    >
      <template #footer>
        <n-button type="primary" @click="load()">重试</n-button>
      </template>
    </n-result>

    <template v-else-if="!usage && loading">
      <section class="stat-grid" aria-label="正在加载 AI 用量">
        <article v-for="index in 5" :key="index" class="stat-card">
          <n-skeleton text :repeat="3" />
        </article>
      </section>
      <section class="panel">
        <n-skeleton text :repeat="8" />
      </section>
    </template>

    <template v-else-if="usage">
      <p v-if="error" class="inline-error">
        {{ error }}
        <n-button text type="primary" @click="load()">重试</n-button>
      </p>

      <section class="stat-grid" aria-label="AI 用量概览">
        <article v-for="item in statItems" :key="item.key" class="stat-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value" :class="{ 'is-danger': item.danger }">{{ item.value }}</strong>
          <span class="stat-hint" :class="{ 'is-danger': item.danger }">{{ item.hint }}</span>
        </article>
      </section>

      <n-empty v-if="isEmpty" class="empty-panel" description="所选区间内没有 AI 调用">
        <template #extra>
          <p class="empty-hint">等一次审核或 Agent 检索后，再回来看看成本。</p>
        </template>
      </n-empty>

      <template v-else>
        <section class="panel" aria-labelledby="ai-daily-title">
          <header class="panel-head">
            <h2 id="ai-daily-title" class="panel-title">按日分布</h2>
            <span class="panel-hint">{{ days }} 天 · {{ usage.byDay.length }} 个有调用的日期</span>
          </header>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th scope="col">日期</th>
                  <th scope="col" class="num">调用</th>
                  <th scope="col" class="num">Tokens</th>
                  <th scope="col" class="num">花费</th>
                  <th scope="col" class="bar-col">调用量</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in usage.byDay" :key="row.key">
                  <td class="mono">{{ row.key }}</td>
                  <td class="num">{{ formatCount(row.calls) }}</td>
                  <td class="num">{{ formatCount(row.totalTokens) }}</td>
                  <td class="num">{{ formatCostUsd(row.costUsd) }}</td>
                  <td class="bar-col">
                    <span class="day-bar" :style="{ width: dayBarWidth(row.calls) }" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <div class="two-col">
          <section class="panel" aria-labelledby="ai-operation-title">
            <header class="panel-head">
              <h2 id="ai-operation-title" class="panel-title">按链路</h2>
              <span class="panel-hint">按成本降序</span>
            </header>
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th scope="col">链路</th>
                    <th scope="col" class="num">调用</th>
                    <th scope="col" class="num">Tokens</th>
                    <th scope="col" class="num">花费</th>
                    <th scope="col" class="share-col">成本占比</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in usage.byOperation" :key="row.key">
                    <td>
                      <span class="op-label">{{ operationLabel(row.key) }}</span>
                      <span class="cell-sub mono">{{ row.key }}</span>
                    </td>
                    <td class="num">{{ formatCount(row.calls) }}</td>
                    <td class="num">{{ formatCount(row.totalTokens) }}</td>
                    <td class="num">{{ formatCostUsd(row.costUsd) }}</td>
                    <td class="share-col">
                      <div v-if="costShare(row) !== null" class="share">
                        <n-progress
                          type="line"
                          :percentage="costShare(row) ?? 0"
                          :show-indicator="false"
                          :height="6"
                          color="#c93a63"
                          rail-color="#f3dde5"
                        />
                        <span class="share-text">{{ (costShare(row) ?? 0).toFixed(1) }}%</span>
                      </div>
                      <span v-else class="cell-sub">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="panel" aria-labelledby="ai-model-title">
            <header class="panel-head">
              <h2 id="ai-model-title" class="panel-title">按模型</h2>
              <span class="panel-hint">按成本降序</span>
            </header>
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th scope="col">模型</th>
                    <th scope="col" class="num">调用</th>
                    <th scope="col" class="num">Tokens</th>
                    <th scope="col" class="num">花费</th>
                    <th scope="col" class="num">单价 / 1K</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in usage.byModel" :key="row.key">
                    <td class="mono model-name">{{ row.key }}</td>
                    <td class="num">{{ formatCount(row.calls) }}</td>
                    <td class="num">{{ formatCount(row.totalTokens) }}</td>
                    <td class="num">{{ formatCostUsd(row.costUsd) }}</td>
                    <td class="num">{{ unitPrice(row) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <section class="panel" aria-labelledby="ai-recent-title">
          <header class="panel-head">
            <h2 id="ai-recent-title" class="panel-title">最近事件</h2>
            <span class="panel-hint">最近 {{ usage.recent.length }} 条 · 按时间倒序</span>
          </header>
          <div class="table-wrap">
            <table class="data-table recent-table">
              <thead>
                <tr>
                  <th scope="col">时间</th>
                  <th scope="col">链路</th>
                  <th scope="col">模型</th>
                  <th scope="col" class="num">Tokens</th>
                  <th scope="col" class="num">延迟</th>
                  <th scope="col">状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="event in usage.recent" :key="event.id" :class="{ 'is-failed': !event.success }">
                  <td class="mono">{{ formatWhen(event.createdAt) }}</td>
                  <td>
                    <span class="op-label">{{ operationLabel(event.operation) }}</span>
                    <span v-if="event.refType" class="cell-sub">{{ event.refType }}</span>
                  </td>
                  <td class="mono model-name">{{ event.modelId || '—' }}</td>
                  <td class="num">{{ formatCount(event.totalTokens) }}</td>
                  <td class="num">{{ formatLatency(event.latencyMs) }}</td>
                  <td>
                    <n-tag :type="event.success ? 'success' : 'error'" size="small" :bordered="false">
                      {{ event.success ? '成功' : '失败' }}
                    </n-tag>
                    <span v-if="event.error" class="event-error" :title="event.error">{{ event.error }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  formatCount,
  formatCostUsd,
  formatLatency,
  getAiUsage,
  operationLabel,
  type AiUsageBucket,
  type AiUsageResponse,
} from '../../api/admin_ai'
import { formatDate } from '../../utils/format'

const DAY_OPTIONS = [7, 30, 90] as const

const days = ref<number>(7)
const usage = ref<AiUsageResponse | null>(null)
const loading = ref(false)
const error = ref('')

let requestSeq = 0

const isEmpty = computed(() => (usage.value?.totals.calls ?? 0) === 0)

const successRate = computed(() => {
  const totals = usage.value?.totals
  if (!totals || totals.calls <= 0) return 0
  return (totals.success / totals.calls) * 100
})

const generatedLabel = computed(() => {
  const generatedAt = usage.value?.generatedAt
  if (!generatedAt) return ''
  const since = usage.value?.since
  const suffix = since ? ` · 统计自 ${formatWhen(since)}` : ''
  return `数据生成于 ${formatWhen(generatedAt)}${suffix}`
})

const statItems = computed(() => {
  const totals = usage.value?.totals
  if (!totals) return []
  const failed = totals.failed
  const rate = successRate.value
  const avgCost = totals.calls > 0 ? totals.costUsd / totals.calls : 0
  return [
    {
      key: 'calls',
      label: '总调用',
      value: formatCount(totals.calls),
      hint: `近 ${days.value} 天 · 成功 ${formatCount(totals.success)}`,
      danger: false,
    },
    {
      key: 'success',
      label: '成功率',
      value: `${rate.toFixed(1)}%`,
      hint: failed > 0 ? `失败 ${formatCount(failed)} 次` : '暂无失败',
      danger: failed > 0,
    },
    {
      key: 'tokens',
      label: '总 Tokens',
      value: formatCount(totals.totalTokens),
      hint: `输入 ${formatCount(totals.promptTokens)} · 输出 ${formatCount(totals.completionTokens)}`,
      danger: false,
    },
    {
      key: 'cost',
      label: '总花费',
      value: formatCostUsd(totals.costUsd),
      hint: `平均每次 ${formatCostUsd(avgCost)}`,
      danger: false,
    },
    {
      key: 'latency',
      label: '平均延迟',
      value: formatLatency(totals.avgLatencyMs),
      hint: totals.calls > 0 ? `共 ${formatCount(totals.calls)} 次调用` : '暂无调用',
      danger: false,
    },
  ]
})

const maxDayCalls = computed(() => {
  const rows = usage.value?.byDay ?? []
  return rows.reduce((max, row) => Math.max(max, row.calls), 0)
})

function dayBarWidth(calls: number): string {
  if (maxDayCalls.value <= 0) return '0%'
  const percent = (calls / maxDayCalls.value) * 100
  return `${Math.max(2, percent).toFixed(1)}%`
}

function costShare(row: AiUsageBucket): number | null {
  const total = usage.value?.totals.costUsd ?? 0
  if (total <= 0) return null
  return (row.costUsd / total) * 100
}

function unitPrice(row: AiUsageBucket): string {
  if (row.totalTokens <= 0) return '—'
  return formatCostUsd((row.costUsd / row.totalTokens) * 1000)
}

function formatWhen(value: string | null): string {
  if (!value) return '—'
  const formatted = formatDate(value, 'YYYY-MM-DD HH:mm')
  return formatted || value
}

function describeError(err: unknown): string {
  const detail =
    typeof err === 'object' && err !== null && 'response' in err
      ? (err as { response?: { status?: number; data?: { detail?: unknown } } }).response
      : undefined
  const status = detail?.status
  const message = typeof detail?.data?.detail === 'string' ? detail.data.detail : ''
  if (status === 401) return '登录已过期，请重新登录后再试。'
  if (status === 403) return '需要超级管理员权限才能查看 AI 成本。'
  if (status === 404) return 'AI 用量接口尚不可用（可能未部署）。'
  if (status === 429) return '请求过于频繁，请稍后再试。'
  if (status && status >= 500) return '服务端暂时不可用，请稍后重试。'
  if (message) return message
  if (status) return `加载失败（HTTP ${status}）`
  return '网络连接失败，请检查网络后重试。'
}

async function load(): Promise<void> {
  const seq = ++requestSeq
  loading.value = true
  error.value = ''
  try {
    const response = await getAiUsage({ days: days.value, recentLimit: 20 })
    if (seq !== requestSeq) return
    usage.value = response
  } catch (err) {
    if (seq !== requestSeq) return
    error.value = describeError(err)
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

function onDaysChange(value: number): void {
  if (value === days.value) return
  days.value = value
  void load()
}

onMounted(() => {
  void load()
})
</script>

<style scoped>
.admin-ai {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.eyebrow {
  margin: 0 0 6px;
  font-size: 11px;
  letter-spacing: 0.18em;
  color: var(--sakura-deep, #c93a63);
  font-weight: 600;
}

.page-title {
  margin: 0;
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: clamp(28px, 3vw, 34px);
  letter-spacing: 0.02em;
  color: var(--ink, #4a2b35);
}

.page-sub {
  margin: 6px 0 0;
  max-width: 62em;
  font-size: 13px;
  line-height: 1.7;
  color: var(--muted, #63474f);
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.generated-at {
  margin: -8px 0 0;
  font-size: 12px;
  color: var(--faint, #ad8e97);
}

.error-panel {
  padding: 16px 0;
}

.inline-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid rgba(201, 58, 99, 0.24);
  background: rgba(201, 58, 99, 0.06);
  font-size: 13px;
  color: var(--sakura-deep, #c93a63);
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 104px;
  padding: 16px 18px;
  border-radius: 16px;
  border: 1px solid var(--line, #f3dde5);
  background: var(--surface, #fff);
  box-shadow: 0 2px 10px rgba(201, 58, 99, 0.05);
}

.stat-label {
  font-size: 12px;
  color: var(--muted, #63474f);
}

.stat-value {
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: 30px;
  line-height: 1.1;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.stat-value.is-danger {
  color: #c0392b;
}

.stat-hint {
  font-size: 12px;
  line-height: 1.5;
  color: var(--faint, #ad8e97);
  font-variant-numeric: tabular-nums;
}

.stat-hint.is-danger {
  color: #c0392b;
}

.empty-panel {
  padding: 32px 0 24px;
  border-radius: 16px;
  border: 1px dashed var(--line-strong, #e8c7d3);
  background: var(--surface, #fff);
}

.empty-hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--muted, #63474f);
}

.panel {
  padding: 18px 20px 20px;
  border-radius: 16px;
  border: 1px solid var(--line, #f3dde5);
  background: var(--surface, #fff);
  box-shadow: 0 2px 10px rgba(201, 58, 99, 0.05);
}

.panel-skeleton {
  border-radius: 16px;
}

.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.panel-hint {
  font-size: 12px;
  color: var(--faint, #ad8e97);
}

.two-col {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 18px;
}

.table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.data-table {
  width: 100%;
  min-width: 640px;
  border-collapse: collapse;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.data-table th {
  padding: 8px 10px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted, #63474f);
  border-bottom: 1px solid var(--line, #f3dde5);
  white-space: nowrap;
}

.data-table td {
  padding: 10px;
  vertical-align: top;
  color: var(--ink, #4a2b35);
  border-bottom: 1px solid rgba(243, 221, 229, 0.7);
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

.data-table tbody tr:hover td {
  background: rgba(255, 233, 240, 0.5);
}

.data-table .num {
  text-align: right;
  white-space: nowrap;
}

.mono {
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
  font-size: 12px;
}

.op-label {
  display: block;
  font-weight: 500;
}

.cell-sub {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--faint, #ad8e97);
}

.bar-col {
  width: 34%;
}

.day-bar {
  display: block;
  height: 8px;
  min-width: 2px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--sakura, #e8628c), var(--sakura-deep, #c93a63));
  opacity: 0.85;
}

.share-col {
  width: 30%;
}

.share {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 120px;
}

.share :deep(.n-progress) {
  flex: 1;
  min-width: 72px;
}

.share-text {
  font-size: 12px;
  color: var(--muted, #63474f);
  white-space: nowrap;
}

.model-name {
  word-break: break-all;
  max-width: 15em;
}

.recent-table th,
.recent-table td {
  white-space: nowrap;
}

.recent-table td .cell-sub {
  white-space: normal;
}

.recent-table tr.is-failed td {
  background: rgba(192, 57, 43, 0.04);
}

.event-error {
  display: block;
  max-width: 22em;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: #c0392b;
}

@media (max-width: 1180px) {
  .stat-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

}

@media (max-width: 760px) {
  .admin-ai {
    gap: 14px;
  }

  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .stat-card {
    min-height: 96px;
    padding: 12px 14px;
  }

  .stat-value {
    font-size: 25px;
  }

  .panel {
    padding: 14px 14px 16px;
  }

  .head-actions {
    width: 100%;
    justify-content: space-between;
  }

  .bar-col,
  .share-col {
    width: auto;
  }

  .data-table {
    min-width: 520px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .data-table tbody tr {
    transition: none;
  }
}
</style>
