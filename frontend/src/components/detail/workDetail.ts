/**
 * 作品详情数据层
 *
 * 数据源：GET /api/v1/photos/public/{id}（旧的 PhotoResponse 契约 + 后续可能新增字段）。
 * 这里只做「读取 + 容错归一化 + 展示字段推导」，不触碰 uploader_student_id / uploader_name
 * 等敏感字段——公开页绝不展示学号与真实姓名。
 */
import request from '../../api/index'
import type { Photo } from '../../types/photo'
import { taxonomyValueName } from '../../types/photo'
import { displayPhotoAuthor, displayPhotoTitle } from '../../utils/photoDisplay'
import { getPhotoDownloadUrl, getPhotoUrl, formatDate, formatFileSize } from '../../utils/format'
import { getPublicPhotoById, getPhotoById, getPublicPhotos } from '../../api/photo'
import type { SearchWork } from '../../api/search'

type UnknownRecord = Record<string, unknown>

/** 后端 PhotoResponse 未来可能扩充的字段，这里放宽类型以便容错读取 */
export type RawPhoto = Photo & UnknownRecord

export interface WorkExifRow {
  label: string
  value: string
}

export interface WorkVariant {
  label: string
  url: string
  width: number
  height: number
}

export interface WorkLicense {
  code: string
  name: string
  url: string
}

export interface WorkAigcInfo {
  model: string
  provider: string
  prompt: string
  label: string
}

export interface WorkDetail {
  id: string
  kind: string
  title: string
  author: string
  description: string
  tags: string[]
  width: number
  height: number
  aspectRatio: string
  fileSize: number
  mimeType: string

  thumbUrl: string
  displayUrl: string
  originalUrl: string
  downloadUrl: string
  variants: WorkVariant[]

  season: string
  category: string
  campus: string
  place: string

  capturedAt: string
  publishedAt: string
  createdAt: string

  exifRows: WorkExifRow[]
  hasExif: boolean

  license: WorkLicense | null
  aigc: WorkAigcInfo | null

  views: number | null
  likes: number | null
  favorites: number | null
  downloads: number | null
}

const SEASON_LABELS: Record<string, string> = {
  spring: '春季', summer: '夏季', autumn: '秋季', winter: '冬季',
  春季: '春季', 夏季: '夏季', 秋季: '秋季', 冬季: '冬季',
}

const CATEGORY_LABELS: Record<string, string> = {
  landscape: '风光', portrait: '人像', activity: '活动', documentary: '纪实',
  风光: '风光', 风光类: '风光', 校园风光: '风光', 建筑楼宇: '建筑', 校区设施: '设施',
  纪实: '纪实', 纪实类: '纪实', 活动: '活动', 人文纪实: '人文', 自然生态: '自然生态', 人像: '人像',
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function textOf(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const text = textOf(value)
    if (text) return text
  }
  return ''
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim() !== '') {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return null
}

function firstBoolean(...values: unknown[]): boolean {
  for (const value of values) {
    if (value === true || value === 1 || value === '1' || value === 'true') return true
  }
  return false
}

function normalizeImageUrl(raw: unknown): string {
  const text = textOf(raw)
  if (!text) return ''
  if (/^(https?:)?\/\//.test(text) || text.startsWith('data:') || text.startsWith('blob:')) return text
  const base = import.meta.env.VITE_API_BASE_URL || ''
  return `${base}${text.startsWith('/') ? '' : '/'}${text}`
}

function seasonLabel(photo: RawPhoto): string {
  const fromTaxonomy = taxonomyValueName(photo.classifications?.season)
  const raw = fromTaxonomy || textOf(photo.season)
  if (!raw) return ''
  return SEASON_LABELS[raw] || SEASON_LABELS[raw.toLowerCase()] || raw
}

function categoryLabel(photo: RawPhoto): string {
  const fromTaxonomy = taxonomyValueName(photo.classifications?.category)
  const raw = fromTaxonomy || textOf(photo.category)
  if (!raw) return ''
  return CATEGORY_LABELS[raw] || CATEGORY_LABELS[raw.toLowerCase()] || raw
}

function classLabel(photo: RawPhoto, ...keys: string[]): string {
  const classifications = photo.classifications as Record<string, unknown> | undefined
  for (const key of keys) {
    const value = classifications?.[key]
    const name = taxonomyValueName(value as never)
    if (name) return name
  }
  return ''
}

/** 快门：秒数转 1/N s，字符串原样 */
function formatShutter(raw: unknown): string {
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text) return ''
    if (text.includes('/') || /s$/i.test(text)) return text
    const parsed = Number(text)
    if (Number.isFinite(parsed)) return formatShutter(parsed)
    return text
  }
  if (typeof raw === 'number' && Number.isFinite(raw) && raw > 0) {
    if (raw >= 1) return `${raw} s`
    return `1/${Math.round(1 / raw)} s`
  }
  return ''
}

function normalizeExposure(value: unknown): string {
  if (Array.isArray(value)) return value.map((entry) => textOf(entry)).filter(Boolean).join('、')
  return textOf(value)
}

/**
 * EXIF 展示白名单。
 * 只读取拍摄参数，GPS / 设备序列号 / 原始完整 EXIF 一律不展示（合规要求见 AGENTS.md §5）。
 */
function buildExifRows(photo: RawPhoto, displayWidth: number, displayHeight: number): WorkExifRow[] {
  const exifRoot = isRecord(photo.exif_data) ? photo.exif_data : {}
  const nested = isRecord(exifRoot.Exif) ? (exifRoot.Exif as UnknownRecord) : {}
  const exif: UnknownRecord = { ...exifRoot, ...nested }

  const read = (...keys: string[]): unknown => {
    for (const key of keys) {
      if (exif[key] !== undefined && exif[key] !== null && exif[key] !== '') return exif[key]
    }
    return null
  }

  const rows: WorkExifRow[] = []
  const push = (label: string, value: string) => {
    if (value) rows.push({ label, value })
  }

  const make = firstString(read('Make', 'make', 'CameraMake'))
  const model = firstString(read('Model', 'model', 'CameraModel'))
  const camera = [make, model].filter(Boolean).join(' ').trim()
  push('相机', camera)

  const lens = firstString(read('LensModel', 'Lens', 'LensSpecification', 'lens'))
  push('镜头', Array.isArray(lens) ? lens.join(' ') : lens)

  const fNumber = firstNumber(read('FNumber', 'FNum', 'Aperture', 'f_number'))
  if (fNumber) push('光圈', `f/${fNumber}`)

  const shutter = formatShutter(read('ExposureTime', 'ShutterSpeed', 'exposure_time'))
  push('快门', shutter)

  const iso = normalizeExposure(read('ISOSpeedRatings', 'ISO', 'PhotographicSensitivity'))
  push('ISO', iso)

  const focal = firstNumber(read('FocalLength', 'focal_length'))
  if (focal) push('焦距', `${focal} mm`)

  const focal35 = firstNumber(read('FocalLengthIn35mmFilm', 'FocalLength35mm'))
  if (focal35) push('等效焦距', `${focal35} mm`)

  const captured = firstString(read('DateTimeOriginal', 'CreateDate', 'DateTime'), photo.captured_at)
  if (captured) push('拍摄时间', formatDate(captured, 'YYYY-MM-DD HH:mm'))

  const software = firstString(read('Software', 'processing_software'))
  push('后期', software)

  // 无 EXIF 时不展示一排短横，只在信息栏给一句话（见 InfoPanel）
  if (rows.length === 0 && displayWidth > 0 && displayHeight > 0) {
    rows.push({ label: '分辨率', value: `${displayWidth} × ${displayHeight}` })
  }
  return rows
}

function normalizeVariants(photo: RawPhoto, id: string): WorkVariant[] {
  const rawVariants = photo.variants
  const variants: WorkVariant[] = []
  const seen = new Set<string>()

  const pushVariant = (label: string, url: string, width = 0, height = 0) => {
    if (!url || seen.has(url)) return
    seen.add(url)
    variants.push({ label, url, width, height })
  }

  if (Array.isArray(rawVariants)) {
    for (const entry of rawVariants) {
      if (isRecord(entry)) {
        const url = normalizeImageUrl(firstString(entry.url, entry.path, entry.src, entry.href))
        const width = firstNumber(entry.width, entry.w) ?? 0
        const height = firstNumber(entry.height, entry.h) ?? 0
        const size = firstNumber(entry.size, entry.long_edge, entry.longEdge)
        const label = firstString(entry.label, entry.name) || (size ? `${size}px` : width ? `${width}px` : '') || '变体'
        pushVariant(label, url, width, height)
      } else if (typeof entry === 'string') {
        pushVariant('变体', normalizeImageUrl(entry))
      }
    }
  } else if (isRecord(rawVariants)) {
    for (const [key, entry] of Object.entries(rawVariants)) {
      const url = normalizeImageUrl(isRecord(entry) ? firstString(entry.url, entry.path) : entry)
      const width = isRecord(entry) ? firstNumber(entry.width) ?? 0 : 0
      const label = /^\d+$/.test(key) ? `${key}px` : key
      pushVariant(label, url, width, heightOfVariant(width, id, photo))
    }
  }

  return variants.sort((a, b) => (b.width || 0) - (a.width || 0))
}

function heightOfVariant(width: number, _id: string, photo: RawPhoto): number {
  const rawWidth = firstNumber(photo.width) ?? 0
  const rawHeight = firstNumber(photo.height) ?? 0
  if (!width || !rawWidth || !rawHeight) return 0
  return Math.round((width / rawWidth) * rawHeight)
}

function normalizeLicense(photo: RawPhoto): WorkLicense | null {
  const raw = photo.license ?? photo.license_info ?? photo.license_code
  if (isRecord(raw)) {
    const code = firstString(raw.code, raw.id, raw.key)
    const name = firstString(raw.name, raw.title, raw.label, code)
    const url = firstString(raw.url, raw.href)
    if (!code && !name) return null
    return { code: code || name, name: name || code, url }
  }
  const code = textOf(raw) || firstString(photo.license_name)
  if (!code) return null
  const licenseUrl = code.toUpperCase().startsWith('CC')
    ? `https://creativecommons.org/licenses/${code.toLowerCase().replace(/^cc\s*/, '').replace(/\s+/g, '-')}/4.0/`
    : ''
  return { code, name: code, url: licenseUrl }
}

function normalizeAigc(photo: RawPhoto): WorkAigcInfo | null {
  const kind = textOf(photo.kind).toLowerCase()
  const labelRaw = photo.aigc_label ?? photo.is_aigc
  const labeled = kind === 'aigc' || firstBoolean(labelRaw) || (typeof labelRaw === 'string' && labelRaw !== '')
  const meta = isRecord(photo.aigc_meta) ? photo.aigc_meta : isRecord(photo.aigc) ? (photo.aigc as UnknownRecord) : {}
  const model = firstString(meta.model, photo.aigc_model)
  const provider = firstString(meta.provider, photo.aigc_provider)
  const prompt = firstString(
    (photo.prompt_public ? photo.prompt : ''),
    meta.prompt_public, meta.prompt,
    photo.aigc_prompt,
  )
  if (!labeled && !model && !provider && !prompt) return null
  return {
    model,
    provider,
    prompt,
    label: typeof labelRaw === 'string' ? labelRaw : '',
  }
}

function pickDisplayVariant(variants: WorkVariant[]): WorkVariant | null {
  if (!variants.length) return null
  // 优先 1080–1600 宽的变体，其次最大变体
  const preferred = variants.find((item) => item.width > 0 && item.width <= 1600 && item.width >= 1000)
  return preferred || variants[0]
}

export function normalizeWorkDetail(raw: RawPhoto): WorkDetail {
  const id = textOf(raw.id)
  const width = firstNumber(raw.width) ?? 0
  const height = firstNumber(raw.height) ?? 0
  const aspectRatio = firstString(raw.aspect_ratio) || (width > 0 && height > 0 ? `${width} / ${height}` : '4 / 3')

  const variants = normalizeVariants(raw, id)
  const displayVariant = pickDisplayVariant(variants)
  const displayUrl = displayVariant?.url || getPhotoUrl(id, 'compressed')
  const originalVariant = variants[0]

  const title = displayPhotoTitle(raw) || '未命名作品'
  const rawAuthor = displayPhotoAuthor(raw)
  const author = rawAuthor && rawAuthor !== '未知' ? rawAuthor : '北化创作者'

  const campus = textOf(raw.campus) || classLabel(raw, 'campus')
  const building = firstString(
    classLabel(raw, 'building', 'landmark'),
    textOf(raw.building),
    textOf(raw.landmark),
  )
  const place = [campus, building].filter(Boolean).join(' · ')

  const exifRows = buildExifRows(raw, width, height)

  return {
    id,
    kind: textOf(raw.kind) || 'photo',
    title,
    author,
    description: textOf(raw.description),
    tags: Array.isArray(raw.tags) ? raw.tags.filter((tag): tag is string => typeof tag === 'string') : [],
    width,
    height,
    aspectRatio,
    fileSize: firstNumber(raw.file_size) ?? 0,
    mimeType: textOf(raw.mime_type),

    thumbUrl: getPhotoUrl(id, 'thumbnail'),
    displayUrl,
    originalUrl: originalVariant?.url || getPhotoUrl(id, 'original'),
    downloadUrl: getPhotoDownloadUrl(id),
    variants,

    season: seasonLabel(raw),
    category: categoryLabel(raw),
    campus,
    place,

    capturedAt: firstString(raw.captured_at),
    publishedAt: firstString(raw.published_at, raw.created_at),
    createdAt: firstString(raw.created_at),

    exifRows,
    hasExif: exifRows.some((row) => row.label !== '分辨率'),

    license: normalizeLicense(raw),
    aigc: normalizeAigc(raw),

    views: firstNumber(raw.views, raw.view_count),
    likes: firstNumber(raw.likes, raw.like_count),
    favorites: firstNumber(raw.favorite_count, raw.favorites),
    downloads: firstNumber(raw.downloads, raw.download_count),
  }
}

/** 读取作品详情：先走公开接口，失败后尝试带鉴权接口（作者 / 审核员可见未发布作品） */
export async function fetchWorkDetail(id: string): Promise<WorkDetail> {
  let raw: RawPhoto
  try {
    raw = (await getPublicPhotoById(id)) as unknown as RawPhoto
  } catch (publicError) {
    try {
      raw = (await getPhotoById(id)) as unknown as RawPhoto
    } catch {
      throw publicError
    }
  }
  return normalizeWorkDetail(raw)
}

export interface RelatedWork {
  id: string
  title: string
  thumbUrl: string
  aspectRatio: string
  meta: string
}

/** 相关作品：优先同季，其次同类，最后最新 */
export async function fetchRelatedWorks(detail: WorkDetail, limit = 8): Promise<RelatedWork[]> {
  const attempts: Array<Record<string, string>> = []
  if (detail.season) attempts.push({ season: detail.season })
  if (detail.category) attempts.push({ category: detail.category })
  attempts.push({})

  for (const filters of attempts) {
    try {
      const response = await getPublicPhotos({ limit: limit + 1, ...filters })
      const works = response.items
        .filter((item) => item.id !== detail.id)
        .slice(0, limit)
        .map((item) => {
          const width = item.width || 0
          const height = item.height || 0
          return {
            id: item.id,
            title: displayPhotoTitle(item) || '未命名作品',
            thumbUrl: getPhotoUrl(item.id, 'thumbnail'),
            aspectRatio: width > 0 && height > 0 ? `${width} / ${height}` : '4 / 3',
            meta: [seasonLabel(item as RawPhoto), categoryLabel(item as RawPhoto)].filter(Boolean).join(' · '),
          }
        })
      if (works.length > 0) return works
    } catch {
      // 某一路筛选失败就换下一种，全部失败时返回空数组由页面展示提示
    }
  }
  return []
}

/** 将详情转换为检索页共用的卡片模型（分享/引用等场景复用） */
export function detailToSearchWork(detail: WorkDetail): SearchWork {
  return {
    id: detail.id,
    kind: detail.kind,
    title: detail.title,
    author: detail.author,
    thumbUrl: detail.thumbUrl,
    fullUrl: detail.displayUrl,
    width: detail.width,
    height: detail.height,
    aspectRatio: detail.aspectRatio,
    tags: detail.tags,
    season: detail.season,
    category: detail.category,
    campus: detail.campus,
    score: null,
    matchReason: '',
    publishedAt: detail.publishedAt,
    aigc: Boolean(detail.aigc),
    blurhash: '',
  }
}

export { formatFileSize }

// ────────────────────────────────────────────────────────────
// 收藏（后端 /api/v1/photos/{id}/favorite，需要登录）
// ────────────────────────────────────────────────────────────

export interface FavoriteState {
  favorited: boolean
  favoriteCount: number | null
}

function normalizeFavorite(raw: unknown): FavoriteState {
  const source = isRecord(raw) ? raw : {}
  const count = firstNumber(source.favorite_count, source.favoriteCount, source.count)
  return {
    favorited: firstBoolean(source.favorited, source.is_favorited, source.favorite),
    favoriteCount: count,
  }
}

export async function getFavoriteState(id: string): Promise<FavoriteState> {
  const raw = await request<unknown>({ url: `/api/v1/photos/${id}/favorite`, method: 'get' })
  return normalizeFavorite(raw)
}

export async function toggleFavoriteState(id: string): Promise<FavoriteState> {
  const raw = await request<unknown>({ url: `/api/v1/photos/${id}/favorite`, method: 'post' })
  return normalizeFavorite(raw)
}
