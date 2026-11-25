/**
 * 公共端「我的投稿」作者工作台 API。
 *
 * 契约（均需登录，作者本人）：
 * - GET  /api/v1/photos/my-submissions/stats
 *        → {total, pending, approved, rejected, pending_appeal}
 * - GET  /api/v1/photos/my-submissions?skip&limit&status&search
 *        → {items, total, page, page_size}（item 是 admin 序列化，不含 thumb_url）
 * - DELETE /api/v1/photos/{photo_id} → 204（后端会清理原图/缩略图/变体/脱敏图）
 *
 * 缩略图坑：待审 / 被驳回作品的 `/image/thumbnail` 对匿名 404，`<img>` 无法带
 * Authorization，因此统一走 `fetchSubmissionThumbUrl()`：fetch + Bearer 拉 blob →
 * objectURL，并缓存 / 合并同一张图的并发请求。已通过作品也走同一 helper，避免两套逻辑。
 */
import request from './index'
import { getImageUrl } from '../utils/format'

export type SubmissionStatus = 'pending' | 'approved' | 'rejected'

export interface MySubmissionStats {
  total: number
  pending: number
  approved: number
  rejected: number
  /** 被驳回且已提交复核、等待受理的作品数 */
  pendingAppeal: number
}

export interface MySubmissionItem {
  id: string
  title: string
  filename: string
  status: SubmissionStatus
  kind: string
  isAigc: boolean
  aigcLabel: string | null
  thumbPath: string | null
  lqip: string | null
  lqipColor: string | null
  season: string | null
  category: string | null
  campus: string | null
  capturedAt: string | null
  createdAt: string | null
  description: string | null
  privacyLevel: string | null
}

export interface MySubmissionQuery {
  skip?: number
  limit?: number
  status?: SubmissionStatus
  search?: string
}

export interface MySubmissionPage {
  items: MySubmissionItem[]
  total: number
  page: number
  pageSize: number
}

const STATUSES: SubmissionStatus[] = ['pending', 'approved', 'rejected']

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

function normalizeStatus(value: unknown): SubmissionStatus {
  const text = textOf(value)
  return STATUSES.includes(text as SubmissionStatus) ? (text as SubmissionStatus) : 'pending'
}

function normalizeCount(value: unknown): number {
  const num = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(num) && num >= 0 ? Math.floor(num) : 0
}

export function normalizeMySubmission(raw: unknown): MySubmissionItem | null {
  if (!isRecord(raw)) return null
  const id = textOf(raw.id)
  if (!id) return null
  return {
    id,
    title: textOf(raw.title),
    filename: textOf(raw.filename),
    status: normalizeStatus(raw.status),
    kind: textOf(raw.kind) || 'photo',
    isAigc: raw.is_aigc === true || raw.kind === 'aigc',
    aigcLabel: nullableText(raw.aigc_label),
    thumbPath: nullableText(raw.thumb_path),
    lqip: nullableText(raw.lqip),
    lqipColor: nullableText(raw.lqip_color),
    season: nullableText(raw.season),
    category: nullableText(raw.category),
    campus: nullableText(raw.campus),
    capturedAt: nullableText(raw.captured_at),
    createdAt: nullableText(raw.created_at),
    description: nullableText(raw.description),
    privacyLevel: nullableText(raw.privacy_level),
  }
}

export async function fetchMySubmissionStats(): Promise<MySubmissionStats> {
  const data = await request.get<Record<string, unknown>>(
    '/api/v1/photos/my-submissions/stats',
    { timeout: 20000 },
  )
  return {
    total: normalizeCount(data?.total),
    pending: normalizeCount(data?.pending),
    approved: normalizeCount(data?.approved),
    rejected: normalizeCount(data?.rejected),
    pendingAppeal: normalizeCount(data?.pending_appeal),
  }
}

export async function fetchMySubmissions(query: MySubmissionQuery = {}): Promise<MySubmissionPage> {
  const data = await request.get<Record<string, unknown>>('/api/v1/photos/my-submissions', {
    params: {
      skip: query.skip ?? 0,
      limit: query.limit ?? 12,
      ...(query.status ? { status: query.status } : {}),
      ...(query.search ? { search: query.search } : {}),
    },
    timeout: 20000,
  })
  const rawItems = Array.isArray(data?.items) ? data.items : []
  const items = rawItems
    .map((row) => normalizeMySubmission(row))
    .filter((row): row is MySubmissionItem => row !== null)
  return {
    items,
    total: normalizeCount(data?.total),
    page: normalizeCount(data?.page),
    pageSize: normalizeCount(data?.page_size) || (query.limit ?? 12),
  }
}

export function submissionThumbSource(photoId: string): string {
  return getImageUrl(`/api/v1/photos/${encodeURIComponent(photoId)}/image/thumbnail`)
}

const THUMB_CACHE = new Map<string, string>()
const THUMB_INFLIGHT = new Map<string, Promise<string | null>>()

/**
 * 带鉴权拉取作品缩略图，返回可直接给 `<img>` 的 objectURL。
 * 同一张图只拉一次；并发调用复用同一 Promise；失败不缓存（下次可重试）。
 */
export function fetchSubmissionThumbUrl(photoId: string): Promise<string | null> {
  const cached = THUMB_CACHE.get(photoId)
  if (cached) return Promise.resolve(cached)

  const inflight = THUMB_INFLIGHT.get(photoId)
  if (inflight) return inflight

  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('auth_token') || sessionStorage.getItem('auth_token')
      : null

  const task = (async (): Promise<string | null> => {
    try {
      const res = await fetch(submissionThumbSource(photoId), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) return null
      const blob = await res.blob()
      const objectUrl = URL.createObjectURL(blob)
      THUMB_CACHE.set(photoId, objectUrl)
      return objectUrl
    } catch {
      return null
    } finally {
      THUMB_INFLIGHT.delete(photoId)
    }
  })()

  THUMB_INFLIGHT.set(photoId, task)
  return task
}

/** 删除后释放该图的 objectURL，避免内存泄漏。 */
export function releaseSubmissionThumb(photoId: string): void {
  const cached = THUMB_CACHE.get(photoId)
  if (!cached) return
  URL.revokeObjectURL(cached)
  THUMB_CACHE.delete(photoId)
}

export async function deleteMySubmission(photoId: string): Promise<void> {
  await request.delete(`/api/v1/photos/${encodeURIComponent(photoId)}`, { timeout: 30000 })
}
