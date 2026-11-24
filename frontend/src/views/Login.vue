<template>
  <AuthShell
    eyebrow="WELCOME BACK · 欢迎回来"
    title="登录视觉百花"
    subtitle="继续分享你的作品，或回到你收藏过的那些光。"
  >
    <template #alert>
      <n-alert v-if="noticeText" :type="noticeType" :bordered="false" closable class="auth-alert" @close="noticeText = ''">
        {{ noticeText }}
      </n-alert>
      <n-alert v-if="formError" type="error" :bordered="false" closable class="auth-alert" @close="formError = ''">
        {{ formError }}
      </n-alert>
    </template>

    <div class="auth-segmented" role="tablist" aria-label="登录方式">
      <button
        class="segmented-btn"
        type="button"
        role="tab"
        :aria-selected="mode === 'password'"
        :class="{ 'is-active': mode === 'password' }"
        @click="mode = 'password'"
      >
        密码登录
      </button>
      <button
        class="segmented-btn"
        type="button"
        role="tab"
        :aria-selected="mode === 'code'"
        :class="{ 'is-active': mode === 'code' }"
        @click="mode = 'code'"
      >
        邮箱验证码
      </button>
    </div>

    <form v-show="mode === 'password'" class="auth-form" novalidate @submit.prevent="handlePasswordLogin">
      <div class="auth-field">
        <label class="auth-label" for="login-identifier">学号 / 邮箱 / 用户名</label>
        <n-input
          id="login-identifier"
          v-model:value="passwordForm.identifier"
          size="large"
          placeholder="请输入学号、邮箱或用户名"
          autocomplete="username"
          :status="errors.identifier ? 'error' : undefined"
          @keydown.enter.prevent="handlePasswordLogin"
        />
        <p v-if="errors.identifier" class="auth-inline-error">{{ errors.identifier }}</p>
      </div>

      <div class="auth-field">
        <div class="auth-label-row">
          <label class="auth-label" for="login-password">密码</label>
          <button class="auth-text-btn" type="button" @click="forgotOpen = true">忘记密码？</button>
        </div>
        <PasswordField
          v-model="passwordForm.password"
          autocomplete="current-password"
          placeholder="请输入密码"
          :error="errors.password"
          @submit="handlePasswordLogin"
        />
      </div>

      <label class="auth-check">
        <input v-model="remember" type="checkbox" />
        <span>记住我（关闭后关闭浏览器即退出）</span>
      </label>

      <n-button class="auth-submit" type="primary" size="large" block :loading="loading" :disabled="loading" attr-type="submit">
        {{ loading ? '登录中…' : '登录' }}
      </n-button>
    </form>

    <form v-show="mode === 'code'" class="auth-form" novalidate @submit.prevent="handleCodeLogin">
      <div class="auth-field">
        <label class="auth-label" for="login-email">邮箱</label>
        <n-input
          id="login-email"
          v-model:value="codeForm.email"
          size="large"
          placeholder="请输入注册邮箱"
          autocomplete="email"
          :status="errors.email ? 'error' : undefined"
          @keydown.enter.prevent="handleCodeLogin"
        />
        <p v-if="errors.email" class="auth-inline-error">{{ errors.email }}</p>
      </div>

      <div class="auth-field">
        <label class="auth-label">邮箱验证码</label>
        <EmailCodeField
          v-model="codeForm.code"
          :email="codeForm.email"
          purpose="login"
          :disabled="loading"
          @submit="handleCodeLogin"
        />
        <p v-if="errors.code" class="auth-inline-error">{{ errors.code }}</p>
      </div>

      <label class="auth-check">
        <input v-model="remember" type="checkbox" />
        <span>记住我（关闭后关闭浏览器即退出）</span>
      </label>

      <n-button class="auth-submit" type="primary" size="large" block :loading="loading" :disabled="loading" attr-type="submit">
        {{ loading ? '登录中…' : '验证码登录' }}
      </n-button>
    </form>

    <template #footer>
      <p class="auth-switch">
        还没有账号？
        <RouterLink :to="{ path: '/register', query: registerQuery }">注册一个</RouterLink>
        <span class="auth-switch-sep" aria-hidden="true">·</span>
        <RouterLink to="/explore">先逛逛作品广场</RouterLink>
      </p>
      <p class="auth-terms">
        登录即表示同意 <button type="button" class="auth-terms-link" @click="termsOpen = true">社区规范与隐私说明</button>
      </p>
    </template>

    <ForgotPasswordDialog
      v-model:show="forgotOpen"
      :default-identifier="passwordForm.identifier"
      @done="onPasswordReset"
    />
    <TermsDialog v-model:show="termsOpen" />
  </AuthShell>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import AuthShell from '../components/auth/AuthShell.vue'
import EmailCodeField from '../components/auth/EmailCodeField.vue'
import PasswordField from '../components/auth/PasswordField.vue'
import ForgotPasswordDialog from '../components/auth/ForgotPasswordDialog.vue'
import TermsDialog from '../components/auth/TermsDialog.vue'
import { useAuthStore } from '../stores/auth'
import '../styles/auth.css'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

type LoginMode = 'password' | 'code'
const mode = ref<LoginMode>('password')
const remember = ref(true)
const loading = ref(false)
const formError = ref('')
const forgotOpen = ref(false)
const termsOpen = ref(false)

const passwordForm = reactive({ identifier: '', password: '' })
const codeForm = reactive({ email: '', code: '' })
const errors = reactive<Record<'identifier' | 'password' | 'email' | 'code', string>>({
  identifier: '',
  password: '',
  email: '',
  code: '',
})

const noticeText = ref('')
const noticeType = ref<'success' | 'info' | 'warning'>('success')

const registerQuery = computed(() => (codeForm.email ? { email: codeForm.email } : {}))

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

onMounted(() => {
  const query = route.query
  const email = typeof query.email === 'string' ? query.email : ''
  if (email) {
    passwordForm.identifier = email
    codeForm.email = email
  }
  if (query.registered === '1') {
    noticeType.value = 'success'
    noticeText.value = '注册成功，请用刚设置的密码登录。'
  } else if (query.pending === '1') {
    noticeType.value = 'info'
    noticeText.value = '注册已提交，等待管理员审批后即可登录。'
  } else if (query.reset === '1') {
    noticeType.value = 'success'
    noticeText.value = '密码已重置，请用新密码登录。'
  }
})

function clearErrors() {
  formError.value = ''
  ;(Object.keys(errors) as Array<keyof typeof errors>).forEach((key) => {
    errors[key] = ''
  })
}

function describeError(err: unknown, fallback: string): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (status === 401) return '账号或密码不正确'
  if (status === 403) return '账号尚未通过审批或被停用'
  if (status === 429) return '操作过于频繁，请稍后再试'
  if (!status) return '网络异常，请检查连接后重试'
  return fallback
}

/** 只允许站内相对路径，避免 redirect 被用作开放跳转 */
function safeRedirect(): string {
  const raw = route.query.redirect
  const target = typeof raw === 'string' ? raw : ''
  if (target.startsWith('/') && !target.startsWith('//')) return target
  return '/'
}

async function finishLogin(redirectTo: string) {
  message.success('登录成功，正在进入…')
  // 等一帧让 toast 出现，再离场，避免页面瞬间切换的割裂
  await new Promise((resolve) => setTimeout(resolve, 220))
  await router.replace(redirectTo)
}

async function handlePasswordLogin() {
  if (loading.value) return
  clearErrors()
  if (!passwordForm.identifier.trim()) {
    errors.identifier = '请输入学号、邮箱或用户名'
    return
  }
  if (!passwordForm.password) {
    errors.password = '请输入密码'
    return
  }
  loading.value = true
  try {
    await authStore.login(passwordForm.identifier.trim(), passwordForm.password, remember.value)
    await finishLogin(safeRedirect())
  } catch (err) {
    formError.value = describeError(err, '登录失败，请检查账号和密码')
    message.error(formError.value)
  } finally {
    loading.value = false
  }
}

async function handleCodeLogin() {
  if (loading.value) return
  clearErrors()
  if (!EMAIL_RE.test(codeForm.email.trim())) {
    errors.email = '请输入正确的邮箱地址'
    return
  }
  if (codeForm.code.trim().length !== 6) {
    errors.code = '请输入 6 位邮箱验证码'
    return
  }
  loading.value = true
  try {
    await authStore.loginWithCode(codeForm.email.trim(), codeForm.code.trim(), remember.value)
    await finishLogin(safeRedirect())
  } catch (err) {
    formError.value = describeError(err, '验证码登录失败')
    message.error(formError.value)
  } finally {
    loading.value = false
  }
}

function onPasswordReset(identifier: string) {
  passwordForm.identifier = identifier
  passwordForm.password = ''
  message.success('密码已重置，请用新密码登录')
}
</script>
