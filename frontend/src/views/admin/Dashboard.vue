<template>
  <div class="dashboard-container">
    <n-spin :show="loading">
      <div class="stats-cards">
        <n-grid x-gap="12" :cols="3">
          <n-grid-item>
            <n-card title="总照片数">
              <n-statistic label="Photos">
                {{ stats?.total_photos || 0 }}
              </n-statistic>
            </n-card>
          </n-grid-item>
          <n-grid-item>
            <n-card title="总浏览量">
              <n-statistic label="Views">
                {{ stats?.total_views || 0 }}
              </n-statistic>
            </n-card>
          </n-grid-item>
          <n-grid-item>
            <n-card title="存储占用">
              <n-statistic label="Storage">
                {{ formatStorage(stats?.total_storage || 0) }}
              </n-statistic>
            </n-card>
          </n-grid-item>
        </n-grid>
      </div>

      <section class="user-overview">
        <div class="uo-head">
          <div>
            <p class="uo-eyebrow">USERS</p>
            <h2 class="uo-title">用户概览</h2>
          </div>
          <n-button text type="primary" @click="$router.push('/admin/users')">用户管理 →</n-button>
        </div>
        <div v-if="userStatsLoading && !userStats" class="uo-grid">
          <div v-for="n in 6" :key="n" class="uo-card uo-card--skeleton">
            <span class="uo-sk uo-sk--label" />
            <span class="uo-sk uo-sk--value" />
          </div>
        </div>
        <div v-else class="uo-grid">
          <article v-for="card in userCards" :key="card.key" class="uo-card">
            <span class="uo-label">{{ card.label }}</span>
            <strong class="uo-value">{{ card.value }}</strong>
            <span class="uo-hint">{{ card.hint }}</span>
          </article>
        </div>
        <div v-if="userStats?.recent_logins?.length" class="uo-recent">
          <h3 class="uo-sub">最近登录</h3>
          <ul class="uo-list">
            <li v-for="item in userStats.recent_logins" :key="item.id" class="uo-list-item">
              <span class="uo-name">{{ item.display_name || item.username || '未命名用户' }}</span>
              <n-tag size="small" :bordered="false" class="uo-role">{{ roleLabel(item.role) }}</n-tag>
              <span class="uo-time">{{ item.last_login_at ? formatRelativeTime(item.last_login_at) : '—' }}</span>
            </li>
          </ul>
        </div>
      </section>

      <n-grid x-gap="12" y-gap="12" :cols="2" style="margin-top: 16px;">
        <n-grid-item>
          <n-card title="近30天上传趋势">
            <div class="chart-container">
              <v-chart class="chart" :option="uploadTrendOption" autoresize />
            </div>
          </n-card>
        </n-grid-item>
        <n-grid-item>
          <n-card title="热门标签">
            <div class="chart-container">
              <v-chart class="chart" :option="popularTagsOption" autoresize />
            </div>
          </n-card>
        </n-grid-item>
      </n-grid>

      <n-card title="热门照片 Top 10" style="margin-top: 16px;">
        <n-data-table
          :columns="columns"
          :data="stats?.top_photos || []"
          :bordered="false"
        />
      </n-card>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useMessage } from 'naive-ui'
import { getDashboardStats, type DashboardStats } from '../../api/stats'
import { getUserStats, type AdminUserStats } from '../../api/users'
import { formatRelativeTime } from '../../utils/format'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, PieChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
} from 'echarts/components'

use([
  CanvasRenderer,
  BarChart,
  PieChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
])

const message = useMessage()
const loading = ref(false)
const stats = ref<DashboardStats | null>(null)
const userStats = ref<AdminUserStats | null>(null)
const userStatsLoading = ref(false)

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

const userCards = computed(() => {
  const s = userStats.value
  return [
    { key: 'total', label: '总用户', value: s ? s.total : '—', hint: '全部注册账号' },
    { key: 'active', label: '活跃', value: s ? s.active : '—', hint: '当前启用' },
    { key: 'pending', label: '待审批', value: s ? s.pending_approval : '—', hint: '注册待放行' },
    { key: 'unverified', label: '邮箱未验证', value: s ? s.email_unverified : '—', hint: '建议提醒补验' },
    { key: 'new7', label: '7 日新增', value: s ? s.new_last_7_days : '—', hint: '近一周注册' },
    { key: 'staff', label: '管理 / 审核', value: s ? `${s.admins} / ${s.auditors}` : '—', hint: '管理员 / 审核员' },
  ]
})

const columns = [
  { title: '文件名', key: 'filename' },
  { title: '浏览量', key: 'views' },
]

onMounted(() => {
  fetchStats()
  fetchUserStats()
})

async function fetchUserStats() {
  userStatsLoading.value = true
  try {
    userStats.value = await getUserStats()
  } catch {
    userStats.value = null
  } finally {
    userStatsLoading.value = false
  }
}

async function fetchStats() {
  loading.value = true
  try {
    const data = await getDashboardStats() as unknown as DashboardStats
    stats.value = data
  } catch (error) {
    message.error('加载统计数据失败')
  } finally {
    loading.value = false
  }
}

const uploadTrendOption = computed(() => {
  if (!stats.value) return {}
  return {
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: stats.value.daily_uploads.map(d => d.date),
    },
    yAxis: { type: 'value' },
    series: [
      {
        data: stats.value.daily_uploads.map(d => d.count),
        type: 'line',
        smooth: true,
      },
    ],
  }
})

const popularTagsOption = computed(() => {
  if (!stats.value) return {}
  
  // Transform data for WordCloud-like Pie or simple Pie
  const data = stats.value.popular_tags.map(t => ({
      value: t.count,
      name: t.name
  }))

  return {
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: false,
          position: 'center'
        },
        data: data
      }
    ]
  }
})

function formatStorage(bytes: number) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}
</script>

<style scoped>
.dashboard-container {
  padding: 24px;
}
.chart-container {
  height: 300px;
}
.chart {
  height: 100%;
  width: 100%;
}

.user-overview {
  margin-top: 16px;
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  border-radius: 16px;
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.08));
  padding: 18px;
}

.uo-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.uo-eyebrow {
  margin: 0 0 4px;
  font-size: 10px;
  letter-spacing: 0.2em;
  color: var(--sakura-deep, #c93a63);
  font-weight: 600;
}

.uo-title {
  margin: 0;
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: 22px;
  letter-spacing: 0.02em;
  color: var(--ink, #4a2b35);
}

.uo-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.uo-card {
  border: 1px solid var(--line, #f3dde5);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  background: var(--ground, #fff6f9);
}

.uo-label {
  font-size: 12px;
  color: var(--muted, #63474f);
}

.uo-value {
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: 24px;
  line-height: 1.1;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.uo-hint {
  font-size: 11px;
  color: var(--faint, #ad8e97);
}

.uo-card--skeleton .uo-sk {
  display: inline-block;
  border-radius: 6px;
  background: linear-gradient(90deg, #f8e7ec 25%, #fdeff4 50%, #f8e7ec 75%);
  background-size: 200% 100%;
  animation: uo-shimmer 1.2s infinite linear;
}

.uo-sk--label {
  width: 56px;
  height: 12px;
}

.uo-sk--value {
  width: 84px;
  height: 22px;
}

@keyframes uo-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

.uo-recent {
  margin-top: 16px;
}

.uo-sub {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-soft, #6d4f58);
}

.uo-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.uo-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  border-bottom: 1px dashed var(--sakura-wash, #ffe9f0);
  font-size: 13px;
}

.uo-list-item:last-child {
  border-bottom: 0;
}

.uo-name {
  color: var(--ink, #4a2b35);
  font-weight: 500;
  min-width: 8em;
}

.uo-role {
  background: var(--sakura-wash, #ffe9f0);
  color: var(--sakura-deep, #c93a63);
}

.uo-time {
  margin-left: auto;
  color: var(--faint, #ad8e97);
  font-size: 12px;
}

@media (max-width: 1280px) {
  .uo-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .uo-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .uo-name {
    min-width: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .uo-card--skeleton .uo-sk {
    animation: none;
  }
}
</style>
