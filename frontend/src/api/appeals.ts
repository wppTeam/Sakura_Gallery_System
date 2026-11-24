/**
 * 作者侧「审核复核（申诉）」API。
 *
 * 契约：
 * - POST /api/v1/photos/{photo_id}/appeal  body {reason: 10–2000 字} → 201 {ok,id,status,message}
 * - GET  /api/v1/photos/{photo_id}/appeal  → 最近一条申请或 null
 *
 * 仅作者本人可提交；同一作品同时只允许一条 pending（重复 409）。
 */
import request from './index'

export type PhotoAppealStatus = 'pending' | 'accepted' | 'rejected'

export interface PhotoAppeal {
  id: string
  photoId: string
  status: PhotoAppealStatus
  reason: string
  note: string | null
  createdAt: string | null
  handledAt: string | null
  raw: Record<string, unknown>
}

export interface SubmitAppealResult {
  ok: boolean
  id: string
  status: string
  message: string
}

const APPEAL_STATUSES: PhotoAppealStatus[] = ['pending', 'accepted', 'rejected']

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

function normalizeStatus(value: unknown): PhotoAppealStatus {
  const text = textOf(value)
  return APPEAL_STATUSES.includes(text as PhotoAppealStatus) ? (text as PhotoAppealStatus) : 'pending'
}

export function normalizePhotoAppeal(raw: unknown): PhotoAppeal | null {
  if (!isRecord(raw)) return null
  const id = textOf(raw.id)
  const photoId = textOf(raw.photo_id)
  if (!id && !photoId) return null
  return {
    id,
    photoId,
    status: normalizeStatus(raw.status),
    reason: textOf(raw.reason),
    note: nullableText(raw.note),
    createdAt: nullableText(raw.created_at),
    handledAt: nullableText(raw.handled_at),
    raw,
  }
}

/** 作者提交复核申请（10–2000 字）。 */
export async function submitPhotoAppeal(photoId: string, reason: string): Promise<SubmitAppealResult> {
  const data = await request.post<Record<string, unknown>>(
    `/api/v1/photos/${encodeURIComponent(photoId)}/appeal`,
    { reason: reason.trim() },
    { timeout: 30000 },
  )
  return {
    ok: data?.ok !== false,
    id: textOf(data?.id),
    status: textOf(data?.status) || 'pending',
    message: textOf(data?.message),
  }
}

/**
 * 读取最近一条复核申请；没有申请（或无权查看）时返回 null，不打断详情页加载。
 */
export async function fetchPhotoAppeal(photoId: string): Promise<PhotoAppeal | null> {
  try {
    const data = await request.get<unknown>(
      `/api/v1/photos/${encodeURIComponent(photoId)}/appeal`,
      { timeout: 20000 },
    )
    if (data === null || data === undefined) return null
    return normalizePhotoAppeal(data)
  } catch {
    return null
  }
}
