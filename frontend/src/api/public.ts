/**
 * 公共端只读接口（匿名可访问）
 *
 * 与 admin 侧的 api/photo.ts 分开：这里只做公开浏览所需的查询、
 * 归一化（真实宽高比 / 图片地址 / 可选的 AIGC 与 LQIP 字段）和分页。
 * 公开响应里可能出现 uploader_name 等字段，但展示只用 username/display 语义，
 * 不展示学号；若后端后续收紧，前端不受影响。
 */
import request from './index'
import type { Photo, PhotoListResponse, TaxonomyValue } from '../types/photo'
import { getPhotoDownloadUrl, getPhotoUrl } from '../utils/format'
import { displayPhotoAuthor, displayPhotoTitle } from '../utils/photoDisplay'

/** 作品类型：后端 works 模型落地前只有 photo，AIGC 角标位预留 */
export type WorkKind = 'photo' | 'aigc' | 'template'

/** 卡片 / 瀑布流使用的归一化作品 */
export interface PublicPhoto {
  id: string
  kind: WorkKind
  title: string
  author: string
  width: number
  height: number
  aspectRatio: number
  /** 缩略图（列表用） */
  thumbUrl: string
  /** 压缩大图（详情 / 大图预览用） */
  imageUrl: string
  downloadUrl: string
  season: string | null
  campus: string | null
  place: string | null
  landscape: string | null
  category: string | null
  capturedAt: string | null
  createdAt: string | null
  /** AIGC 显式角标（法定要求），当前后端无字段，预留 */
  aigc: boolean
  license: string | null
  tags: string[]
  blurhash: string | null
  /** 20px 内联 WebP data-URI，用 background-size: cover 铺底 */
  lqip: string | null
  /** LQIP 主色，LQIP 缺省时作为占位底色 */
  lqipColor: string | null
  raw: Photo
}

export interface PublicPhotoQuery {
  skip?: number
  limit?: number
  season?: string
  campus?: string
  category?: string
  landscape?: string
  plant?: string
  photo_type?: string
  natural_phenomenon?: string
  technique?: string
  animal?: string
  building?: string
  search?: string
  tag?: string
  sort_by?: 'created_at' | 'views' | 'published_at'
  sort_order?: 'asc' | 'desc'
}

export interface PublicPhotoPage {
  items: PublicPhoto[]
  total: number
  page: number
  pageSize: number
}

export interface PublicTaxonomyNode {
  id: number
  facet_id: number
  parent_id: number | null
  key: string
  name: string
  description: string | null
  sort_order: number
  is_active: boolean
  is_selectable?: boolean
  children: PublicTaxonomyNode[]
}

export interface PublicTaxonomyFacet {
  id: number
  key: string
  name: string
  description: string | null
  selection_mode: 'single' | 'multiple'
  nodes: PublicTaxonomyNode[]
}

function taxonomyName(value: TaxonomyValue | TaxonomyValue[] | undefined | null): string | null {
  if (!value) return null
  const first = Array.isArray(value) ? value[0] : value
  return first?.node_name || null
}

/** 旧数据里 season / category / campus 存的是英文枚举，展示层统一成中文 */
const SEASON_LABEL: Record<string, string> = {
  spring: '春季',
  summer: '夏季',
  autumn: '秋季',
  winter: '冬季',
}

const CATEGORY_LABEL: Record<string, string> = {
  landscape: '校园景观',
  documentary: '校园纪实',
  activity: '校园活动',
  architecture: '建筑空间',
  people: '人物',
  nature: '自然生态',
}

const CAMPUS_LABEL: Record<string, string> = {
  changping: '昌平校区',
  chaoyang: '朝阳校区',
  haidian: '海淀校区',
}

function labelOf(map: Record<string, string>, value: string | null | undefined): string | null {
  if (!value) return null
  return map[value.trim().toLowerCase()] || value
}

function normalizeDimension(value: number | null | undefined): number {
  return value && value > 0 ? value : 0
}

interface RawPhotoExtra {
  kind?: string
  aigc_label?: boolean
  license?: string
  blurhash?: string | null
  lqip?: string | null
  lqip_color?: string | null
}

export function toPublicPhoto(photo: Photo): PublicPhoto {
  const extra = photo as Photo & RawPhotoExtra
  const width = normalizeDimension(photo.width)
  const height = normalizeDimension(photo.height)
  const knownRatio = width > 0 && height > 0
  const aspectRatio = knownRatio ? width / height : 4 / 3
  const kind: WorkKind =
    extra.kind === 'aigc' || extra.kind === 'template' ? extra.kind : 'photo'
  const classLandscape = taxonomyName(photo.classifications?.landscape)
  // 后端的分类节点名才是权威中文名（photo.season 等旧列可能仍是英文枚举）
  const season = taxonomyName(photo.classifications?.season) || labelOf(SEASON_LABEL, photo.season)
  const campus = taxonomyName(photo.classifications?.campus) || labelOf(CAMPUS_LABEL, photo.campus)
  const category = labelOf(CATEGORY_LABEL, photo.category)
  const photoType = taxonomyName(photo.classifications?.photo_type)

  return {
    id: photo.id,
    kind,
    title: displayPhotoTitle(photo),
    author: displayPhotoAuthor(photo),
    width: knownRatio ? width : 0,
    height: knownRatio ? height : 0,
    aspectRatio: Math.min(Math.max(aspectRatio, 0.55), 2.2),
    thumbUrl: getPhotoUrl(photo.id, 'thumbnail'),
    imageUrl: getPhotoUrl(photo.id, 'compressed'),
    downloadUrl: getPhotoDownloadUrl(photo.id),
    season,
    campus,
    place: taxonomyName(photo.classifications?.landmark) || classLandscape || photoType,
    landscape: classLandscape,
    category,
    capturedAt: photo.captured_at,
    createdAt: photo.published_at || photo.created_at,
    aigc: kind === 'aigc' || extra.aigc_label === true,
    license: extra.license ?? null,
    tags: [...(photo.tags || []), ...(photo.free_tags || [])],
    blurhash: extra.blurhash ?? null,
    lqip: extra.lqip ?? null,
    lqipColor: extra.lqip_color ?? null,
    raw: photo,
  }
}

/** 去除空参数，避免 URL 里出现 season=&campus= */
function cleanQuery(query: PublicPhotoQuery): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    out[key] = value as string | number
  }
  return out
}

/**
 * 公开作品列表。limit 后端硬上限 100。
 * 匿名访问只返回已发布（approved）作品。
 */
export async function fetchPublicPhotos(query: PublicPhotoQuery = {}): Promise<PublicPhotoPage> {
  const data = await request.get<PhotoListResponse>('/api/v1/photos/public', {
    params: cleanQuery(query),
  })
  return {
    items: (data.items || []).map(toPublicPhoto),
    total: data.total || 0,
    page: data.page || 1,
    pageSize: data.page_size || query.limit || 20,
  }
}

/** 公开分类法（季节 / 校区 / 八景 / 植物等筛选来源） */
export async function fetchPublicTaxonomy(): Promise<PublicTaxonomyFacet[]> {
  return request.get<PublicTaxonomyFacet[]>('/api/v1/taxonomy/public')
}

/** 按 facet key 取节点列表，容错返回空数组 */
export async function fetchPublicFacetNodes(
  facetKey: string,
): Promise<PublicTaxonomyNode[]> {
  try {
    const facets = await fetchPublicTaxonomy()
    return facets.find((facet) => facet.key === facetKey)?.nodes || []
  } catch {
    return []
  }
}
