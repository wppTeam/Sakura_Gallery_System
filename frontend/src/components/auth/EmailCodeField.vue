<template>
  <div class="code-field">
    <div class="code-row">
      <n-input
        :value="modelValue"
        :disabled="disabled"
        size="large"
        maxlength="6"
        inputmode="numeric"
        autocomplete="one-time-code"
        placeholder="6 位邮箱验证码"
        :input-props="{ id, 'aria-label': '邮箱验证码' }"
        :status="error ? 'error' : undefined"
        @update:value="onInput"
        @keydown.enter.prevent="$emit('submit')"
      />
      <n-button
        class="code-send"
        size="large"
        secondary
        :disabled="!canSend"
        :loading="sending"
        @click="send"
      >
        {{ sendLabel }}
      </n-button>
    </div>

    <p v-if="error" class="code-hint is-error">{{ error }}</p>
    <p v-else-if="devCode" class="code-hint is-dev">
      开发模式验证码：<strong>{{ devCode }}</strong>
      <span class="code-hint-note">（EMAIL_ENABLED=false 时仅本地可见）</span>
    </p>
    <p v-else class="code-hint">验证码会发到你的邮箱，10 分钟内有效。</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { sendEmailCode, type EmailCodePurpose } from '../../api/auth'

const props = withDefaults(
  defineProps<{
    modelValue: string
    email: string
    purpose: EmailCodePurpose
    /** 供 <label for> 关联，键盘/读屏可定位 */
    id?: string
    disabled?: boolean
    /** 后端未返回 cooldown 时的默认倒计时秒数 */
    defaultCooldown?: number
  }>(),
  { disabled: false, defaultCooldown: 60 },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  submit: []
}>()

const message = useMessage()
const sending = ref(false)
const countdown = ref(0)
const devCode = ref('')
const error = ref('')
let timer: ReturnType<typeof setInterval> | undefined

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const emailValid = computed(() => EMAIL_RE.test(props.email.trim()))
const canSend = computed(() => !props.disabled && !sending.value && countdown.value <= 0 && emailValid.value)
const sendLabel = computed(() => {
  if (countdown.value > 0) return `${countdown.value}s 后重发`
  return sending.value ? '发送中…' : '发送验证码'
})

function onInput(value: string) {
  const digits = value.replace(/\D/g, '').slice(0, 6)
  if (error.value) error.value = ''
  emit('update:modelValue', digits)
}

function startCountdown(seconds: number) {
  countdown.value = Math.max(1, Math.round(seconds || props.defaultCooldown))
  if (timer) clearInterval(timer)
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) {
      countdown.value = 0
      if (timer) clearInterval(timer)
      timer = undefined
    }
  }, 1000)
}

function describeError(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (status === 429) return '发送过于频繁，请稍后再试'
  if (status === 422) return '邮箱格式不正确'
  if (!status) return '网络异常，请检查连接后重试'
  return '验证码发送失败，请稍后重试'
}

async function send() {
  error.value = ''
  if (!emailValid.value) {
    error.value = '请先填写正确的邮箱地址'
    return
  }
  sending.value = true
  try {
    const result = await sendEmailCode({ email: props.email.trim(), purpose: props.purpose })
    devCode.value = result.dev_code || ''
    startCountdown(result.cooldown_seconds)
    if (result.dev_code) {
      message.success('验证码已生成（开发模式）')
    } else if (result.delivered) {
      message.success('验证码已发送，请查收邮箱')
    } else {
      message.warning('邮件服务未开启，请联系管理员或稍后重试')
    }
  } catch (err) {
    error.value = describeError(err)
    message.error(error.value)
  } finally {
    sending.value = false
  }
}

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

defineExpose({ startCountdown })
</script>

<style scoped>
.code-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.code-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.code-send {
  min-width: 118px;
  font-variant-numeric: tabular-nums;
}

.code-hint {
  margin: 0;
  font-size: var(--fs-xs, 12px);
  line-height: 1.6;
  color: var(--faint, #9a8088);
}
.code-hint.is-error { color: var(--sakura-deep, #c93a63); }
.code-hint.is-dev {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  padding: 7px 10px;
  border-radius: var(--r-sm, 10px);
  background: var(--sakura-wash, rgba(232, 98, 140, 0.08));
  color: var(--ink, #4a2b35);
}
.code-hint.is-dev strong {
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.12em;
  color: var(--sakura-deep, #c93a63);
}
.code-hint-note { color: var(--faint, #9a8088); }

@media (max-width: 420px) {
  .code-row { grid-template-columns: minmax(0, 1fr); }
  .code-send { width: 100%; }
}
</style>
