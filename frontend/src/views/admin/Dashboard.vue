<template>
  <div class="dashboard">
    <header class="page-head">
      <div class="head-text">
        <p class="eyebrow">OVERVIEW</p>
        <h1 class="page-title">仪表盘</h1>
        <p class="page-sub">先看需要人处理的事，再看站点整体运转。数据每次进入页面时刷新。</p>
      </div>
      <div class="head-actions">
        <n-button secondary :loading="loading" @click="loadAll()">刷新</n-button>
      </div>
    </header>

    <n-result v-if="error && !overview" class="error-panel" status="error" title="概览加载失败" :description="error">
      <template #footer>
        <n-button type="primary" @click="loadAll()">重试</n-button>
      </template>
    </n-result>

    <template v-else>
      <section class="todo-section" aria-labelledby="todo-title">
        <div class="section-head">
          <h2 id="todo-title" class="section-title">待办</h2>
          <span class="section-hint">{{ todoTotal > 0 ? `${todoTotal} 件事等着处理` : '都处理完了，喝口水吧' }}</span>
        </div>
        <div class="todo-grid">
          <RouterLink
            v-for="item in todoItems"
            :key="item.key"
            :to="item.to"
            class="todo-card"
            :class="{ 'is-active': item.count > 0 }"
          >
            <span class="todo-label">{{ item.label }}</span>
            <strong class="todo-value">{{ overview ? item.count : '—' }}</strong>
            <span class="todo-hint">{{ item.hint }}</span>
            <span class="todo-go">{{ item.count > 0 ? '去处理 →' : '查看 →' }}</span>
          </RouterLink>
        </div>
      </section>

      <section class="stat-grid" aria-label="站点概览">
        <article v-for="item in statItems" :key="item.key" class="stat-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value">{{ item.value }}</strong>
          <span class="stat-hint">{{ item.hint }}</span>
        </article>
      </section>

      <section class="panel" aria-labelledby="dash-users-title">
        <header class="panel-head">
          <h2 id="dash-users-title" class="panel-title">用户概览</h2>
          <RouterLink v-if="isAdmin" class="panel-link" to="/admin/users">用户管理 →</RouterLink>
        </header>
        <div class="user-grid">
          <article v-for="card in userCards" :key="card.key" class="user-card">
            <span class="user-label">{{ card.label }}</span>
            <strong class="user-value">{{ card.value }}</strong>
            <span class="user-hint">{{ card.hint }}</span>
          </article>
        </div>
        <div v-if="overview?.recentLogins.length" class="recent">
          <h3 class="recent-title">最近登录</h3>
          <ul class="recent-list">
            <li v-for="item in overview.recentLogins" :key="item.id">
              <span class="recent-name">{{ item.displayName || item.username || '未命名用户' }}</span>
              <n-tag size="small" :bordered="false" class="recent-role">{{ roleLabel(item.role) }}</n-tag>
              <span class="recent-time">{{ item.lastLoginAt ? formatRelativeTime(item.lastLoginAt) : '—' }}</span>
            </li>
          </ul>
        </div>
      </section>

      <div class="chart-grid">
        <section class="panel" aria-labelledby="dash-upload-title">
          <header class="panel-head">
            <h2 id="dash-upload-title" class="panel-title">近 30 天上传趋势</h2>
          </header>
          <div class="chart-box"><v-chart class="chart" :option="uploadTrendOption" autoresize /></div>
        </section>
        <section class="panel" aria-labelledby="dash-tags-title">
          <header class="panel-head">
            <h2 id="dash-tags-title" class="panel-title">热门标签</h2>
          </header>
          <div class="chart-box"><v-chart class="chart" :option="popularTagsOption" autoresize /></div>
        </section>
      </div>

      <section class="panel" aria-labelledby="dash-top-title">
        <header class="panel-head">
          <h2 id="dash-top-title" class="panel-title">热门作品 Top 10</h2>
          <span class="panel-hint">按浏览量 · 点开看详情</span>
        </header>
        <n-empty v-if="!overview?.topPhotos.length" description="还没有已发布作品" />
        <ol v-else class="top-list">
          <li v-for="(photo, index) in overview.topPhotos" :key="photo.id">
            <span class="top-rank">{{ index + 1 }}</span>
            <img v-if="topThumbs[photo.id]" :src="topThumbs[photo.id]" alt="" class="top-thumb" />
            <span v-else class="top-thumb top-thumb--placeholder" aria-hidden="true"></span>
            <RouterLink :to="`/photo/${photo.id}`" class="top-title">{{ photo.title || '未命名作品' }}</RouterLink>
            <span class="top-views">{{ photo.views.toLocaleString('zh-CN') }} 次浏览</span>
          </li>
        </ol>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { getDashboardStats, type DashboardStats } from '../../api/stats'
import { getAdminOverview, type AdminOverview } from '../../api/admin_overview'
import { fetchAdminThumbUrl } from '../../api/admin_appeals'
import { formatRelativeTime } from '../../utils/format'
import { useAuthStore } from '../../stores/auth'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'

use([CanvasRenderer, PieChart, LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent])

const message = useMessage()
const authStore = useAuthStore()

const loading = ref(false)
const error = ref('')
const overview = ref<AdminOverview | null>(null)
const stats = ref<DashboardStats | null>(null)
const topThumbs = ref<Record<string, string>>({})

const isAdmin = computed(() => authStore.isAdmin)

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  auditor: '审核员',
  tagger: '标注员',
  dept_user: '部门用户',
  user: '普通用户',
}

function roleLabel(role: string) {
  return ROLE_LABELS[role] || role
}

const todoItems = computed(() => {
  const todos = overview.value?.todos
  return [
    { key: 'review', label: '待审作品', count: todos?.reviewPending ?? 0, hint: '新投稿等待结论', to: '/admin/review' },
    { key: 'human', label: '待人工复核', count: todos?.moderationPendingHuman ?? 0, hint: 'AI 未自动放行', to: '/admin/review' },
    { key: 'reports', label: '待处理举报', count: todos?.reportsPending ?? 0, hint: '侵权 / 违规投诉', to: '/admin/reports' },
    { key: 'appeals', label: '待处理申诉', count: todos?.appealsPending ?? 0, hint: '作者对驳回不服', to: '/admin/appeals' },
  ]
})

const todoTotal = computed(() => todoItems.value.reduce((sum, item) => sum + item.count, 0))

const statItems = computed(() => {
  const data = overview.value
  if (!data) return []
  return [
    { key: 'photos', label: '作品总数', value: String(data.photos.total), hint: `已发布 ${data.photos.approved} · 待审 ${data.photos.pending}` },
    { key: 'views', label: '总浏览量', value: data.photos.views.toLocaleString('zh-CN'), hint: '全站累计' },
    { key: 'storage', label: '存储占用', value: formatStorage(data.photos.storageBytes), hint: '原图与派生文件' },
    { key: 'aigc', label: '今日生图', value: String(data.aigc.todayTotal), hint: `成功 ${data.aigc.todaySucceeded} · 失败 ${data.aigc.todayFailed}` },
    { key: 'aicost', label: 'AI 成本 · 7 天', value: formatCost(data.aiCost7d + data.aigc.cost7d), hint: `含生图 ${formatCost(data.aigc.cost7d)}` },
    { key: 'bonus', label: '赠送池剩余', value: `${data.aigc.bonusRemaining} 张`, hint: '管理员赠送未消耗' },
  ]
})

const userCards = computed(() => {
  const users = overview.value?.users
  return [
    { key: 'total', label: '总用户', value: users ? String(users.total) : '—', hint: '全部注册账号' },
    { key: 'active', label: '活跃', value: users ? String(users.active) : '—', hint: '当前启用' },
    { key: 'new7', label: '7 日新增', value: users ? String(users.new7Days) : '—', hint: '近一周注册' },
    { key: 'unverified', label: '邮箱未验证', value: users ? String(users.emailUnverified) : '—', hint: '建议提醒补验' },
  ]
})

function formatStorage(bytes: number) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}

function formatCost(value: number) {
  if (!value) return '$0'
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`
}

async function loadTopThumbs() {
  const photos = overview.value?.topPhotos ?? []
  const entries = await Promise.all(
    photos.map(async (photo) => [photo.id, await fetchAdminThumbUrl(photo.thumbUrl)] as const),
  )
  const next: Record<string, string> = {}
  for (const [id, url] of entries) if (url) next[id] = url
  topThumbs.value = next
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [overviewData, statsData] = await Promise.all([
      getAdminOverview(),
      getDashboardStats().catch(() => null),
    ])
    overview.value = overviewData
    stats.value = statsData as DashboardStats | null
    void loadTopThumbs()
  } catch (err) {
    const anyErr = err as { response?: { data?: { detail?: unknown } }; message?: string }
    const detail = anyErr?.response?.data?.detail
    error.value = typeof detail === 'string' ? detail : anyErr?.message || '概览加载失败，请稍后重试。'
    message.error(error.value)
  } finally {
    loading.value = false
  }
}

const uploadTrendOption = computed(() => {
  if (!stats.value) return {}
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 24, bottom: 28 },
    xAxis: { type: 'category', data: stats.value.daily_uploads.map((d) => d.date) },
    yAxis: { type: 'value' },
    series: [
      {
        data: stats.value.daily_uploads.map((d) => d.count),
        type: 'line',
        smooth: true,
        itemStyle: { color: '#c93a63' },
        areaStyle: { color: 'rgba(201, 58, 99, 0.10)' },
      },
    ],
  }
})

const popularTagsOption = computed(() => {
  if (!stats.value) return {}
  return {
    tooltip: { trigger: 'item' },
    legend: { type: 'scroll', orient: 'vertical', right: 8, top: 16, bottom: 16 },
    series: [
      {
        type: 'pie',
        radius: ['42%', '70%'],
        center: ['38%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        data: stats.value.popular_tags.slice(0, 10).map((t) => ({ value: t.count, name: t.name })),
      },
    ],
  }
})

onMounted(() => {
  void loadAll()
})
</script>

<style scoped>
.dashboard {
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

.error-panel {
  padding: 16px 0;
}

.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.section-hint {
  font-size: 12px;
  color: var(--faint, #ad8e97);
}

.todo-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.todo-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px 18px;
  border-radius: 16px;
  border: 1px solid var(--line, #f3dde5);
  background: var(--surface, #fff);
  text-decoration: none;
  box-shadow: 0 2px 10px rgba(201, 58, 99, 0.05);
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.todo-card:hover {
  border-color: var(--line-strong, #e8c7d3);
  transform: translateY(-1px);
}

.todo-card:focus-visible {
  outline: 3px solid var(--sakura-deep, #c93a63);
  outline-offset: 2px;
}

.todo-card.is-active {
  border-color: rgba(201, 58, 99, 0.4);
  background: linear-gradient(150deg, #fff 0%, var(--sakura-wash, #ffe9f0) 100%);
}

.todo-label {
  font-size: 12px;
  color: var(--muted, #63474f);
}

.todo-value {
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: 32px;
  line-height: 1.1;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.todo-card.is-active .todo-value {
  color: var(--sakura-deep, #c93a63);
}

.todo-hint {
  font-size: 11px;
  color: var(--faint, #ad8e97);
}

.todo-go {
  margin-top: 6px;
  font-size: 12px;
  font-weight: 600;
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
  min-height: 100px;
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
  font-size: 26px;
  line-height: 1.1;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.stat-hint {
  font-size: 11px;
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

.panel-link {
  font-size: 13px;
  font-weight: 600;
  color: var(--sakura-deep, #c93a63);
  text-decoration: none;
}

.panel-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.user-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.user-card {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--line, #f3dde5);
  background: var(--ground, #fff6f9);
}

.user-label {
  font-size: 12px;
  color: var(--muted, #63474f);
}

.user-value {
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: 24px;
  line-height: 1.1;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.user-hint {
  font-size: 11px;
  color: var(--faint, #ad8e97);
}

.recent {
  margin-top: 16px;
}

.recent-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-soft, #6d4f58);
}

.recent-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.recent-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  border-bottom: 1px dashed var(--sakura-wash, #ffe9f0);
  font-size: 13px;
}

.recent-list li:last-child {
  border-bottom: 0;
}

.recent-name {
  min-width: 8em;
  color: var(--ink, #4a2b35);
  font-weight: 500;
}

.recent-role {
  background: var(--sakura-wash, #ffe9f0);
  color: var(--sakura-deep, #c93a63);
}

.recent-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--faint, #ad8e97);
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.chart-box {
  height: 280px;
}

.chart {
  height: 100%;
  width: 100%;
}

.top-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.top-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 4px;
  border-bottom: 1px dashed var(--line, #f3dde5);
}

.top-list li:last-child {
  border-bottom: 0;
}

.top-rank {
  flex: none;
  width: 22px;
  font-size: 12px;
  font-weight: 600;
  color: var(--faint, #ad8e97);
  font-variant-numeric: tabular-nums;
}

.top-thumb {
  flex: none;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  object-fit: cover;
  background: var(--sakura-mist, #fff6f9);
}

.top-thumb--placeholder {
  display: inline-block;
}

.top-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 500;
  color: var(--ink, #4a2b35);
  text-decoration: none;
}

.top-title:hover {
  color: var(--sakura-deep, #c93a63);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.top-views {
  flex: none;
  font-size: 12px;
  color: var(--muted, #63474f);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 1280px) {
  .stat-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .todo-grid,
  .user-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chart-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .recent-name {
    min-width: 0;
  }
}

@media (max-width: 560px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (prefers-reduced-motion: reduce) {
  .todo-card {
    transition: none;
  }

  .todo-card:hover {
    transform: none;
  }
}
</style>