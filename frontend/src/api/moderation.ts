/**
 * AI 审核管理端 API（与 backend/app/api/v1/endpoints/moderation.py 对齐）
 *
 * - GET  /api/v1/admin/moderation/queue        人工审核队列（每张照片最新一次 agent 结论）
 * - GET  /api/v1/admin/moderation/{photo_id}   单张照片最新审核详情
 * - POST /api/v1/admin/moderation/{photo_id}/run      重新触发审核（202）
 * - POST /api/v1/admin/moderation/{photo_id}/decision 人工终判
 * - GET  /api/v1/admin/moderation/stats?days=7
 *
 * 后端响应已经是稳定结构，这里只做「兼容别名 + 缺省值兜底」，不做展示文案。
 */
import request from './index'
import { getImageUrl, getPhotoUrl } from '../utils/format'

type UnknownRecord = Record<string, unknown>

export type ModerationTier = 'L0' | 'L1' | 'L2'
export type ModerationDecision = 'approve' | 'reject' | 'hold'
export type ReviewStatus = 'queued' | 'running' | 'completed' | 'failed'
export type RuleSeverity = 'info' | 'warn' | 'block'

// ────────────────────────────────────────────────────────────
// 工具
// ────────────────────────────────────────────────────────────

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

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

function toBoolean(value: unknown): boolean {
  if (value === true || value === 1) return true
  if (typeof value === 'string') return ['true', '1', 'yes', 'y'].includes(value.toLowerCase())
  return false
}

function normalizeTier(value: unknown): ModerationTier | null {
  const text = textOf(value).toUpperCase()
  return text === 'L0' || text === 'L1' || text === 'L2' ? text : null
}

function normalizeDecision(value: unknown): ModerationDecision | null {
  const text = textOf(value).toLowerCase()
  return text === 'approve' || text === 'reject' || text === 'hold' ? text : null
}

/** 兼容 thumb_path / thumb_url / 绝对 URL */
export function resolveThumbUrl(raw: unknown): string {
  const text = textOf(raw)
  if (!text) return ''
  if (/^(https?:)?\/\//.test(text) || text.startsWith('data:') || text.startsWith('blob:')) return text
  return getImageUrl(text)
}

// ────────────────────────────────────────────────────────────
// 类型
// ────────────────────────────────────────────────────────────

export interface ModerationPhoto {
  id: string
  title: string
  filename: string
  status: string
  processingStatus: string
  category: string
  season: string
  width: number
  height: number
  thumbUrl: string
  /** 管理端可见的上传者展示名（公开身份，非真实姓名/学号） */
  displayName: string
  username: string
  createdAt: string
}

export interface RuleHit {
  code: string
  severity: RuleSeverity
  detail: string
}

/**
 * 投稿时申报的 AIGC 生成信息（review.rules.aigc_declaration）。
 * 由后端在规则前置阶段写入，是「AI 生成」法定标识的申报证据。
 */
export interface AigcDeclarationEvidence {
  declared: boolean
  /** 显式标识文案，如「AI 生成」 */
  label: string
  model: string
  provider: string
  sourceWorkId: string
  faceSwap: boolean
  consentConfirmed: boolean
  promptPublic: boolean
  raw: UnknownRecord
}

export interface RuleResult {
  blocked: boolean
  maxSeverity: RuleSeverity | ''
  checked: boolean
  width: number
  height: number
  fileSize: number
  imageFormat: string
  dhash: string
  hits: RuleHit[]
  /** AIGC 声明证据（非 AIGC 作品为 null） */
  aigcDeclaration: AigcDeclarationEvidence | null
}

export interface PrefilterResult {
  hasIdentifiablePerson: boolean
  likelyAigc: boolean
  sensitiveContent: boolean
  copyrightRisk: string
  watermark: boolean
  textInImage: boolean
  suggestedTier: ModerationTier | null
  confidence: number | null
  reason: string
}

export interface EscalationResult {
  finalTier: ModerationTier | null
  decision: ModerationDecision | null
  riskPoints: string[]
  needsHuman: boolean
  confidence: number | null
  reason: string
}

export interface ModerationReview {
  id: string
  photoId: string
  status: string
  tier: ModerationTier | null
  suggestedTier: ModerationTier | null
  rules: RuleResult | null
  prefilter: PrefilterResult | null
  escalation: EscalationResult | null
  finalDecision: ModerationDecision | null
  finalTier: ModerationTier | null
  reviewerId: string
  reviewedAt: string
  provider: string
  modelId: string
  latencyMs: number
  promptTokens: number
  completionTokens: number
  costUsd: number
  error: string
  createdAt: string
  updatedAt: string
  photo: ModerationPhoto | null
  /** 原始对象，便于排障，不用于展示 */
  raw: UnknownRecord
}

export interface ModerationQueueParams {
  status?: string
  tier?: string
  limit?: number
  offset?: number
}

export interface ModerationQueueResponse {
  items: ModerationReview[]
  total: number
  limit: number
  offset: number
}

export interface ModerationStats {
  days: number
  total: number
  byTier: Record<ModerationTier, number>
  byStatus: Record<string, number>
  pendingHuman: number
  avgLatencyMs: number
  promptTokens: number
  completionTokens: number
  costUsd: number
  todayCalls: number
  dailyBudget: number
  remainingCalls: number | null
}

export interface ModerationRunResponse {
  ok: boolean
  photoId: string
  reviewId: string
  status: string
  message: string
}

export interface DecisionPayload {
  decision: ModerationDecision
  reason?: string
  finalTier?: ModerationTier
}

// ────────────────────────────────────────────────────────────
// 归一化
// ────────────────────────────────────────────────────────────

function normalizePhoto(raw: unknown): ModerationPhoto | null {
  if (!isRecord(raw)) return null
  const id = firstString(raw.id, raw.photo_id)
  if (!id) return null
  const uploader = isRecord(raw.uploader) ? raw.uploader : {}
  return {
    id,
    title: firstString(raw.title, raw.filename) || '未命名作品',
    filename: firstString(raw.filename),
    status: firstString(raw.status),
    processingStatus: firstString(raw.processing_status, raw.processingStatus),
    category: firstString(raw.category),
    season: firstString(raw.season),
    width: toNumber(raw.width),
    height: toNumber(raw.height),
    // pending 照片的缩略图端点需要鉴权，统一走 getPhotoUrl 拼 access_token
    thumbUrl: getPhotoUrl(id, 'thumbnail') || resolveThumbUrl(firstString(raw.thumb_url, raw.thumbUrl, raw.thumb_path)),
    displayName: firstString(uploader.display_name, uploader.displayName),
    username: firstString(uploader.username),
    createdAt: firstString(raw.created_at, raw.createdAt),
  }
}

function normalizeAigcDeclaration(raw: unknown): AigcDeclarationEvidence | null {
  if (!isRecord(raw) || Object.keys(raw).length === 0) return null
  return {
    declared: toBoolean(raw.declared),
    label: firstString(raw.label),
    model: firstString(raw.model),
    provider: firstString(raw.provider),
    sourceWorkId: firstString(raw.source_work_id, raw.sourceWorkId),
    faceSwap: toBoolean(raw.face_swap ?? raw.faceSwap),
    consentConfirmed: toBoolean(raw.consent_confirmed ?? raw.consentConfirmed),
    promptPublic: toBoolean(raw.prompt_public ?? raw.promptPublic),
    raw,
  }
}

function normalizeRules(raw: unknown): RuleResult | null {
  if (!isRecord(raw) || Object.keys(raw).length === 0) return null
  const hitsRaw = Array.isArray(raw.hits) ? raw.hits : []
  const hits: RuleHit[] = hitsRaw
    .filter(isRecord)
    .map((hit) => {
      const severity = textOf(hit.severity).toLowerCase()
      return {
        code: firstString(hit.code) || 'unknown',
        severity: severity === 'block' || severity === 'warn' ? (severity as RuleSeverity) : 'info',
        detail: firstString(hit.detail),
      }
    })
  const maxSeverity = firstString(raw.max_severity, raw.maxSeverity).toLowerCase()
  return {
    blocked: toBoolean(raw.blocked),
    maxSeverity: maxSeverity === 'block' || maxSeverity === 'warn' || maxSeverity === 'info' ? (maxSeverity as RuleSeverity) : '',
    checked: toBoolean(raw.checked),
    width: toNumber(raw.width),
    height: toNumber(raw.height),
    fileSize: toNumber(raw.file_size, toNumber(raw.fileSize)),
    imageFormat: firstString(raw.image_format, raw.imageFormat),
    dhash: firstString(raw.dhash),
    hits,
    aigcDeclaration: normalizeAigcDeclaration(raw.aigc_declaration ?? raw.aigcDeclaration),
  }
}

function normalizePrefilter(raw: unknown): PrefilterResult | null {
  if (!isRecord(raw) || Object.keys(raw).length === 0) return null
  return {
    hasIdentifiablePerson: toBoolean(raw.has_identifiable_person ?? raw.hasIdentifiablePerson ?? raw.person),
    likelyAigc: toBoolean(raw.likely_aigc ?? raw.likelyAigc ?? raw.is_aigc),
    sensitiveContent: toBoolean(raw.sensitive_content ?? raw.sensitiveContent ?? raw.sensitive),
    copyrightRisk: firstString(raw.copyright_risk, raw.copyrightRisk) || 'unknown',
    watermark: toBoolean(raw.watermark),
    textInImage: toBoolean(raw.text_in_image ?? raw.textInImage),
    suggestedTier: normalizeTier(raw.suggested_tier ?? raw.suggestedTier),
    confidence: typeof raw.confidence === 'number' ? raw.confidence : null,
    reason: firstString(raw.reason, raw.explanation),
  }
}

function normalizeEscalation(raw: unknown): EscalationResult | null {
  if (!isRecord(raw) || Object.keys(raw).length === 0) return null
  const riskPointsRaw = Array.isArray(raw.risk_points) ? raw.risk_points : Array.isArray(raw.riskPoints) ? raw.riskPoints : []
  return {
    finalTier: normalizeTier(raw.final_tier ?? raw.finalTier),
    decision: normalizeDecision(raw.decision),
    riskPoints: riskPointsRaw.filter((item): item is string => typeof item === 'string' && item.trim() !== ''),
    needsHuman: toBoolean(raw.needs_human ?? raw.needsHuman),
    confidence: typeof raw.confidence === 'number' ? raw.confidence : null,
    reason: firstString(raw.reason, raw.explanation),
  }
}

/** 队列项既可能是扁平的 review，也可能是 { photo, review } —— 两种都兼容 */
export function normalizeReview(raw: unknown): ModerationReview {
  const outer = isRecord(raw) ? raw : {}
  const reviewRaw = isRecord(outer.review) ? outer.review : outer
  const photoRaw = isRecord(outer.photo) ? outer.photo : isRecord(reviewRaw.photo) ? reviewRaw.photo : null
  const photo = normalizePhoto(photoRaw)

  return {
    id: firstString(reviewRaw.id, outer.id),
    photoId: firstString(reviewRaw.photo_id, reviewRaw.photoId, outer.photo_id, photo?.id),
    status: firstString(reviewRaw.status) || 'queued',
    tier: normalizeTier(reviewRaw.tier),
    suggestedTier: normalizeTier(reviewRaw.suggested_tier ?? reviewRaw.suggestedTier),
    rules: normalizeRules(reviewRaw.rules),
    prefilter: normalizePrefilter(reviewRaw.prefilter),
    escalation: normalizeEscalation(reviewRaw.escalation),
    finalDecision: normalizeDecision(reviewRaw.final_decision ?? reviewRaw.finalDecision),
    finalTier: normalizeTier(reviewRaw.final_tier ?? reviewRaw.finalTier),
    reviewerId: firstString(reviewRaw.reviewer_id, reviewRaw.reviewerId),
    reviewedAt: firstString(reviewRaw.reviewed_at, reviewRaw.reviewedAt),
    provider: firstString(reviewRaw.provider),
    modelId: firstString(reviewRaw.model_id, reviewRaw.modelId),
    latencyMs: toNumber(reviewRaw.latency_ms ?? reviewRaw.latencyMs),
    promptTokens: toNumber(reviewRaw.prompt_tokens ?? reviewRaw.promptTokens),
    completionTokens: toNumber(reviewRaw.completion_tokens ?? reviewRaw.completionTokens),
    costUsd: toNumber(reviewRaw.cost_usd ?? reviewRaw.costUsd),
    error: firstString(reviewRaw.error),
    createdAt: firstString(reviewRaw.created_at, reviewRaw.createdAt),
    updatedAt: firstString(reviewRaw.updated_at, reviewRaw.updatedAt),
    photo,
    raw: reviewRaw,
  }
}

function extractList(raw: unknown): unknown[] {
  if (Array.isArray(raw)) return raw
  if (!isRecord(raw)) return []
  for (const key of ['items', 'results', 'reviews', 'data']) {
    const value = raw[key]
    if (Array.isArray(value)) return value
  }
  return []
}

// ────────────────────────────────────────────────────────────
// 接口
// ────────────────────────────────────────────────────────────

export async function getModerationQueue(params: ModerationQueueParams = {}): Promise<ModerationQueueResponse> {
  const query: Record<string, string | number> = {}
  if (params.status) query.status = params.status
  if (params.tier) query.tier = params.tier
  if (params.limit) query.limit = params.limit
  if (params.offset) query.offset = params.offset

  const raw = await request<unknown>({ url: '/api/v1/admin/moderation/queue', method: 'get', params: query })
  const root = isRecord(raw) ? raw : {}
  const items = extractList(raw).map(normalizeReview).filter((item) => item.photoId || item.photo)
  return {
    items,
    total: toNumber(root.total, items.length),
    limit: toNumber(root.limit, params.limit ?? items.length),
    offset: toNumber(root.offset, params.offset ?? 0),
  }
}

export async function getModerationDetail(photoId: string): Promise<ModerationReview> {
  const raw = await request<unknown>({ url: `/api/v1/admin/moderation/${photoId}`, method: 'get' })
  return normalizeReview(raw)
}

export async function runModeration(photoId: string): Promise<ModerationRunResponse> {
  const raw = await request<unknown>({
    url: `/api/v1/admin/moderation/${photoId}/run`,
    method: 'post',
    timeout: 60000,
  })
  const root = isRecord(raw) ? raw : {}
  return {
    ok: root.ok !== false,
    photoId: firstString(root.photo_id, root.photoId, photoId),
    reviewId: firstString(root.review_id, root.reviewId),
    status: firstString(root.status) || 'queued',
    message: firstString(root.message) || '审核任务已入队',
  }
}

export async function submitModerationDecision(
  photoId: string,
  payload: DecisionPayload,
): Promise<ModerationReview> {
  const body: UnknownRecord = { decision: payload.decision }
  if (payload.reason) body.reason = payload.reason
  if (payload.finalTier) body.final_tier = payload.finalTier

  const raw = await request<unknown>({
    url: `/api/v1/admin/moderation/${photoId}/decision`,
    method: 'post',
    data: body,
  })
  return normalizeReview(raw)
}

export async function getModerationStats(days = 7): Promise<ModerationStats> {
  const raw = await request<unknown>({
    url: '/api/v1/admin/moderation/stats',
    method: 'get',
    params: { days },
  })
  const root = isRecord(raw) ? raw : {}
  const byTierRaw = isRecord(root.by_tier) ? root.by_tier : isRecord(root.byTier) ? root.byTier : {}
  const byStatusRaw = isRecord(root.by_status) ? root.by_status : isRecord(root.byStatus) ? root.byStatus : {}
  const byTier: Record<ModerationTier, number> = { L0: 0, L1: 0, L2: 0 }
  for (const tier of ['L0', 'L1', 'L2'] as const) {
    byTier[tier] = toNumber(byTierRaw[tier])
  }
  const byStatus: Record<string, number> = {}
  for (const [key, value] of Object.entries(byStatusRaw)) {
    byStatus[String(key)] = toNumber(value)
  }
  const remainingRaw = root.remaining_calls ?? root.remainingCalls
  return {
    days: toNumber(root.days, days),
    total: toNumber(root.total),
    byTier,
    byStatus,
    pendingHuman: toNumber(root.pending_human ?? root.pendingHuman),
    avgLatencyMs: toNumber(root.avg_latency_ms ?? root.avgLatencyMs),
    promptTokens: toNumber(root.prompt_tokens ?? root.promptTokens),
    completionTokens: toNumber(root.completion_tokens ?? root.completionTokens),
    costUsd: toNumber(root.cost_usd ?? root.costUsd),
    todayCalls: toNumber(root.today_calls ?? root.todayCalls),
    dailyBudget: toNumber(root.daily_budget ?? root.dailyBudget),
    remainingCalls: remainingRaw === null || remainingRaw === undefined ? null : toNumber(remainingRaw),
  }
}

/** 是否已有不可再改的人工终判（approve / reject；hold 仍可复审） */
export function isFinalized(review: ModerationReview | null): boolean {
  return review?.finalDecision === 'approve' || review?.finalDecision === 'reject'
}

/** 高置信度 L0 且无风险命中：适合人工一眼确认的样本，用于列表排序/提示 */
export function isHighConfidenceL0(review: ModerationReview): boolean {
  if (review.tier !== 'L0' || review.error) return false
  if (review.rules?.blocked) return false
  const confidence = review.prefilter?.confidence
  return typeof confidence === 'number' && confidence >= 0.85
}

// ────────────────────────────────────────────────────────────
// 展示用字典（纯文案，供管理端组件复用）
// ────────────────────────────────────────────────────────────

export const RULE_LABELS: Record<string, string> = {
  file_type_unsupported: '文件类型不支持',
  file_too_small: '文件过小',
  file_too_large: '文件过大',
  image_unreadable: '图片无法解码',
  image_too_small: '分辨率过低',
  extreme_aspect_ratio: '极端宽高比',
  exif_gps_present: 'EXIF 含 GPS 定位',
  exif_personal_fields: 'EXIF 含身份字段',
  aigc_metadata_detected: '检测到 AIGC 元数据',
  duplicate_near: '疑似重复投稿',
  suspicious_filename: '文件名可疑',
}

export const REVIEW_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: 'AI 审核中',
  completed: 'AI 已完成',
  failed: 'AI 失败',
}

export const TIER_LABELS: Record<ModerationTier, string> = {
  L0: 'L0 免审即发',
  L1: 'L1 人工精选',
  L2: 'L2 强制前审',
}

export const DECISION_LABELS: Record<ModerationDecision, string> = {
  approve: '通过',
  reject: '驳回',
  hold: '挂起待补',
}
