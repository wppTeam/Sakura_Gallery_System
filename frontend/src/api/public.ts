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
  /** AI 画面描述（≤300 字，仅审核快筛打标后的作品；人像脱敏视角/旧作品为 null） */
  aiCaption: string | null
  /** 是否可查看/下载原图：脱敏版本一律不可（服务端同样会 403） */
  canViewOriginal: boolean
  /** 上传者 id：用于判断「这是你的作品」，不对外展示 */
  uploaderId: string | null
  /** 上传者公开用户名：详情页作者可点进创作者主页；为空时不渲染链接 */
  uploaderUsername: string | null
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
  /** 光线时段筛选：与首页「光的一日」同一套时段定义（后端 normalize_period 也接受中文） */
  period?: LightPeriodKey
}

/** 光线时段：晨 / 昼 / 暮 / 夜（本地小时 5–9 / 9–15 / 15–19 / 其余） */
export type LightPeriodKey = 'dawn' | 'noon' | 'dusk' | 'night'

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
  /** 公开作者用户名（学号与真实姓名恒为 null） */
  uploader_username?: string | null
  license?: string
  blurhash?: string | null
  lqip?: string | null
  lqip_color?: string | null
  /** AI 画面描述（审核快筛打标写入，公开详情返回；人像脱敏视角为 null） */
  ai_caption?: string | null
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
    aiCaption: typeof extra.ai_caption === 'string' && extra.ai_caption.trim() ? extra.ai_caption.trim() : null,
    canViewOriginal: !isRedacted,
    uploaderId: extra.uploader_id ?? photo.uploader_id ?? null,
    uploaderUsername:
      typeof extra.uploader_username === 'string' && extra.uploader_username.trim()
        ? extra.uploader_username.trim()
        : null,
    license: extra.license ?? null,
    tags: Array.from(new Set([...(photo.tags || []), ...(photo.free_tags || [])])),
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

/** 视觉相似推荐：一条 = 作品 + 相似度 + 中文理由（后端 reasons 最多 3 条） */
export interface SimilarPhoto {
  photo: PublicPhoto
  similarity: number
  reasons: string[]
}

/**
 * 视觉相似作品（GET /api/v1/photos/{id}/similar）。
 * 目标不存在/未公开 → 抛错，由调用方决定回退策略。
 */
export async function fetchSimilarPhotos(photoId: string, limit = 8): Promise<SimilarPhoto[]> {
  const data = await request.get<{ items?: unknown[]; total?: number }>(
    `/api/v1/photos/${encodeURIComponent(photoId)}/similar`,
    { params: { limit } },
  )
  const items = Array.isArray(data?.items) ? data.items : []
  const results: SimilarPhoto[] = []
  for (const raw of items) {
    if (!raw || typeof raw !== 'object') continue
    const item = raw as Record<string, unknown> & Photo
    const photo = toPublicPhoto(item)
    if (!photo.id) continue
    const reasons = Array.isArray(item.reasons)
      ? item.reasons.filter((reason): reason is string => typeof reason === 'string' && reason.trim() !== '').slice(0, 3)
      : []
    const similarity = typeof item.similarity === 'number' ? item.similarity : 0
    results.push({ photo, similarity, reasons })
  }
  return results
}

/** 公开分类法（季节 / 校区 / 取景地 / 植物等筛选来源） */
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

/* ---------------- 详情页观展导航（上一张 / 下一张） ---------------- */

/** 序列来源：最新发布流或某个策展专题 */
export type PhotoNavContextKind = 'latest' | 'collection'

export interface PhotoNeighborsContext {
  kind: PhotoNavContextKind
  slug: string | null
  title: string
  /** 当前作品在序列中的位置（从 1 起） */
  position: number
  total: number
}

/** 胶片条单项：只带缩略与角标所需字段，避免整份 EXIF 进入灯箱 */
export interface PhotoNeighborItem {
  id: string
  title: string
  width: number
  height: number
  aspectRatio: number
  isAigc: boolean
  aigcLabel: string
  lqipColor: string
  thumbUrl: string
}

export interface PhotoNeighbors {
  context: PhotoNeighborsContext | null
  items: PhotoNeighborItem[]
  /** 当前作品在 items 中的下标（服务端给不到时按 id 兜底） */
  index: number
  prev: string | null
  next: string | null
}

export interface PhotoNeighborsOptions {
  /** latest 或 collection:<slug>；省略时后端按最新流处理 */
  context?: string | null
  before?: number
  after?: number
}

function textOfValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

/**
 * 读取当前作品在序列中的前后邻居。
 * 匿名可读；失败时返回 null，由详情页静默降级（不打断正文阅读）。
 */
export async function fetchPhotoNeighbors(
  photoId: string,
  options: PhotoNeighborsOptions = {},
): Promise<PhotoNeighbors | null> {
  if (!photoId) return null
  try {
    const data = await request.get<Record<string, unknown>>(
      `/api/v1/photos/${encodeURIComponent(photoId)}/neighbors`,
      {
        params: {
          context: options.context || undefined,
          before: options.before ?? 5,
          after: options.after ?? 5,
        },
      },
    )
    if (!data || typeof data !== 'object') return null

    let context: PhotoNeighborsContext | null = null
    const rawContext = data.context
    if (rawContext && typeof rawContext === 'object') {
      const c = rawContext as Record<string, unknown>
      const kind = textOfValue(c.kind) === 'collection' ? 'collection' : 'latest'
      const total = typeof c.total === 'number' && c.total > 0 ? c.total : 0
      const position = typeof c.position === 'number' && c.position > 0 ? c.position : 0
      if (total > 0 && position > 0) {
        context = {
          kind,
          slug: textOfValue(c.slug) || null,
          title: textOfValue(c.title) || (kind === 'collection' ? '专题' : '最新发布'),
          position,
          total,
        }
      }
    }

    const rawItems = Array.isArray(data.items) ? data.items : []
    const items: PhotoNeighborItem[] = []
    for (const raw of rawItems) {
      if (!raw || typeof raw !== 'object') continue
      const item = raw as Record<string, unknown>
      const id = textOfValue(item.id)
      if (!id) continue
      const width = typeof item.width === 'number' && item.width > 0 ? item.width : 0
      const height = typeof item.height === 'number' && item.height > 0 ? item.height : 0
      const rawAspect = typeof item.aspect_ratio === 'number' ? item.aspect_ratio : 0
      let aspectRatio = rawAspect > 0 ? rawAspect : 0
      if (!aspectRatio && width > 0 && height > 0) aspectRatio = width / height
      const thumb = textOfValue(item.thumb_url)
      items.push({
        id,
        title: textOfValue(item.title) || '未命名作品',
        width,
        height,
        aspectRatio: aspectRatio > 0 ? aspectRatio : 1,
        isAigc: item.is_aigc === true || textOfValue(item.aigc_label) !== '',
        aigcLabel: textOfValue(item.aigc_label) || 'AI 生成',
        lqipColor: textOfValue(item.lqip_color),
        thumbUrl: thumb ? getImageUrl(thumb) : '',
      })
    }
    if (!items.length) return null

    const rawIndex = typeof data.index === 'number' ? data.index : -1
    const index = rawIndex >= 0 && rawIndex < items.length ? rawIndex : items.findIndex((item) => item.id === photoId)
    return {
      context,
      items,
      index,
      prev: textOfValue(data.prev) || null,
      next: textOfValue(data.next) || null,
    }
  } catch {
    return null
  }
}

/* ---------------- 公开热门关键词（画面关键词） ---------------- */

/** 热门关键词：name 为标签名，count 为包含该标签的已发布作品数 */
export interface PublicTagCount {
  name: string
  count: number
}

/**
 * 公开热门关键词（只统计 approved 且非 sensitive 作品，按作品数降序）。
 * 失败时返回空数组，调用方静默隐藏整块，不打扰首屏。
 */
export async function fetchPublicPopularTags(limit = 12): Promise<PublicTagCount[]> {
  const safeLimit = Math.min(Math.max(Math.trunc(limit) || 12, 1), 50)
  try {
    const data = await request.get<{ items?: unknown[] }>('/api/v1/tags/public/popular', {
      params: { limit: safeLimit },
    })
    const rawItems = Array.isArray(data?.items) ? data.items : []
    const items: PublicTagCount[] = []
    const seen = new Set<string>()
    for (const raw of rawItems) {
      if (!raw || typeof raw !== 'object') continue
      const entry = raw as { name?: unknown; count?: unknown }
      const name = typeof entry.name === 'string' ? entry.name.trim() : ''
      if (!name || seen.has(name)) continue
      seen.add(name)
      const count = typeof entry.count === 'number' && entry.count > 0 ? Math.trunc(entry.count) : 0
      items.push({ name, count })
    }
    return items.slice(0, safeLimit)
  } catch {
    return []
  }
}

/* ============================================================
   创作者主页（公开）
   ------------------------------------------------------------
   直接用 fetch 而不是共享 axios 实例：404 是「创作者不存在」这种正常
   业务分支，走全局拦截器会弹全局 toast 并 console.error，把页面自己的
   空态抢掉、也污染控制台。
   ============================================================ */

/** 创作者请求失败：保留 HTTP 状态，供页面区分 404 与网络错误 */
export class CreatorRequestError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'CreatorRequestError'
    this.status = status
  }
}

const CREATOR_API_BASE = import.meta.env.VITE_API_BASE_URL || ''

async function fetchCreatorJson<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${CREATOR_API_BASE}${path}`, {
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw new CreatorRequestError('网络请求失败，请检查网络后重试', 0)
  }
  if (!response.ok) {
    throw new CreatorRequestError(`创作者接口返回 ${response.status}`, response.status)
  }
  return (await response.json()) as T
}

function countOf(value: unknown): number {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric) || numeric < 0) return 0
  return Math.trunc(numeric)
}

function textOrNull(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

/** 公开创作者资料（GET /api/v1/creators/{username} 的 profile） */
export interface CreatorProfile {
  username: string
  displayName: string
  joinedAt: string | null
  worksCount: number
  viewsTotal: number
  favoritesTotal: number
  collectionsCount: number
}

/** 作者作品集（公开卡片：封面 + 标题 + 作品数） */
export interface CreatorCollection {
  slug: string
  title: string
  subtitle: string
  photoCount: number
  cover: PublicPhoto | null
}

/** 创作者作品分页 */
export interface CreatorWorksPage {
  items: PublicPhoto[]
  total: number
  limit: number
  offset: number
}

/** 创作者主页首屏数据：资料 + 第一页作品 + 作品集 */
export interface CreatorDetail {
  profile: CreatorProfile
  works: CreatorWorksPage
  collections: CreatorCollection[]
}

export interface CreatorFetchOptions {
  worksLimit?: number
  worksOffset?: number
  collectionsLimit?: number
}

function normalizeCreatorProfile(raw: Record<string, unknown>): CreatorProfile | null {
  const username = textOrNull(raw.username)
  if (!username) return null
  return {
    username,
    displayName: textOrNull(raw.display_name) ?? username,
    joinedAt: textOrNull(raw.joined_at),
    worksCount: countOf(raw.works_count),
    viewsTotal: countOf(raw.views_total),
    favoritesTotal: countOf(raw.favorites_total),
    collectionsCount: countOf(raw.collections_count),
  }
}

function normalizeCreatorCollection(raw: unknown): CreatorCollection | null {
  if (!raw || typeof raw !== 'object') return null
  const entry = raw as Record<string, unknown>
  const slug = textOrNull(entry.slug)
  if (!slug) return null
  const coverRaw = entry.cover
  return {
    slug,
    title: textOrNull(entry.title) ?? '未命名作品集',
    subtitle: textOrNull(entry.subtitle) ?? '',
    photoCount: countOf(entry.photo_count),
    cover: coverRaw && typeof coverRaw === 'object' ? toPublicPhoto(coverRaw as Photo) : null,
  }
}

function normalizeCreatorWorks(raw: unknown): CreatorWorksPage {
  if (!raw || typeof raw !== 'object') return { items: [], total: 0, limit: 0, offset: 0 }
  const entry = raw as Record<string, unknown>
  const items = Array.isArray(entry.items)
    ? entry.items
        .filter((item): item is Photo => !!item && typeof item === 'object')
        .map(toPublicPhoto)
        .filter((photo) => !!photo.id)
    : []
  return {
    items,
    total: countOf(entry.total),
    limit: countOf(entry.limit),
    offset: countOf(entry.offset),
  }
}

/** 创作者主页首屏（资料 + 作品 + 作品集一次取回，减少瀑布流前空白） */
export async function fetchCreator(
  username: string,
  options: CreatorFetchOptions = {},
): Promise<CreatorDetail> {
  const handle = (username || '').trim()
  if (!handle) throw new CreatorRequestError('缺少创作者用户名', 0)
  const query = new URLSearchParams()
  if (typeof options.worksLimit === 'number') query.set('works_limit', String(options.worksLimit))
  if (typeof options.worksOffset === 'number') query.set('works_offset', String(options.worksOffset))
  if (typeof options.collectionsLimit === 'number') {
    query.set('collections_limit', String(options.collectionsLimit))
  }
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const data = await fetchCreatorJson<Record<string, unknown>>(
    `/api/v1/creators/${encodeURIComponent(handle)}${suffix}`,
  )
  const profile = normalizeCreatorProfile(
    data && typeof data.profile === 'object' && data.profile
      ? (data.profile as Record<string, unknown>)
      : {},
  )
  if (!profile) throw new CreatorRequestError('创作者资料解析失败', 0)
  const collections = Array.isArray(data.collections)
    ? data.collections
        .map(normalizeCreatorCollection)
        .filter((item): item is CreatorCollection => item !== null)
    : []
  return {
    profile,
    works: normalizeCreatorWorks(data.works),
    collections,
  }
}

/** 创作者作品「加载更多」（GET /api/v1/creators/{username}/works） */
export async function fetchCreatorWorks(
  username: string,
  options: { limit?: number; offset?: number } = {},
): Promise<CreatorWorksPage> {
  const handle = (username || '').trim()
  if (!handle) throw new CreatorRequestError('缺少创作者用户名', 0)
  const query = new URLSearchParams()
  query.set('limit', String(options.limit ?? 12))
  query.set('offset', String(options.offset ?? 0))
  const data = await fetchCreatorJson<unknown>(
    `/api/v1/creators/${encodeURIComponent(handle)}/works?${query.toString()}`,
  )
  return normalizeCreatorWorks(data)
}
