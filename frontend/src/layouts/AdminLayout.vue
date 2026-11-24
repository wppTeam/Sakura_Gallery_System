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
          <n-input
            v-if="!isNarrow"
            class="topbar-search"
            round
            size="small"
            readonly
            placeholder="全局搜索用户 / 作品（即将上线）"
            title="全局搜索即将上线"
          >
            <template #prefix>
              <n-icon :component="SearchOutline" />
            </template>
          </n-input>

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
  MenuOutline,
  PeopleOutline,
  PricetagOutline,
  PricetagsOutline,
  SearchOutline,
  ServerOutline,
  WalletOutline,
  SettingsOutline,
} from '@vicons/ionicons5'
import type { MenuOption } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import ChangePasswordDialog from '../components/common/ChangePasswordDialog.vue'
import NotificationBell from '../components/common/NotificationBell.vue'

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

const PAGE_TITLES: Record<string, string> = {
  Dashboard: '仪表盘',
  PhotoReview: '照片审核',
  AiUsage: 'AI 成本',
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
})

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener('change', onMediaChange)
})

watch(
  () => route.name,
  (name) => {
    if (name) activeKey.value = name.toString()
    document.title = `${currentTitle.value} · 后台管理 · 视觉百花`
  },
  { immediate: true },
)

function renderMenuIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const contentMenuOptions: MenuOption[] = [
  { label: '仪表盘', key: 'Dashboard', icon: renderMenuIcon(BarChartOutline) },
  { label: '照片审核', key: 'PhotoReview', icon: renderMenuIcon(CheckmarkCircleOutline) },
  { label: '自由标签', key: 'TagManagement', icon: renderMenuIcon(PricetagsOutline) },
  { label: '分类治理', key: 'TaxonomyManagement', icon: renderMenuIcon(GitNetworkOutline) },
  { label: '标注任务', key: 'TaggingTaskManagement', icon: renderMenuIcon(PricetagOutline) },
]

const adminMenuOptions: MenuOption[] = [
  { label: '批量导入', key: 'PhotoImport', icon: renderMenuIcon(CloudUploadOutline) },
  { label: '用户管理', key: 'UserManagement', icon: renderMenuIcon(PeopleOutline) },
  { label: 'AI 成本', key: 'AiUsage', icon: renderMenuIcon(WalletOutline) },
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
