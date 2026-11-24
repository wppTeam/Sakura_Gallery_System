/**
 * 认证状态管理
 *
 * 包含用户登录状态、角色权限判断、Token 自动刷新等功能。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { LoginResponse, User, UserRole } from '../types/user'
import * as authApi from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  // 状态
  const user = ref<User | null>(null)
  const token = ref<string | null>(null)
  const refreshTokenValue = ref<string | null>(null)

  // 计算属性
  const isAuthenticated = computed(() => !!token.value)

  /**
   * 是否为超级管理员
   */
  const isAdmin = computed(() => user.value?.role === 'admin')

  /**
   * 是否为审核员（包含管理员）
   * 用于内容审核相关能力，不代表拥有系统管理权限。
   */
  const isAuditor = computed(() =>
    user.value?.role === 'admin' || user.value?.role === 'auditor'
  )

  const isTagger = computed(() =>
    user.value?.role === 'admin' || user.value?.role === 'auditor' || user.value?.role === 'tagger'
  )

  /**
   * 是否有审核权限（管理员或审核员）
   */
  const canReview = computed(() => isAuditor.value)

  /**
   * 检查用户是否拥有指定角色
   */
  function hasRole(role: UserRole | UserRole[]): boolean {
    if (!user.value) return false
    if (Array.isArray(role)) {
      return role.includes(user.value.role)
    }
    return user.value.role === role
  }

  /**
   * 初始化只执行一次（App.vue 与路由守卫都会调用），返回同一个 Promise，
   * 让守卫可以 await 到「用户信息已回填」之后再判断角色权限。
   */
  let initPromise: Promise<void> | null = null

  async function restoreSession(): Promise<void> {
    let storedToken = localStorage.getItem('auth_token')
    let storedRefreshToken = localStorage.getItem('refresh_token')
    // 兼容未勾选"记住我"时存储在 sessionStorage 的情况
    if (!storedToken) {
      storedToken = sessionStorage.getItem('auth_token')
      storedRefreshToken = sessionStorage.getItem('refresh_token')
    }
    if (!storedToken) return

    token.value = storedToken
    refreshTokenValue.value = storedRefreshToken
    try {
      // 尝试获取用户信息
      await fetchCurrentUser()
    } catch {
      // Access Token 可能过期，尝试刷新
      if (storedRefreshToken) {
        try {
          await refreshAccessToken()
        } catch {
          logout()
        }
      } else {
        logout()
      }
    }
  }

  // 从 localStorage / sessionStorage 初始化（幂等）
  function initFromStorage(): Promise<void> {
    if (!initPromise) initPromise = restoreSession()
    return initPromise
  }

  /**
   * 等待本地会话恢复完成；未初始化时主动触发。路由守卫在判断角色权限前必须 await。
   */
  function whenReady(): Promise<void> {
    return initFromStorage()
  }

  /**
   * 写入会话：remember=true 存 localStorage（长期），false 存 sessionStorage（关标签页即失效）。
   * 两处互斥，避免旧 token 残留导致「记住我」失效。
   */
  function persistSession(response: LoginResponse, remember = true) {
    token.value = response.access_token
    refreshTokenValue.value = response.refresh_token
    user.value = response.user

    const storage = remember ? localStorage : sessionStorage
    const other = remember ? sessionStorage : localStorage
    other.removeItem('auth_token')
    other.removeItem('refresh_token')
    storage.setItem('auth_token', response.access_token)
    storage.setItem('refresh_token', response.refresh_token)
  }

  // 用户登录（支持学号 / 邮箱 / 用户名）
  async function login(identifier: string, password: string, remember = true) {
    const response = await authApi.login({ identifier, password })
    persistSession(response, remember)
    return response
  }

  /**
   * 邮箱验证码登录（免密码）。
   */
  async function loginWithCode(email: string, code: string, remember = true) {
    const response = await authApi.loginWithCode({ email, code })
    persistSession(response, remember)
    return response
  }

  // 用户登出
  function logout() {
    user.value = null
    token.value = null
    refreshTokenValue.value = null
    localStorage.removeItem('auth_token')
    localStorage.removeItem('refresh_token')
    sessionStorage.removeItem('auth_token')
    sessionStorage.removeItem('refresh_token')
  }

  // 获取当前用户信息
  async function fetchCurrentUser() {
    const userData = await authApi.getCurrentUser()
    user.value = userData
    return userData
  }

  /**
   * 使用 Refresh Token 刷新 Access Token
   *
   * 刷新成功后更新 localStorage 和内存中的 Token。
   */
  async function refreshAccessToken() {
    if (!refreshTokenValue.value) {
      throw new Error('No refresh token available')
    }

    const response = await authApi.refreshToken(refreshTokenValue.value)
    token.value = response.access_token
    refreshTokenValue.value = response.refresh_token

    localStorage.setItem('auth_token', response.access_token)
    localStorage.setItem('refresh_token', response.refresh_token)

    // 刷新后重新获取用户信息
    await fetchCurrentUser()

    return response
  }

  return {
    user,
    token,
    refreshTokenValue,
    isAuthenticated,
    isAdmin,
    isAuditor,
    isTagger,
    canReview,
    hasRole,
    initFromStorage,
    whenReady,
    login,
    loginWithCode,
    logout,
    fetchCurrentUser,
    refreshAccessToken,
  }
})
