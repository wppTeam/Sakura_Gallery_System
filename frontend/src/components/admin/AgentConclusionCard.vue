<template>
  <section class="agent-card" aria-label="Agent 审核意见">
    <header class="agent-head">
      <div class="agent-title-wrap">
        <p class="agent-eyebrow">
          <n-icon :size="13"><SparklesOutline /></n-icon>
          AGENT 审核意见 · 仅作参考
        </p>
        <div class="agent-title-row">
          <span class="agent-tier" :class="`is-${tierKey}`">{{ tierLabel(suggestionTier) }}</span>
          <n-tag size="small" :type="reviewStatusTagType(review.status)" :bordered="false">
            {{ reviewStatusLabel(review.status) }}
          </n-tag>
          <n-tag v-if="review.finalDecision" size="small" type="info" :bordered="false">
            人工终判：{{ decisionLabel(review.finalDecision) }}
          </n-tag>
        </div>
        <p class="agent-suggestion">{{ agentSummary(review) }}</p>
      </div>
      <dl class="agent-metrics">
        <div>
          <dt>延迟</dt>
          <dd>{{ formatLatency(review.latencyMs) }}</dd>
        </div>
        <div>
          <dt>Tokens</dt>
          <dd>{{ formatInteger(review.promptTokens + review.completionTokens) }}</dd>
        </div>
        <div>
          <dt>成本</dt>
          <dd>{{ formatCost(review.costUsd) }}</dd>
        </div>
      </dl>
    </header>

    <n-alert v-if="review.error" type="error" :bordered="false" class="agent-alert">
      <template #header>模型审核失败</template>
      {{ review.error }}
      <p class="agent-alert-hint">该样本需人工补判；失败不会自动放行。</p>
    </n-alert>

    <n-alert v-if="review.rules?.blocked" type="warning" :bordered="false" class="agent-alert">
      <template #header>规则前置硬拦</template>
      命中硬拦规则，已跳过 VLM 快筛，直接进入 L2 强制前审。
    </n-alert>

    <RulesPanel :rules="review.rules" class="agent-layer" />

    <section class="agent-layer layer-prefilter">
      <header class="layer-head">
        <div class="panel-heading">
          <span class="panel-index">②</span>
          <div>
            <h3 class="panel-title">VLM 快筛</h3>
            <p class="panel-sub">qwen3-vl-plus · 结构化风险判断</p>
          </div>
        </div>
        <span v-if="prefilter" class="confidence-chip" :class="confidenceTone">
          置信度 {{ percentText(prefilter.confidence) }}
        </span>
      </header>

      <p v-if="!prefilter" class="panel-note">
        {{ review.rules?.blocked ? '规则硬拦，快筛未执行。' : '本次审核未产生快筛结果。' }}
      </p>

      <template v-else>
        <div v-if="flags.length" class="risk-tags">
          <n-tag
            v-for="flag in flags"
            :key="flag.label"
            size="small"
            :type="flag.tone"
            :bordered="false"
            :title="flag.detail"
          >
            {{ flag.label }}
          </n-tag>
        </div>

        <dl class="check-grid">
          <div>
            <dt>可识别人物</dt>
            <dd :class="prefilter.hasIdentifiablePerson ? 'is-risk' : 'is-ok'">
              <n-icon :size="13">
                <CloseCircleOutline v-if="prefilter.hasIdentifiablePerson" />
                <CheckmarkCircleOutline v-else />
              </n-icon>
              {{ prefilter.hasIdentifiablePerson ? '是' : '否' }}
            </dd>
          </div>
          <div>
            <dt>疑似 AIGC</dt>
            <dd :class="prefilter.likelyAigc ? 'is-warn' : 'is-ok'">
              <n-icon :size="13">
                <AlertCircleOutline v-if="prefilter.likelyAigc" />
                <CheckmarkCircleOutline v-else />
              </n-icon>
              {{ prefilter.likelyAigc ? '是' : '否' }}
            </dd>
          </div>
          <div>
            <dt>敏感内容</dt>
            <dd :class="prefilter.sensitiveContent ? 'is-risk' : 'is-ok'">
              <n-icon :size="13">
                <CloseCircleOutline v-if="prefilter.sensitiveContent" />
                <CheckmarkCircleOutline v-else />
              </n-icon>
              {{ prefilter.sensitiveContent ? '是' : '否' }}
            </dd>
          </div>
          <div>
            <dt>版权风险</dt>
            <dd :class="copyrightTone">
              {{ copyrightLabel }}
            </dd>
          </div>
          <div>
            <dt>画面水印</dt>
            <dd :class="prefilter.watermark ? 'is-warn' : 'is-ok'">
              <n-icon :size="13">
                <AlertCircleOutline v-if="prefilter.watermark" />
                <CheckmarkCircleOutline v-else />
              </n-icon>
              {{ prefilter.watermark ? '是' : '否' }}
            </dd>
          </div>
          <div>
            <dt>图内文字</dt>
            <dd :class="prefilter.textInImage ? 'is-warn' : 'is-ok'">
              {{ prefilter.textInImage ? '是' : '否' }}
            </dd>
          </div>
        </dl>

        <p class="suggest-line">
          建议分级
          <n-tag size="tiny" :type="tierTagType(prefilter.suggestedTier)" :bordered="false">
            {{ tierShort(prefilter.suggestedTier) }}
          </n-tag>
          <span class="suggest-desc">{{ prefilter.suggestedTier ? TIER_DESCRIPTIONS[prefilter.suggestedTier] : '未给出' }}</span>
        </p>

        <blockquote v-if="prefilter.reason" class="reason-quote">{{ prefilter.reason }}</blockquote>
      </template>
    </section>

    <section class="agent-layer layer-escalation">
      <header class="layer-head">
        <div class="panel-heading">
          <span class="panel-index">③</span>
          <div>
            <h3 class="panel-title">复核推理</h3>
            <p class="panel-sub">deepseek-v4.1-flash · 仅难例触发</p>
          </div>
        </div>
        <n-tag v-if="escalation" size="small" :type="decisionTagType(escalation.decision)" :bordered="false">
          {{ decisionLabel(escalation.decision) }}
        </n-tag>
      </header>

      <p v-if="!escalation" class="panel-note">快筛置信度足够高，未触发复核推理。</p>

      <template v-else>
        <dl class="escalation-facts">
          <div>
            <dt>复核分级</dt>
            <dd>
              <n-tag size="tiny" :type="tierTagType(escalation.finalTier)" :bordered="false">
                {{ tierLabel(escalation.finalTier) }}
              </n-tag>
            </dd>
          </div>
          <div>
            <dt>置信度</dt>
            <dd>{{ percentText(escalation.confidence) }}</dd>
          </div>
          <div>
            <dt>需人工确认</dt>
            <dd :class="escalation.needsHuman ? 'is-risk' : 'is-ok'">{{ escalation.needsHuman ? '是' : '否' }}</dd>
          </div>
        </dl>

        <div v-if="escalation.riskPoints.length" class="risk-points">
          <p class="risk-points-title">风险点</p>
          <ul>
            <li v-for="(point, index) in escalation.riskPoints" :key="index">{{ point }}</li>
          </ul>
        </div>

        <blockquote v-if="escalation.reason" class="reason-quote">{{ escalation.reason }}</blockquote>
      </template>
    </section>

    <footer class="agent-foot">
      <span class="foot-model mono">{{ review.provider || 'provider' }} / {{ review.modelId || '未记录模型' }}</span>
      <span class="foot-time">创建 {{ formatDateTime(review.createdAt) }}</span>
      <span class="foot-warn">Agent 结论不能替代人工终判</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  AlertCircleOutline,
  CheckmarkCircleOutline,
  CloseCircleOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import type { ModerationReview } from '../../api/moderation'
import RulesPanel from './RulesPanel.vue'
import {
  TIER_DESCRIPTIONS,
  agentSummary,
  decisionLabel,
  decisionTagType,
  formatCost,
  formatDateTime,
  formatInteger,
  formatLatency,
  percentText,
  reviewStatusLabel,
  reviewStatusTagType,
  riskFlags,
  tierLabel,
  tierShort,
  tierTagType,
} from './reviewDisplay'

const props = defineProps<{
  review: ModerationReview
}>()

const suggestionTier = computed(
  () => props.review.escalation?.finalTier || props.review.finalTier || props.review.suggestedTier || props.review.tier,
)

const tierKey = computed(() => suggestionTier.value?.toLowerCase() || 'none')

const prefilter = computed(() => props.review.prefilter)
const escalation = computed(() => props.review.escalation)
const flags = computed(() => riskFlags(props.review))

const copyrightLabel = computed(() => {
  const risk = prefilter.value?.copyrightRisk || 'unknown'
  if (risk === 'high') return '高'
  if (risk === 'medium') return '中'
  if (risk === 'low') return '低'
  return '未知'
})

const copyrightTone = computed(() => {
  const risk = prefilter.value?.copyrightRisk || 'unknown'
  if (risk === 'high') return 'is-risk'
  if (risk === 'medium') return 'is-warn'
  if (risk === 'low') return 'is-ok'
  return 'is-muted'
})

const confidenceTone = computed(() => {
  const confidence = prefilter.value?.confidence
  if (typeof confidence !== 'number') return 'is-muted'
  if (confidence >= 0.85) return 'is-ok'
  if (confidence >= 0.6) return 'is-warn'
  return 'is-risk'
})
</script>

<style scoped>
.agent-card {
  border: 1px solid var(--sakura, rgba(232, 98, 140, 0.35));
  border-radius: var(--r-card, 20px);
  background: linear-gradient(180deg, var(--sakura-wash, #fffafc), var(--surface, #fff) 160px);
  padding: 16px;
}

.agent-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
}

.agent-title-wrap {
  min-width: 0;
}

.agent-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--sakura-deep, #c93a63);
}

.agent-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-tier {
  font-family: var(--font, 'Noto Sans SC');
  font-size: 20px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--ink, #4a2b35);
}

.agent-tier.is-l0 { color: var(--summer, #3b9c80); }
.agent-tier.is-l1 { color: var(--autumn, #b5703c); }
.agent-tier.is-l2 { color: var(--sakura-deep, #c93a63); }

.agent-suggestion {
  margin: 5px 0 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--muted, #63474f);
}

.agent-metrics {
  display: flex;
  gap: 14px;
  margin: 0;
  flex: none;
}

.agent-metrics > div {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
}

.agent-metrics dt {
  font-size: 10.5px;
  color: var(--faint, #97808a);
}

.agent-metrics dd {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
}

.agent-alert {
  margin: 0 0 10px;
}

.agent-alert-hint {
  margin: 4px 0 0;
  font-size: 12px;
  opacity: 0.85;
}

.agent-layer {
  margin-top: 10px;
}

.layer-prefilter,
.layer-escalation {
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-md, 14px);
  background: var(--surface, #fff);
  padding: 13px 14px;
}

.layer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.panel-heading {
  display: flex;
  gap: 8px;
  min-width: 0;
}

.panel-index {
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--sakura-deep, #c93a63);
  background: var(--sakura-pale, #ffe9f0);
  font-variant-numeric: tabular-nums;
}

.panel-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--ink, #4a2b35);
  line-height: 1.4;
}

.panel-sub {
  margin: 1px 0 0;
  font-size: 11px;
  color: var(--faint, #97808a);
}

.panel-note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--faint, #97808a);
}

.confidence-chip {
  flex: none;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  background: var(--ground, #fff6f9);
  color: var(--muted, #63474f);
}

.confidence-chip.is-ok {
  color: var(--summer, #3b9c80);
  background: var(--summer-pale, #d4f0e4);
}
.confidence-chip.is-warn {
  color: var(--autumn, #b5703c);
  background: var(--autumn-pale, #ffdfd6);
}
.confidence-chip.is-risk {
  color: var(--sakura-deep, #c93a63);
  background: var(--sakura-pale, #ffe9f0);
}

.risk-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 11px;
}

.check-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px 14px;
  margin: 12px 0 0;
}

.check-grid > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
  padding-bottom: 5px;
  border-bottom: 1px dashed var(--line, #f3dde5);
}

.check-grid dt {
  font-size: 11.5px;
  color: var(--faint, #97808a);
  white-space: nowrap;
}

.check-grid dd {
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.check-grid dd.is-risk { color: var(--sakura-deep, #c93a63); }
.check-grid dd.is-warn { color: var(--autumn, #b5703c); }
.check-grid dd.is-ok { color: var(--summer, #3b9c80); }
.check-grid dd.is-muted { color: var(--faint, #97808a); }

.suggest-line {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--muted, #63474f);
}

.suggest-desc {
  font-size: 11.5px;
  color: var(--faint, #97808a);
}

.reason-quote {
  margin: 11px 0 0;
  padding: 9px 12px;
  border-left: 3px solid var(--sakura, #e8628c);
  border-radius: 0 var(--r-sm, 10px) var(--r-sm, 10px) 0;
  background: var(--ground, #fff6f9);
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--muted, #63474f);
  word-break: break-word;
}

.escalation-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  margin: 11px 0 0;
}

.escalation-facts > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.escalation-facts dt {
  font-size: 10.5px;
  color: var(--faint, #97808a);
}

.escalation-facts dd {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.escalation-facts dd.is-risk { color: var(--sakura-deep, #c93a63); }
.escalation-facts dd.is-ok { color: var(--summer, #3b9c80); }

.risk-points {
  margin-top: 11px;
}

.risk-points-title {
  margin: 0 0 5px;
  font-size: 11px;
  color: var(--faint, #97808a);
}

.risk-points ul {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--muted, #63474f);
}

.agent-foot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin-top: 12px;
  padding-top: 9px;
  border-top: 1px dashed var(--line, #f3dde5);
  font-size: 11px;
  color: var(--faint, #97808a);
}

.foot-model {
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  word-break: break-all;
}

.foot-warn {
  margin-left: auto;
  color: var(--sakura-deep, #c93a63);
}

@media (max-width: 900px) {
  .check-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .agent-card {
    padding: 13px;
    border-radius: var(--r-md, 14px);
  }

  .agent-head {
    flex-direction: column;
    gap: 10px;
  }

  .agent-metrics {
    width: 100%;
    justify-content: space-between;
  }

  .agent-metrics > div {
    align-items: flex-start;
  }

  .check-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 7px 12px;
  }

  .agent-foot {
    gap: 3px 8px;
  }

  .foot-warn {
    margin-left: 0;
  }
}
</style>
