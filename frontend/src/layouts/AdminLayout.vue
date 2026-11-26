<template>
  <n-layout class="admin-shell" has-sider>
    <n-layout-sider
      v-if="!isNarrow"
      class="admin-sider"
      bordered
      :width="252"
      :collapsed="collapsed"
      :collapsed-width="72"
      :show-trigger="false"
    >
      <div class="sider-brand" :class="{ 'is-collapsed': collapsed }">
        <img class="sider-logo" src="/brand/logo-symbol.png" alt="" />
        <div v-if="!collapsed" class="sider-brand-text">
          <strong>视觉百花</strong>
          <span>管理后台</span>
        </div>
      </div>

      <n-menu
        v-model:value="activeKey"
        class="admin-menu"
        :collapsed="collapsed"
        :collapsed-width="72"
        :indent="18"
        :options="filteredMenuOptions"
        @update:value="handleMenuSelect"
      />

      <div class="sider-foot">
        <button v-if="!collapsed" class="sider-link" type="button" @click="goFront">
          <n-icon :component="ImagesOutline" />
          返回前台
        </button>
        <button class="sider-collapse" type="button" :title="collapsed ? '展开侧栏' : '收起侧栏'" @click="collapsed = !collapsed">
          <n-icon :component="collapsed ? ChevronForwardOutline : ChevronBackOutline" />
        </button>
      </div>
    </n-layout-sider>

    <n-layout class="admin-main">
      <n-layout-header bordered class="admin-topbar">
        <div class="topbar-left">
          <button v-if="isNarrow" class="icon-btn" type="button" aria-label="打开菜单" @click="drawerOpen = true">
            <n-icon :component="MenuOutline" />
          </button>
          <n-breadcrumb class="topbar-crumb">
            <n-breadcrumb-item @click="router.push({ name: 'Dashboard' })">后台管理</n-breadcrumb-item>
            <n-breadcrumb-item>{{ currentTitle }}</n-breadcrumb-item>
          </n-breadcrumb>
        </div>

        <div class="topbar-right">
          <div v-if="!isNarrow" class="topbar-search-wrap">
            <n-input
              v-model:value="searchQuery"
              class="topbar-search"
              round
              size="small"
              clearable
              placeholder="全局搜索用户 / 作品 / 专题"
              aria-label="全局搜索"
              :loading="searchLoading"
              @keydown="onSearchKeydown"
              @focus="searchOpen = !!searchQuery.trim()"
              @blur="onSearchBlur"
              @clear="closeSearch"
            >
              <template #prefix>
                <n-icon :component="SearchOutline" />
              </template>
            </n-input>
            <div v-if="searchOpen" class="search-panel" role="listbox" aria-label="全局搜索结果">
              <p v-if="searchLoading" class="search-status">搜索中…</p>
              <p v-else-if="!searchHits.length" class="search-status">没有匹配的用户 / 作品 / 专题</p>
              <template v-else>
                <div v-for="section in searchSections" :key="section.label" class="search-group">
                  <p class="search-group-title">{{ section.label }}</p>
                  <button
                    v-for="hit in section.items"
                    :key="hit.key"
                    type="button"
                    class="search-hit"
                    :class="{ 'is-active': hit.index === searchCursor }"
                    role="option"
                    :aria-selected="hit.index === searchCursor"
                    @mousedown.prevent="goSearchHit(hit)"
                    @mouseenter="searchCursor = hit.index"
                  >
                    <span class="search-hit-label">{{ hit.label }}</span>
                    <span class="search-hit-sub">{{ hit.sub }}</span>
                  </button>
                </div>
                <p class="search-tip">↑↓ 选择 · Enter 直达 · Esc 关闭</p>
              </template>
            </div>
          </div>

          <NotificationBell />

          <n-dropdown trigger="click" :options="userMenuOptions" @select="onUserMenuSelect">
            <button class="user-chip" type="button">
              <n-avatar round :size="28" class="user-avatar">{{ avatarText }}</n-avatar>
              <span v-if="!isNarrow" class="user-name">{{ displayName }}</span>
              <n-tag v-if="!isNarrow" size="small" :type="roleTagType" class="user-role">{{ roleLabel }}</n-tag>
              <n-icon :component="ChevronDownOutline" class="user-caret" />
            </button>
          </n-dropdown>
        </div>
      </n-layout-header>

      <n-layout-content class="admin-content" :native-scrollbar="false" :content-style="contentStyle">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>

  <n-drawer v-model:show="drawerOpen" placement="left" :width="276">
    <n-drawer-content body-content-style="padding: 0;">
      <div class="sider-brand drawer-brand">
        <img class="sider-logo" src="/brand/logo-symbol.png" alt="" />
        <div class="sider-brand-text">
          <strong>视觉百花</strong>
          <span>管理后台</span>
        </div>
      </div>
      <n-menu
        v-model:value="activeKey"
        class="admin-menu admin-menu--drawer"
        :options="filteredMenuOptions"
        @update:value="handleDrawerMenuSelect"
      />
      <div class="drawer-foot">
        <n-button block secondary @click="goFront">返回前台</n-button>
      </div>
    </n-drawer-content>
  </n-drawer>

  <ChangePasswordDialog v-model:show="showChangePassword" />
</template>

<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon, useDialog, useMessage } from 'naive-ui'
import {
  BarChartOutline,
  ChatbubbleEllipsesOutline,
  CheckmarkCircleOutline,
  ChevronBackOutline,
  ChevronDownOutline,
  ChevronForwardOutline,
  CloudUploadOutline,
  DocumentTextOutline,
  GitNetworkOutline,
  ImagesOutline,
  KeyOutline,
  LogOutOutline,
  FlagOutline,
  MenuOutline,
  PeopleOutline,
  PricetagOutline,
  PricetagsOutline,
  SearchOutline,
  ServerOutline,
  SparklesOutline,
  WalletOutline,
  SettingsOutline,
} from '@vicons/ionicons5'
import type { MenuOption } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import { adminSearch, type AdminSearchResult } from '../api/admin_search'
import ChangePasswordDialog from '../components/common/ChangePasswordDialog.vue'
import NotificationBell from '../components/common/NotificationBell.vue'
import { fetchReportStats } from '../api/admin_reports'
import { fetchAdminAppealStats } from '../api/admin_appeals'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const dialog = useDialog()
const message = useMessage()

const collapsed = ref(false)
const isNarrow = ref(false)
const drawerOpen = ref(false)
const activeKey = ref(route.name?.toString() || 'Dashboard')
const contentStyle = computed(() => (isNarrow.value ? 'padding: 12px;' : 'padding: 24px;'))
const user = computed(() => authStore.user)
const showChangePassword = ref(false)

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  auditor: '审核员',
  tagger: '标注员',
  dept_user: '部门用户',
  user: '普通用户',
}

const roleLabel = computed(() => ROLE_LABELS[user.value?.role || 'user'] || '未知')
const roleTagType = computed(() => {
  const map: Record<string, 'success' | 'warning' | 'info' | 'default'> = {
    admin: 'success',
    auditor: 'warning',
    tagger: 'info',
    dept_user: 'info',
    user: 'default',
  }
  return map[user.value?.role || 'user'] || 'default'
})

const displayName = computed(() => user.value?.display_name || user.value?.full_name || user.value?.username || user.value?.email || '未登录')
const avatarText = computed(() => (displayName.value || '?').trim().slice(0, 1).toUpperCase())

/* --------------------------- 全局搜索 --------------------------- */
interface SearchHit {
  key: string
  label: string
  sub: string
  to: string
  index: number
}

const searchQuery = ref('')
const searchLoading = ref(false)
const searchOpen = ref(false)
const searchCursor = ref(0)
const searchResult = ref<AdminSearchResult | null>(null)
let searchTimer: number | undefined

const searchSections = computed(() => {
  const result = searchResult.value
  if (!result) return [] as { label: string; items: SearchHit[] }[]
  const sections: { label: string; items: SearchHit[] }[] = []
  let index = 0
  const push = (label: string, items: Omit<SearchHit, 'index'>[]) => {
    if (!items.length) return
    sections.push({ label, items: items.map((item) => ({ ...item, index: index++ })) })
  }
  push(
    '用户',
    result.users.map((u) => ({
      key: `user-${u.id}`,
      label: u.displayName || u.username || u.studentId || '未命名用户',
      sub: [u.username ? `@${u.username}` : null, u.email, ROLE_LABELS[u.role] || u.role, u.isActive ? null : '已停用']
        .filter(Boolean)
        .join(' · '),
      to: `/admin/users?focus=${u.id}`,
    })),
  )
  push(
    '作品',
    result.photos.map((p) => ({
      key: `photo-${p.id}`,
      label: p.title || '未命名作品',
      sub: [p.uploaderUsername ? `@${p.uploaderUsername}` : null, p.status].filter(Boolean).join(' · '),
      to: `/photo/${p.id}`,
    })),
  )
  push(
    '专题',
    result.collections.map((c) => ({
      key: `collection-${c.slug}`,
      label: c.title,
      sub: `${c.kind === 'user' ? '作者手账' : '策展'} · ${c.photoCount} 件`,
      to: `/collections/${c.slug}`,
    })),
  )
  return sections
})

const searchHits = computed(() => searchSections.value.flatMap((section) => section.items))

watch(searchQuery, (query) => {
  if (searchTimer) window.clearTimeout(searchTimer)
  const term = query.trim()
  if (!term) {
    searchResult.value = null
    searchOpen.value = false
    searchLoading.value = false
    return
  }
  searchOpen.value = true
  searchLoading.value = true
  searchTimer = window.setTimeout(async () => {
    try {
      searchResult.value = await adminSearch(term)
      searchCursor.value = 0
    } catch {
      searchResult.value = null
    } finally {
      searchLoading.value = false
    }
  }, 250)
})

function closeSearch() {
  searchOpen.value = false
  searchCursor.value = 0
}

function onSearchBlur() {
  window.setTimeout(() => {
    searchOpen.value = false
  }, 120)
}

function goSearchHit(hit: SearchHit) {
  closeSearch()
  searchQuery.value = ''
  searchResult.value = null
  router.push(hit.to)
}

function onSearchKeydown(event: KeyboardEvent) {
  if (!searchOpen.value) return
  const hits = searchHits.value
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    searchCursor.value = hits.length ? (searchCursor.value + 1) % hits.length : 0
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    searchCursor.value = hits.length ? (searchCursor.value - 1 + hits.length) % hits.length : 0
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const hit = hits[searchCursor.value]
    if (hit) goSearchHit(hit)
  } else if (event.key === 'Escape') {
    closeSearch()
  }
}

const PAGE_TITLES: Record<string, string> = {
  Dashboard: '仪表盘',
  PhotoReview: '照片审核',
  Reports: '举报处理',
  Appeals: '复核申诉',
  AiUsage: 'AI 成本',
  AigcManagement: 'AI 生图管理',
  TagManagement: '自由标签',
  TaxonomyManagement: '分类治理',
  TaggingTaskManagement: '标注任务',
  PhotoImport: '批量导入',
  UserManagement: '用户管理',
  SystemSettings: '系统设置',
  AuditLog: '审计日志',
  DatabaseManagement: '数据库管理',
}
const currentTitle = computed(() => PAGE_TITLES[activeKey.value] || '后台管理')

let mediaQuery: MediaQueryList | null = null

function syncNarrow(matches: boolean) {
  isNarrow.value = matches
  collapsed.value = matches
}

function onMediaChange(event: MediaQueryListEvent) {
  syncNarrow(event.matches)
}

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 900px)')
  syncNarrow(mediaQuery.matches)
  mediaQuery.addEventListener('change', onMediaChange)
  window.addEventListener('reports:changed', loadReportPendingCount)
  window.addEventListener('appeals:changed', loadAppealPendingCount)
  void loadReportPendingCount()
  void loadAppealPendingCount()
})

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener('change', onMediaChange)
  window.removeEventListener('reports:changed', loadReportPendingCount)
  window.removeEventListener('appeals:changed', loadAppealPendingCount)
})

watch(
  () => route.name,
  (name) => {
    if (name) activeKey.value = name.toString()
    document.title = `${currentTitle.value} · 后台管理 · 视觉百花`
    void loadReportPendingCount()
    void loadAppealPendingCount()
  },
  { immediate: true },
)

function renderMenuIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const reportPendingCount = ref(0)

function renderReportsLabel() {
  return h('span', { class: 'menu-label-with-badge' }, [
    h('span', null, '举报处理'),
    reportPendingCount.value > 0
      ? h('span', { class: 'menu-pending-badge' }, String(reportPendingCount.value))
      : null,
  ])
}

async function loadReportPendingCount() {
  if (!authStore.canReview) return
  try {
    const stats = await fetchReportStats(7)
    reportPendingCount.value = stats.pending
  } catch {
    // 角标失败不影响后台使用
  }
}

const appealPendingCount = ref(0)

function renderAppealsLabel() {
  return h('span', { class: 'menu-label-with-badge' }, [
    h('span', null, '复核申诉'),
    appealPendingCount.value > 0
      ? h('span', { class: 'menu-pending-badge menu-pending-badge--appeal' }, String(appealPendingCount.value))
      : null,
  ])
}

async function loadAppealPendingCount() {
  if (!authStore.canReview) return
  try {
    const stats = await fetchAdminAppealStats(7)
    appealPendingCount.value = stats.pending
  } catch {
    // 角标失败不影响后台使用
  }
}

const contentMenuOptions: MenuOption[] = [
  { label: '仪表盘', key: 'Dashboard', icon: renderMenuIcon(BarChartOutline) },
  { label: '照片审核', key: 'PhotoReview', icon: renderMenuIcon(CheckmarkCircleOutline) },
  { label: renderReportsLabel, key: 'Reports', icon: renderMenuIcon(FlagOutline) },
  { label: renderAppealsLabel, key: 'Appeals', icon: renderMenuIcon(ChatbubbleEllipsesOutline) },
  { label: '自由标签', key: 'TagManagement', icon: renderMenuIcon(PricetagsOutline) },
  { label: '分类治理', key: 'TaxonomyManagement', icon: renderMenuIcon(GitNetworkOutline) },
  { label: '标注任务', key: 'TaggingTaskManagement', icon: renderMenuIcon(PricetagOutline) },
]

const adminMenuOptions: MenuOption[] = [
  { label: '批量导入', key: 'PhotoImport', icon: renderMenuIcon(CloudUploadOutline) },
  { label: '用户管理', key: 'UserManagement', icon: renderMenuIcon(PeopleOutline) },
  { label: 'AI 成本', key: 'AiUsage', icon: renderMenuIcon(WalletOutline) },
  { label: 'AI 生图管理', key: 'AigcManagement', icon: renderMenuIcon(SparklesOutline) },
  { label: '审计日志', key: 'AuditLog', icon: renderMenuIcon(DocumentTextOutline) },
  { label: '数据库管理', key: 'DatabaseManagement', icon: renderMenuIcon(ServerOutline) },
  { label: '系统设置', key: 'SystemSettings', icon: renderMenuIcon(SettingsOutline) },
]

const filteredMenuOptions = computed<MenuOption[]>(() => {
  const options: MenuOption[] = [
    {
      type: 'group',
      label: '内容与审核',
      key: 'group-content',
      children: contentMenuOptions,
    },
  ]
  if (authStore.isAdmin) {
    options.push({
      type: 'group',
      label: '用户与系统',
      key: 'group-admin',
      children: adminMenuOptions,
    })
  }
  return options
})

function handleMenuSelect(key: string) {
  activeKey.value = key
  router.push({ name: key })
}

function handleDrawerMenuSelect(key: string) {
  drawerOpen.value = false
  handleMenuSelect(key)
}

function goFront() {
  drawerOpen.value = false
  router.push('/')
}

const userMenuOptions = [
  { label: '返回前台', key: 'front', icon: renderMenuIcon(ImagesOutline) },
  { label: '修改密码', key: 'password', icon: renderMenuIcon(KeyOutline) },
  { type: 'divider' as const, key: 'divider-user' },
  { label: '退出登录', key: 'logout', icon: renderMenuIcon(LogOutOutline) },
]

function onUserMenuSelect(key: string) {
  if (key === 'front') return goFront()
  if (key === 'password') {
    showChangePassword.value = true
    return
  }
  if (key === 'logout') {
    dialog.warning({
      title: '退出登录',
      content: '确定退出管理后台吗？',
      positiveText: '退出',
      negativeText: '取消',
      onPositiveClick: () => {
        authStore.logout()
        message.success('已退出登录')
        router.push('/login')
      },
    })
  }
}
</script>

<style scoped>
.admin-shell {
  height: 100vh;
  background: var(--ground, #fff6f9);
}

.admin-sider {
  position: relative;
  background: var(--surface, #ffffff);
}

.sider-brand {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  border-bottom: 1px solid var(--line, #f3dde5);
}

.sider-brand.is-collapsed {
  justify-content: center;
  padding: 0;
}

.sider-logo {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
}

.sider-brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
  min-width: 0;
}

.sider-brand-text strong {
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: 19px;
  letter-spacing: 0.02em;
  color: var(--ink, #4a2b35);
}

.sider-brand-text span {
  font-size: 11px;
  color: var(--muted, #63474f);
  letter-spacing: 0.16em;
}

.admin-menu {
  padding: 10px 0;
  height: calc(100vh - 64px - 64px);
  overflow-y: auto;
}

.admin-menu {
  --n-item-color-active: var(--sakura-pale, #ffe9f0) !important;
  --n-item-color-active-hover: var(--sakura-pale, #ffe9f0) !important;
  --n-item-text-color-active: var(--sakura-deep, #c93a63) !important;
  --n-item-text-color-active-hover: var(--sakura-deep, #c93a63) !important;
  --n-item-icon-color-active: var(--sakura-deep, #c93a63) !important;
  --n-item-icon-color-active-hover: var(--sakura-deep, #c93a63) !important;
  --n-group-text-color: var(--faint, #ad8e97) !important;
}

.admin-menu :deep(.n-menu-item-content) {
  border-radius: 10px;
  margin: 2px 8px;
}

.admin-menu :deep(.n-menu-item-content--selected .n-menu-item-content-header) {
  font-weight: 600;
}

.admin-menu :deep(.menu-label-with-badge) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.admin-menu :deep(.menu-pending-badge--appeal) {
  background: var(--sakura-deep, #c93a63);
}

.admin-menu :deep(.menu-pending-badge) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--sakura, #e8628c);
  color: #fff;
  font-size: 11px;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.admin-menu :deep(.n-menu-item-group-title) {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--faint, #ad8e97);
  padding-left: 22px;
}

.sider-foot {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-top: 1px solid var(--line, #f3dde5);
  background: var(--surface, #fff);
}

.sider-link,
.sider-collapse,
.icon-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: var(--muted, #63474f);
  cursor: pointer;
  font-size: 13px;
  padding: 6px 8px;
  border-radius: 8px;
}

.sider-link:hover,
.sider-collapse:hover,
.icon-btn:hover {
  background: var(--sakura-wash, #ffe9f0);
  color: var(--sakura-deep, #c93a63);
}

.sider-link:focus-visible,
.sider-collapse:focus-visible,
.icon-btn:focus-visible {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.35));
  outline-offset: 2px;
}

.admin-main {
  background: var(--ground, #fff6f9);
}

.admin-topbar {
  height: 64px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: var(--surface, #fff);
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.topbar-crumb {
  white-space: nowrap;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.topbar-search {
  width: 280px;
}

.topbar-search-wrap {
  position: relative;
}

.search-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 60;
  width: 360px;
  max-height: 420px;
  overflow-y: auto;
  padding: 8px;
  border-radius: 14px;
  border: 1px solid var(--line, #f3dde5);
  background: var(--surface, #fff);
  box-shadow: 0 12px 32px rgba(74, 43, 53, 0.16);
}

.search-status {
  margin: 0;
  padding: 14px 10px;
  font-size: 13px;
  color: var(--faint, #ad8e97);
  text-align: center;
}

.search-group + .search-group {
  margin-top: 6px;
  border-top: 1px dashed var(--line, #f3dde5);
  padding-top: 6px;
}

.search-group-title {
  margin: 0 0 4px;
  padding: 0 10px;
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--faint, #ad8e97);
  font-weight: 600;
}

.search-hit {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: 10px;
  background: none;
  text-align: left;
  cursor: pointer;
  font: inherit;
}

.search-hit.is-active {
  background: var(--sakura-wash, #ffe9f0);
}

.search-hit-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-hit-sub {
  font-size: 11px;
  color: var(--muted, #63474f);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-tip {
  margin: 6px 0 0;
  padding: 6px 10px 2px;
  border-top: 1px dashed var(--line, #f3dde5);
  font-size: 11px;
  color: var(--faint, #ad8e97);
}

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--line, #f3dde5);
  background: var(--surface, #fff);
  border-radius: 999px;
  padding: 4px 10px 4px 4px;
  cursor: pointer;
  transition: border-color 0.2s var(--ease-out, ease), background 0.2s var(--ease-out, ease);
}

.user-chip:hover {
  border-color: var(--sakura, #e8628c);
  background: var(--sakura-wash, #ffe9f0);
}

.user-chip:focus-visible {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.35));
  outline-offset: 2px;
}

.user-avatar {
  background: var(--sakura-pale, #ffe9f0);
  color: var(--sakura-deep, #c93a63);
  font-weight: 700;
}

.user-name {
  font-size: 13px;
  color: var(--ink, #4a2b35);
  max-width: 12em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-caret {
  color: var(--faint, #ad8e97);
}

.admin-content {
  height: calc(100vh - 64px);
  overflow-y: auto;
}

.drawer-brand {
  border-bottom: 1px solid var(--line, #f3dde5);
}

.drawer-foot {
  padding: 16px;
}

@media (max-width: 768px) {
  .admin-topbar {
    height: 56px;
    padding: 0 12px;
  }

  .admin-content {
    height: calc(100vh - 56px);
  }
}
</style>
