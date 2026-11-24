<script setup lang="ts">
import { computed, ref } from 'vue'
import { NIcon } from 'naive-ui'
import {
  ChevronDownOutline,
  ChevronUpOutline,
  SparklesOutline,
  TimerOutline,
  GitBranchOutline,
} from '@vicons/ionicons5'
import type { AgentSearchResult, SearchStep } from '../../api/search'

const props = defineProps<{ result: AgentSearchResult }>()

const expanded = ref(false)

const TOOL_LABELS: Record<string, string> = {
  planner: '意图解析',
  lexical_search: '关键词检索',
  lexical_search_relaxed: '放宽关键词检索',
  vector_search: '语义检索',
  facets: '分面统计',
  explainer: '生成解释',
  suggest: '生成联想词',
  keyword_search: '关键词检索',
  search: '检索作品',
  filter: '条件过滤',
  rerank: '结果重排',
  clarify: '澄清追问',
}

const MODE_LABELS: Record<string, string> = {
  agent: 'Agent 智能检索',
  fast: '快速检索',
  keyword: '关键词检索',
  vector: '语义检索',
  hybrid: '混合检索',
  lexical: '关键词检索',
}

function toolLabel(step: SearchStep): string {
  return TOOL_LABELS[step.tool] || step.tool
}

function statusTone(step: SearchStep): 'ok' | 'warn' | 'muted' {
  const status = step.status.toLowerCase()
  if (status.startsWith('skipped')) return 'muted'
  if (status === 'degraded' || status === 'error' || status === 'timeout' || status === 'failed') return 'warn'
  return 'ok'
}

function statusText(step: SearchStep): string {
  const status = step.status.toLowerCase()
  if (status.startsWith('skipped')) {
    const reason = status.split(':')[1]
    return reason ? `跳过（${reason}）` : '跳过'
  }
  if (status === 'ok' || status === 'success') return '完成'
  if (status === 'degraded') return '降级'
  if (status === 'timeout') return '超时'
  if (status === 'error' || status === 'failed') return '失败'
  return status
}

function argsChips(step: SearchStep): string[] {
  const chips: string[] = []
  for (const [key, value] of Object.entries(step.args || {})) {
    if (value === null || value === undefined || typeof value === 'object') continue
    const text = String(value)
    if (!text) continue
    chips.push(`${key}=${text.length > 24 ? `${text.slice(0, 24)}…` : text}`)
    if (chips.length >= 4) break
  }
  return chips
}

const modeLabel = computed(() => MODE_LABELS[props.result.searchMode] || props.result.searchMode || '检索')
const stepCount = computed(() => props.result.steps.length)
const summary = computed(() => {
  const seconds = (props.result.queryTimeMs / 1000).toFixed(1)
  const short = props.result.searchMode === 'agent' ? 'Agent 检索' : modeLabel.value
  if (stepCount.value === 0) return `${short} · ${seconds}s`
  return `${short} · ${seconds}s · ${stepCount.value} 步`
})
</script>

<template>
  <section class="agent-process" aria-label="Agent 检索过程">
    <button
      type="button"
      class="agent-toggle"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <span class="agent-toggle__lead">
        <n-icon :component="SparklesOutline" :size="15" />
        <span class="agent-toggle__title">Agent 检索过程</span>
        <span class="agent-toggle__summary">{{ summary }}</span>
      </span>
      <n-icon :component="expanded ? ChevronUpOutline : ChevronDownOutline" :size="16" />
    </button>

    <p v-if="result.explanation" class="agent-explain">{{ result.explanation }}</p>

    <div v-if="expanded" class="agent-detail">
      <div v-if="result.intent.keywords.length || Object.keys(result.intent.filters).length" class="agent-intent">
        <span class="agent-intent__label">理解到的意图</span>
        <div class="agent-intent__values">
          <span v-for="keyword in result.intent.keywords" :key="`kw-${keyword}`" class="agent-keyword">
            {{ keyword }}
          </span>
          <span
            v-for="(value, key) in result.intent.filters"
            :key="`filter-${key}`"
            class="agent-filter"
          >
            {{ key }}：{{ value }}
          </span>
        </div>
      </div>

      <ol v-if="result.steps.length" class="agent-steps">
        <li v-for="(step, index) in result.steps" :key="`${step.tool}-${index}`" class="agent-step">
          <span class="agent-step__dot" :class="`is-${statusTone(step)}`" />
          <div class="agent-step__body">
            <div class="agent-step__head">
              <span class="agent-step__name">
                <span class="agent-step__index">{{ index + 1 }}</span>
                {{ toolLabel(step) }}
                <code v-if="toolLabel(step) !== step.tool" class="agent-step__code">{{ step.tool }}</code>
              </span>
              <span class="agent-step__status" :class="`is-${statusTone(step)}`">{{ statusText(step) }}</span>
            </div>
            <div class="agent-step__meta">
              <span v-if="step.resultCount !== null">
                <n-icon :component="GitBranchOutline" :size="12" />
                {{ step.resultCount }} 条
              </span>
              <span v-if="step.latencyMs !== null">
                <n-icon :component="TimerOutline" :size="12" />
                {{ Math.round(step.latencyMs) }} ms
              </span>
            </div>
            <div v-if="argsChips(step).length" class="agent-step__args">
              <code v-for="chip in argsChips(step)" :key="chip">{{ chip }}</code>
            </div>
          </div>
        </li>
      </ol>
      <p v-else class="agent-detail__hint">本次检索没有返回可展示的执行步骤。</p>

      <div v-if="result.traceId || result.indexVersion" class="agent-meta">
        <span v-if="result.traceId">trace：{{ result.traceId }}</span>
        <span v-if="result.indexVersion">索引：{{ result.indexVersion }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.agent-process {
  margin: 16px 0 0;
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-card, 20px);
  box-shadow: 0 2px 10px rgba(201, 58, 99, 0.04);
  overflow: hidden;
}

.agent-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 13px 18px;
  border: 0;
  background: transparent;
  color: var(--ink, #4a2b35);
  cursor: pointer;
  text-align: left;
}

.agent-toggle:hover {
  background: var(--sakura-mist, #fff2f7);
}

.agent-toggle__lead {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--sakura-deep, #c93a63);
}

.agent-toggle__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  white-space: nowrap;
}

.agent-toggle__summary {
  font-size: 12px;
  color: var(--faint, #947881);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-explain {
  margin: 0;
  padding: 0 18px 14px;
  color: var(--ink-soft, #563842);
  font-size: 14px;
  line-height: 1.75;
  max-width: var(--measure, 24em);
}

.agent-detail {
  padding: 2px 18px 16px;
  border-top: 1px dashed var(--line, #f3dde5);
}

.agent-intent {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 12px 0 4px;
}

.agent-intent__label {
  font-size: 12px;
  color: var(--faint, #947881);
}

.agent-intent__values {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.agent-keyword {
  padding: 2px 9px;
  border-radius: var(--r-pill, 999px);
  background: var(--sakura-pale, #ffe9f0);
  color: var(--sakura-deep, #c93a63);
  font-size: 12px;
}

.agent-filter {
  padding: 2px 9px;
  border-radius: var(--r-pill, 999px);
  border: 1px solid var(--line, #f3dde5);
  color: var(--muted, #63474f);
  font-size: 12px;
}

.agent-steps {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-step {
  display: flex;
  gap: 10px;
  padding: 9px 0;
}

.agent-step + .agent-step {
  border-top: 1px dashed var(--line, #f3dde5);
}

.agent-step__dot {
  flex: none;
  width: 8px;
  height: 8px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--line-strong, #eccdd8);
}

.agent-step__dot.is-ok {
  background: var(--summer, #3b9c80);
}

.agent-step__dot.is-warn {
  background: var(--autumn, #b5703c);
}

.agent-step__dot.is-muted {
  background: var(--line-strong, #eccdd8);
}

.agent-step__body {
  min-width: 0;
  flex: 1;
}

.agent-step__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.agent-step__name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--ink, #4a2b35);
}

.agent-step__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 17px;
  height: 17px;
  border-radius: 50%;
  background: var(--sakura-mist, #fff2f7);
  color: var(--sakura-deep, #c93a63);
  font-size: 10px;
}

.agent-step__code {
  font-size: 11px;
  color: var(--faint, #947881);
  background: var(--surface-warm, #fff9fb);
  border: 1px solid var(--line, #f3dde5);
  border-radius: 5px;
  padding: 0 5px;
}

.agent-step__status {
  flex: none;
  font-size: 11px;
  color: var(--summer, #3b9c80);
}

.agent-step__status.is-warn {
  color: var(--autumn, #b5703c);
}

.agent-step__status.is-muted {
  color: var(--faint, #947881);
}

.agent-step__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 3px;
  color: var(--muted, #63474f);
  font-size: 11px;
}

.agent-step__meta span {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.agent-step__args {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 5px;
}

.agent-step__args code {
  padding: 1px 6px;
  border-radius: 5px;
  background: var(--surface-warm, #fff9fb);
  border: 1px solid var(--line, #f3dde5);
  color: var(--muted, #63474f);
  font-size: 11px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-detail__hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--faint, #947881);
}

.agent-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--line, #f3dde5);
  font-size: 11px;
  color: var(--faint, #947881);
  word-break: break-all;
}

@media (max-width: 640px) {
  .agent-toggle,
  .agent-explain,
  .agent-detail {
    padding-left: 14px;
    padding-right: 14px;
  }

  .agent-toggle__summary {
    display: none;
  }

  .agent-step__head {
    flex-wrap: wrap;
  }
}
</style>
