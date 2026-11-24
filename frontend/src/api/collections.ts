/**
 * 策展专题（collections）API。
 *
 * 公开接口：
 * - GET /api/v1/collections/public  公开专题列表（published + public）
 * - GET /api/v1/collections/{slug}  专题详情（photos 按 position 正序，仅 approved）
 * - GET /api/v1/photos/{id}/collections  作品所属专题（详情页「收录于」）
 *
 * 作者手账（需登录）：
 * - POST   /api/v1/collections              新建专辑（kind=user）
 * - GET    /api/v1/collections/mine         我的专辑列表
 * - GET    /api/v1/collections/{id}/manage  我的专辑编辑数据（作者或 admin）
 * - PATCH  /api/v1/collections/{id}         修改标题/副标题/引言/封面/状态
 * - DELETE /api/v1/collections/{id}         删除专辑
 * - PUT    /api/v1/collections/{id}/photos  整体替换并保序
 *
 * 约定：封面与作品都是完整 PhotoResponse，这里统一走 api/public 的
 * toPublicPhoto 转成公共端展示模型（作者署名、中文分类、变体、LQIP 等）。
 */
import request from './index'
import type { Photo } from '../types/photo'
import { toPublicPhoto, type PublicPhoto } from './public'

export type CollectionStatus = 'published' | 'draft'

/** 公开作者身份（无学号） */
export interface CollectionOwner {
  username: string
  displayName: string
}

export interface CollectionSummary {
  id: string
  slug: string
  title: string
  subtitle: string
  kind: string
  sortOrder: number
  photoCount: number
  /** published | draft（公开列表恒为 published） */
  status: CollectionStatus
  /** 作者手账的公开作者；编辑部专题为 null */
  owner: CollectionOwner | null
  /** 专题内 position 最小的 approved 作品；可能为 null（空专题/全部未审） */
  cover: PublicPhoto | null
}

export interface CollectionDetail extends CollectionSummary {
  description: string
  photos: PublicPhoto[]
  prevSlug: string | null
  nextSlug: string | null
}

export interface PhotoCollectionRef {
  slug: string
  title: string
  kind: string
}

export interface CollectionListResponse {
  items: CollectionSummary[]
  total: number
  limit: number
  offset: number
}

export interface MyCollection extends CollectionSummary {
  description: string
  updatedAt: string
}

export interface MyCollectionsResponse {
  items: MyCollection[]
  total: number
}

/** 管理端编辑数据：photos 为当前有序作品，photoIds 为其 id 序列 */
export interface ManagedCollection extends CollectionDetail {
  photoIds: string[]
}

export interface CollectionCreatePayload {
  title: string
  subtitle?: string
  description?: string
}

export interface CollectionUpdatePayload {
  title?: string
  subtitle?: string
  description?: string
  /** null 表示清除封面；undefined 表示不改 */
  coverPhotoId?: string | null
  status?: CollectionStatus
}

interface RawCollection {
  id?: unknown
  slug?: unknown
  title?: unknown
  subtitle?: unknown
  description?: unknown
  kind?: unknown
  sort_order?: unknown
  photo_count?: unknown
  status?: unknown
  owner?: unknown
  cover?: unknown
  photos?: unknown
  prev_slug?: unknown
  next_slug?: unknown
  updated_at?: unknown
}

function textOf(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function numOf(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function nullableText(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

function normalizeStatus(value: unknown): CollectionStatus {
  return value === 'draft' ? 'draft' : 'published'
}

function normalizeOwner(value: unknown): CollectionOwner | null {
  if (!value || typeof value !== 'object') return null
  const raw = value as Record<string, unknown>
  const username = textOf(raw.username)
  const displayName = textOf(raw.display_name) || textOf(raw.displayName) || username
  if (!username && !displayName) return null
  return { username, displayName }
}

function toSummary(raw: RawCollection): CollectionSummary {
  const coverRaw = raw.cover as Photo | null | undefined
  return {
    id: textOf(raw.id),
    slug: textOf(raw.slug),
    title: textOf(raw.title, '未命名专题'),
    subtitle: textOf(raw.subtitle),
    kind: textOf(raw.kind, 'editorial'),
    sortOrder: numOf(raw.sort_order),
    photoCount: numOf(raw.photo_count),
    status: normalizeStatus(raw.status),
    owner: normalizeOwner(raw.owner),
    cover: coverRaw ? toPublicPhoto(coverRaw) : null,
  }
}

function toDetail(raw: RawCollection): CollectionDetail {
  const summary = toSummary(raw)
  const photos = Array.isArray(raw.photos)
    ? (raw.photos as Photo[]).map(toPublicPhoto)
    : []
  return {
    ...summary,
    description: textOf(raw.description),
    photos,
    prevSlug: nullableText(raw.prev_slug),
    nextSlug: nullableText(raw.next_slug),
  }
}

function toMyCollection(raw: RawCollection): MyCollection {
  return {
    ...toSummary(raw),
    description: textOf(raw.description),
    updatedAt: textOf(raw.updated_at),
  }
}

function toManaged(raw: RawCollection): ManagedCollection {
  const detail = toDetail(raw)
  return {
    ...detail,
    photoIds: detail.photos.map((photo) => photo.id),
  }
}

/** 公开专题列表（首页横向卡区 / 索引用） */
export async function fetchCollections(
  params: { limit?: number; offset?: number } = {},
): Promise<CollectionListResponse> {
  const data = await request.get<{
    items?: RawCollection[]
    total?: unknown
    limit?: unknown
    offset?: unknown
  }>('/api/v1/collections/public', {
    params: {
      limit: params.limit ?? 12,
      offset: params.offset ?? 0,
    },
  })
  const items = Array.isArray(data.items) ? data.items.map(toSummary) : []
  return {
    items,
    total: numOf(data.total, items.length),
    limit: numOf(data.limit, params.limit ?? 12),
    offset: numOf(data.offset, params.offset ?? 0),
  }
}

/** 专题详情；未发布/不存在时后端 404，调用方按「专题不存在」处理 */
export async function fetchCollection(slug: string): Promise<CollectionDetail> {
  const raw = await request.get<RawCollection>(
    `/api/v1/collections/${encodeURIComponent(slug)}`,
  )
  return toDetail(raw)
}

/** 作品被收录于哪些专题（详情页「收录于」），失败时返回空数组不阻塞详情页 */
export async function fetchPhotoCollections(photoId: string): Promise<PhotoCollectionRef[]> {
  try {
    const data = await request.get<{ items?: unknown }>(
      `/api/v1/photos/${encodeURIComponent(photoId)}/collections`,
    )
    if (!Array.isArray(data.items)) return []
    return data.items
      .filter((item): item is RawCollection => Boolean(item && typeof item === 'object'))
      .map((item) => ({
        slug: textOf(item.slug),
        title: textOf(item.title),
        kind: textOf(item.kind, 'editorial'),
      }))
      .filter((item) => item.slug && item.title)
  } catch (error) {
    console.warn('[collections] 作品所属专题加载失败', error)
    return []
  }
}

/* ------------------------------------------------------------------ */
/* 作者手账（需登录）                                                   */
/* ------------------------------------------------------------------ */

/** 我的专辑列表（含草稿） */
export async function fetchMyCollections(): Promise<MyCollectionsResponse> {
  const data = await request.get<{ items?: RawCollection[]; total?: unknown }>(
    '/api/v1/collections/mine',
  )
  const items = Array.isArray(data.items) ? data.items.map(toMyCollection) : []
  return { items, total: numOf(data.total, items.length) }
}

/** 我的专辑编辑数据（作者或 admin） */
export async function fetchManagedCollection(id: string): Promise<ManagedCollection> {
  const raw = await request.get<RawCollection>(
    `/api/v1/collections/${encodeURIComponent(id)}/manage`,
  )
  return toManaged(raw)
}

/** 新建专辑（默认发布；草稿由后续 PATCH 设置） */
export async function createCollection(
  payload: CollectionCreatePayload,
): Promise<ManagedCollection> {
  const raw = await request.post<RawCollection>('/api/v1/collections', {
    title: payload.title,
    subtitle: payload.subtitle || undefined,
    description: payload.description || undefined,
  })
  return toManaged(raw)
}

/** 修改专辑信息（只发传入的字段） */
export async function updateCollection(
  id: string,
  payload: CollectionUpdatePayload,
): Promise<ManagedCollection> {
  const body: Record<string, unknown> = {}
  if (payload.title !== undefined) body.title = payload.title
  if (payload.subtitle !== undefined) body.subtitle = payload.subtitle
  if (payload.description !== undefined) body.description = payload.description
  if (payload.coverPhotoId !== undefined) body.cover_photo_id = payload.coverPhotoId
  if (payload.status !== undefined) body.status = payload.status
  const raw = await request.patch<RawCollection>(
    `/api/v1/collections/${encodeURIComponent(id)}`,
    body,
  )
  return toManaged(raw)
}

/** 删除专辑 */
export async function deleteCollection(id: string): Promise<void> {
  await request.delete(`/api/v1/collections/${encodeURIComponent(id)}`)
}

/** 整体替换作品并保序（≤100，只能放自己的 approved 作品） */
export async function replaceCollectionPhotos(
  id: string,
  photoIds: string[],
): Promise<ManagedCollection> {
  const raw = await request.put<RawCollection>(
    `/api/v1/collections/${encodeURIComponent(id)}/photos`,
    { photo_ids: photoIds },
  )
  return toManaged(raw)
}

/* ============ 樱色光谱（按主色自动策展） ============ */

export interface SpectrumPalette {
  key: string
  name: string
  hex: string
  description: string
  slug: string | null
  photoCount: number
  cover: PublicPhoto | null
}

export interface SpectrumResponse {
  palettes: SpectrumPalette[]
  total: number
}

function toSpectrumPalette(raw: unknown): SpectrumPalette {
  const item = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const coverRaw = item.cover
  return {
    key: textOf(item.key),
    name: textOf(item.name),
    hex: textOf(item.hex) || '#e8628c',
    description: textOf(item.description),
    slug: nullableText(item.slug),
    photoCount: numOf(item.photo_count ?? item.photoCount),
    cover:
      coverRaw && typeof coverRaw === 'object'
        ? toPublicPhoto(coverRaw as unknown as Photo)
        : null,
  }
}

/* ============ 光的一日（今日之光） ============ */

/** 一个光时段：晨 / 昼 / 暮 / 夜（固定顺序，空时段 photos=[]） */
export interface LightPeriod {
  key: string
  slug: string
  label: string
  timeRange: string
  title: string
  subtitle: string
  intro: string
  photoCount: number
  photos: PublicPhoto[]
}

export interface LightPeriodsResponse {
  periods: LightPeriod[]
  total: number
}

function toLightPeriod(raw: unknown): LightPeriod {
  const item = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const photos = Array.isArray(item.photos)
    ? (item.photos as Photo[]).map(toPublicPhoto)
    : []
  return {
    key: textOf(item.key),
    slug: textOf(item.slug),
    label: textOf(item.label),
    timeRange: textOf(item.time_range) || textOf(item.timeRange),
    title: textOf(item.title),
    subtitle: textOf(item.subtitle),
    intro: textOf(item.intro),
    photoCount: numOf(item.photo_count ?? item.photoCount, photos.length),
    photos,
  }
}

/** 今日之光：固定 晨/昼/暮/夜 四时段，每段最多 perPeriod 张公开作品 */
export async function fetchLightPeriods(perPeriod = 4): Promise<LightPeriodsResponse> {
  const raw = await request.get<Record<string, unknown>>('/api/v1/collections/light', {
    params: { per_period: perPeriod },
  })
  const rawObj = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const list = Array.isArray(rawObj.periods) ? rawObj.periods : []
  const periods = list.map(toLightPeriod).filter((item) => item.key)
  return {
    periods,
    total: numOf(rawObj.total) || periods.reduce((sum, item) => sum + item.photoCount, 0),
  }
}

/** 樱色光谱：5 个色卡（固定顺序，slug 可能为 null） */
export async function fetchSpectrum(): Promise<SpectrumResponse> {
  const raw = await request.get<Record<string, unknown>>('/api/v1/collections/spectrum')
  const rawObj = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const list = Array.isArray(rawObj.palettes) ? rawObj.palettes : []
  const palettes = list.map(toSpectrumPalette).filter((item) => item.key && item.name)
  return {
    palettes,
    total: numOf(rawObj.total) || palettes.reduce((sum, item) => sum + item.photoCount, 0),
  }
}
