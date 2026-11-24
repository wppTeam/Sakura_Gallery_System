<template>
  <AuthShell
    eyebrow="JOIN US · 加入视觉百花"
    title="创建你的账号"
    subtitle="一个账号，记录你与这所校园的每一次相遇。"
  >
    <template #alert>
      <n-alert v-if="formError" type="error" :bordered="false" closable class="auth-alert" @close="formError = ''">
        {{ formError }}
      </n-alert>
    </template>

    <form class="auth-form" novalidate @submit.prevent="handleRegister">
      <div class="auth-grid">
        <div class="auth-field">
          <label class="auth-label" for="reg-student-id">学号 / 工号 <span class="auth-required">*</span></label>
          <n-input
            id="reg-student-id"
            v-model:value="form.student_id"
            size="large"
            placeholder="例如 2024010123"
            autocomplete="off"
            :status="errors.student_id ? 'error' : undefined"
          />
          <p v-if="errors.student_id" class="auth-inline-error">{{ errors.student_id }}</p>
        </div>

        <div class="auth-field">
          <label class="auth-label" for="reg-email">邮箱 <span class="auth-required">*</span></label>
          <n-input
            id="reg-email"
            v-model:value="form.email"
            size="large"
            placeholder="用于接收验证码与找回密码"
            autocomplete="email"
            :status="errors.email ? 'error' : undefined"
          />
          <p v-if="errors.email" class="auth-inline-error">{{ errors.email }}</p>
        </div>
      </div>

      <div class="auth-field">
        <label class="auth-label">邮箱验证码 <span class="auth-required">*</span></label>
        <EmailCodeField
          v-model="form.email_code"
          :email="form.email"
          purpose="register"
          :disabled="submitting"
        />
        <p v-if="errors.email_code" class="auth-inline-error">{{ errors.email_code }}</p>
      </div>

      <div class="auth-grid">
        <div class="auth-field">
          <label class="auth-label" for="reg-username">公开用户名 <span class="auth-optional">可选</span></label>
          <n-input
            id="reg-username"
            v-model:value="form.username"
            size="large"
            placeholder="3–32 位字母、数字或 _ . -"
            autocomplete="username"
            :status="errors.username ? 'error' : undefined"
          />
          <p class="auth-field-hint">公开页展示用，学号不会对外显示。</p>
          <p v-if="errors.username" class="auth-inline-error">{{ errors.username }}</p>
        </div>

        <div class="auth-field">
          <label class="auth-label" for="reg-display">显示名 <span class="auth-optional">可选</span></label>
          <n-input
            id="reg-display"
            v-model:value="form.display_name"
            size="large"
            placeholder="例如 王同学 / 阿樱"
            autocomplete="nickname"
            maxlength="64"
          />
          <p class="auth-field-hint">不填则回退到公开用户名。</p>
        </div>
      </div>

      <div class="auth-field">
        <label class="auth-label" for="reg-password">设置密码 <span class="auth-required">*</span></label>
        <PasswordField
          v-model="form.password"
          show-meter
          autocomplete="new-password"
          placeholder="至少 8 位，含大小写字母和数字"
          :error="errors.password"
        />
      </div>

      <div class="auth-field">
        <label class="auth-label" for="reg-confirm">确认密码 <span class="auth-required">*</span></label>
        <n-input
          id="reg-confirm"
          v-model:value="form.confirmPassword"
          type="password"
          show-password-on="click"
          size="large"
          placeholder="再次输入密码"
          autocomplete="new-password"
          :status="errors.confirmPassword ? 'error' : undefined"
          @keydown.enter.prevent="handleRegister"
        />
        <p v-if="errors.confirmPassword" class="auth-inline-error">{{ errors.confirmPassword }}</p>
      </div>

      <label class="auth-check auth-check--terms">
        <input v-model="agreed" type="checkbox" />
        <span>
          我已阅读并同意
          <button type="button" class="auth-terms-link" @click.prevent="termsOpen = true">《社区规范与隐私说明》</button>
        </span>
      </label>

      <n-button
        class="auth-submit"
        type="primary"
        size="large"
        block
        :loading="submitting"
        :disabled="submitting || !agreed"
        attr-type="submit"
      >
        {{ submitting ? '注册中…' : '注册' }}
      </n-button>
      <p v-if="!agreed" class="auth-hint-center">请先阅读并勾选社区规范与隐私说明</p>
    </form>

    <template #footer>
      <p class="auth-switch">
        已有账号？
        <RouterLink :to="{ path: '/login', query: loginQuery }">直接登录</RouterLink>
        <span class="auth-switch-sep" aria-hidden="true">·</span>
        <RouterLink to="/explore">先逛逛作品广场</RouterLink>
      </p>
    </template>

    <TermsDialog v-model:show="termsOpen" />
  </AuthShell>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import AuthShell from '../components/auth/AuthShell.vue'
import EmailCodeField from '../components/auth/EmailCodeField.vue'
import PasswordField from '../components/auth/PasswordField.vue'
import TermsDialog from '../components/auth/TermsDialog.vue'
import { register } from '../api/auth'
import '../styles/auth.css'

const router = useRouter()
const message = useMessage()

const form = reactive({
  student_id: '',
  email: '',
  email_code: '',
  username: '',
  display_name: '',
  password: '',
  confirmPassword: '',
})
const agreed = ref(false)
const submitting = ref(false)
const formError = ref('')
const termsOpen = ref(false)

const errors = reactive<Record<keyof typeof form, string>>({
  student_id: '',
  email: '',
  email_code: '',
  username: '',
  display_name: '',
  password: '',
  confirmPassword: '',
})

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const USERNAME_RE = /^[A-Za-z0-9_.-]{3,32}$/

const loginQuery = computed(() => (form.email ? { email: form.email } : {}))

const passwordOk = computed(() =>
  form.password.length >= 8
  && /[a-z]/.test(form.password)
  && /[A-Z]/.test(form.password)
  && /[0-9]/.test(form.password),
)

function clearErrors() {
  formError.value = ''
  ;(Object.keys(errors) as Array<keyof typeof errors>).forEach((key) => {
    errors[key] = ''
  })
}

function validate(): boolean {
  clearErrors()
  let ok = true
  if (!form.student_id.trim()) {
    errors.student_id = '请输入学号 / 工号'
    ok = false
  }
  if (!EMAIL_RE.test(form.email.trim())) {
    errors.email = '请输入正确的邮箱地址'
    ok = false
  }
  if (form.email_code.trim().length !== 6) {
    errors.email_code = '请输入 6 位邮箱验证码'
    ok = false
  }
  if (form.username.trim() && !USERNAME_RE.test(form.username.trim())) {
    errors.username = '用户名需为 3–32 位字母、数字、下划线、点或短横线'
    ok = false
  }
  if (!passwordOk.value) {
    errors.password = '密码至少 8 位，且包含大小写字母和数字'
    ok = false
  }
  if (form.confirmPassword !== form.password) {
    errors.confirmPassword = '两次输入的密码不一致'
    ok = false
  }
  if (!agreed.value) {
    formError.value = '请先阅读并勾选社区规范与隐私说明'
    ok = false
  }
  return ok
}

function describeError(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (status === 409) return '学号、邮箱或用户名已被注册'
  if (status === 422) return '注册信息未通过校验，请检查填写内容'
  if (status === 429) return '操作过于频繁，请稍后再试'
  if (!status) return '网络异常，请检查连接后重试'
  return '注册失败，请稍后重试'
}

async function handleRegister() {
  if (submitting.value) return
  if (!validate()) {
    if (formError.value) message.warning(formError.value)
    return
  }
  submitting.value = true
  try {
    const user = await register({
      student_id: form.student_id.trim(),
      email: form.email.trim(),
      email_code: form.email_code.trim(),
      username: form.username.trim() || undefined,
      display_name: form.display_name.trim() || undefined,
      password: form.password,
    })
    const email = form.email.trim()
    if (user.is_active === false) {
      message.info('注册已提交，等待管理员审批')
      await router.replace({ path: '/login', query: { email, pending: '1' } })
    } else {
      message.success('注册成功，请登录')
      await router.replace({ path: '/login', query: { email, registered: '1' } })
    }
  } catch (err) {
    formError.value = describeError(err)
    message.error(formError.value)
  } finally {
    submitting.value = false
  }
}
</script>
