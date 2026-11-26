/**
 * AI 生图后台管理 API（仅超级管理员）。
 *
 * 后端 `/api/v1/admin/aigc/*`：总览、生成记录、额度赠送台账、按人赠送 / 撤销。
 * 额度口径与作者端一致：每日基础额度 + 赠送池，失败不计。
 */
import request from './index'
import { normalizeAigcQuota, type AigcQuota } from './aigc'

const BASE_URL = '/api/v1/admin/aigc'

export interface AigcUserBrief {
  id: string
  username: string | null
  displayName: string | null
  email: string | null
  studentId: string | null
}

export interface AigcTotals {
  total: number
  succeeded: number
  failed: number
  pending: number
  costUsd: number
  avgLatencyMs: number
  successRate: number
}

export interface AigcDayBucket {
  day: string
  total: number
  succeeded: number
  failed: number
  costUsd: number
}

export interface AigcTopUser {
  user: AigcUserBrief
  total: number
  succeeded: number
  costUsd: number
}

export interface AigcQuotaSummary {
  grantCount: number
  recipients: number
  grantedTotal: number
  bonusUsed: number
  bonusRemaining: number
}

export interface AigcOverview {
  days: number
  baseDailyLimit: number
  totals: AigcTotals
  today: AigcTotals
  byDay: AigcDayBucket[]
  topUsers: AigcTopUser[]
  quota: AigcQuotaSummary
}

export interface AigcGenerationAdminItem {
  id: string
  user: AigcUserBrief
  prompt: string
  sizeKey: string
  status: string
  quotaSource: string
  modelId: string
  width: number | null
  height: number | null
  latencyMs: number | null
  costUsd: number
  error: string | null
  imageUrl: string | null
  createdAt: string
  finishedAt: string | null
}

export interface AigcGenerationAdminList {
  items: AigcGenerationAdminItem[]
  total: number
  skip: number
  limit: number
}

export interface AigcGrantItem {
  id: string
  user: AigcUserBrief
  amount: number
  reason: string | null
  grantedBy: string | null
  grantedByName: string | null
  createdAt: string
}

export interface AigcGrantList {
  items: AigcGrantItem[]
  total: number
  skip: number
  limit: number
}

export interface AigcUserQuota {
  user: AigcUserBrief
  quota: AigcQuota
  grants: AigcGrantItem[]
  recent: AigcGenerationAdminItem[]
}

export interface AigcGenerationQuery {
  skip?: number
  limit?: number
  status?: string
  quotaSource?: string
  userId?: string
  search?: string
  days?: number
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

function normalizeUser(raw: unknown): AigcUserBrief {
  const data = isRecord(raw) ? raw : {}
  return {
    id: text(data.id) ?? '',
    username: text(data.username),
    displayName: text(data.display_name),
    email: text(data.email),
    studentId: text(data.student_id),
  }
}

function normalizeTotals(raw: unknown): AigcTotals {
  const data = isRecord(raw) ? raw : {}
  return {
    total: num(data.total),
    succeeded: num(data.succeeded),
    failed: num(data.failed),
    pending: num(data.pending),
    costUsd: num(data.cost_usd),
    avgLatencyMs: num(data.avg_latency_ms),
    successRate: num(data.success_rate),
  }
}

function normalizeGeneration(raw: unknown): AigcGenerationAdminItem | null {
  if (!isRecord(raw)) return null
  const id = text(raw.id)
  if (!id) return null
  return {
    id,
    user: normalizeUser(raw.user),
    prompt: text(raw.prompt) ?? '',
    sizeKey: text(raw.size_key) ?? 'square',
    status: text(raw.status) ?? 'queued',
    quotaSource: text(raw.quota_source) ?? 'daily',
    modelId: text(raw.model_id) ?? '',
    width: raw.width == null ? null : num(raw.width),
    height: raw.height == null ? null : num(raw.height),
    latencyMs: raw.latency_ms == null ? null : num(raw.latency_ms),
    costUsd: num(raw.cost_usd),
    error: text(raw.error),
    imageUrl: text(raw.image_url),
    createdAt: text(raw.created_at) ?? '',
    finishedAt: text(raw.finished_at),
  }
}

function normalizeGrant(raw: unknown): AigcGrantItem | null {
  if (!isRecord(raw)) return null
  const id = text(raw.id)
  if (!id) return null
  return {
    id,
    user: normalizeUser(raw.user),
    amount: num(raw.amount),
    reason: text(raw.reason),
    grantedBy: text(raw.granted_by),
    grantedByName: text(raw.granted_by_name),
    createdAt: text(raw.created_at) ?? '',
  }
}

function mapItems<T>(raw: unknown, normalize: (item: unknown) => T | null): T[] {
  if (!Array.isArray(raw)) return []
  return raw.map(normalize).filter((item): item is T => item !== null)
}

export async function getAigcOverview(days = 30): Promise<AigcOverview> {
  const response = await request.get<unknown>(`${BASE_URL}/overview`, { params: { days } })
  const data = isRecord(response) ? response : {}
  const quota = isRecord(data.quota) ? data.quota : {}
  return {
    days: num(data.days, days),
    baseDailyLimit: num(data.base_daily_limit, 3),
    totals: normalizeTotals(data.totals),
    today: normalizeTotals(data.today),
    byDay: mapItems(data.by_day, (raw) => {
      if (!isRecord(raw)) return null
      return {
        day: text(raw.day) ?? '',
        total: num(raw.total),
        succeeded: num(raw.succeeded),
        failed: num(raw.failed),
        costUsd: num(raw.cost_usd),
      }
    }),
    topUsers: mapItems(data.top_users, (raw) => {
      if (!isRecord(raw)) return null
      return {
        user: normalizeUser(raw.user),
        total: num(raw.total),
        succeeded: num(raw.succeeded),
        costUsd: num(raw.cost_usd),
      }
    }),
    quota: {
      grantCount: num(quota.grant_count),
      recipients: num(quota.recipients),
      grantedTotal: num(quota.granted_total),
      bonusUsed: num(quota.bonus_used),
      bonusRemaining: num(quota.bonus_remaining),
    },
  }
}

export async function listAigcGenerationsAdmin(
  query: AigcGenerationQuery = {},
): Promise<AigcGenerationAdminList> {
  const params: Record<string, unknown> = {
    skip: query.skip ?? 0,
    limit: query.limit ?? 20,
  }
  if (query.status) params.status = query.status
  if (query.quotaSource) params.quota_source = query.quotaSource
  if (query.userId) params.user_id = query.userId
  if (query.search?.trim()) params.search = query.search.trim()
  if (query.days) params.days = query.days
  const response = await request.get<unknown>(`${BASE_URL}/generations`, { params })
  const data = isRecord(response) ? response : {}
  const items = mapItems(data.items, normalizeGeneration)
  return {
    items,
    total: num(data.total, items.length),
    skip: num(data.skip),
    limit: num(data.limit, items.length),
  }
}

export async function listAigcGrants(query: { skip?: number; limit?: number; userId?: string } = {}): Promise<AigcGrantList> {
  const params: Record<string, unknown> = { skip: query.skip ?? 0, limit: query.limit ?? 20 }
  if (query.userId) params.user_id = query.userId
  const response = await request.get<unknown>(`${BASE_URL}/grants`, { params })
  const data = isRecord(response) ? response : {}
  const items = mapItems(data.items, normalizeGrant)
  return { items, total: num(data.total, items.length), skip: num(data.skip), limit: num(data.limit) }
}

export async function getAigcUserQuota(userId: string): Promise<AigcUserQuota> {
  const response = await request.get<unknown>(`${BASE_URL}/users/${encodeURIComponent(userId)}/quota`)
  const data = isRecord(response) ? response : {}
  return {
    user: normalizeUser(data.user),
    quota: normalizeAigcQuota(data.quota),
    grants: mapItems(data.grants, normalizeGrant),
    recent: mapItems(data.recent, normalizeGeneration),
  }
}

export async function grantAigcQuota(userId: string, amount: number, reason?: string): Promise<AigcGrantItem> {
  const response = await request.post<unknown>(
    `${BASE_URL}/users/${encodeURIComponent(userId)}/grants`,
    { amount, reason: reason?.trim() || undefined },
  )
  const grant = normalizeGrant(response)
  if (!grant) throw new Error('赠送失败：服务器返回数据异常')
  return grant
}

export async function revokeAigcGrant(grantId: string): Promise<void> {
  await request.delete(`${BASE_URL}/grants/${encodeURIComponent(grantId)}`)
}