/**
 * 后台一屏概览 API（admin + auditor）。
 *
 * 后端 `GET /api/v1/admin/overview`：待办计数 + 作品 / 用户 / 生图 / AI 成本概览。
 * 图表数据仍走 `GET /api/v1/stats/dashboard`。
 */
import request from './index'

export interface OverviewTodos {
  reviewPending: number
  moderationPendingHuman: number
  reportsPending: number
  appealsPending: number
}

export interface OverviewPhotos {
  total: number
  approved: number
  pending: number
  rejected: number
  views: number
  storageBytes: number
}

export interface OverviewUsers {
  total: number
  active: number
  new7Days: number
  emailUnverified: number
}

export interface OverviewRecentLogin {
  id: string
  username: string | null
  displayName: string | null
  role: string
  lastLoginAt: string | null
  loginCount: number
}

export interface OverviewAigc {
  todayTotal: number
  todaySucceeded: number
  todayFailed: number
  cost7d: number
  bonusRemaining: number
}

export interface OverviewTopPhoto {
  id: string
  title: string | null
  views: number
  thumbUrl: string
}

export interface AdminOverview {
  role: string
  todos: OverviewTodos
  photos: OverviewPhotos
  users: OverviewUsers
  recentLogins: OverviewRecentLogin[]
  aigc: OverviewAigc
  aiCost7d: number
  topPhotos: OverviewTopPhoto[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function num(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

export async function getAdminOverview(): Promise<AdminOverview> {
  const response = await request.get<unknown>('/api/v1/admin/overview')
  const data = isRecord(response) ? response : {}
  const todos = isRecord(data.todos) ? data.todos : {}
  const photos = isRecord(data.photos) ? data.photos : {}
  const users = isRecord(data.users) ? data.users : {}
  const aigc = isRecord(data.aigc) ? data.aigc : {}
  return {
    role: text(data.role) ?? 'auditor',
    todos: {
      reviewPending: num(todos.review_pending),
      moderationPendingHuman: num(todos.moderation_pending_human),
      reportsPending: num(todos.reports_pending),
      appealsPending: num(todos.appeals_pending),
    },
    photos: {
      total: num(photos.total),
      approved: num(photos.approved),
      pending: num(photos.pending),
      rejected: num(photos.rejected),
      views: num(photos.views),
      storageBytes: num(photos.storage_bytes),
    },
    users: {
      total: num(users.total),
      active: num(users.active),
      new7Days: num(users.new_7_days),
      emailUnverified: num(users.email_unverified),
    },
    recentLogins: (Array.isArray(data.recent_logins) ? data.recent_logins : [])
      .filter(isRecord)
      .map((item) => ({
        id: text(item.id) ?? '',
        username: text(item.username),
        displayName: text(item.display_name),
        role: text(item.role) ?? 'user',
        lastLoginAt: text(item.last_login_at),
        loginCount: num(item.login_count),
      })),
    aigc: {
      todayTotal: num(aigc.today_total),
      todaySucceeded: num(aigc.today_succeeded),
      todayFailed: num(aigc.today_failed),
      cost7d: num(aigc.cost_7d),
      bonusRemaining: num(aigc.bonus_remaining),
    },
    aiCost7d: num(data.ai_cost_7d),
    topPhotos: (Array.isArray(data.top_photos) ? data.top_photos : [])
      .filter(isRecord)
      .map((item) => ({
        id: text(item.id) ?? '',
        title: text(item.title),
        views: num(item.views),
        thumbUrl: text(item.thumb_url) ?? '',
      }))
      .filter((item) => item.id),
  }
}