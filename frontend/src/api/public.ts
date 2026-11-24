/**
 * 公共端只读接口（匿名可访问）
 *
 * 与 admin 侧的 api/photo.ts 分开：这里只做公开浏览所需的查询、
 * 归一化（真实宽高比 / 图片地址 / 可选的 AIGC 与 LQIP 字段）和分页。
 * 公开响应里可能出现 uploader_name 等字段，但展示只用 username/display 语义，
 * 不展示学号；若后端后续收紧，前端不受影响。
 */
import request, { encodeQueryParams } from './index'
import type { Photo, PhotoListResponse, TaxonomyValue } from '../types/photo'
import { getImageUrl, getPhotoDownloadUrl, getPhotoUrl } from '../utils/format'
import { displayPhotoAuthor, displayPhotoTitle } from '../utils/photoDisplay'

/** 作品类型：后端 works 模型落地前只有 photo，AIGC 角标位预留 */
export type WorkKind = 'photo' | 'aigc' | 'template'

/** 单个响应式变体：WebP 主用 + JPEG 兜底，width 用作 srcset 描述符 */
export interface PublicVariant {
  /** 长边档位（320 / 640 / 1080 / 1600 / 2400） */
  size: number
  /** WebP URL；后端未生成时为 null */
  webpUrl: string | null
  /** JPEG 兜底 URL（srcset 的兼容来源） */
  jpegUrl: string | null
  width: number
  height: number
}

/** 卡片 / 瀑布流使用的归一化作品 */
export interface PublicPhoto {
  id: string
  kind: WorkKind
  title: string
  author: string
  width: number
  height: number
  aspectRatio: number
  /** 缩略图（列表用，单图回退） */
  thumbUrl: string
  /** 响应式变体（按宽度升序）；老图为空数组，保持 thumbUrl 单图行为 */
  variants: PublicVariant[]
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
  /** AIGC 显式角标（法定要求）：由后端 is_aigc / kind / aigc_label 归一化 */
  aigc: boolean
  /** 人像隐私分级：sensitive 作品默认不在公共列表展示 */
  privacyLevel: 'normal' | 'sensitive'
  /** 当前图片是否为脱敏版本（非作者查看 sensitive 作品时 true） */
  isRedacted: boolean
  /** 是否可查看/下载原图：脱敏版本一律不可（服务端同样会 403） */
  canViewOriginal: boolean
  /** 上传者 id：用于判断「这是你的作品」，不对外展示 */
  uploaderId: string | null
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
  /** 是否纳入人像作品（仅登录后生效；后端仍受 portrait_visibility 约束） */
  include_sensitive?: boolean
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
  /** 响应式变体（serialize_photo 白名单） */
  variants?: Photo['variants']
  /** 后端 AIGC 法定标识字段（serialize_photo 白名单） */
  is_aigc?: boolean
  aigc_label?: string | boolean | null
  aigc_meta?: Record<string, unknown> | null
  label_written?: boolean | null
  privacy_level?: string | null
  is_redacted?: boolean | null
  uploader_id?: string | null
  license?: string
  blurhash?: string | null
  lqip?: string | null
  lqip_color?: string | null
}

function toPublicVariants(raw: Photo['variants'] | null | undefined): PublicVariant[] {
  if (!raw || typeof raw !== 'object') return []
  const variants: PublicVariant[] = []
  for (const [key, value] of Object.entries(raw)) {
    if (!value || typeof value !== 'object') continue
    const entry = value as { webp?: unknown; jpeg?: unknown; width?: unknown; height?: unknown }
    const width = typeof entry.width === 'number' ? entry.width : Number(key) || 0
    const height = typeof entry.height === 'number' ? entry.height : 0
    const size = Number(key) || width
    const webpUrl = typeof entry.webp === 'string' && entry.webp ? getImageUrl(entry.webp) : null
    const jpegUrl = typeof entry.jpeg === 'string' && entry.jpeg ? getImageUrl(entry.jpeg) : null
    if (!webpUrl && !jpegUrl) continue
    variants.push({ size, webpUrl, jpegUrl, width: width || size, height })
  }
  return variants.sort((a, b) => (a.width || a.size) - (b.width || b.size))
}

/**
 * 由变体生成 srcset 字符串（width 描述符）。
 * 返回空串表示无可用变体，调用方回退单图。
 */
export function buildSrcset(variants: PublicVariant[], format: 'webp' | 'jpeg'): string {
  return variants
    .map((variant) => {
      const url = format === 'webp' ? variant.webpUrl : variant.jpegUrl
      if (!url) return ''
      const width = variant.width || variant.size
      return `${url} ${width}w`
    })
    .filter(Boolean)
    .join(', ')
}

export function toPublicPhoto(photo: Photo): PublicPhoto {
  const extra = photo as Photo & RawPhotoExtra
  const width = normalizeDimension(photo.width)
  const height = normalizeDimension(photo.height)
  const knownRatio = width > 0 && height > 0
  const aspectRatio = knownRatio ? width / height : 4 / 3
  // AIGC 判定：is_aigc=true 是权威字段；兼容 kind='aigc' 与字符串 aigc_label（"AI 生成"）
  const aigcDeclared =
    extra.is_aigc === true ||
    extra.kind === 'aigc' ||
    (typeof extra.aigc_label === 'string' && extra.aigc_label.trim() !== '')
  const kind: WorkKind =
    extra.kind === 'template' ? 'template' : aigcDeclared ? 'aigc' : 'photo'
  const classLandscape = taxonomyName(photo.classifications?.landscape)
  // 后端的分类节点名才是权威中文名（photo.season 等旧列可能仍是英文枚举）
  const season = taxonomyName(photo.classifications?.season) || labelOf(SEASON_LABEL, photo.season)
  const campus = taxonomyName(photo.classifications?.campus) || labelOf(CAMPUS_LABEL, photo.campus)
  const category = labelOf(CATEGORY_LABEL, photo.category)
  const photoType = taxonomyName(photo.classifications?.photo_type)
  const isRedacted = extra.is_redacted === true
  const privacyLevel: 'normal' | 'sensitive' =
    extra.privacy_level === 'sensitive' || isRedacted ? 'sensitive' : 'normal'

  return {
    id: photo.id,
    kind,
    title: displayPhotoTitle(photo),
    author: displayPhotoAuthor(photo),
    width: knownRatio ? width : 0,
    height: knownRatio ? height : 0,
    aspectRatio: Math.min(Math.max(aspectRatio, 0.55), 2.2),
    thumbUrl: getPhotoUrl(photo.id, 'thumbnail'),
    variants: toPublicVariants(extra.variants),
    imageUrl: getPhotoUrl(photo.id, 'compressed'),
    downloadUrl: getPhotoDownloadUrl(photo.id),
    season,
    campus,
    place: taxonomyName(photo.classifications?.landmark) || classLandscape || photoType,
    landscape: classLandscape,
    category,
    capturedAt: photo.captured_at,
    createdAt: photo.published_at || photo.created_at,
    aigc: aigcDeclared,
    privacyLevel,
    isRedacted,
    canViewOriginal: !isRedacted,
    uploaderId: extra.uploader_id ?? photo.uploader_id ?? null,
    license: extra.license ?? null,
    tags: [...(photo.tags || []), ...(photo.free_tags || [])],
    blurhash: extra.blurhash ?? null,
    lqip: extra.lqip ?? null,
    lqipColor: extra.lqip_color ?? null,
    raw: photo,
  }
}

/** 去除空参数；include_sensitive 等布尔参数统一序列化为 "true"/"false" */
function cleanQuery(query: PublicPhotoQuery): Record<string, string | number> {
  return encodeQueryParams(query)
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
