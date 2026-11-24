<template>
  <n-modal
    :show="show"
    preset="card"
    :bordered="false"
    class="forgot-modal"
    :mask-closable="!submitting"
    :close-on-esc="!submitting"
    @update:show="(value: boolean) => emit('update:show', value)"
  >
    <template #header>
      <div class="forgot-head">
        <span class="forgot-eyebrow">PASSWORD · 找回密码</span>
        <strong>{{ step === 1 ? '先确认你的身份' : '设置新密码' }}</strong>
      </div>
    </template>

    <n-alert v-if="error" type="error" :bordered="false" class="forgot-alert" closable @close="error = ''">
      {{ error }}
    </n-alert>

    <div v-if="step === 1" class="forgot-step">
      <p class="forgot-lead">
        输入注册邮箱、学号或用户名，我们会向绑定邮箱发送 6 位重置验证码。
      </p>
      <n-input
        v-model:value="identifier"
        size="large"
        placeholder="邮箱 / 学号 / 用户名"
        autocomplete="username"
        :disabled="submitting"
        @keydown.enter.prevent="sendCode"
      />
      <div class="forgot-actions">
        <n-button quaternary :disabled="submitting" @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" :loading="submitting" :disabled="!identifier.trim()" @click="sendCode">
          发送验证码
        </n-button>
      </div>
    </div>

    <div v-else class="forgot-step">
      <p class="forgot-lead">
        验证码已发送，请查看邮箱（10 分钟内有效）。<span v-if="devCode" class="forgot-dev">开发模式验证码：<strong>{{ devCode }}</strong></span>
      </p>
      <label class="forgot-label" for="forgot-code">验证码</label>
      <n-input
        id="forgot-code"
        v-model:value="code"
        size="large"
        maxlength="6"
        inputmode="numeric"
        placeholder="6 位验证码"
        :disabled="submitting"
        @keydown.enter.prevent="submit"
      />
      <label class="forgot-label">新密码</label>
      <PasswordField
        v-model="newPassword"
        :disabled="submitting"
        show-meter
        autocomplete="new-password"
        placeholder="至少 8 位，含大小写字母和数字"
      />
      <label class="forgot-label">确认新密码</label>
      <n-input
        v-model:value="confirmPassword"
        type="password"
        show-password-on="click"
        size="large"
        autocomplete="new-password"
        placeholder="再次输入新密码"
        :disabled="submitting"
        :status="confirmError ? 'error' : undefined"
        @keydown.enter.prevent="submit"
      />
      <p v-if="confirmError" class="forgot-inline-error">{{ confirmError }}</p>

      <div class="forgot-actions">
        <n-button quaternary :disabled="submitting" @click="step = 1">上一步</n-button>
        <n-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
          重设密码
        </n-button>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { forgotPassword, resetPassword } from '../../api/auth'
import PasswordField from './PasswordField.vue'

const props = withDefaults(
  defineProps<{ show: boolean; defaultIdentifier?: string }>(),
  { defaultIdentifier: '' },
)

const emit = defineEmits<{
  'update:show': [value: boolean]
  done: [identifier: string]
}>()

const message = useMessage()
const step = ref<1 | 2>(1)
const identifier = ref('')
const code = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const devCode = ref('')
const submitting = ref(false)
const error = ref('')

const confirmError = computed(() => {
  if (!confirmPassword.value) return ''
  return confirmPassword.value === newPassword.value ? '' : '两次输入的密码不一致'
})

const passwordOk = computed(() =>
  newPassword.value.length >= 8
  && /[a-z]/.test(newPassword.value)
  && /[A-Z]/.test(newPassword.value)
  && /[0-9]/.test(newPassword.value),
)

const canSubmit = computed(() =>
  code.value.trim().length === 6 && passwordOk.value && !confirmError.value,
)

watch(
  () => props.show,
  (visible) => {
    if (!visible) return
    step.value = 1
    identifier.value = props.defaultIdentifier || ''
    code.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    devCode.value = ''
    error.value = ''
  },
)

function describeError(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (status === 429) return '操作过于频繁，请稍后再试'
  if (!status) return '网络异常，请检查连接后重试'
  return '操作失败，请稍后重试'
}

async function sendCode() {
  if (!identifier.value.trim() || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    const result = await forgotPassword({ identifier: identifier.value.trim() })
    devCode.value = result.dev_code || ''
    if (result.dev_code) {
      message.success('验证码已生成（开发模式）')
    } else {
      message.success('如果该账号存在，重置验证码已发送到绑定邮箱')
    }
    step.value = 2
  } catch (err) {
    error.value = describeError(err)
    message.error(error.value)
  } finally {
    submitting.value = false
  }
}

async function submit() {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    const result = await resetPassword({
      identifier: identifier.value.trim(),
      code: code.value.trim(),
      new_password: newPassword.value,
    })
    message.success(result.detail || '密码已重置，请用新密码登录')
    emit('done', identifier.value.trim())
    emit('update:show', false)
  } catch (err) {
    error.value = describeError(err)
    message.error(error.value)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.forgot-modal {
  width: min(460px, calc(100vw - 32px));
  border-radius: var(--r-card, 20px);
}

.forgot-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.forgot-eyebrow {
  font-size: var(--fs-xs, 12px);
  font-weight: 600;
  letter-spacing: 0.16em;
  color: var(--sakura-deep, #c93a63);
}
.forgot-head strong {
  font-size: 19px;
  font-weight: 700;
  color: var(--ink, #4a2b35);
}

.forgot-alert { margin-bottom: 14px; }

.forgot-step {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.forgot-lead {
  margin: 0 0 2px;
  font-size: var(--fs-sm, 14px);
  line-height: 1.75;
  color: var(--muted, #63474f);
}
.forgot-dev {
  display: block;
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: var(--r-sm, 10px);
  background: var(--sakura-wash, rgba(232, 98, 140, 0.08));
  color: var(--ink, #4a2b35);
}
.forgot-dev strong {
  letter-spacing: 0.12em;
  color: var(--sakura-deep, #c93a63);
}

.forgot-label {
  font-size: var(--fs-xs, 12px);
  font-weight: 600;
  color: var(--muted, #63474f);
}

.forgot-inline-error {
  margin: 0;
  font-size: var(--fs-xs, 12px);
  color: var(--sakura-deep, #c93a63);
}

.forgot-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
