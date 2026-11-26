/**
 * 后台全局搜索 API（admin + auditor）。
 *
 * 后端 `GET /api/v1/admin/search?q=`：用户 / 作品 / 专题分组返回。
 * auditor 的用户结果不含学号与邮箱。
 */
import request from './index'

export interface SearchUserHit {
  id: string
  username: string | null
  displayName: string | null
  role: string
  isActive: boolean
  email: string | null
  studentId: string | null
}

export interface SearchPhotoHit {
  id: string
  title: string | null
  status: string
  uploaderUsername: string | null
  thumbUrl: string
}

export interface SearchCollectionHit {
  slug: string
  title: string
  kind: string
  photoCount: number
}

export interface AdminSearchResult {
  query: string
  users: SearchUserHit[]
  photos: SearchPhotoHit[]
  collections: SearchCollectionHit[]
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

function bool(value: unknown, fallback = false): boolean {
  return typeof value === 'boolean' ? value : fallback
}

export async function adminSearch(query: string, limit = 5): Promise<AdminSearchResult> {
  const response = await request.get<unknown>('/api/v1/admin/search', { params: { q: query, limit } })
  const data = isRecord(response) ? response : {}
  const list = (raw: unknown) => (Array.isArray(raw) ? raw.filter(isRecord) : [])
  return {
    query: text(data.query) ?? query,
    users: list(data.users).map((item) => ({
      id: text(item.id) ?? '',
      username: text(item.username),
      displayName: text(item.display_name),
      role: text(item.role) ?? 'user',
      isActive: bool(item.is_active, true),
      email: text(item.email),
      studentId: text(item.student_id),
    })),
    photos: list(data.photos).map((item) => ({
      id: text(item.id) ?? '',
      title: text(item.title),
      status: text(item.status) ?? 'pending',
      uploaderUsername: text(item.uploader_username),
      thumbUrl: text(item.thumb_url) ?? '',
    })),
    collections: list(data.collections).map((item) => ({
      slug: text(item.slug) ?? '',
      title: text(item.title) ?? '',
      kind: text(item.kind) ?? 'editorial',
      photoCount: num(item.photo_count),
    })),
  }
}