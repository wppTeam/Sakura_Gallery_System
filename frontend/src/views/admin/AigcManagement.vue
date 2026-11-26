<template>
  <div class="admin-aigc">
    <header class="page-head">
      <div class="head-text">
        <p class="eyebrow">AI STUDIO OPS</p>
        <h1 class="page-title">AI 生图管理</h1>
        <p class="page-sub">
          创作台的生成量、成功率与成本，以及按人赠送额外额度。额度口径：每人每天
          {{ overview?.baseDailyLimit ?? 3 }} 张基础额度（管理员不限），用尽后自动消耗赠送池；失败不计。
        </p>
      </div>
      <div class="head-actions">
        <n-radio-group :value="days" size="small" @update:value="onDaysChange">
          <n-radio-button v-for="option in DAY_OPTIONS" :key="option" :value="option">{{ option }} 天</n-radio-button>
        </n-radio-group>
        <n-button secondary :loading="loading" @click="loadAll()">刷新</n-button>
      </div>
    </header>

    <n-result v-if="error && !overview" class="error-panel" status="error" title="生图数据加载失败" :description="error">
      <template #footer>
        <n-button type="primary" @click="loadAll()">重试</n-button>
      </template>
    </n-result>

    <template v-else-if="!overview && loading">
      <section class="stat-grid">
        <article v-for="index in 6" :key="index" class="stat-card"><n-skeleton text :repeat="3" /></article>
      </section>
      <section class="panel"><n-skeleton text :repeat="8" /></section>
    </template>

    <template v-else-if="overview">
      <p v-if="error" class="inline-error">
        {{ error }}
        <n-button text type="primary" @click="loadAll()">重试</n-button>
      </p>

      <section class="stat-grid" aria-label="生图概览">
        <article v-for="item in statItems" :key="item.key" class="stat-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value" :class="{ 'is-danger': item.danger }">{{ item.value }}</strong>
          <span class="stat-hint">{{ item.hint }}</span>
        </article>
      </section>

      <div class="two-col">
        <section class="panel" aria-labelledby="aigc-day-title">
          <header class="panel-head">
            <h2 id="aigc-day-title" class="panel-title">按日生成</h2>
            <span class="panel-hint">{{ days }} 天 · {{ overview.byDay.length }} 个有生成的日期</span>
          </header>
          <n-empty v-if="!overview.byDay.length" description="区间内没有生成记录" />
          <div v-else class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th scope="col">日期</th>
                  <th scope="col" class="num">生成</th>
                  <th scope="col" class="num">成功</th>
                  <th scope="col" class="num">失败</th>
                  <th scope="col" class="num">成本</th>
                  <th scope="col" class="bar-col">生成量</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in overview.byDay" :key="row.day">
                  <td class="mono">{{ row.day }}</td>
                  <td class="num">{{ row.total }}</td>
                  <td class="num">{{ row.succeeded }}</td>
                  <td class="num" :class="{ 'is-danger': row.failed > 0 }">{{ row.failed }}</td>
                  <td class="num">{{ formatCost(row.costUsd) }}</td>
                  <td class="bar-col"><span class="day-bar" :style="{ width: dayBarWidth(row.total) }" /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel" aria-labelledby="aigc-top-title">
          <header class="panel-head">
            <h2 id="aigc-top-title" class="panel-title">活跃作者</h2>
            <span class="panel-hint">按生成量降序 · 点名字看额度</span>
          </header>
          <n-empty v-if="!overview.topUsers.length" description="区间内没有作者生成" />
          <div v-else class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th scope="col">作者</th>
                  <th scope="col" class="num">生成</th>
                  <th scope="col" class="num">成功</th>
                  <th scope="col" class="num">成本</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in overview.topUsers" :key="row.user.id">
                  <td>
                    <button type="button" class="user-link" @click="openUserQuota(row.user.id)">
                      {{ row.user.displayName || row.user.username || '未命名' }}
                    </button>
                    <span class="cell-sub mono">@{{ row.user.username || '—' }}</span>
                  </td>
                  <td class="num">{{ row.total }}</td>
                  <td class="num">{{ row.succeeded }}</td>
                  <td class="num">{{ formatCost(row.costUsd) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section class="panel" aria-labelledby="aigc-grant-title">
        <header class="panel-head">
          <h2 id="aigc-grant-title" class="panel-title">赠送额度</h2>
          <span class="panel-hint">
            累计赠送 {{ overview.quota.grantedTotal }} 张 · 已消耗 {{ overview.quota.bonusUsed }} 张 ·
            剩余 {{ overview.quota.bonusRemaining }} 张 · {{ overview.quota.recipients }} 位作者受赠
          </span>
        </header>

        <div class="grant-form">
          <n-select
            v-model:value="grantUserId"
            class="grant-user"
            filterable
            remote
            clearable
            placeholder="搜索作者（用户名 / 邮箱 / 学号）"
            :options="userOptions"
            :loading="userSearching"
            @search="onUserSearch"
          />
          <n-input-number v-model:value="grantAmount" class="grant-amount" :min="1" :max="1000" :show-button="false" placeholder="张数" />
          <n-input v-model:value="grantReason" class="grant-reason" maxlength="200" placeholder="赠送理由（会通知作者，可留空）" />
          <n-button type="primary" :loading="granting" :disabled="!grantUserId || !grantAmount" @click="submitGrant">
            赠送
          </n-button>
        </div>

        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th scope="col">时间</th>
                <th scope="col">作者</th>
                <th scope="col" class="num">张数</th>
                <th scope="col">理由</th>
                <th scope="col">操作人</th>
                <th scope="col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!grants.items.length">
                <td colspan="6" class="empty-cell">还没有赠送记录</td>
              </tr>
              <tr v-for="row in grants.items" :key="row.id">
                <td class="mono">{{ formatTime(row.createdAt) }}</td>
                <td>
                  <button type="button" class="user-link" @click="openUserQuota(row.user.id)">
                    {{ row.user.displayName || row.user.username || '未命名' }}
                  </button>
                </td>
                <td class="num">+{{ row.amount }}</td>
                <td>{{ row.reason || '—' }}</td>
                <td>{{ row.grantedByName || '—' }}</td>
                <td>
                  <n-popconfirm @positive-click="revoke(row.id)">
                    <template #trigger>
                      <n-button text type="error" size="small">撤销</n-button>
                    </template>
                    撤销这笔 {{ row.amount }} 张的赠送？已消耗的部分不会回退。
                  </n-popconfirm>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="grants.total > grants.limit" class="pager">
          <n-pagination
            :page="grantPage"
            :page-size="grants.limit"
            :item-count="grants.total"
            @update:page="onGrantPage"
          />
        </div>
      </section>

      <section class="panel" aria-labelledby="aigc-gen-title">
        <header class="panel-head">
          <h2 id="aigc-gen-title" class="panel-title">生成记录</h2>
          <span class="panel-hint">共 {{ generations.total }} 条</span>
        </header>

        <div class="gen-filters">
          <n-select v-model:value="genStatus" class="filter-status" clearable placeholder="全部状态" :options="STATUS_OPTIONS" @update:value="reloadGenerations(0)" />
          <n-select v-model:value="genSource" class="filter-source" clearable placeholder="全部额度来源" :options="SOURCE_OPTIONS" @update:value="reloadGenerations(0)" />
          <n-input v-model:value="genSearch" class="filter-search" clearable placeholder="提示词关键词" @keyup.enter="reloadGenerations(0)" @clear="reloadGenerations(0)" />
          <n-button secondary :loading="genLoading" @click="reloadGenerations(0)">查询</n-button>
          <n-button v-if="genUserId" text type="primary" @click="clearUserFilter">清除作者筛选</n-button>
        </div>

        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th scope="col">时间</th>
                <th scope="col">作者</th>
                <th scope="col">提示词</th>
                <th scope="col">尺寸</th>
                <th scope="col">状态</th>
                <th scope="col">额度</th>
                <th scope="col" class="num">耗时</th>
                <th scope="col" class="num">成本</th>
                <th scope="col">图</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="genLoading && !generations.items.length">
                <td colspan="9" class="empty-cell">加载中…</td>
              </tr>
              <tr v-else-if="!generations.items.length">
                <td colspan="9" class="empty-cell">没有匹配的生成记录</td>
              </tr>
              <tr v-for="row in generations.items" :key="row.id">
                <td class="mono">{{ formatTime(row.createdAt) }}</td>
                <td>
                  <button type="button" class="user-link" @click="openUserQuota(row.user.id)">
                    {{ row.user.displayName || row.user.username || '未命名' }}
                  </button>
                </td>
                <td class="prompt-cell" :title="row.prompt">{{ row.prompt }}</td>
                <td>{{ sizeLabel(row.sizeKey) }}</td>
                <td>
                  <n-tag size="small" :type="statusTagType(row.status)" :bordered="false">{{ statusLabel(row.status) }}</n-tag>
                  <span v-if="row.error" class="cell-sub error-sub" :title="row.error">{{ row.error }}</span>
                </td>
                <td>{{ sourceLabel(row.quotaSource) }}</td>
                <td class="num">{{ latencyLabel(row.latencyMs) }}</td>
                <td class="num">{{ formatCost(row.costUsd) }}</td>
                <td>
                  <n-button v-if="row.imageUrl" text type="primary" size="small" @click="preview(row)">查看</n-button>
                  <span v-else class="cell-sub">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="pager">
          <n-pagination
            :page="genPage"
            :page-size="generations.limit"
            :item-count="generations.total"
            @update:page="onGenPage"
          />
        </div>
      </section>
    </template>

    <n-modal v-model:show="previewOpen" preset="card" title="生成草稿图" class="preview-modal" :bordered="false">
      <n-spin :show="previewLoading">
        <img v-if="previewUrl" :src="previewUrl" alt="AI 生成草稿图" class="preview-img" />
        <n-empty v-else-if="!previewLoading" description="草稿图加载失败或已被删除" />
      </n-spin>
      <p v-if="previewPrompt" class="preview-prompt">{{ previewPrompt }}</p>
    </n-modal>

    <n-drawer v-model:show="quotaOpen" :width="460" placement="right">
      <n-drawer-content :title="quotaTitle" closable>
        <n-spin :show="quotaLoading">
          <template v-if="userQuota">
            <dl class="quota-list">
              <div><dt>身份</dt><dd>{{ userQuota.quota.unlimited ? '管理员 · 不限' : '普通作者' }}</dd></div>
              <div><dt>今日基础</dt><dd>{{ userQuota.quota.dailyUsed }} / {{ userQuota.quota.dailyLimit }}（剩 {{ userQuota.quota.dailyRemaining }}）</dd></div>
              <div><dt>赠送池</dt><dd>共 {{ userQuota.quota.bonusTotal }} 张 · 已用 {{ userQuota.quota.bonusUsed }} · 剩 {{ userQuota.quota.bonusRemaining }}</dd></div>
            </dl>
            <h3 class="drawer-sub">赠送台账</h3>
            <n-empty v-if="!userQuota.grants.length" description="没有赠送记录" size="small" />
            <ul v-else class="grant-list">
              <li v-for="grant in userQuota.grants" :key="grant.id">
                <span class="mono">{{ formatTime(grant.createdAt) }}</span>
                <strong>+{{ grant.amount }}</strong>
                <span>{{ grant.reason || '无理由' }}</span>
              </li>
            </ul>
            <h3 class="drawer-sub">最近生成</h3>
            <n-empty v-if="!userQuota.recent.length" description="没有生成记录" size="small" />
            <ul v-else class="recent-list">
              <li v-for="item in userQuota.recent" :key="item.id">
                <n-tag size="tiny" :type="statusTagType(item.status)" :bordered="false">{{ statusLabel(item.status) }}</n-tag>
                <span class="recent-prompt" :title="item.prompt">{{ item.prompt }}</span>
                <span class="mono cell-sub">{{ formatTime(item.createdAt) }}</span>
              </li>
            </ul>
          </template>
        </n-spin>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  getAigcOverview,
  getAigcUserQuota,
  grantAigcQuota,
  listAigcGenerationsAdmin,
  listAigcGrants,
  revokeAigcGrant,
  type AigcGenerationAdminItem,
  type AigcGenerationAdminList,
  type AigcGrantList,
  type AigcOverview,
  type AigcUserQuota,
} from '../../api/admin_aigc'
import { fetchAdminThumbUrl } from '../../api/admin_appeals'
import { getUsers } from '../../api/users'

const DAY_OPTIONS = [7, 30, 90]
const PAGE_SIZE = 20
const STATUS_OPTIONS = [
  { label: '排队中', value: 'queued' },
  { label: '生成中', value: 'running' },
  { label: '已完成', value: 'succeeded' },
  { label: '失败', value: 'failed' },
]
const SOURCE_OPTIONS = [
  { label: '每日基础', value: 'daily' },
  { label: '赠送池', value: 'bonus' },
  { label: '管理员不限', value: 'unlimited' },
]
const SIZE_LABELS: Record<string, string> = { square: '方图', landscape: '横图', portrait: '竖图' }

const message = useMessage()
const route = useRoute()

const days = ref(30)
const loading = ref(false)
const error = ref('')
const overview = ref<AigcOverview | null>(null)

const grants = ref<AigcGrantList>({ items: [], total: 0, skip: 0, limit: PAGE_SIZE })
const grantPage = ref(1)
const grantUserId = ref<string | null>(null)
const grantAmount = ref<number | null>(5)
const grantReason = ref('')
const granting = ref(false)
const userOptions = ref<{ label: string; value: string }[]>([])
const userSearching = ref(false)

const generations = ref<AigcGenerationAdminList>({ items: [], total: 0, skip: 0, limit: PAGE_SIZE })
const genPage = ref(1)
const genLoading = ref(false)
const genStatus = ref<string | null>(null)
const genSource = ref<string | null>(null)
const genSearch = ref('')
const genUserId = ref<string | null>(null)

const previewOpen = ref(false)
const previewLoading = ref(false)
const previewUrl = ref('')
const previewPrompt = ref('')

const quotaOpen = ref(false)
const quotaLoading = ref(false)
const userQuota = ref<AigcUserQuota | null>(null)

let userSearchTimer: number | undefined

const statItems = computed(() => {
  const data = overview.value
  if (!data) return []
  const rate = data.totals.successRate
  return [
    { key: 'total', label: `近 ${data.days} 天生成`, value: String(data.totals.total), hint: `成功 ${data.totals.succeeded} · 失败 ${data.totals.failed}` },
    { key: 'rate', label: '成功率', value: `${(rate * 100).toFixed(1)}%`, hint: `进行中 ${data.totals.pending}`, danger: rate < 0.8 && data.totals.total > 0 },
    { key: 'cost', label: '区间成本', value: formatCost(data.totals.costUsd), hint: `平均 ${latencyLabel(Math.round(data.totals.avgLatencyMs))}/张` },
    { key: 'today', label: '今日生成', value: String(data.today.total), hint: `成功 ${data.today.succeeded} · 失败 ${data.today.failed}` },
    { key: 'granted', label: '累计赠送', value: `${data.quota.grantedTotal} 张`, hint: `${data.quota.grantCount} 笔 · ${data.quota.recipients} 位作者` },
    { key: 'left', label: '赠送池剩余', value: `${data.quota.bonusRemaining} 张`, hint: `已消耗 ${data.quota.bonusUsed} 张` },
  ]
})

const quotaTitle = computed(() => {
  const user = userQuota.value?.user
  if (!user) return '作者额度'
  return `${user.displayName || user.username || '作者'} 的额度`
})

const maxDayTotal = computed(() => Math.max(1, ...(overview.value?.byDay.map((row) => row.total) ?? [1])))

function dayBarWidth(total: number): string {
  return `${Math.max(4, Math.round((total / maxDayTotal.value) * 100))}%`
}

function formatCost(value: number): string {
  if (!value) return '$0'
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`
}

function latencyLabel(ms: number | null): string {
  if (!ms) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

function formatTime(raw: string): string {
  if (!raw) return '—'
  const date = new Date(raw.endsWith('Z') || raw.includes('+') ? raw : `${raw}Z`)
  if (Number.isNaN(date.getTime())) return raw
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}

function sizeLabel(key: string): string {
  return SIZE_LABELS[key] || key
}

function statusLabel(status: string): string {
  return STATUS_OPTIONS.find((item) => item.value === status)?.label || status
}

function statusTagType(status: string): 'default' | 'info' | 'success' | 'error' | 'warning' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'running') return 'info'
  return 'warning'
}

function sourceLabel(source: string): string {
  return SOURCE_OPTIONS.find((item) => item.value === source)?.label || source
}

function describeError(err: unknown, fallback: string): string {
  const anyErr = err as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = anyErr?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  return anyErr?.message || fallback
}

async function loadOverview() {
  overview.value = await getAigcOverview(days.value)
}

async function loadGrants(page = grantPage.value) {
  grantPage.value = page
  grants.value = await listAigcGrants({ skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE })
}

async function reloadGenerations(skip = 0) {
  genLoading.value = true
  try {
    generations.value = await listAigcGenerationsAdmin({
      skip,
      limit: PAGE_SIZE,
      status: genStatus.value || undefined,
      quotaSource: genSource.value || undefined,
      userId: genUserId.value || undefined,
      search: genSearch.value || undefined,
    })
    genPage.value = Math.floor(skip / PAGE_SIZE) + 1
  } catch (err) {
    message.error(describeError(err, '生成记录加载失败'))
  } finally {
    genLoading.value = false
  }
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([loadOverview(), loadGrants(1), reloadGenerations(0)])
  } catch (err) {
    error.value = describeError(err, '生图数据加载失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

function onDaysChange(value: number) {
  days.value = value
  void loadOverview().catch((err) => {
    error.value = describeError(err, '总览加载失败')
  })
}

function onGrantPage(page: number) {
  void loadGrants(page)
}

function onGenPage(page: number) {
  void reloadGenerations((page - 1) * PAGE_SIZE)
}

function onUserSearch(query: string) {
  if (userSearchTimer) window.clearTimeout(userSearchTimer)
  if (!query.trim()) {
    userOptions.value = []
    return
  }
  userSearchTimer = window.setTimeout(async () => {
    userSearching.value = true
    try {
      const data = await getUsers({ search: query.trim(), limit: 10 })
      userOptions.value = data.users.map((user) => ({
        label: `${user.display_name || user.username || user.student_id}（@${user.username || user.student_id}）`,
        value: user.id,
      }))
    } catch {
      userOptions.value = []
    } finally {
      userSearching.value = false
    }
  }, 300)
}

async function submitGrant() {
  if (!grantUserId.value || !grantAmount.value) return
  granting.value = true
  try {
    await grantAigcQuota(grantUserId.value, grantAmount.value, grantReason.value)
    message.success(`已赠送 ${grantAmount.value} 张，作者会收到站内通知`)
    grantReason.value = ''
    await Promise.all([loadGrants(1), loadOverview()])
    if (quotaOpen.value && userQuota.value?.user.id === grantUserId.value) await openUserQuota(grantUserId.value)
  } catch (err) {
    message.error(describeError(err, '赠送失败'))
  } finally {
    granting.value = false
  }
}

async function revoke(grantId: string) {
  try {
    await revokeAigcGrant(grantId)
    message.success('已撤销')
    await Promise.all([loadGrants(grantPage.value), loadOverview()])
  } catch (err) {
    message.error(describeError(err, '撤销失败'))
  }
}

async function preview(row: AigcGenerationAdminItem) {
  previewOpen.value = true
  previewLoading.value = true
  previewPrompt.value = row.prompt
  previewUrl.value = ''
  const url = await fetchAdminThumbUrl(row.imageUrl)
  previewUrl.value = url || ''
  previewLoading.value = false
}

async function openUserQuota(userId: string) {
  if (!userId) return
  quotaOpen.value = true
  quotaLoading.value = true
  userQuota.value = null
  try {
    userQuota.value = await getAigcUserQuota(userId)
  } catch (err) {
    message.error(describeError(err, '作者额度加载失败'))
  } finally {
    quotaLoading.value = false
  }
}

function clearUserFilter() {
  genUserId.value = null
  void reloadGenerations(0)
}

onMounted(() => {
  const user = route.query.user
  if (typeof user === 'string' && user) genUserId.value = user
  void loadAll()
})

watch(
  () => route.query.user,
  (user) => {
    genUserId.value = typeof user === 'string' && user ? user : null
    void reloadGenerations(0)
  },
)
</script>

<style scoped>
.admin-aigc {
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
  grid-template-columns: repeat(6, minmax(0, 1fr));
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
  font-size: 28px;
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

.panel {
  padding: 18px 20px 20px;
  border-radius: 16px;
  border: 1px solid var(--line, #f3dde5);
  background: var(--surface, #fff);
  box-shadow: 0 2px 10px rgba(201, 58, 99, 0.05);
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
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
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

.data-table th,
.data-table td {
  padding: 9px 10px;
  text-align: left;
  border-bottom: 1px solid var(--line, #f3dde5);
  vertical-align: top;
}

.data-table th {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted, #63474f);
  white-space: nowrap;
}

.data-table .num {
  text-align: right;
  white-space: nowrap;
}

.data-table .num.is-danger {
  color: #c0392b;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
}

.cell-sub {
  display: block;
  font-size: 11px;
  color: var(--faint, #ad8e97);
}

.error-sub {
  max-width: 22em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #c0392b;
}

.empty-cell {
  padding: 22px 10px;
  text-align: center;
  color: var(--faint, #ad8e97);
}

.bar-col {
  width: 120px;
}

.day-bar {
  display: block;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(90deg, #e8628c, #c93a63);
}

.user-link {
  padding: 0;
  border: 0;
  background: none;
  color: var(--sakura-deep, #c93a63);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.user-link:focus-visible {
  outline: 3px solid var(--sakura-deep, #c93a63);
  outline-offset: 2px;
  border-radius: 4px;
}

.grant-form {
  display: grid;
  grid-template-columns: minmax(0, 2fr) 110px minmax(0, 2fr) auto;
  gap: 10px;
  margin-bottom: 14px;
}

.gen-filters {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.filter-status,
.filter-source {
  width: 150px;
}

.filter-search {
  width: 220px;
}

.prompt-cell {
  max-width: 26em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.preview-modal {
  width: min(720px, 92vw);
}

.preview-img {
  display: block;
  width: 100%;
  max-height: 62vh;
  object-fit: contain;
  border-radius: 12px;
  background: var(--sakura-mist, #fff6f9);
}

.preview-prompt {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--muted, #63474f);
}

.quota-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0 0 18px;
}

.quota-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--line, #f3dde5);
}

.quota-list dt {
  font-size: 13px;
  color: var(--muted, #63474f);
}

.quota-list dd {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.drawer-sub {
  margin: 18px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.grant-list,
.recent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
}

.grant-list li,
.recent-list li {
  display: flex;
  align-items: center;
  gap: 8px;
}

.grant-list strong {
  color: var(--summer, #3b9c80);
}

.recent-prompt {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .stat-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .two-col {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 700px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .grant-form {
    grid-template-columns: minmax(0, 1fr);
  }

  .filter-search {
    width: 100%;
  }
}
</style>