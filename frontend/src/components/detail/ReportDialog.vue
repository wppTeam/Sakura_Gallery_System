<template>
  <n-modal
    :show="show"
    preset="card"
    :style="{ width: 'min(92vw, 520px)' }"
    :bordered="false"
    :mask-closable="!submitting"
    :close-on-esc="!submitting"
    :closable="!submitting"
    :auto-focus="true"
    @update:show="onUpdateShow"
    @after-enter="onAfterEnter"
    @after-leave="onAfterLeave"
  >
    <template #header>
      <div class="report-head">
        <span class="report-seal" aria-hidden="true">!</span>
        <div>
          <h2 class="report-title">举报 / 侵权投诉</h2>
          <p class="report-sub">
            针对{{ targetType === 'photo' ? '作品' : '专题' }}
            <strong>{{ targetTitle || '当前内容' }}</strong>
            提交投诉，平台按「通知—删除」规则处理。
          </p>
        </div>
      </div>
    </template>

    <!-- 已提交 -->
    <div v-if="created" class="report-success" role="status">
      <n-icon :component="CheckmarkCircleOutline" :size="40" class="success-icon" />
      <h3 class="success-title">已提交，3 个工作日内受理</h3>
      <p class="success-text">我们已收到你的投诉，会尽快核实处理。如需补充权属证明，可通过下方邮箱联系。</p>
      <p class="success-code">
        投诉编号 <span class="mono">{{ created.id || '—' }}</span>
      </p>
      <div class="report-actions">
        <n-button type="primary" round @click="close">知道了</n-button>
      </div>
    </div>

    <!-- 表单 -->
    <form v-else class="report-form" novalidate @submit.prevent="submit">
      <p class="report-hint">
        请如实填写。投诉信息仅用于本次处理、不会公开展示；恶意投诉将承担相应责任。
        详细规则见
        <router-link to="/terms" @click="close">服务条款</router-link>。
      </p>

      <div class="report-field">
        <label id="report-reason-label" class="field-label" for="report-reason">
          投诉原因<span class="required" aria-hidden="true">*</span>
        </label>
        <n-select
          id="report-reason"
          v-model:value="reasonCode"
          :options="reasonOptions"
          placeholder="请选择投诉原因"
          :disabled="submitting"
          aria-labelledby="report-reason-label"
          data-test="report-reason"
        />
        <p v-if="reasonHint" class="field-hint">{{ reasonHint }}</p>
      </div>

      <div class="report-field">
        <label class="field-label" for="report-reason-text">
          问题说明<span class="required" aria-hidden="true">*</span>
        </label>
        <n-input
          v-model:value="reasonText"
          type="textarea"
          :rows="4"
          :maxlength="2000"
          show-count
          :disabled="submitting"
          placeholder="请描述问题，建议包含：涉及的权利、作品出处或授权情况、你希望的处理方式（不少于 5 字）"
          :input-props="{ id: 'report-reason-text', 'aria-label': '问题说明' }"
        />
        <p v-if="textError" class="field-error" role="alert">{{ textError }}</p>
      </div>

      <div class="report-field">
        <label class="field-label" for="report-contact">联系方式<span class="optional">（可选）</span></label>
        <n-input
          v-model:value="contact"
          :maxlength="120"
          :disabled="submitting"
          placeholder="邮箱或手机号，便于回复处理结果"
          :input-props="{ id: 'report-contact', 'aria-label': '联系方式（可选）' }"
        />
      </div>

      <n-alert v-if="errorText" type="error" :bordered="false" class="report-error" role="alert">
        {{ errorText }}
      </n-alert>

      <p class="report-legal">
        提交即表示你确认以上信息真实。如需撤回或补充材料，请联系
        <a href="mailto:hello@buct-sakura.cn">hello@buct-sakura.cn</a>。
      </p>

      <div class="report-actions">
        <n-button quaternary :disabled="submitting" @click="close">取消</n-button>
        <n-button
          type="primary"
          attr-type="submit"
          round
          :loading="submitting"
          :disabled="!canSubmit"
          data-test="report-submit"
        >
          {{ submitting ? '提交中…' : '提交投诉' }}
        </n-button>
      </div>
    </form>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { NAlert, NButton, NIcon, NInput, NModal, NSelect } from 'naive-ui'
import { CheckmarkCircleOutline } from '@vicons/ionicons5'
import {
  REPORT_REASON_OPTIONS,
  createReport,
  type ReportCreated,
  type ReportReasonCode,
  type ReportTargetType,
} from '../../api/reports'

const props = defineProps<{
  show: boolean
  targetType: ReportTargetType
  targetId: string
  targetTitle?: string
}>()

const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const reasonCode = ref<ReportReasonCode | null>(null)
const reasonText = ref('')
const contact = ref('')
const submitting = ref(false)
const errorText = ref('')
const created = ref<ReportCreated | null>(null)
const lastFocused = ref<HTMLElement | null>(null)

const reasonOptions = REPORT_REASON_OPTIONS.map((item) => ({ label: item.label, value: item.code }))

const reasonHint = computed(() => {
  if (!reasonCode.value) return ''
  return REPORT_REASON_OPTIONS.find((item) => item.code === reasonCode.value)?.hint || ''
})

const textLength = computed(() => reasonText.value.trim().length)
const textError = computed(() => {
  if (!reasonText.value) return ''
  if (textLength.value < 5) return '问题说明至少 5 个字，请补充具体信息。'
  return ''
})
const canSubmit = computed(() => {
  return (
    !!reasonCode.value &&
    textLength.value >= 5 &&
    textLength.value <= 2000 &&
    !submitting.value
  )
})

function resetForm() {
  reasonCode.value = null
  reasonText.value = ''
  contact.value = ''
  errorText.value = ''
  created.value = null
  submitting.value = false
}

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      lastFocused.value = (document.activeElement as HTMLElement | null) ?? null
      resetForm()
    }
  },
)

function onUpdateShow(value: boolean) {
  if (!value) emit('update:show', false)
}

function onAfterEnter() {
  void nextTick(() => {
    const el = document.getElementById('report-reason-text') as HTMLTextAreaElement | null
    el?.focus()
  })
}

function onAfterLeave() {
  // 焦点归位：把焦点还给触发按钮，键盘用户不会丢位置
  const target = lastFocused.value
  lastFocused.value = null
  if (target && document.contains(target)) target.focus()
}

function close() {
  emit('update:show', false)
}

interface ApiLikeError {
  response?: { status?: number; data?: { detail?: unknown } }
  message?: string
}

function extractDetail(error: ApiLikeError): string {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : String(item)))
      .filter(Boolean)
      .join('；')
  }
  return ''
}

function describeError(error: unknown): string {
  const err = error as ApiLikeError
  const status = err?.response?.status
  const detail = extractDetail(err)
  if (status === 429) {
    return detail || '你刚刚已经提交过这条投诉，我们正在处理，请勿重复提交。'
  }
  if (status === 404) {
    return detail || '该内容不存在或已下架，无法提交投诉。'
  }
  if (status === 422) {
    return detail || '提交内容不符合要求，请检查投诉原因与问题说明后重试。'
  }
  return detail || '网络异常，投诉未提交成功，请稍后重试。'
}

async function submit() {
  if (submitting.value) return
  if (!reasonCode.value) {
    errorText.value = '请选择投诉原因。'
    return
  }
  if (textLength.value < 5) {
    errorText.value = '问题说明至少 5 个字，请补充具体信息。'
    return
  }
  errorText.value = ''
  submitting.value = true
  try {
    created.value = await createReport({
      targetType: props.targetType,
      targetId: props.targetId,
      reasonCode: reasonCode.value,
      reasonText: reasonText.value.trim(),
      contact: contact.value,
    })
  } catch (error) {
    errorText.value = describeError(error)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.report-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.report-seal {
  flex: none;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--sakura-pale);
  border: 1px solid var(--sakura-mist);
  color: var(--sakura-deep);
  font-family: var(--display);
  font-size: 20px;
  line-height: 1;
}

.report-title {
  margin: 0;
  font-family: var(--font);
  font-size: 20px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--ink);
}

.report-sub {
  margin: 4px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--muted);
}

.report-sub strong {
  color: var(--ink-soft);
  font-weight: 600;
}

.report-form,
.report-success {
  display: grid;
  gap: 14px;
}

.report-hint {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: var(--sakura-wash);
  color: var(--ink-soft);
  font-size: 12.5px;
  line-height: 1.7;
}

.report-hint a {
  color: var(--sakura-deep);
}

.report-field {
  display: grid;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-soft);
}

.required {
  color: var(--sakura-deep);
  margin-left: 2px;
}

.optional {
  color: var(--faint);
  font-weight: 400;
  font-size: 12px;
}

.field-hint {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}

.field-error {
  margin: 0;
  font-size: 12px;
  color: #b42342;
}

.report-error {
  margin: 0;
}

.report-legal {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--faint);
}

.report-legal a {
  color: var(--sakura-deep);
}

.report-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 2px;
}

.report-success {
  justify-items: center;
  text-align: center;
  padding: 8px 4px 2px;
}

.success-icon {
  color: var(--summer);
}

.success-title {
  margin: 0;
  font-family: var(--display);
  font-size: 24px;
  font-weight: 400;
  letter-spacing: 0.02em;
  color: var(--ink);
}

.success-text {
  margin: 0;
  max-width: 24em;
  font-size: 13px;
  line-height: 1.8;
  color: var(--muted);
}

.success-code {
  margin: 0;
  font-size: 12.5px;
  color: var(--faint);
}

.success-code .mono {
  color: var(--ink-soft);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.report-success .report-actions {
  padding-top: 6px;
}

@media (max-width: 560px) {
  .report-head {
    gap: 10px;
  }

  .report-actions {
    flex-direction: column-reverse;
  }

  .report-actions :deep(.n-button) {
    width: 100%;
  }
}
</style>
