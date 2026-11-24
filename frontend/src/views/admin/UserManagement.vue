<template>
  <div class="admin-users">
    <header class="page-head">
      <div class="head-text">
        <p class="eyebrow">USER MANAGEMENT</p>
        <h1 class="page-title">用户管理</h1>
        <p class="page-sub">账号、角色与登录状态。所有操作会记入审计日志，请谨慎授权。</p>
      </div>
      <div class="head-actions">
        <n-button secondary :loading="loading" @click="refreshAll">刷新</n-button>
        <n-button type="primary" @click="openCreate">新建用户</n-button>
      </div>
    </header>

    <section class="stat-grid" aria-label="用户概览">
      <article v-for="item in statItems" :key="item.key" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
        <span class="stat-hint">{{ item.hint }}</span>
      </article>
    </section>

    <section class="panel">
      <div class="toolbar">
        <n-input
          v-model:value="searchInput"
          class="toolbar-search"
          clearable
          placeholder="搜索学号 / 邮箱 / 用户名 / 姓名"
          @update:value="onSearchInput"
          @keyup.enter="applySearch"
        >
          <template #prefix>
            <n-icon :component="SearchOutline" />
          </template>
        </n-input>

        <n-select v-model:value="roleFilter" class="toolbar-select" placeholder="全部角色" clearable :options="roleFilterOptions" @update:value="reload(1)" />
        <n-select v-model:value="statusFilter" class="toolbar-select" placeholder="全部状态" clearable :options="statusFilterOptions" @update:value="reload(1)" />
        <n-select v-model:value="sortBy" class="toolbar-select" :options="sortOptions" @update:value="reload(1)" />

        <span class="toolbar-spacer" />

        <span class="toolbar-count">共 <strong>{{ total }}</strong> 位用户</span>
        <n-select v-model:value="pageSize" class="toolbar-size" :options="pageSizeOptions" @update:value="reload(1)" />
      </div>

      <div v-if="error" class="state-panel">
        <n-icon :component="CloudOfflineOutline" class="state-icon" />
        <p class="state-title">用户列表加载失败</p>
        <p class="state-desc">{{ error }}</p>
        <n-button type="primary" @click="reload()">重新加载</n-button>
      </div>

      <div v-else-if="loading && !users.length" class="skeleton-list" aria-busy="true">
        <div v-for="n in 6" :key="n" class="skeleton-row">
          <span class="sk sk-avatar" />
          <span class="sk sk-name" />
          <span class="sk sk-line" />
          <span class="sk sk-tag" />
          <span class="sk sk-time" />
        </div>
      </div>

      <div v-else-if="!users.length" class="state-panel">
        <n-icon :component="PeopleOutline" class="state-icon" />
        <p class="state-title">没有匹配的用户</p>
        <p class="state-desc">换个关键词，或清除筛选条件再试。</p>
        <n-space>
          <n-button secondary @click="clearFilters">清除筛选</n-button>
          <n-button type="primary" @click="openCreate">新建用户</n-button>
        </n-space>
      </div>

      <div v-else class="table-wrap">
        <table class="user-table">
          <thead>
            <tr>
              <th class="col-user">用户</th>
              <th class="col-contact">学号 / 邮箱</th>
              <th class="col-role">角色</th>
              <th class="col-status">状态</th>
              <th class="col-login">最后登录</th>
              <th v-if="!isNarrow" class="col-created">注册时间</th>
              <th class="col-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in users" :key="row.id" :class="{ 'is-self': row.id === selfId }">
              <td class="col-user">
                <div class="user-cell">
                  <n-avatar round :size="34" class="row-avatar">{{ avatarOf(row) }}</n-avatar>
                  <div class="user-meta">
                    <span class="user-title">
                      {{ displayNameOf(row) }}
                      <n-tag v-if="row.id === selfId" size="small" :bordered="false" class="self-tag">我</n-tag>
                    </span>
                    <span class="user-sub">@{{ row.username || '未设置用户名' }}</span>
                  </div>
                </div>
              </td>
              <td class="col-contact">
                <div class="contact-line">
                  <span class="mono">{{ row.student_id || '—' }}</span>
                </div>
                <div class="contact-line email-line">
                  <span class="email-text">{{ row.email }}</span>
                  <n-tooltip v-if="row.email_verified" trigger="hover">
                    <template #trigger>
                      <n-icon :component="CheckmarkCircleOutline" class="verified-icon" />
                    </template>
                    邮箱已验证
                  </n-tooltip>
                  <n-tag v-else size="tiny" type="warning" :bordered="false">未验证</n-tag>
                </div>
              </td>
              <td class="col-role">
                <n-tag size="small" :type="roleTag(row.role).type" :bordered="false">{{ roleTag(row.role).label }}</n-tag>
              </td>
              <td class="col-status">
                <span class="status-dot" :class="row.is_active ? 'is-on' : 'is-off'" />
                {{ row.is_active ? '启用' : '禁用 / 待审批' }}
              </td>
              <td class="col-login">
                <div class="login-line">{{ formatLastLogin(row.last_login_at) }}</div>
                <div class="login-count">登录 {{ row.login_count ?? 0 }} 次</div>
              </td>
              <td v-if="!isNarrow" class="col-created">{{ formatDate(row.created_at, 'YYYY-MM-DD') }}</td>
              <td class="col-actions">
                <n-dropdown trigger="click" :options="actionsFor(row)" @select="(key: string) => onAction(key, row)">
                  <n-button size="small" secondary>管理
                    <template #icon>
                      <n-icon :component="EllipsisHorizontalOutline" />
                    </template>
                  </n-button>
                </n-dropdown>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="!error && total > 0" class="pager">
        <n-pagination
          :page="page"
          :page-size="pageSize"
          :item-count="total"
          :page-slot="6"
          @update:page="onPageChange"
          @update:page-size="onPageSizeChange"
        />
      </div>
    </section>

    <!-- 新建用户 -->
    <n-modal v-model:show="createOpen" preset="card" title="新建用户" class="modal-card" :mask-closable="false">
      <n-form ref="createFormRef" :model="createForm" :rules="createRules" label-placement="top">
        <div class="form-grid">
          <n-form-item label="学号 / 工号" path="student_id">
            <n-input v-model:value="createForm.student_id" placeholder="必填，作为登录身份" />
          </n-form-item>
          <n-form-item label="邮箱">
            <n-input v-model:value="createForm.email" placeholder="选填，用于找回密码" />
          </n-form-item>
          <n-form-item label="用户名">
            <n-input v-model:value="createForm.username" placeholder="选填，公开展示" />
          </n-form-item>
          <n-form-item label="显示名">
            <n-input v-model:value="createForm.display_name" placeholder="选填" />
          </n-form-item>
          <n-form-item label="初始密码" path="password">
            <n-input v-model:value="createForm.password" type="password" show-password-on="click" placeholder="至少 8 位" />
          </n-form-item>
          <n-form-item label="角色">
            <n-select v-model:value="createForm.role" :options="roleFilterOptions" />
          </n-form-item>
        </div>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="createOpen = false">取消</n-button>
          <n-button type="primary" :loading="submitting" @click="submitCreate">创建</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 编辑资料 -->
    <n-modal v-model:show="editOpen" preset="card" title="编辑用户" class="modal-card" :mask-closable="false">
      <n-form label-placement="top">
        <div class="form-grid">
          <n-form-item label="学号 / 工号">
            <n-input v-model:value="editForm.student_id" />
          </n-form-item>
          <n-form-item label="邮箱">
            <n-input v-model:value="editForm.email" />
          </n-form-item>
          <n-form-item label="姓名">
            <n-input v-model:value="editForm.full_name" />
          </n-form-item>
        </div>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="editOpen = false">取消</n-button>
          <n-button type="primary" :loading="submitting" @click="submitEdit">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 改角色 -->
    <n-modal v-model:show="roleOpen" preset="card" title="调整角色" class="modal-small">
      <p class="modal-desc">
        将 <strong>{{ activeUser ? displayNameOf(activeUser) : '' }}</strong> 的角色调整为：
      </p>
      <n-select v-model:value="roleDraft" :options="roleFilterOptions" />
      <p class="modal-note">角色变更立即生效，请确认对方职责范围。</p>
      <template #footer>
        <n-space justify="end">
          <n-button @click="roleOpen = false">取消</n-button>
          <n-button type="primary" :loading="submitting" @click="submitRole">保存角色</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 重置密码 -->
    <n-modal v-model:show="resetOpen" preset="card" title="重置密码" class="modal-small">
      <p class="modal-desc">为 <strong>{{ activeUser ? displayNameOf(activeUser) : '' }}</strong> 设置新密码，对方需用新密码登录。</p>
      <n-input v-model:value="resetDraft" type="password" show-password-on="click" placeholder="至少 8 位，建议包含大小写与数字" />
      <p v-if="resetError" class="modal-error">{{ resetError }}</p>
      <template #footer>
        <n-space justify="end">
          <n-button @click="resetOpen = false">取消</n-button>
          <n-button type="primary" :loading="submitting" @click="submitReset">重置密码</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 权限授权（沿用原有权限管理能力） -->
    <n-modal v-model:show="permissionOpen" preset="card" title="权限管理" style="width: min(720px, 94vw)">
      <template #header-extra>
        当前用户：{{ activeUser?.full_name || activeUser?.username || activeUser?.email }}
      </template>
      <n-space vertical size="large">
        <n-card size="small" title="已授予权限">
          <n-data-table
            :columns="permissionColumns"
            :data="userPermissions"
            :loading="permissionLoading"
            size="small"
            :max-height="200"
          />
        </n-card>
        <n-card size="small" title="新增授权">
          <n-form inline :model="permissionForm" label-placement="left">
            <n-form-item label="资源类别">
              <n-input value="人像摄影 (Portrait)" disabled style="width: 150px" />
            </n-form-item>
            <n-form-item label="有效期(天)">
              <n-input-number v-model:value="permissionForm.days" :min="1" style="width: 110px" />
            </n-form-item>
            <n-form-item label="备注">
              <n-input v-model:value="permissionForm.note" placeholder="选填" />
            </n-form-item>
            <n-form-item>
              <n-button type="primary" :loading="submitting" @click="handleGrantPermission">授予权限</n-button>
            </n-form-item>
          </n-form>
        </n-card>
      </n-space>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useDialog, useMessage, NButton, type FormInst } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import {
  CheckmarkCircleOutline,
  CloudOfflineOutline,
  EllipsisHorizontalOutline,
  PeopleOutline,
  SearchOutline,
} from '@vicons/ionicons5'
import type { User, UserRole, UserUpdateRequest } from '../../types/user'
import * as usersApi from '../../api/users'
import type { AdminUserStats } from '../../api/users'
import * as permissionApi from '../../api/permissions'
import type { PermissionResponse, PermissionGrantRequest } from '../../api/permissions'
import { useAuthStore } from '../../stores/auth'
import { formatDate, formatRelativeTime } from '../../utils/format'

const message = useMessage()
const dialog = useDialog()
const authStore = useAuthStore()

const isNarrow = ref(false)
const users = ref<User[]>([])
const total = ref(0)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const stats = ref<AdminUserStats | null>(null)

const searchInput = ref('')
const searchQuery = ref('')
const roleFilter = ref<UserRole | null>(null)
const statusFilter = ref<'active' | 'inactive' | 'unverified' | 'verified' | null>(null)
const sortBy = ref<'created_at_desc' | 'created_at_asc' | 'last_login_desc' | 'login_count_desc' | 'student_id_asc'>('created_at_desc')
const page = ref(1)
const pageSize = ref(20)
const pageSizeList = [20, 50, 100]
const pageSizeOptions = pageSizeList.map((n) => ({ label: `每页 ${n} 人`, value: n }))

const selfId = computed(() => authStore.user?.id || '')

const roleFilterOptions: Array<{ label: string; value: UserRole }> = [
  { label: '超级管理员', value: 'admin' },
  { label: '审核员', value: 'auditor' },
  { label: '标注员', value: 'tagger' },
  { label: '部门用户', value: 'dept_user' },
  { label: '普通用户', value: 'user' },
]

const statusFilterOptions = [
  { label: '启用中', value: 'active' },
  { label: '禁用 / 待审批', value: 'inactive' },
  { label: '邮箱未验证', value: 'unverified' },
  { label: '邮箱已验证', value: 'verified' },
]

const sortOptions = [
  { label: '注册时间（新→旧）', value: 'created_at_desc' },
  { label: '注册时间（旧→新）', value: 'created_at_asc' },
  { label: '最后登录（近→远）', value: 'last_login_desc' },
  { label: '登录次数（多→少）', value: 'login_count_desc' },
  { label: '学号（升序）', value: 'student_id_asc' },
]

const statItems = computed(() => {
  const s = stats.value
  return [
    { key: 'total', label: '总用户', value: s ? s.total : '—', hint: '全部注册账号' },
    { key: 'active', label: '活跃', value: s ? s.active : '—', hint: '当前启用' },
    { key: 'pending', label: '待审批', value: s ? s.pending_approval : '—', hint: '注册待放行' },
    { key: 'unverified', label: '邮箱未验证', value: s ? s.email_unverified : '—', hint: '建议提醒补验' },
    { key: 'new7', label: '7 日新增', value: s ? s.new_last_7_days : '—', hint: '近一周注册' },
    { key: 'staff', label: '管理/审核', value: s ? `${s.admins} / ${s.auditors}` : '—', hint: '管理员 / 审核员' },
  ]
})

const roleTagMap: Record<UserRole, { label: string; type: 'success' | 'warning' | 'info' | 'default' }> = {
  admin: { label: '超级管理员', type: 'success' },
  auditor: { label: '审核员', type: 'warning' },
  tagger: { label: '标注员', type: 'info' },
  dept_user: { label: '部门用户', type: 'info' },
  user: { label: '普通用户', type: 'default' },
}

function roleTag(role: UserRole) {
  return roleTagMap[role] || { label: role, type: 'default' as const }
}

function displayNameOf(row: User) {
  return row.display_name || row.full_name || row.username || row.email?.split('@')[0] || '未命名用户'
}

function avatarOf(row: User) {
  return displayNameOf(row).trim().slice(0, 1).toUpperCase()
}

function formatLastLogin(value?: string | null) {
  if (!value) return '从未登录'
  return formatRelativeTime(value)
}

function buildParams() {
  const params: Parameters<typeof usersApi.getUsers>[0] = {
    skip: (page.value - 1) * pageSize.value,
    limit: pageSize.value,
    sort: sortBy.value,
  }
  if (searchQuery.value) params.search = searchQuery.value
  if (roleFilter.value) params.role = roleFilter.value
  if (statusFilter.value === 'active') params.is_active = true
  if (statusFilter.value === 'inactive') params.is_active = false
  if (statusFilter.value === 'unverified') params.email_verified = false
  if (statusFilter.value === 'verified') params.email_verified = true
  return params
}

async function reload(targetPage?: number) {
  if (typeof targetPage === 'number') page.value = targetPage
  loading.value = true
  error.value = ''
  try {
    const res = await usersApi.getUsers(buildParams())
    users.value = res.users || []
    total.value = res.total || 0
    const maxPage = Math.max(1, Math.ceil(total.value / pageSize.value))
    if (page.value > maxPage) {
      page.value = maxPage
      await reload()
    }
  } catch (err) {
    error.value = describeError(err)
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    stats.value = await usersApi.getUserStats()
  } catch {
    stats.value = null
  }
}

function refreshAll() {
  void loadStats()
  void reload()
}

let searchTimer: ReturnType<typeof setTimeout> | undefined

function onSearchInput(value: string) {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    searchQuery.value = value.trim()
    void reload(1)
  }, 320)
}

function applySearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchQuery.value = searchInput.value.trim()
  void reload(1)
}

function clearFilters() {
  searchInput.value = ''
  searchQuery.value = ''
  roleFilter.value = null
  statusFilter.value = null
  sortBy.value = 'created_at_desc'
  void reload(1)
}

function onPageChange(next: number) {
  page.value = next
  void reload()
}

function onPageSizeChange(size: number) {
  pageSize.value = size
  void reload(1)
}

function describeError(err: unknown) {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return '登录已过期，请重新登录后再试。'
  if (status === 403) return '当前账号没有用户管理权限（仅管理员可用）。'
  if (!status) return '网络连接失败，请检查网络后重试。'
  return `请求失败（HTTP ${status}），请稍后重试。`
}

/* ---------- 弹窗 ---------- */
const createOpen = ref(false)
const editOpen = ref(false)
const roleOpen = ref(false)
const resetOpen = ref(false)
const permissionOpen = ref(false)
const activeUser = ref<User | null>(null)
const createFormRef = ref<FormInst | null>(null)

const createForm = reactive<UserCreateRequest & { username?: string; display_name?: string }>({
  student_id: '',
  email: '',
  full_name: '',
  username: '',
  display_name: '',
  password: '',
  role: 'user',
})

const createRules = {
  student_id: [{ required: true, message: '请输入学号/工号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入初始密码', trigger: 'blur' }],
}

const editForm = reactive<UserUpdateRequest>({
  student_id: '',
  email: '',
  full_name: '',
})

const roleDraft = ref<UserRole>('user')
const resetDraft = ref('')
const resetError = ref('')

function resetCreateForm() {
  createForm.student_id = ''
  createForm.email = ''
  createForm.full_name = ''
  createForm.username = ''
  createForm.display_name = ''
  createForm.password = ''
  createForm.role = 'user'
}

function openCreate() {
  resetCreateForm()
  createOpen.value = true
}

async function submitCreate() {
  if (!createFormRef.value) return
  try {
    await createFormRef.value.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    await usersApi.createUser({
      student_id: createForm.student_id,
      email: createForm.email,
      full_name: createForm.full_name,
      username: createForm.username,
      display_name: createForm.display_name,
      password: createForm.password,
      role: createForm.role,
    })
    message.success('用户已创建')
    createOpen.value = false
    refreshAll()
  } catch (err) {
    message.error(describeError(err))
  } finally {
    submitting.value = false
  }
}

function openEdit(row: User) {
  activeUser.value = row
  editForm.student_id = row.student_id || ''
  editForm.email = row.email || ''
  editForm.full_name = row.full_name || ''
  editOpen.value = true
}

async function submitEdit() {
  if (!activeUser.value) return
  const target = activeUser.value
  submitting.value = true
  try {
    await usersApi.updateUser(target.id, editForm)
    message.success('资料已更新')
    editOpen.value = false
    refreshAll()
  } catch (err) {
    message.error(describeError(err))
  } finally {
    submitting.value = false
  }
}

function openRole(row: User) {
  activeUser.value = row
  roleDraft.value = row.role
  roleOpen.value = true
}

async function submitRole() {
  if (!activeUser.value) return
  if (roleDraft.value === activeUser.value.role) {
    roleOpen.value = false
    return
  }
  submitting.value = true
  try {
    await usersApi.updateUserRole(activeUser.value.id, roleDraft.value)
    message.success('角色已更新')
    roleOpen.value = false
    refreshAll()
  } catch (err) {
    message.error(describeError(err))
  } finally {
    submitting.value = false
  }
}

function openReset(row: User) {
  activeUser.value = row
  resetDraft.value = ''
  resetError.value = ''
  resetOpen.value = true
}

async function submitReset() {
  if (!activeUser.value) return
  if (resetDraft.value.length < 8) {
    resetError.value = '密码至少 8 位'
    return
  }
  submitting.value = true
  try {
    await usersApi.resetUserPassword(activeUser.value.id, resetDraft.value)
    message.success('密码已重置，请通知用户使用新密码登录')
    resetOpen.value = false
    refreshAll()
  } catch (err) {
    resetError.value = describeError(err)
  } finally {
    submitting.value = false
  }
}

async function toggleActive(row: User) {
  const next = !row.is_active
  dialog.warning({
    title: next ? '启用账号' : '禁用账号',
    content: next
      ? `确定启用「${displayNameOf(row)}」吗？启用后即可正常登录。`
      : `确定禁用「${displayNameOf(row)}」吗？该账号将无法登录，但数据保留。`,
    positiveText: next ? '启用' : '禁用',
    negativeText: '取消',
    onPositiveClick: async () => {
      submitting.value = true
      try {
        await usersApi.updateUser(row.id, { is_active: next })
        message.success(next ? '账号已启用' : '账号已禁用')
        refreshAll()
      } catch (err) {
        message.error(describeError(err))
      } finally {
        submitting.value = false
      }
    },
  })
}

async function verifyEmail(row: User) {
  submitting.value = true
  try {
    await usersApi.verifyUserEmail(row.id)
    message.success('邮箱已标记为已验证')
    refreshAll()
  } catch (err) {
    message.error(describeError(err))
  } finally {
    submitting.value = false
  }
}

function handleDelete(row: User) {
  dialog.error({
    title: '删除用户',
    content: `确定删除「${displayNameOf(row)}」吗？此操作不可恢复，其作品数据不会自动删除。`,
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      submitting.value = true
      try {
        await usersApi.deleteUser(row.id)
        message.success('用户已删除')
        refreshAll()
      } catch (err) {
        message.error(describeError(err))
      } finally {
        submitting.value = false
      }
    },
  })
}

function actionsFor(row: User) {
  const options = [
    { label: '调整角色', key: 'role' },
    { label: row.is_active ? '禁用账号' : '启用账号', key: 'toggle' },
    { label: '重置密码', key: 'reset' },
    { label: '编辑资料', key: 'edit' },
    { label: '权限授权', key: 'permission' },
    ...(row.email_verified ? [] : [{ label: '标记邮箱已验证', key: 'verify' }]),
  ]
  if (row.id !== selfId.value) {
    options.push({ label: '删除用户', key: 'delete' })
  }
  return options
}

function onAction(key: string, row: User) {
  if (key === 'role') return openRole(row)
  if (key === 'toggle') return toggleActive(row)
  if (key === 'reset') return openReset(row)
  if (key === 'edit') return openEdit(row)
  if (key === 'permission') return openPermission(row)
  if (key === 'verify') return verifyEmail(row)
  if (key === 'delete') return handleDelete(row)
}

/* ---------- 权限管理（沿用原有接口） ---------- */
const permissionLoading = ref(false)
const userPermissions = ref<PermissionResponse[]>([])
const permissionForm = reactive<PermissionGrantRequest>({
  student_id: '',
  resource_type: 'category',
  resource_key: 'Portrait',
  permission_type: 'view',
  days: 30,
  note: '',
})

const permissionColumns: DataTableColumns<PermissionResponse> = [
  { title: '资源类型', key: 'resource_type', width: 120 },
  { title: '资源', key: 'resource_key', width: 120 },
  { title: '权限', key: 'permission_type', width: 90 },
  { title: '到期', key: 'end_time', render: (row: PermissionResponse) => (row.end_time ? formatDate(row.end_time, 'YYYY-MM-DD') : '长期') },
  { title: '状态', key: 'is_active', render: (row: PermissionResponse) => (row.is_active ? '生效中' : '已失效') },
  {
    title: '操作',
    key: 'actions',
    render: (row: PermissionResponse) =>
      h(
        NButton,
        {
          size: 'small',
          type: 'error',
          onClick: () => revokePermission(row),
        },
        { default: () => '撤销' },
      ),
  },
]

async function openPermission(row: User) {
  activeUser.value = row
  permissionOpen.value = true
  permissionForm.student_id = row.student_id || ''
  if (!row.student_id) {
    message.warning('该用户没有学号信息，无法查询权限')
    return
  }
  permissionLoading.value = true
  try {
    const res = await permissionApi.getUserPermissions(row.student_id)
    userPermissions.value = res.permissions || []
  } catch (err) {
    message.error(describeError(err))
    userPermissions.value = []
  } finally {
    permissionLoading.value = false
  }
}

async function handleGrantPermission() {
  if (!activeUser.value) return
  submitting.value = true
  try {
    await permissionApi.grantPermission(permissionForm)
    message.success('权限已授予')
    await openPermission(activeUser.value)
  } catch (err) {
    message.error(describeError(err))
  } finally {
    submitting.value = false
  }
}

async function revokePermission(row: PermissionResponse) {
  dialog.warning({
    title: '撤销权限',
    content: `确定撤销「${row.resource_type} / ${row.resource_key}」的 ${row.permission_type} 权限吗？`,
    positiveText: '撤销',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await permissionApi.revokePermission(row.id)
        message.success('权限已撤销')
        if (activeUser.value) await openPermission(activeUser.value)
      } catch (err) {
        message.error(describeError(err))
      }
    },
  })
}

/* ---------- 生命周期 ---------- */
let mediaQuery: MediaQueryList | null = null
function syncNarrow(event: MediaQueryListEvent | MediaQueryList) {
  isNarrow.value = event.matches
}

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 1100px)')
  syncNarrow(mediaQuery)
  mediaQuery.addEventListener('change', syncNarrow)
  refreshAll()
})

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener('change', syncNarrow)
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<style scoped>
.admin-users {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.eyebrow {
  margin: 0 0 6px;
  font-size: 11px;
  letter-spacing: 0.18em;
  color: var(--sakura-deep, #c93a63);
  font-weight: 600;
}

.page-title {
  margin: 0;
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: clamp(28px, 3vw, 34px);
  letter-spacing: 0.02em;
  color: var(--ink, #4a2b35);
}

.page-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--muted, #63474f);
}

.head-actions {
  display: flex;
  gap: 10px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.stat-card {
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  border-radius: 14px;
  padding: 14px 16px;
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.08));
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--muted, #63474f);
}

.stat-value {
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: 26px;
  line-height: 1.1;
  color: var(--ink, #4a2b35);
  font-variant-numeric: tabular-nums;
}

.stat-hint {
  font-size: 11px;
  color: var(--faint, #ad8e97);
}

.panel {
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  border-radius: 18px;
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.08));
  padding: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.toolbar-search {
  width: 280px;
}

.toolbar-select {
  width: 148px;
}

.toolbar-size {
  width: 120px;
}

.toolbar-spacer {
  flex: 1;
}

.toolbar-count {
  font-size: 12px;
  color: var(--muted, #63474f);
}

.toolbar-count strong {
  color: var(--sakura-deep, #c93a63);
  font-variant-numeric: tabular-nums;
}

.table-wrap {
  overflow-x: auto;
}

.user-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.user-table th {
  text-align: left;
  font-weight: 600;
  font-size: 12px;
  color: var(--muted, #63474f);
  padding: 10px 12px;
  border-bottom: 1px solid var(--line, #f3dde5);
  white-space: nowrap;
}

.user-table td {
  padding: 12px;
  border-bottom: 1px solid var(--sakura-wash, #ffe9f0);
  vertical-align: middle;
}

.user-table tbody tr:hover {
  background: var(--sakura-wash, #ffe9f0);
}

.user-table tbody tr.is-self {
  background: rgba(232, 98, 140, 0.06);
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.row-avatar {
  background: var(--sakura-pale, #ffe9f0);
  color: var(--sakura-deep, #c93a63);
  font-weight: 700;
}

.user-meta {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.user-title {
  color: var(--ink, #4a2b35);
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.self-tag {
  background: var(--sakura-pale, #ffe9f0);
  color: var(--sakura-deep, #c93a63);
}

.user-sub {
  font-size: 12px;
  color: var(--faint, #ad8e97);
}

.contact-line {
  display: flex;
  align-items: center;
  gap: 6px;
  line-height: 1.5;
}

.contact-line .mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--ink-soft, #6d4f58);
}

.email-text {
  font-size: 12px;
  color: var(--muted, #63474f);
  word-break: break-all;
}

.verified-icon {
  color: var(--summer, #3b9c80);
  font-size: 15px;
}

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}

.status-dot.is-on {
  background: var(--summer, #3b9c80);
}

.status-dot.is-off {
  background: var(--faint, #ad8e97);
}

.login-line {
  color: var(--ink-soft, #6d4f58);
  font-size: 12px;
}

.login-count {
  font-size: 11px;
  color: var(--faint, #ad8e97);
  font-variant-numeric: tabular-nums;
}

.col-created {
  color: var(--muted, #63474f);
  white-space: nowrap;
}

.col-actions {
  text-align: right;
}

.col-role,
.col-status {
  white-space: nowrap;
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

.state-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 56px 16px;
  text-align: center;
}

.state-icon {
  font-size: 34px;
  color: var(--sakura, #e8628c);
}

.state-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.state-desc {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--muted, #63474f);
}

.skeleton-list {
  display: flex;
  flex-direction: column;
}

.skeleton-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 12px;
  border-bottom: 1px solid var(--sakura-wash, #ffe9f0);
}

.sk {
  display: inline-block;
  height: 14px;
  border-radius: 7px;
  background: linear-gradient(90deg, #f8e7ec 25%, #fdeff4 50%, #f8e7ec 75%);
  background-size: 200% 100%;
  animation: sk-shimmer 1.2s infinite linear;
}

.sk-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
}

.sk-name {
  width: 140px;
}

.sk-line {
  flex: 1;
  max-width: 240px;
}

.sk-tag {
  width: 76px;
}

.sk-time {
  width: 110px;
}

@keyframes sk-shimmer {
  from {
    background-position: 200% 0;
  }
  to {
    background-position: -200% 0;
  }
}

.modal-card {
  width: min(640px, 94vw);
}

.modal-small {
  width: min(420px, 94vw);
}

.modal-desc {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--ink-soft, #6d4f58);
}

.modal-note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--faint, #ad8e97);
}

.modal-error {
  margin: 8px 0 0;
  font-size: 12px;
  color: #c0392b;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.panel :deep(.n-input),
.panel :deep(.n-base-selection) {
  border-radius: 10px;
}

@media (max-width: 1280px) {
  .stat-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .toolbar-search {
    width: 100%;
  }

  .toolbar-select,
  .toolbar-size {
    flex: 1;
    min-width: 132px;
  }

  .form-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .user-table {
    font-size: 12px;
  }

  .col-contact {
    min-width: 140px;
  }
}
@media (max-width: 700px) {
  .table-wrap {
    overflow-x: visible;
  }

  .user-table,
  .user-table tbody,
  .user-table tr,
  .user-table td {
    display: block;
    width: auto;
  }

  .user-table thead {
    display: none;
  }

  .user-table tbody tr {
    border: 1px solid var(--line, #f3dde5);
    border-radius: 14px;
    padding: 12px 14px;
    margin-bottom: 10px;
    background: var(--surface, #fff);
  }

  .user-table tbody tr:hover {
    background: var(--sakura-wash, #ffe9f0);
  }

  .user-table td {
    border: 0;
    padding: 3px 0;
  }

  .user-cell {
    margin-bottom: 4px;
  }

  .col-contact {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .email-text {
    word-break: normal;
    overflow-wrap: anywhere;
  }

  .col-role,
  .col-status,
  .col-login {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-right: 14px;
    font-size: 12px;
  }

  .col-actions {
    margin-top: 6px;
    text-align: left;
  }

  .col-actions :deep(.n-button) {
    width: 100%;
  }

  .toolbar-count {
    width: 100%;
    order: 5;
  }

  .toolbar-size {
    order: 6;
  }

  .pager {
    justify-content: center;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sk {
    animation: none;
  }
}
</style>
