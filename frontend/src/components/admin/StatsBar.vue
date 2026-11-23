<template>
  <section class="stats-bar" aria-label="审核概览">
    <header class="stats-head">
      <div class="stats-heading">
        <n-icon :size="18" color="var(--sakura-deep, #c93a63)"><StatsChartOutline /></n-icon>
        <h2 class="stats-title">审核概览</h2>
        <span class="stats-sub">规则前置 · VLM 快筛 · 复核推理</span>
      </div>
      <n-select
        class="stats-days"
        size="small"
        :value="days"
        :options="dayOptions"
        :consistent-menu-width="false"
        @update:value="(value: number) => emit('update:days', value)"
      />
    </header>

    <div v-if="loading && !stats" class="stats-loading" aria-busy="true">
      <span v-for="index in 6" :key="index" class="stats-skeleton" />
    </div>

    <n-alert v-else-if="error && !stats" type="error" :bordered="false" class="stats-alert">
      {{ error }}
      <template #action>
        <n-button size="tiny" quaternary @click="emit('refresh')">重新加载</n-button>
      </template>
    </n-alert>

    <template v-else-if="stats">
      <div class="stats-grid">
        <article class="stat stat-accent">
          <span class="stat-label"><n-icon :size="14"><PeopleOutline /></n-icon>待人工处理</span>
          <strong class="stat-value">{{ formatInteger(stats.pendingHuman) }}</strong>
          <span class="stat-hint">AI 已完成、未终判</span>
        </article>

        <article class="stat">
          <span class="stat-label"><n-icon :size="14"><LayersOutline /></n-icon>近 {{ stats.days }} 天审核</span>
          <strong class="stat-value">{{ formatInteger(stats.total) }}</strong>
          <span class="stat-hint">含排队与失败</span>
        </article>

        <article class="stat">
          <span class="stat-label"><n-icon :size="14"><TimerOutline /></n-icon>平均延迟</span>
          <strong class="stat-value">{{ formatLatency(stats.avgLatencyMs) }}</strong>
          <span class="stat-hint">规则 + 模型合计</span>
        </article>

        <article class="stat">
          <span class="stat-label"><n-icon :size="14"><WalletOutline /></n-icon>模型花费</span>
          <strong class="stat-value">{{ formatCost(stats.costUsd) }}</strong>
          <span class="stat-hint">{{ formatInteger(stats.promptTokens + stats.completionTokens) }} tokens</span>
        </article>

        <article class="stat">
          <span class="stat-label"><n-icon :size="14"><FlashOutline /></n-icon>今日调用</span>
          <strong class="stat-value">
            {{ formatInteger(stats.todayCalls) }}<span v-if="stats.dailyBudget > 0" class="stat-value-sub"> / {{ formatInteger(stats.dailyBudget) }}</span>
          </strong>
          <span class="stat-hint">{{ stats.dailyBudget > 0 ? '每日预算内调用' : '未设置每日预算' }}</span>
        </article>

        <article class="stat">
          <span class="stat-label"><n-icon :size="14"><SpeedometerOutline /></n-icon>剩余额度</span>
          <strong class="stat-value">{{ stats.remainingCalls === null ? '—' : formatInteger(stats.remainingCalls) }}</strong>
          <span class="stat-hint">{{ stats.remainingCalls === null ? '未配置预算' : '按今日预算估算' }}</span>
        </article>
      </div>

      <div class="tier-row">
        <div class="tier-bars" role="img" :aria-label="`分级分布：L0 ${stats.byTier.L0}，L1 ${stats.byTier.L1}，L2 ${stats.byTier.L2}`">
          <span class="tier-bar is-l0" :style="{ flexGrow: Math.max(stats.byTier.L0, 0.001) }" />
          <span class="tier-bar is-l1" :style="{ flexGrow: Math.max(stats.byTier.L1, 0.001) }" />
          <span class="tier-bar is-l2" :style="{ flexGrow: Math.max(stats.byTier.L2, 0.001) }" />
        </div>
        <ul class="tier-legend">
          <li><i class="dot is-l0" />L0 免审即发 <strong>{{ formatInteger(stats.byTier.L0) }}</strong></li>
          <li><i class="dot is-l1" />L1 人工精选 <strong>{{ formatInteger(stats.byTier.L1) }}</strong></li>
          <li><i class="dot is-l2" />L2 强制前审 <strong>{{ formatInteger(stats.byTier.L2) }}</strong></li>
          <li v-if="failedCount > 0" class="is-failed">
            <n-icon :size="12"><AlertCircleOutline /></n-icon>AI 失败 <strong>{{ formatInteger(failedCount) }}</strong>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  AlertCircleOutline,
  FlashOutline,
  LayersOutline,
  PeopleOutline,
  SpeedometerOutline,
  StatsChartOutline,
  TimerOutline,
  WalletOutline,
} from '@vicons/ionicons5'
import type { ModerationStats } from '../../api/moderation'
import { formatCost, formatInteger, formatLatency } from './reviewDisplay'

const props = defineProps<{
  stats: ModerationStats | null
  loading: boolean
  error: string
  days: number
}>()

const emit = defineEmits<{
  refresh: []
  'update:days': [days: number]
}>()

const dayOptions = [
  { label: '近 7 天', value: 7 },
  { label: '近 14 天', value: 14 },
  { label: '近 30 天', value: 30 },
]

const failedCount = computed(() => props.stats?.byStatus?.failed ?? 0)
</script>

<style scoped>
.stats-bar {
  background: var(--surface, #ffffff);
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-card, 20px);
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
  padding: 18px 20px 16px;
}

.stats-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.stats-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.stats-title {
  margin: 0;
  font-family: var(--font, 'Noto Sans SC');
  font-size: 15px;
  font-weight: 700;
  color: var(--ink, #4a2b35);
}

.stats-sub {
  font-size: 12px;
  color: var(--faint, #97808a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stats-days {
  width: 116px;
  flex: none;
}

.stats-loading {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.stats-skeleton {
  height: 84px;
  border-radius: var(--r-md, 14px);
  background: linear-gradient(90deg, var(--sakura-pale, #ffe9f0) 25%, #fff 50%, var(--sakura-pale, #ffe9f0) 75%);
  background-size: 200% 100%;
  animation: stats-shimmer 1.4s ease-in-out infinite;
}

@keyframes stats-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

.stats-alert {
  margin: 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px;
  border-radius: var(--r-md, 14px);
  background: var(--ground, #fff6f9);
  border: 1px solid transparent;
  min-width: 0;
}

.stat-accent {
  background: var(--sakura-pale, #ffe9f0);
  border-color: color-mix(in srgb, var(--sakura, #e8628c) 22%, transparent);
}

.stat-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--muted, #63474f);
  white-space: nowrap;
}

.stat-value {
  font-family: var(--font, 'Noto Sans SC');
  font-size: 21px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.stat-accent .stat-value {
  color: var(--sakura-deep, #c93a63);
}

.stat-value-sub {
  font-size: 13px;
  font-weight: 500;
  color: var(--muted, #63474f);
}

.stat-hint {
  font-size: 11px;
  color: var(--faint, #97808a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tier-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.tier-bars {
  display: flex;
  gap: 3px;
  height: 8px;
  flex: 1 1 220px;
  min-width: 160px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--line, #f3dde5);
}

.tier-bar {
  flex-basis: 0;
  min-width: 4px;
  transition: flex-grow var(--dur, 240ms) var(--ease-out, ease);
}

.is-l0 { background: var(--summer, #3b9c80); }
.is-l1 { background: var(--autumn, #b5703c); }
.is-l2 { background: var(--sakura-deep, #c93a63); }

.tier-legend {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
  color: var(--muted, #63474f);
}

.tier-legend li {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}

.tier-legend strong {
  font-variant-numeric: tabular-nums;
  color: var(--ink, #4a2b35);
}

.tier-legend .is-failed {
  color: var(--sakura-deep, #c93a63);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

@media (max-width: 1180px) {
  .stats-grid,
  .stats-loading {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .stats-bar {
    padding: 14px 14px 12px;
    border-radius: var(--r-md, 14px);
  }

  .stats-sub {
    display: none;
  }

  .stats-grid,
  .stats-loading {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .stat-value {
    font-size: 19px;
  }

  .tier-row {
    gap: 10px;
  }

  .tier-legend {
    flex-wrap: wrap;
    gap: 8px 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .stats-skeleton {
    animation: none;
  }

  .tier-bar {
    transition: none;
  }
}
</style>
