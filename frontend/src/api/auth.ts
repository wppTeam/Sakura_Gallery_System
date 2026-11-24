/**
 * 认证相关 API
 */
import request from './index'
import type { LoginRequest, LoginResponse, User } from '../types/user'

/**
 * 用户登录
 */
export function login(data: LoginRequest): Promise<LoginResponse> {
  return request({
    url: '/api/v1/auth/login',
    method: 'post',
    data,
  })
}

/**
 * 获取当前用户信息
 */
export function getCurrentUser(): Promise<User> {
  return request({
    url: '/api/v1/auth/me',
    method: 'get',
  })
}

/**
 * 使用 Refresh Token 刷新 Access Token
 */
export function refreshToken(refresh_token: string): Promise<{ access_token: string; refresh_token: string; token_type: string }> {
  return request({
    url: '/api/v1/auth/refresh',
    method: 'post',
    data: { refresh_token },
  })
}

/**
 * 用户自助修改密码
 */
export function changePassword(old_password: string, new_password: string): Promise<{ detail: string }> {
  return request({
    url: '/api/v1/auth/password',
    method: 'put',
    data: { old_password, new_password },
  })
}

/**
 * 更新当前用户个人资料
 */
export function updateProfile(data: { email?: string; full_name?: string }): Promise<User> {
  return request({
    url: '/api/v1/user/profile',
    method: 'put',
    data,
  })
}

// ────────────────────────────────────────────────────────────
// 邮箱验证码 / 无密码登录 / 找回密码（2026-11 新增）
// ────────────────────────────────────────────────────────────

export type EmailCodePurpose = 'register' | 'login' | 'reset_password' | 'verify_email'

export interface EmailCodeResponse {
  ok: boolean
  /** 验证码有效期（秒） */
  expires_in: number
  /** 重发冷却（秒） */
  cooldown_seconds: number
  /** 后端是否真的投递了邮件（EMAIL_ENABLED=false 时为 false） */
  delivered: boolean
  /** 仅本地开发（EMAIL_ENABLED=false 且 DEBUG）返回，用于免邮箱联调 */
  dev_code?: string | null
}

export interface ForgotPasswordResponse {
  ok: boolean
  message: string
  cooldown_seconds: number
  dev_code?: string | null
}

/**
 * 发送邮箱验证码。
 * purpose: register | login | reset_password | verify_email
 */
export function sendEmailCode(data: { email: string; purpose: EmailCodePurpose }): Promise<EmailCodeResponse> {
  return request({
    url: '/api/v1/auth/email-code',
    method: 'post',
    data,
  })
}

export interface RegisterWithCodeRequest {
  student_id: string
  email: string
  email_code: string
  username?: string
  display_name?: string
  full_name?: string
  password: string
}

/**
 * 邮箱验证码注册（后端要求 email_code 必填）。
 */
export function register(data: RegisterWithCodeRequest): Promise<User> {
  return request({
    url: '/api/v1/auth/register',
    method: 'post',
    data,
  })
}

/**
 * 邮箱验证码登录（免密码）。
 */
export function loginWithCode(data: { email: string; code: string }): Promise<LoginResponse> {
  return request({
    url: '/api/v1/auth/login-with-code',
    method: 'post',
    data,
  })
}

/**
 * 忘记密码：向绑定邮箱（或按学号/用户名解析出的邮箱）发送重置验证码。
 */
export function forgotPassword(data: { identifier: string }): Promise<ForgotPasswordResponse> {
  return request({
    url: '/api/v1/auth/password/forgot',
    method: 'post',
    data,
  })
}

/**
 * 重置密码（需验证码）。
 */
export function resetPassword(data: {
  identifier: string
  code: string
  new_password: string
}): Promise<{ detail: string }> {
  return request({
    url: '/api/v1/auth/password/reset',
    method: 'post',
    data,
  })
}
