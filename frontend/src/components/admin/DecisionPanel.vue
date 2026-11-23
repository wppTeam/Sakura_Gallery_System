<template>
  <section class="decision-panel" aria-label="人工终判">
    <header class="decision-head">
      <div class="decision-heading">
        <span class="decision-badge"><n-icon :size="13"><PersonCircleOutline /></n-icon>人工操作</span>
        <h3 class="decision-title">人工终判</h3>
        <p class="decision-sub">Agent 只给建议，发布与否由人决定</p>
      </div>
      <span v-if="agentHint" class="decision-agent-hint">Agent 建议：{{ agentHint }}</span>
    </header>

    <template v-if="finalized">
      <div class="finalized-box">
        <div class="finalized-row">
          <n-tag size="large" :type="decisionTagType(review.finalDecision)" :bordered="false">
            人工已{{ decisionLabel(review.finalDecision) }}
          </n-tag>
          <span v-if="review.finalTier" class="finalized-tier">终判分级 {{ tierLabel(review.finalTier) }}</span>
        </div>
        <p v-if="decisionReason" class="finalized-reason">{{ decisionReason }}</p>
        <p class="finalized-meta">
          {{ review.reviewerId ? `操作人 ${review.reviewerId.slice(0, 8)}` : '操作人未记录' }}
          <span class="meta-dot">·</span>
          {{ formatDateTime(review.reviewedAt) || '时间未记录' }}
        </p>
        <p class="finalized-hint">该照片已有终判，不能重复决策；如判断有误请联系超级管理员重新入队。</p>
      </div>
    </template>

    <template v-else>
      <div class="decision-field">
        <span class="field-label">终判结果</span>
        <n-radio-group v-model:value="decision" class="decision-radios" name="moderation-decision">
          <n-radio-button value="approve">通过发布</n-radio-button>
          <n-radio-button value="reject">驳回</n-radio-button>
          <n-radio-button value="hold">挂起待补</n-radio-button>
        </n-radio-group>
        <p class="field-hint">{{ decisionHint }}</p>
      </div>

      <div v-if="decision !== 'reject'" class="decision-field">
        <span class="field-label">终判分级</span>
        <n-select
          v-model:value="finalTier"
          :options="tierOptions"
          size="small"
          class="decision-select"
          :consistent-menu-width="false"
        />
        <p class="field-hint">通过后按该等级进入发布/精选流程。</p>
      </div>

      <div class="decision-field">
        <span class="field-label">
          终判理由
          <em class="field-required" :class="{ 'is-required': decision === 'reject' }">
            {{ decision === 'reject' ? '驳回必填' : '选填' }}
          </em>
        </span>
        <n-input
          v-model:value="reason"
          type="textarea"
          :rows="3"
          maxlength="1000"
          show-count
          placeholder="写清判断依据，会随通知发给上传者（最多 1000 字）"
          class="decision-reason"
          :status="reasonError ? 'error' : undefined"
          @update:value="reasonError = false"
        />
        <p v-if="reasonError" class="field-error">驳回时请填写理由，让上传者知道如何修改。</p>
        <div class="reason-templates">
          <span class="templates-label">常用理由</span>
          <button
            v-for="template in reasonTemplates"
            :key="template"
            type="button"
            class="template-chip"
            @click="useTemplate(template)"
          >
            {{ template }}
          </button>
        </div>
      </div>

      <div class="decision-actions">
        <n-button
          type="primary"
          :loading="deciding"
          :disabled="deciding"
          @click="confirmSubmit"
        >
          {{ deciding ? '提交中…' : '提交人工终判' }}
        </n-button>
        <n-button quaternary :disabled="deciding" @click="resetForm">重置</n-button>
        <span class="action-note">通过/驳回会给上传者发送通知</span>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDialog } from 'naive-ui'
import { PersonCircleOutline } from '@vicons/ionicons5'
import type {
  DecisionPayload,
  ModerationDecision,
  ModerationReview,
  ModerationTier,
} from '../../api/moderation'
import {
  TIER_DESCRIPTIONS,
  decisionLabel,
  decisionTagType,
  formatDateTime,
  tierLabel,
} from './reviewDisplay'

const props = defineProps<{
  review: ModerationReview
  deciding: boolean
}>()

const emit = defineEmits<{
  submit: [payload: DecisionPayload]
}>()

const dialog = useDialog()

const decision = ref<ModerationDecision>('approve')
const finalTier = ref<ModerationTier>('L1')
const reason = ref('')
const reasonError = ref(false)

const finalized = computed(() => props.review.finalDecision === 'approve' || props.review.finalDecision === 'reject')

const agentHint = computed(() => {
  const review = props.review
  const tier = review.escalation?.finalTier || review.finalTier || review.suggestedTier || review.tier
  const agentDecision = review.escalation?.decision
  const parts: string[] = []
  if (tier) parts.push(tier)
  if (agentDecision) parts.push(decisionLabel(agentDecision))
  else if (review.status === 'failed') parts.push('审核失败')
  return parts.join(' · ')
})

const decisionHint = computed(() => {
  if (decision.value === 'approve') {
    return props.review.photo?.status === 'approved'
      ? '该作品当前已发布，提交通过不会重复发布。'
      : '通过后照片立即发布，并进入公开检索。'
  }
  if (decision.value === 'reject') return '驳回后照片不会公开，上传者可修改后重新投稿。'
  return '挂起后照片保持待审，可稍后补充材料再终判。'
})

const tierOptions = (['L0', 'L1', 'L2'] as ModerationTier[]).map((tier) => ({
  label: `${tierLabel(tier)} · ${TIER_DESCRIPTIONS[tier]}`,
  value: tier,
}))

const reasonTemplates = computed(() => {
  if (decision.value === 'reject') {
    return [
      '涉及可识别人物，缺少肖像授权',
      '疑似侵犯版权或素材来源不明',
      '含违规、敏感内容',
      '需补充 AIGC 标识说明后再发布',
    ]
  }
  if (decision.value === 'hold') {
    return ['版权风险待确认，暂缓发布', '需补充作品说明或授权信息', '等待作者回应']
  }
  return ['内容合规，同意发布', '原创摄影，无肖像与版权风险', 'AIGC 标识已补齐', '模板字体风险已明示']
})

const decisionReason = computed(() => {
  const raw = props.review.raw || {}
  for (const key of ['reason', 'final_reason', 'decision_reason', 'review_reason']) {
    const value = raw[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
})

function resetForm() {
  const suggested = props.review.suggestedTier || props.review.finalTier || props.review.tier
  decision.value = suggested === 'L2' ? 'hold' : 'approve'
  finalTier.value = suggested || 'L1'
  reason.value = ''
  reasonError.value = false
}

function useTemplate(template: string) {
  reason.value = reason.value.trim() ? `${reason.value.trim()}；${template}` : template
  reasonError.value = false
}

function confirmSubmit() {
  if (props.deciding) return
  if (decision.value === 'reject' && !reason.value.trim()) {
    reasonError.value = true
    return
  }
  const payload: DecisionPayload = {
    decision: decision.value,
    reason: reason.value.trim() || undefined,
    finalTier: decision.value === 'reject' ? undefined : finalTier.value,
  }
  dialog.warning({
    title: `确认${decisionLabel(payload.decision)}该作品？`,
    content:
      payload.decision === 'approve'
        ? '通过后作品将对外公开，并给上传者发送通知。终判提交后不可重复决策。'
        : payload.decision === 'reject'
          ? '驳回后作品不会公开，理由会随通知发给上传者。终判提交后不可重复决策。'
          : '挂起后作品保持待审状态，可稍后再次终判。',
    positiveText: `确认${decisionLabel(payload.decision)}`,
    negativeText: '再想想',
    onPositiveClick: () => {
      emit('submit', payload)
    },
  })
}

watch(
  () => props.review.photoId,
  () => resetForm(),
  { immediate: true },
)
</script>

<style scoped>
.decision-panel {
  border: 2px solid var(--sakura, #e8628c);
  border-radius: var(--r-card, 20px);
  background: var(--surface, #fff);
  box-shadow: var(--shadow-lift, 0 10px 30px rgba(201, 58, 99, 0.12));
  padding: 16px;
}

.decision-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.decision-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--on-accent, #fff);
  background: var(--sakura-deep, #c93a63);
}

.decision-title {
  margin: 6px 0 0;
  font-family: var(--font, 'Noto Sans SC');
  font-size: 17px;
  font-weight: 700;
  color: var(--ink, #4a2b35);
}

.decision-sub {
  margin: 2px 0 0;
  font-size: 11.5px;
  color: var(--faint, #97808a);
}

.decision-agent-hint {
  flex: none;
  font-size: 11px;
  color: var(--muted, #63474f);
  background: var(--ground, #fff6f9);
  border-radius: 999px;
  padding: 4px 10px;
  font-variant-numeric: tabular-nums;
}

.decision-field {
  margin-bottom: 13px;
}

.field-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.field-required {
  font-style: normal;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--faint, #97808a);
}

.field-required.is-required {
  color: var(--sakura-deep, #c93a63);
}

.decision-radios {
  display: flex;
  flex-wrap: wrap;
}

.field-hint {
  margin: 5px 0 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--faint, #97808a);
}

.decision-select {
  max-width: 320px;
}

.decision-reason {
  width: 100%;
}

.field-error {
  margin: 4px 0 0;
  font-size: 11.5px;
  color: var(--sakura-deep, #c93a63);
}

.reason-templates {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}

.templates-label {
  font-size: 11px;
  color: var(--faint, #97808a);
}

.template-chip {
  border: 1px solid var(--line, #f3dde5);
  border-radius: 999px;
  background: var(--ground, #fff6f9);
  color: var(--muted, #63474f);
  font-size: 11px;
  line-height: 1.4;
  padding: 3px 9px;
  cursor: pointer;
  font-family: inherit;
  transition: background-color 120ms var(--ease-out, ease), transform 120ms var(--ease-out, ease);
}

.template-chip:hover {
  background: var(--sakura-pale, #ffe9f0);
  color: var(--sakura-deep, #c93a63);
}

.template-chip:active {
  transform: scale(0.97);
}

.template-chip:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 2px;
}

.decision-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 12px;
  border-top: 1px dashed var(--line, #f3dde5);
}

.action-note {
  font-size: 11px;
  color: var(--faint, #97808a);
}

.finalized-box {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.finalized-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.finalized-tier {
  font-size: 12.5px;
  color: var(--muted, #63474f);
}

.finalized-reason {
  margin: 0;
  padding: 9px 12px;
  border-radius: var(--r-sm, 10px);
  background: var(--ground, #fff6f9);
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--muted, #63474f);
  word-break: break-word;
}

.finalized-meta {
  margin: 0;
  font-size: 11.5px;
  color: var(--faint, #97808a);
  font-variant-numeric: tabular-nums;
}

.meta-dot {
  margin: 0 4px;
  opacity: 0.6;
}

.finalized-hint {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--faint, #97808a);
}

@media (max-width: 768px) {
  .decision-panel {
    padding: 13px;
    border-radius: var(--r-md, 14px);
  }

  .decision-head {
    flex-direction: column;
    gap: 6px;
  }

  .decision-agent-hint {
    align-self: flex-start;
  }

  .decision-select {
    max-width: none;
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .template-chip {
    transition: none;
  }
}
</style>
