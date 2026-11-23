/**
 * 策展专题（collections）API。
 *
 * 后端接口：
 * - GET /api/v1/collections/public  公开专题列表（published + public）
 * - GET /api/v1/collections/{slug}  专题详情（photos 按 position 正序，仅 approved）
 * - GET /api/v1/photos/{id}/collections  作品所属专题（详情页「收录于」）
 *
 * 约定：封面与作品都是完整 PhotoResponse，这里统一走 api/public 的
 * toPublicPhoto 转成公共端展示模型（作者署名、中文分类、变体、LQIP 等）。
 */
import request from './index'
import type { Photo } from '../types/photo'
import { toPublicPhoto, type PublicPhoto } from './public'

export interface CollectionSummary {
  id: string
  slug: string
  title: string
  subtitle: string
  kind: string
  sortOrder: number
  photoCount: number
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

interface RawCollection {
  id?: unknown
  slug?: unknown
  title?: unknown
  subtitle?: unknown
  description?: unknown
  kind?: unknown
  sort_order?: unknown
  photo_count?: unknown
  cover?: unknown
  photos?: unknown
  prev_slug?: unknown
  next_slug?: unknown
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
    cover: coverRaw ? toPublicPhoto(coverRaw) : null,
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
