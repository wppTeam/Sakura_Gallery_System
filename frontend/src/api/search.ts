/**
 * 检索 API
 *
 * 新契约（Agent 检索，后端并行实现，以实际为准）：
 *   GET /api/v1/search?q=&mode=agent|fast&limit=&offset=&season=&category=&campus=&tag=
 *   GET /api/v1/search/facets
 *   GET /api/v1/search/suggest?q=
 *
 * 兼容旧字段 results/total/query_time_ms/search_mode/fallback_reason/index_version，
 * 新增 explanation/steps/clarify/intent/facets/trace_id。
 *
 * 后端字段可能缺失或命名有出入，这里统一做容错归一化，页面只消费归一化后的结构。
 */
import request from './index'
import { getImageUrl, getPhotoUrl } from '../utils/format'

type UnknownRecord = Record<string, unknown>

// ────────────────────────────────────────────────────────────
// 容错工具
// ────────────────────────────────────────────────────────────

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function recordOf(value: unknown): UnknownRecord | null {
  return isRecord(value) ? value : null
}

function firstRecord(...values: unknown[]): UnknownRecord | null {
  for (const value of values) {
    const record = recordOf(value)
    if (record && Object.keys(record).length > 0) return record
  }
  return null
}

function toStringValue(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const text = toStringValue(value)
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

function firstBoolean(...values: unknown[]): boolean | null {
  for (const value of values) {
    if (typeof value === 'boolean') return value
    if (value === 1 || value === '1' || value === 'true') return true
    if (value === 0 || value === '0' || value === 'false') return false
  }
  return null
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function stringList(value: unknown): string[] {
  const collected: string[] = []
  const push = (item: unknown) => {
    if (typeof item === 'string') {
      const text = item.trim()
      if (text) collected.push(text)
    } else if (isRecord(item)) {
      const text = firstString(item.name, item.label, item.value, item.title, item.tag)
      if (text) collected.push(text)
    }
  }
  if (Array.isArray(value)) value.forEach(push)
  else push(value)
  return Array.from(new Set(collected))
}

function resolveImageUrl(raw: unknown): string {
  const text = toStringValue(raw)
  if (!text) return ''
  if (/^(https?:)?\/\//.test(text) || text.startsWith('data:') || text.startsWith('blob:')) return text
  return getImageUrl(text)
}

// ────────────────────────────────────────────────────────────
// 类型
// ────────────────────────────────────────────────────────────

export type SearchMode = 'agent' | 'fast'

export interface SearchStep {
  tool: string
  args: Record<string, unknown>
  resultCount: number | null
  latencyMs: number | null
  status: string
}

export interface SearchIntent {
  keywords: string[]
  filters: Record<string, string>
}

export interface FacetValue {
  value: string
  label: string
  count: number
}

export interface SearchFacets {
  season: FacetValue[]
  category: FacetValue[]
  tag: FacetValue[]
  campus: FacetValue[]
}

/** 归一化后的作品卡片模型（检索结果 / 详情推荐共用） */
export interface SearchWork {
  id: string
  kind: string
  title: string
  author: string
  thumbUrl: string
  fullUrl: string
  width: number
  height: number
  aspectRatio: string
  tags: string[]
  season: string
  category: string
  campus: string
  score: number | null
  matchReason: string
  publishedAt: string
  aigc: boolean
  blurhash: string
}

export interface AgentSearchResult {
  works: SearchWork[]
  total: number
  queryTimeMs: number
  searchMode: string
  fallbackReason: string | null
  indexVersion: string | null
  explanation: string | null
  steps: SearchStep[]
  clarify: string | null
  clarifyOptions: string[]
  intent: SearchIntent
  facets: SearchFacets
  traceId: string | null
}

export interface WorkSearchParams {
  q: string
  mode?: SearchMode
  limit?: number
  offset?: number
  season?: string | null
  category?: string | null
  campus?: string | null
  tag?: string | null
}

// ────────────────────────────────────────────────────────────
// 归一化
// ────────────────────────────────────────────────────────────

const EMPTY_FACETS: SearchFacets = { season: [], category: [], tag: [], campus: [] }

/** 后端分类键 → 中文展示名（筛选值仍用后端原始 value） */
const SEASON_LABELS: Record<string, string> = {
  spring: '春季', summer: '夏季', autumn: '秋季', winter: '冬季',
}

const CATEGORY_LABELS: Record<string, string> = {
  landscape: '风光', portrait: '人像', activity: '活动', documentary: '纪实',
  nature: '自然生态', architecture: '建筑', building: '建筑', sport: '运动',
  still_life: '静物', animal: '动物', plant: '植物', food: '美食',
  night: '夜景', street: '街拍', event: '活动', campus: '校园',
  '自然生态': '自然生态',
}

export function displaySeason(value: string): string {
  return SEASON_LABELS[value.trim().toLowerCase()] || value
}

export function displayCategory(value: string): string {
  return CATEGORY_LABELS[value.trim().toLowerCase()] || value
}

function normalizeFacetValues(value: unknown): FacetValue[] {
  const result: FacetValue[] = []

  if (Array.isArray(value)) {
    for (const entry of value) {
      if (isRecord(entry)) {
        const facetValue = firstString(entry.value, entry.key, entry.name, entry.label, entry.tag, entry.node_name)
        if (!facetValue) continue
        const count = firstNumber(entry.count, entry.total, entry.doc_count, entry.n) ?? 0
        result.push({ value: facetValue, label: firstString(entry.label, entry.name, facetValue), count })
      } else {
        const facetValue = toStringValue(entry)
        if (facetValue) result.push({ value: facetValue, label: facetValue, count: 0 })
      }
    }
    return result
  }

  if (isRecord(value)) {
    for (const [key, entry] of Object.entries(value)) {
      if (isRecord(entry)) {
        const count = firstNumber(entry.count, entry.total, entry.doc_count, entry.n) ?? 0
        result.push({ value: key, label: firstString(entry.label, entry.name, key), count })
      } else {
        const count = firstNumber(entry) ?? 0
        result.push({ value: key, label: key, count })
      }
    }
  }

  return result
}

export function normalizeFacets(raw: unknown): SearchFacets {
  const root = firstRecord(raw) ?? {}
  const nested = firstRecord(root.facets) ?? root
  const season = normalizeFacetValues(nested.season ?? nested.seasons ?? nested['季节'])
  const category = normalizeFacetValues(nested.category ?? nested.categories ?? nested['类别'])
  return {
    season: season.map((item) => ({ ...item, label: displaySeason(item.label || item.value) })),
    category: category.map((item) => ({ ...item, label: displayCategory(item.label || item.value) })),
    tag: normalizeFacetValues(nested.tag ?? nested.tags ?? nested['标签']),
    campus: normalizeFacetValues(nested.campus ?? nested.campuses ?? nested['校区']),
  }
}

function normalizeWork(raw: unknown): SearchWork | null {
  const outer = recordOf(raw)
  if (!outer) return null

  const provider = firstRecord(outer.work, outer.photo, outer.item) ?? outer

  const id = firstString(
    provider.id, provider.work_id, provider.photo_id, provider.uuid,
    outer.id, outer.work_id, outer.photo_id,
  )
  if (!id) return null

  const width = firstNumber(provider.width, provider.w, provider.image_width, outer.width) ?? 0
  const height = firstNumber(provider.height, provider.h, provider.image_height, outer.height) ?? 0

  let aspectRatio = firstString(provider.aspect_ratio, provider.aspectRatio, outer.aspect_ratio)
  if (aspectRatio && !/[/:]/.test(aspectRatio) && Number(aspectRatio) > 0) {
    // 后端可能返回 0.6654 这类「宽/高」小数比值
    aspectRatio = `${aspectRatio} / 1`
  }
  if (!aspectRatio && width > 0 && height > 0) aspectRatio = `${width} / ${height}`
  if (!aspectRatio) aspectRatio = '4 / 3'

  const thumbCandidate = firstString(
    provider.thumb_url, provider.thumbnail_url, provider.thumb, provider.thumbnail,
    provider.preview_url, provider.cover_url, provider.image_url, provider.url,
    outer.thumb_url, outer.thumbnail_url,
  )

  const fullCandidate = firstString(
    provider.full_url, provider.compressed_url, provider.original_url,
    outer.full_url, outer.compressed_url,
  )

  const uploader = firstRecord(provider.uploader, provider.user, provider.author_obj)
  const author = firstString(
    provider.author, provider.username, provider.uploader_name, provider.uploader_username,
    uploader?.username, uploader?.display_name, uploader?.name,
    outer.author, outer.username,
  )

  const tagsSource = provider.tags ?? outer.tags
  const classifications = firstRecord(provider.classifications) ?? {}

  const facetText = (key: string) => {
    const direct = firstString(provider[key], outer[key])
    if (direct) return direct
    const fromClass = classifications[key]
    if (isRecord(fromClass)) return firstString(fromClass.node_name, fromClass.name, fromClass.value)
    return ''
  }

  const matchReason = firstString(
    outer.match_reason, outer.matchReason, outer.reason, outer.why, outer.explanation,
    provider.match_reason, provider.reason,
  )

  return {
    id,
    kind: firstString(provider.kind, provider.type, outer.kind) || 'photo',
    title: firstString(provider.title, provider.name, provider.filename, outer.title) || '未命名作品',
    author,
    thumbUrl: thumbCandidate ? resolveImageUrl(thumbCandidate) : getPhotoUrl(id, 'thumbnail'),
    fullUrl: fullCandidate ? resolveImageUrl(fullCandidate) : '',
    width,
    height,
    aspectRatio,
    tags: stringList(tagsSource),
    season: displaySeason(facetText('season')),
    category: displayCategory(facetText('category')),
    campus: facetText('campus'),
    score: firstNumber(outer.score, provider.score, outer.relevance, outer.similarity),
    matchReason,
    publishedAt: firstString(provider.published_at, provider.created_at, outer.published_at, outer.created_at),
    aigc: firstBoolean(provider.is_aigc, provider.aigc, provider.aigc_label, outer.is_aigc) ?? false,
    blurhash: firstString(provider.blurhash, provider.lqip, outer.blurhash),
  }
}

function normalizeSteps(raw: unknown): SearchStep[] {
  return asArray(raw)
    .map((entry) => {
      if (!isRecord(entry)) return null
      const tool = firstString(entry.tool, entry.name, entry.step, entry.action)
      if (!tool) return null
      const args = firstRecord(entry.args, entry.params, entry.arguments) ?? {}
      return {
        tool,
        args,
        resultCount: firstNumber(entry.result_count, entry.resultCount, entry.count, entry.hits),
        latencyMs: firstNumber(entry.latency_ms, entry.latencyMs, entry.elapsed_ms, entry.duration_ms),
        status: firstString(entry.status, entry.state) || 'ok',
      }
    })
    .filter((step): step is SearchStep => step !== null)
}

function normalizeIntent(raw: unknown): SearchIntent {
  const intent = firstRecord(raw) ?? {}
  const filters: Record<string, string> = {}
  const rawFilters = firstRecord(intent.filters, intent.facet_filters) ?? {}
  for (const [key, value] of Object.entries(rawFilters)) {
    const text = toStringValue(value)
    if (text) filters[key] = text
  }
  return {
    keywords: stringList(intent.keywords ?? intent.terms),
    filters,
  }
}

function normalizeClarify(rawClarify: unknown, rawOptions: unknown): { clarify: string | null; options: string[] } {
  let clarify = ''
  let options: string[] = stringList(rawOptions)

  if (typeof rawClarify === 'string') {
    clarify = rawClarify.trim()
  } else if (isRecord(rawClarify)) {
    clarify = firstString(rawClarify.question, rawClarify.text, rawClarify.message, rawClarify.prompt)
    if (options.length === 0) {
      options = stringList(rawClarify.options ?? rawClarify.suggestions ?? rawClarify.choices)
    }
  }

  return { clarify: clarify || null, options: Array.from(new Set(options)).slice(0, 8) }
}

export function normalizeSearchResponse(raw: unknown): AgentSearchResult {
  const root = firstRecord(raw) ?? {}
  const rawResults = asArray(root.results ?? root.items ?? root.works ?? root.data)

  const works: SearchWork[] = []
  for (const entry of rawResults) {
    const work = normalizeWork(entry)
    if (work) works.push(work)
  }

  const { clarify, options } = normalizeClarify(root.clarify, root.clarify_options ?? root.options)
  const explanation = firstString(root.explanation, root.summary, root.answer) || null
  const fallbackReason = firstString(root.fallback_reason, root.fallbackReason) || null
  const rawExplainSteps = Array.isArray(root.steps) ? root.steps : (isRecord(root.trace) ? asArray(root.trace.steps) : [])

  return {
    works,
    total: firstNumber(root.total, root.total_count) ?? works.length,
    queryTimeMs: firstNumber(root.query_time_ms, root.queryTimeMs, root.elapsed_ms, root.took_ms) ?? 0,
    searchMode: firstString(root.search_mode, root.mode, root.searchMode) || 'agent',
    fallbackReason,
    indexVersion: firstString(root.index_version, root.indexVersion) || null,
    explanation,
    steps: normalizeSteps(rawExplainSteps),
    clarify,
    clarifyOptions: options,
    intent: normalizeIntent(root.intent),
    facets: normalizeFacets(root.facets ?? root.facet_counts),
    traceId: firstString(root.trace_id, root.traceId) || null,
  }
}

// ────────────────────────────────────────────────────────────
// 新接口
// ────────────────────────────────────────────────────────────

function compactParams(params: Record<string, unknown>): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    result[key] = String(value)
  }
  return result
}

/**
 * Agent / 快速检索。
 * 不吞错误：调用方需要区分超时、网络、5xx 等状态并展示降级提示。
 */
export async function searchWorks(params: WorkSearchParams): Promise<AgentSearchResult> {
  const raw = await request.get<unknown>('/api/v1/search', {
    timeout: 60000,
    params: compactParams({
      q: params.q,
      mode: params.mode ?? 'agent',
      limit: params.limit ?? 24,
      offset: params.offset ?? 0,
      season: params.season,
      category: params.category,
      campus: params.campus,
      tag: params.tag,
    }),
  })
  return normalizeSearchResponse(raw)
}

/** 检索 facet 候选（空查询态展示热门方向；失败时返回空 facet，由页面降级） */
export async function getSearchFacets(params?: { q?: string }): Promise<SearchFacets> {
  const raw = await request.get<unknown>('/api/v1/search/facets', {
    params: compactParams({ q: params?.q }),
  })
  return normalizeFacets(raw)
}

/** 搜索联想词 */
export async function getSearchSuggestions(q: string): Promise<string[]> {
  if (!q.trim()) return []
  const raw = await request.get<unknown>('/api/v1/search/suggest', { params: { q: q.trim() } })
  if (Array.isArray(raw)) return stringList(raw)
  const root = firstRecord(raw)
  if (!root) return []
  return stringList(root.suggestions ?? root.items ?? root.results ?? root.words)
}

// ────────────────────────────────────────────────────────────
// 旧接口（GalleryView 仍在用，保持兼容，新页面不要使用）
// ────────────────────────────────────────────────────────────

export interface SearchResult {
  photo_id: string
  score: number
  tags: string[]
  classifications: Record<string, string | null>
  photo?: {
    id: string
    filename: string
    width: number
    height: number
    thumb_url: string
    created_at: string
  }
}

export interface SearchResponse {
  results: SearchResult[]
  total: number
  query_time_ms: number
  search_mode: string
  fallback_reason?: string | null
  index_version?: string | null
}

export interface SearchParams {
  q: string
  limit?: number
  season?: string
  campus?: string
  category?: string
  building?: string
  gallery_series?: string
  gallery_year?: string
  award_level?: string
  photo_type?: string
  source_type?: string
  facility?: string
  landscape?: string
  natural_phenomenon?: string
  technique?: string
  animal?: string
  plant?: string
}

/** @deprecated 旧检索接口，GalleryView 兼容用 */
export function searchPhotos(params: SearchParams): Promise<SearchResponse> {
  return request.get<SearchResponse>('/api/v1/search', { params })
}

/** @deprecated 旧搜索理解接口 */
export function interpretSearch(query: string): Promise<{
  facet_filters: Record<string, string>
  keywords: string[]
  original_query: string
  method: string
  confidence: number
  explanation: string | null
}> {
  return request.post('/api/v1/photos/interpret-search', { query })
}

export { EMPTY_FACETS }
