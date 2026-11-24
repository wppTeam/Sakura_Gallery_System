/**
 * 后台「审核复核（申诉）」管理 API。
 *
 * 契约（admin/auditor）：
 * - GET  /api/v1/admin/appeals?status=&limit=&offset=
 * - GET  /api/v1/admin/appeals/stats?days=7
 * - POST /api/v1/admin/appeals/{id}/resolve  body {decision: accept|reject, note?}
 */
import request from './index'
import { getImageUrl } from '../utils/format'

export type AppealStatus = 'pending' | 'accepted' | 'rejected'
export type AppealDecision = 'accept' | 'reject'

export interface AdminAppealItem {
  id: string
  photoId: string
  photoTitle: string
  thumbUrl: string | null
  uploaderUsername: string | null
  uploaderDisplayName: string | null
  reason: string
  status: AppealStatus
  note: string | null
  createdAt: string | null
  handledAt: string | null
  raw: Record<string, unknown>
}

export interface AdminAppealStats {
  total: number
  pending: number
  accepted: number
  rejected: number
  last7Days: number
}

export interface AdminAppealQuery {
  status?: AppealStatus
  limit?: number
  offset?: number
}

export interface AdminAppealPage {
  items: AdminAppealItem[]
  total: number
}

export interface ResolveAppealPayload {
  decision: AppealDecision
  note?: string
}

export interface ResolveAppealResult {
  ok: boolean
  status: string
  message: string
}

export const APPEAL_STATUS_LABELS: Record<AppealStatus, string> = {
  pending: '待处理',
  accepted: '已受理',
  rejected: '已驳回',
}

const APPEAL_STATUSES: AppealStatus[] = ['pending', 'accepted', 'rejected']

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function textOf(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  return ''
}

function nullableText(value: unknown): string | null {
  const text = textOf(value).trim()
  return text ? text : null
}

function toNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return 0
}

function normalizeStatus(value: unknown): AppealStatus {
  const text = textOf(value)
  return APPEAL_STATUSES.includes(text as AppealStatus) ? (text as AppealStatus) : 'pending'
}

function resolveThumbUrl(value: unknown): string | null {
  const text = textOf(value).trim()
  if (!text) return null
  if (/^(https?:)?\/\//.test(text) || text.startsWith('data:') || text.startsWith('blob:')) return text
  return getImageUrl(text)
}

export function normalizeAdminAppeal(raw: unknown): AdminAppealItem | null {
  if (!isRecord(raw)) return null
  const id = textOf(raw.id)
  if (!id) return null
  return {
    id,
    photoId: textOf(raw.photo_id),
    photoTitle: textOf(raw.photo_title) || '未命名作品',
    thumbUrl: resolveThumbUrl(raw.thumb_url),
    uploaderUsername: nullableText(raw.uploader_username),
    uploaderDisplayName: nullableText(raw.uploader_display_name),
    reason: textOf(raw.reason),
    status: normalizeStatus(raw.status),
    note: nullableText(raw.note),
    createdAt: nullableText(raw.created_at),
    handledAt: nullableText(raw.handled_at),
    raw,
  }
}

function extractItems(data: unknown): AdminAppealItem[] {
  if (Array.isArray(data)) return data.map(normalizeAdminAppeal).filter((item): item is AdminAppealItem => item !== null)
  if (isRecord(data)) {
    const candidates = [data.items, data.appeals, data.results, data.data]
    for (const candidate of candidates) {
      if (Array.isArray(candidate)) {
        return candidate.map(normalizeAdminAppeal).filter((item): item is AdminAppealItem => item !== null)
      }
    }
  }
  return []
}

export function normalizeAdminAppealStats(raw: unknown): AdminAppealStats {
  const data = isRecord(raw) ? raw : {}
  return {
    total: toNumber(data.total),
    pending: toNumber(data.pending),
    accepted: toNumber(data.accepted),
    rejected: toNumber(data.rejected),
    last7Days: toNumber(data.last_7_days),
  }
}

export async function fetchAdminAppeals(query: AdminAppealQuery = {}): Promise<AdminAppealPage> {
  const params: Record<string, unknown> = {
    limit: query.limit ?? 20,
    offset: query.offset ?? 0,
  }
  if (query.status) params.status = query.status
  const data = await request.get<unknown>('/api/v1/admin/appeals', { params, timeout: 30000 })
  const record = isRecord(data) ? data : {}
  return {
    items: extractItems(data),
    total: toNumber(record.total) || 0,
  }
}

export async function fetchAdminAppealStats(days = 7): Promise<AdminAppealStats> {
  const data = await request.get<unknown>('/api/v1/admin/appeals/stats', {
    params: { days },
    timeout: 30000,
  })
  return normalizeAdminAppealStats(data)
}

export async function resolveAdminAppeal(
  appealId: string,
  payload: ResolveAppealPayload,
): Promise<ResolveAppealResult> {
  const body: Record<string, unknown> = { decision: payload.decision }
  const note = payload.note?.trim()
  if (note) body.note = note
  const data = await request.post<Record<string, unknown>>(
    `/api/v1/admin/appeals/${encodeURIComponent(appealId)}/resolve`,
    body,
    { timeout: 60000 },
  )
  return {
    ok: data?.ok !== false,
    status: textOf(data?.status),
    message: textOf(data?.message),
  }
}

// ---------------------------------------------------------------------------
// 后台缩略图：被驳回作品的缩略图对匿名不可见（后端按 status 判定 404），
// <img> 无法带 Authorization，所以用 fetch + blob URL 拉取。
// 同一 URL 只请求一次，objectURL 在页面生命周期内复用。
// ---------------------------------------------------------------------------
const thumbCache = new Map<string, string>()

export async function fetchAdminThumbUrl(raw: string | null): Promise<string | null> {
  if (!raw) return null
  const url = getImageUrl(raw)
  const cached = thumbCache.get(url)
  if (cached) return cached
  const token = localStorage.getItem('auth_token') || sessionStorage.getItem('auth_token')
  try {
    const res = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) return null
    const blob = await res.blob()
    const objectUrl = URL.createObjectURL(blob)
    thumbCache.set(url, objectUrl)
    return objectUrl
  } catch {
    return null
  }
}
