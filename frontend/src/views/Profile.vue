<template>
  <div class="profile-page">
    <SiteHeader />

    <main class="profile-main">
      <div class="wrap profile-shell">
        <header class="profile-head">
          <p class="profile-eyebrow">MY SPACE · 创作空间</p>
          <h1 class="profile-title">个人中心</h1>
          <p class="profile-lead">
            管理你的收藏与投稿，维护公开资料。所有作品展示尊重原始构图，不裁切。
          </p>
          <div class="profile-quick-links">
            <RouterLink class="profile-quick-link" to="/notifications">通知中心 →</RouterLink>
            <RouterLink class="profile-quick-link" to="/favorites">我的收藏 →</RouterLink>
            <RouterLink class="profile-quick-link" to="/my-collections">我的策展 →</RouterLink>
            <a class="profile-quick-link" href="#account-security">账号与安全 →</a>
          </div>
          <ul class="profile-chips" aria-label="账户概览">
            <li>
              <span class="chip-num">{{ formatInteger(stats.total) }}</span>
              <span class="chip-label">投稿</span>
            </li>
            <li>
              <span class="chip-num">{{ formatInteger(stats.approved) }}</span>
              <span class="chip-label">已发布</span>
            </li>
            <li>
              <span class="chip-num">{{ formatInteger(stats.favorites) }}</span>
              <span class="chip-label">收藏</span>
            </li>
            <li class="chip-role">
              <n-tag :type="roleTagType" size="small" :bordered="false" round>{{ roleLabel }}</n-tag>
            </li>
          </ul>
        </header>

        <n-tabs v-model:value="activeTab" type="line" animated class="profile-tabs" @update:value="onTabChange">
          <!-- 我的收藏 -->
          <n-tab-pane name="favorites" tab="我的收藏">
            <div v-if="favoritesLoading && !favorites.length" class="profile-skeleton-grid" aria-busy="true">
              <SkeletonCard v-for="index in 4" :key="index" :aspect-ratio="SKELETON_SHAPES[index % 4]" />
            </div>

            <EmptyState
              v-else-if="favoritesError"
              title="收藏暂时没有加载出来"
              :description="favoritesError"
              action-label="重新加载"
              error
              @action="loadFavorites(true)"
            />

            <EmptyState
              v-else-if="!favoritesTotal && !favorites.length"
              title="还没有收藏"
              description="在作品详情页点一下「收藏」，喜欢的画面就会出现在这里。"
              action-label="去探索作品"
              @action="goExplore"
            />

            <template v-else>
              <MasonryGrid :items="favorites" :max-columns="4" :skeleton-rows="2" />
              <div class="profile-more">
                <n-button
                  v-if="favorites.length < favoritesTotal"
                  secondary
                  :loading="favoritesLoading"
                  @click="loadFavorites(false)"
                >
                  {{ favoritesLoading ? '加载中…' : `加载更多（还有 ${favoritesTotal - favorites.length} 张）` }}
                </n-button>
                <p v-else class="profile-end">已经到底啦</p>
              </div>
            </template>
          </n-tab-pane>

          <!-- 我的投稿 -->
          <n-tab-pane name="submissions" tab="我的投稿">
            <div v-if="submissionsLoading && !submissions.length" class="profile-skeleton-list" aria-busy="true">
              <div v-for="index in 4" :key="index" class="skill-skeleton" />
            </div>

            <EmptyState
              v-else-if="submissionsError"
              title="投稿列表暂时没有加载出来"
              :description="submissionsError"
              action-label="重新加载"
              error
              @action="loadSubmissions"
            />

            <EmptyState
              v-else-if="!submissions.length"
              title="还没有投稿"
              description="把你拍到的校园瞬间分享出来，通过 AI 审核后就会出现在作品广场。"
              action-label="去投稿"
              @action="goUpload"
            />

            <ul v-else class="submission-list">
              <li v-for="item in submissions" :key="item.id" class="submission-item">
                <RouterLink :to="`/photo/${item.id}`" class="submission-thumb">
                  <img
                    :src="getPhotoUrl(item.id, 'thumbnail')"
                    :alt="item.title || '投稿作品'"
                    loading="lazy"
                    decoding="async"
                  />
                </RouterLink>
                <div class="submission-main">
                  <div class="submission-title-row">
                    <RouterLink :to="`/photo/${item.id}`" class="submission-title">
                      {{ displayPhotoTitle(item) }}
                    </RouterLink>
                    <n-tag :type="statusTagType(item.status)" size="tiny" :bordered="false">
                      {{ statusLabel(item.status) }}
                    </n-tag>
                  </div>
                  <p class="submission-meta">
                    <span>{{ formatDate(item.created_at) }}</span>
                    <template v-if="item.season"><span class="meta-dot">·</span><span>{{ seasonLabel(item.season) }}</span></template>
                    <template v-if="item.category"><span class="meta-dot">·</span><span>{{ categoryLabel(item.category) }}</span></template>
                  </p>
                </div>
                <RouterLink :to="`/photo/${item.id}`" class="submission-link">查看 →</RouterLink>
              </li>
            </ul>
          </n-tab-pane>

          <!-- 资料设置 -->
          <n-tab-pane name="settings" tab="资料设置">
            <n-form
              ref="formRef"
              :model="formData"
              :rules="formRules"
              label-placement="left"
              label-width="96px"
              class="profile-form"
            >
              <n-form-item label="学号/工号">
                <n-input :value="authStore.user?.student_id" disabled />
              </n-form-item>
              <n-form-item label="邮箱" path="email">
                <n-input v-model:value="formData.email" placeholder="请输入邮箱" />
              </n-form-item>
              <n-form-item label="显示名称" path="full_name">
                <n-input v-model:value="formData.full_name" placeholder="公开页展示的昵称" />
              </n-form-item>
              <n-form-item label="注册时间">
                <n-text depth="3">{{ formatDate(authStore.user?.created_at) }}</n-text>
              </n-form-item>
              <n-form-item>
                <n-space>
                  <n-button type="primary" :loading="saving" @click="handleSave">保存修改</n-button>
                  <n-button @click="showChangePassword = true">修改密码</n-button>
                </n-space>
              </n-form-item>
            </n-form>
          </n-tab-pane>
        </n-tabs>

        <!-- 账号与安全：注销不可恢复，单独做成危险区，不放进 tabs 里降低误触 -->
        <section id="account-security" class="profile-security" aria-labelledby="account-security-title">
          <header class="security-head">
            <p class="profile-eyebrow">ACCOUNT &amp; SECURITY · 账号与安全</p>
            <h2 id="account-security-title" class="security-title">账号与安全</h2>
            <p class="security-lead">
              管理登录密码与账号生命周期。注销是<strong>不可恢复</strong>的操作，请确认你已了解下方说明。
            </p>
          </header>

          <div class="danger-zone">
            <div class="danger-zone-head">
              <span class="danger-zone-badge" aria-hidden="true">!</span>
              <div class="danger-zone-intro">
                <h3 class="danger-zone-title">注销账号</h3>
                <p class="danger-zone-lead">
                  注销后，你的账号与全部内容将从本站彻底删除，且<strong>无法恢复</strong>。
                </p>
              </div>
            </div>

            <ul class="danger-zone-list">
              <li>账号下的全部作品会连同原图、缩略图、压缩图与响应式变体一并删除；</li>
              <li>你创建的自建专辑、收藏、站内通知与邮箱验证码记录也会被删除；</li>
              <li>审核记录与审计日志按后端实际删除范围处理，注销后当前登录立即失效、无法再登录。</li>
            </ul>

            <form class="danger-zone-form" @submit.prevent="openDeleteModal">
              <label class="dz-field">
                <span class="dz-label">当前密码</span>
                <n-input
                  v-model:value="deletePassword"
                  type="password"
                  show-password-on="click"
                  placeholder="用于二次确认身份"
                  autocomplete="current-password"
                />
              </label>
              <label class="dz-field">
                <span class="dz-label">确认词</span>
                <n-input
                  v-model:value="deleteConfirm"
                  placeholder="请输入「注销」两个字"
                  autocomplete="off"
                />
              </label>
              <div class="dz-actions">
                <button type="submit" class="dz-button" :disabled="!deleteReady">注销账号</button>
                <p class="dz-hint">两个字段都填写且确认词精确为「注销」后才能继续。</p>
              </div>
            </form>
          </div>
        </section>
      </div>
    </main>

    <SiteFooter />
    <ChangePasswordDialog v-model:show="showChangePassword" />

    <!-- 注销二次确认：确认按钮再点一次才真正提交 -->
    <n-modal
      v-model:show="showDeleteModal"
      preset="card"
      :bordered="false"
      :mask-closable="!deleteSubmitting"
      :closable="!deleteSubmitting"
      class="delete-account-modal"
      style="width: min(92vw, 540px)"
    >
      <template #header>
        <div class="delete-modal-head">
          <span class="delete-modal-seal" aria-hidden="true">!</span>
          <span>确认注销账号？</span>
        </div>
      </template>

      <div class="delete-modal-body">
        <p class="delete-modal-warn">
          此操作<strong>不可恢复</strong>。确认后，你的账号、作品、自建专辑、收藏与站内通知将被永久删除。
        </p>
        <p class="delete-modal-account">
          当前账号：<strong>{{ authStore.user?.display_name || authStore.user?.username || '（未知）' }}</strong>
        </p>
        <div v-if="deleteError" class="delete-modal-error" role="alert">{{ deleteError }}</div>
        <p class="delete-modal-note">如果只是想暂时离开，请点「取消」；站内创作与收藏会原样保留。</p>
      </div>

      <template #footer>
        <div class="delete-modal-actions">
          <n-button :disabled="deleteSubmitting" @click="showDeleteModal = false">取消</n-button>
          <n-button type="error" :loading="deleteSubmitting" @click="submitDelete">确认注销</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, type FormInst, type FormRules } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import ChangePasswordDialog from '../components/common/ChangePasswordDialog.vue'
import SiteHeader from '../components/layout/SiteHeader.vue'
import SiteFooter from '../components/layout/SiteFooter.vue'
import EmptyState from '../components/public/EmptyState.vue'
import MasonryGrid from '../components/public/MasonryGrid.vue'
import SkeletonCard from '../components/public/SkeletonCard.vue'
import type { PublicPhoto } from '../api/public'
import { toPublicPhoto } from '../api/public'
import * as photoApi from '../api/photo'
import * as authApi from '../api/auth'
import { deleteAccount } from '../api/user'
import { formatDate, getPhotoUrl } from '../utils/format'
import { displayPhotoTitle } from '../utils/photoDisplay'
import type { Photo } from '../types/photo'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const PAGE_SIZE = 20
const SKELETON_SHAPES = ['4 / 3', '1 / 1', '3 / 4', '4 / 3']
const DEFAULT_TITLE = '个人中心 · 视觉百花 Sakura Gallery'

const activeTab = ref<'favorites' | 'submissions' | 'settings'>('favorites')
const loadedTabs = reactive<Record<string, boolean>>({})

const formRef = ref<FormInst | null>(null)
const saving = ref(false)
const showChangePassword = ref(false)

const formData = reactive({
  email: authStore.user?.email || '',
  full_name: authStore.user?.full_name || '',
})

const formRules: FormRules = {
  email: [{ type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' }],
}

const stats = reactive({ total: 0, approved: 0, pending: 0, rejected: 0, favorites: 0 })

/* ---------- 账号与安全：注销 ---------- */

const deletePassword = ref('')
const deleteConfirm = ref('')
const showDeleteModal = ref(false)
const deleteSubmitting = ref(false)
const deleteError = ref('')

const deleteReady = computed(
  () => deletePassword.value.length > 0 && deleteConfirm.value === '注销',
)

function openDeleteModal() {
  if (!deleteReady.value) return
  deleteError.value = ''
  showDeleteModal.value = true
}

/** 优先原样展示后端 detail（409 最后管理员文案需完整保留） */
function describeDeleteError(error: unknown): string {
  const err = error as { response?: { status?: number; data?: { detail?: unknown } } } | undefined
  const status = err?.response?.status
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (status === 401) return '登录状态已过期，请重新登录后再试。'
  if (status === 409) return '当前账号暂时无法注销，请稍后再试或联系管理员。'
  if (status === 429) return '操作太频繁，请稍后再试。'
  if (!status) return '网络连接失败，请检查网络后重试。'
  return `注销失败，请稍后再试（HTTP ${status}）。`
}

async function submitDelete() {
  if (!deleteReady.value || deleteSubmitting.value) return
  deleteSubmitting.value = true
  deleteError.value = ''
  try {
    await deleteAccount({ password: deletePassword.value, confirm: deleteConfirm.value })
    showDeleteModal.value = false
    deletePassword.value = ''
    deleteConfirm.value = ''
    authStore.logout()
    await router.replace('/')
    message.success('账号已注销')
  } catch (error) {
    deleteError.value = describeDeleteError(error)
  } finally {
    deleteSubmitting.value = false
  }
}

/* ---------- 收藏 ---------- */

const favorites = ref<PublicPhoto[]>([])
const favoritesTotal = ref(0)
const favoritesLoading = ref(false)
const favoritesError = ref('')

/* ---------- 投稿 ---------- */

const submissions = ref<Photo[]>([])
const submissionsLoading = ref(false)
const submissionsError = ref('')

const roleLabel = computed(() => {
  const map: Record<string, string> = {
    admin: '超级管理员',
    auditor: '审核员',
    tagger: '标注员',
    dept_user: '部门用户',
    user: '普通用户',
  }
  return map[authStore.user?.role || 'user'] || '普通用户'
})

const roleTagType = computed(() => {
  const map: Record<string, 'success' | 'warning' | 'info' | 'default'> = {
    admin: 'success',
    auditor: 'warning',
    tagger: 'info',
    dept_user: 'info',
    user: 'default',
  }
  return map[authStore.user?.role || 'user'] || 'default'
})

function formatInteger(value: number | null | undefined): string {
  return new Intl.NumberFormat('zh-CN').format(value ?? 0)
}

const SEASON_LABELS: Record<string, string> = {
  Spring: '春季',
  Summer: '夏季',
  Autumn: '秋季',
  Winter: '冬季',
  春: '春季',
  夏: '夏季',
  秋: '秋季',
  冬: '冬季',
}

const CATEGORY_LABELS: Record<string, string> = {
  Landscape: '风光',
  Documentary: '纪实',
  Portrait: '人像',
  Activity: '活动',
  Architecture: '建筑',
  StillLife: '静物',
  风光: '风光',
  纪实: '纪实',
  人像: '人像',
  活动: '活动',
  建筑: '建筑',
  静物: '静物',
}

function seasonLabel(value: string | null | undefined): string {
  if (!value) return ''
  return SEASON_LABELS[value] || value
}

function categoryLabel(value: string | null | undefined): string {
  if (!value) return ''
  return CATEGORY_LABELS[value] || value
}

const STATUS_LABELS: Record<string, string> = {
  approved: '已发布',
  pending: '审核中',
  processing: '处理中',
  rejected: '已驳回',
}

function statusLabel(status: string | null | undefined): string {
  return STATUS_LABELS[status || ''] || status || '未知'
}

function statusTagType(status: string | null | undefined): 'success' | 'warning' | 'error' | 'default' {
  if (status === 'approved') return 'success'
  if (status === 'pending' || status === 'processing') return 'warning'
  if (status === 'rejected') return 'error'
  return 'default'
}

function describeError(error: unknown, fallback: string): string {
  const err = error as { response?: { status?: number; data?: { detail?: unknown } } } | undefined
  const status = err?.response?.status
  if (status === 401) return '登录状态已过期，请重新登录。'
  if (status === 403) return '暂时没有权限查看这些内容。'
  if (!status) return '网络连接失败，请检查网络后重试。'
  return `${fallback}（HTTP ${status}）`
}

async function loadFavorites(reset: boolean) {
  if (favoritesLoading.value) return
  favoritesLoading.value = true
  if (reset) favoritesError.value = ''
  try {
    const page = await photoApi.getMyFavorites({
      skip: reset ? 0 : favorites.value.length,
      limit: PAGE_SIZE,
    })
    const mapped = (page.items || []).map(toPublicPhoto)
    favorites.value = reset ? mapped : [...favorites.value, ...mapped]
    favoritesTotal.value = page.total || mapped.length
    stats.favorites = favoritesTotal.value
  } catch (error) {
    const text = describeError(error, '收藏加载失败')
    if (!favorites.value.length) favoritesError.value = text
    else message.error(text)
  } finally {
    favoritesLoading.value = false
  }
}

async function loadSubmissions() {
  if (submissionsLoading.value) return
  submissionsLoading.value = true
  submissionsError.value = ''
  try {
    const response = await photoApi.getMySubmissions({ limit: 1000 })
    const items = response.items || []
    submissions.value = items
    stats.total = items.length
    stats.approved = items.filter((item) => item.status === 'approved').length
    stats.pending = items.filter((item) => item.status === 'pending' || item.status === 'processing').length
    stats.rejected = items.filter((item) => item.status === 'rejected').length
  } catch (error) {
    submissionsError.value = describeError(error, '投稿加载失败')
  } finally {
    submissionsLoading.value = false
  }
}

function onTabChange(name: string) {
  const tab = name as 'favorites' | 'submissions' | 'settings'
  activeTab.value = tab
  if (loadedTabs[tab]) return
  loadedTabs[tab] = true
  if (tab === 'favorites' && !favorites.value.length) void loadFavorites(true)
  if (tab === 'submissions' && !submissions.value.length) void loadSubmissions()
}

function goExplore() {
  void router.push('/explore')
}

function goUpload() {
  void router.push('/upload')
}

async function handleSave() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    await authApi.updateProfile({
      email: formData.email || undefined,
      full_name: formData.full_name || undefined,
    })
    message.success('资料已更新')
    await authStore.fetchCurrentUser()
  } catch (error) {
    message.error(describeError(error, '更新失败'))
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  document.title = DEFAULT_TITLE
  loadedTabs.favorites = true
  loadedTabs.submissions = true
  void loadFavorites(true)
  void loadSubmissions()
})
</script>

<style scoped>
.profile-page {
  min-height: 100vh;
  background: var(--ground, #fff6f9);
}

.profile-main {
  padding: clamp(20px, 3.2vw, 40px) 0 clamp(48px, 6vw, 80px);
}

.profile-shell {
  max-width: 1120px;
}

.profile-head {
  margin-bottom: 10px;
}

.profile-eyebrow {
  margin: 0 0 8px;
  color: var(--sakura-deep, #c93a63);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.14em;
}

.profile-title {
  margin: 0;
  color: var(--ink, #4a2b35);
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: clamp(40px, 4.4vw, 52px);
  font-weight: 400;
  line-height: 1.12;
  letter-spacing: 0.02em;
}

.profile-lead {
  max-width: 34em;
  margin: 10px 0 0;
  color: var(--muted, #63474f);
  font-size: 15px;
  line-height: 1.8;
}

.profile-quick-links {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.profile-quick-link {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--sakura-deep);
  font-size: var(--fs-sm);
  text-decoration: none;
  transition: border-color var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out);
}

.profile-quick-link:hover {
  border-color: var(--sakura);
  background: var(--sakura-wash);
}

.profile-quick-link:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 2px;
}

.profile-chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 16px 0 4px;
  padding: 0;
  list-style: none;
}

.profile-chips li {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  padding: 6px 13px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-pill, 999px);
  background: var(--surface, #fff);
}

.chip-num {
  color: var(--ink, #4a2b35);
  font-size: 16px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.chip-label {
  color: var(--faint, #947881);
  font-size: 12px;
}

.chip-role {
  border-color: transparent !important;
  background: transparent !important;
  padding: 0 !important;
}

.profile-tabs {
  margin-top: 18px;
}

.profile-tabs :deep(.n-tabs-nav) {
  margin-bottom: 18px;
}

.profile-skeleton-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--gap, 20px);
}

.profile-skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skill-skeleton {
  height: 92px;
  border-radius: var(--r-card, 20px);
  background: linear-gradient(90deg, var(--surface, #fff) 0%, var(--sakura-wash, #fff5f8) 50%, var(--surface, #fff) 100%);
  background-size: 200% 100%;
  animation: profile-shimmer 1.4s ease-in-out infinite;
}

@keyframes profile-shimmer {
  from {
    background-position: 200% 0;
  }
  to {
    background-position: -200% 0;
  }
}

.profile-more {
  display: flex;
  justify-content: center;
  margin-top: 26px;
}

.profile-end {
  margin: 0;
  color: var(--faint, #947881);
  font-size: 13px;
}

.submission-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.submission-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-sm, 10px);
  background: var(--surface, #fff);
  transition: border-color var(--dur-fast, 160ms) var(--ease-out, ease);
}

.submission-item:hover {
  border-color: var(--sakura, #e8628c);
}

.submission-thumb {
  flex: none;
  display: block;
  width: 84px;
  height: 64px;
  overflow: hidden;
  border-radius: 8px;
  background: var(--sakura-wash, #fff5f8);
}

.submission-thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.submission-main {
  min-width: 0;
  flex: 1;
}

.submission-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.submission-title {
  overflow: hidden;
  color: var(--ink, #4a2b35);
  font-size: 15px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-decoration: none;
}

.submission-title:hover {
  color: var(--sakura-deep, #c93a63);
}

.submission-title:focus-visible,
.submission-thumb:focus-visible,
.submission-link:focus-visible {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.4));
  outline-offset: 2px;
  border-radius: 6px;
}

.submission-meta {
  margin: 4px 0 0;
  color: var(--faint, #947881);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.meta-dot {
  margin: 0 5px;
}

.submission-link {
  flex: none;
  color: var(--sakura-deep, #c93a63);
  font-size: 13px;
  text-decoration: none;
}

.submission-link:hover {
  text-decoration: underline;
}

.profile-form {
  max-width: 520px;
  margin-top: 6px;
}

/* ---------- 账号与安全 ---------- */

.profile-security {
  margin-top: clamp(40px, 5vw, 64px);
  padding-top: clamp(26px, 3.4vw, 36px);
  border-top: 1px solid var(--line);
  scroll-margin-top: 88px;
}

.security-head {
  max-width: 42em;
}

.security-title {
  margin: 0;
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(26px, 2.8vw, 34px);
  font-weight: 400;
  line-height: 1.2;
  letter-spacing: 0.02em;
}

.security-lead {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 15px;
  line-height: 1.8;
}

.security-lead strong,
.danger-zone-lead strong,
.delete-modal-warn strong {
  color: var(--danger-ink);
  font-weight: 600;
}

.danger-zone {
  --danger-ink: #96324c;
  --danger-line: rgba(201, 58, 99, 0.32);
  margin-top: 18px;
  padding: clamp(18px, 2.4vw, 26px);
  border: 1px solid var(--danger-line);
  border-radius: var(--r-card, 20px);
  background:
    radial-gradient(120% 140% at 0% 0%, rgba(232, 98, 140, 0.09) 0%, transparent 58%),
    var(--surface, #fff);
}

.danger-zone-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.danger-zone-badge {
  flex: none;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin-top: 2px;
  border: 1px solid var(--danger-line);
  border-radius: 999px;
  background: var(--sakura-pale);
  color: var(--danger-ink);
  font-family: var(--display);
  font-size: 18px;
  line-height: 1;
}

.danger-zone-intro {
  min-width: 0;
}

.danger-zone-title {
  margin: 0;
  color: var(--danger-ink);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.4;
}

.danger-zone-lead {
  margin: 4px 0 0;
  color: var(--ink-soft, #63474f);
  font-size: 14px;
  line-height: 1.7;
}

.danger-zone-list {
  margin: 14px 0 0;
  padding: 0 0 0 18px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.9;
}

.danger-zone-form {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px dashed var(--danger-line);
}

.dz-field {
  display: block;
  max-width: 360px;
  margin-bottom: 14px;
}

.dz-label {
  display: block;
  margin-bottom: 6px;
  color: var(--ink-soft, #63474f);
  font-size: 13px;
  font-weight: 600;
}

.dz-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 2px;
}

.dz-button {
  min-width: 168px;
  min-height: 46px;
  padding: 0 22px;
  border: 1px solid var(--danger-ink);
  border-radius: 999px;
  background: var(--danger-ink);
  color: #fff;
  font-family: inherit;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out), opacity var(--dur-fast) var(--ease-out);
}

.dz-button:hover:not(:disabled) {
  background: #7f2940;
}

.dz-button:disabled {
  border-color: var(--line-strong, #e7c4cf);
  background: var(--surface-soft, #fff2f7);
  color: var(--faint, #947881);
  cursor: not-allowed;
  opacity: 0.85;
}

.dz-button:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 3px;
}

.dz-hint {
  margin: 0;
  flex: 1 1 220px;
  color: var(--faint, #947881);
  font-size: 12px;
  line-height: 1.7;
}

.delete-modal-head {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--ink);
  font-size: 17px;
  font-weight: 600;
}

.delete-modal-seal {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 1px solid rgba(201, 58, 99, 0.36);
  border-radius: 999px;
  background: var(--sakura-pale);
  color: #96324c;
  font-family: var(--display);
  font-size: 17px;
  line-height: 1;
}

.delete-modal-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.8;
}

.delete-modal-warn {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid rgba(201, 58, 99, 0.24);
  border-radius: var(--r-sm, 10px);
  background: rgba(255, 233, 240, 0.55);
  color: var(--ink);
}

.delete-modal-account {
  margin: 0;
}

.delete-modal-account strong {
  color: var(--ink);
  font-weight: 600;
}

.delete-modal-error {
  padding: 10px 14px;
  border: 1px solid rgba(201, 58, 99, 0.4);
  border-radius: var(--r-sm, 10px);
  background: var(--sakura-pale);
  color: #7f2940;
  font-size: 13px;
  line-height: 1.7;
  word-break: break-word;
}

.delete-modal-note {
  margin: 0;
  color: var(--faint, #947881);
  font-size: 12px;
}

.delete-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.delete-modal-actions :deep(.n-button) {
  min-height: 44px;
  padding: 0 20px;
}

@media (max-width: 560px) {
  .dz-button {
    width: 100%;
  }

  .dz-field {
    max-width: none;
  }

  .danger-zone-form {
    margin-top: 18px;
  }
}

@media (pointer: coarse) {
  .dz-button {
    min-height: 48px;
  }
}

@media (max-width: 820px) {
  .profile-skeleton-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .profile-title {
    font-size: 40px;
  }

  .submission-item {
    align-items: flex-start;
  }

  .submission-thumb {
    width: 64px;
    height: 52px;
  }

  .submission-link {
    display: none;
  }

  .profile-skeleton-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .skill-skeleton {
    animation: none;
  }
}
</style>
