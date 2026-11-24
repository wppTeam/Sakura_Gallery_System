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
      </div>
    </main>

    <SiteFooter />
    <ChangePasswordDialog v-model:show="showChangePassword" />
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
