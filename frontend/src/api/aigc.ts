/**
 * AI 创作台（站内 AI 生图）前端 API。
 *
 * 后端接口（均需登录）：
 * - GET  /api/v1/aigc/config                开关 / 模型 / 尺寸档位 / 基础每日额度
 * - GET  /api/v1/aigc/quota                 我的额度（每日基础 + 管理员赠送池）
 * - POST /api/v1/aigc/generations           202 + 后台任务（3 次/分钟）
 * - GET  /api/v1/aigc/generations/{id}      轮询状态
 * - GET  /api/v1/aigc/generations           我的生成记录
 * - GET  /api/v1/aigc/generations/{id}/image  草稿图字节（需 Authorization，<img> 不能带 header）
 * - DELETE /api/v1/aigc/generations/{id}    删除记录（204）
 *
 * 发布：走既有上传接口 POST /api/v1/photos/upload（multipart），
 * 草稿图作为 file，连同 AIGC 法定声明字段一起提交，成功后跳详情页（待审核）。
 */
import request from './index'

export type AigcSizeKey = 'square' | 'landscape' | 'portrait'

export interface AigcSize {
  key: AigcSizeKey | string
  label: string
  width: number
  height: number
  ratio: string
}

export interface AigcConfig {
  enabled: boolean
  model: string | null
  sizes: AigcSize[]
  promptMax: number
  dailyLimit: number
  estSeconds: number
}

export type AigcGenerationStatus = 'queued' | 'running' | 'succeeded' | 'failed'
export type AigcQuotaSource = 'daily' | 'bonus' | 'unlimited'

/** 生图额度：每日基础额度（0 点重置）+ 管理员赠送池（不重置）。 */
export interface AigcQuota {
  unlimited: boolean
  dailyLimit: number
  dailyUsed: number
  dailyRemaining: number
  bonusTotal: number
  bonusUsed: number
  bonusRemaining: number
  totalRemaining: number
}

export interface AigcGeneration {
  id: string
  prompt: string
  size: string
  width: number | null
  height: number | null
  status: AigcGenerationStatus
  model: string | null
  quotaSource: AigcQuotaSource
  imageUrl: string | null
  error: string | null
  latencyMs: number | null
  costUsd: number | null
  createdAt: string | null
  finishedAt: string | null
}

export interface AigcGenerationList {
  items: AigcGeneration[]
  total: number
  quota: AigcQuota
}

export interface PublishAigcPayload {
  blob: Blob
  title: string
  prompt: string
  model?: string | null
  provider?: string | null
  promptPublic: boolean
}

export interface PublishAigcResult {
  id: string
  status?: string | null
  message?: string | null
}

/* ------------------------------------------------------------------ */
/* 容错解析                                                            */
/* ------------------------------------------------------------------ */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function numOf(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

function textOf(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

const STATUSES: AigcGenerationStatus[] = ['queued', 'running', 'succeeded', 'failed']
const QUOTA_SOURCES: AigcQuotaSource[] = ['daily', 'bonus', 'unlimited']

function normalizeStatus(value: unknown): AigcGenerationStatus {
  return STATUSES.includes(value as AigcGenerationStatus) ? (value as AigcGenerationStatus) : 'queued'
}

function normalizeQuotaSource(value: unknown): AigcQuotaSource {
  return QUOTA_SOURCES.includes(value as AigcQuotaSource) ? (value as AigcQuotaSource) : 'daily'
}

export function normalizeAigcQuota(raw: unknown): AigcQuota {
  const data = isRecord(raw) ? raw : {}
  const dailyLimit = numOf(data.daily_limit, 3)
  const dailyUsed = numOf(data.daily_used)
  const bonusTotal = numOf(data.bonus_total)
  const bonusUsed = numOf(data.bonus_used)
  const dailyRemaining = numOf(data.daily_remaining, Math.max(0, dailyLimit - dailyUsed))
  const bonusRemaining = numOf(data.bonus_remaining, Math.max(0, bonusTotal - bonusUsed))
  return {
    unlimited: data.unlimited === true,
    dailyLimit,
    dailyUsed,
    dailyRemaining,
    bonusTotal,
    bonusUsed,
    bonusRemaining,
    totalRemaining: numOf(data.total_remaining, dailyRemaining + bonusRemaining),
  }
}

function normalizeSize(raw: unknown): AigcSize | null {
  if (!isRecord(raw)) return null
  const key = textOf(raw.key) ?? textOf(raw.size)
  if (!key) return null
  return {
    key,
    label: textOf(raw.label) ?? key,
    width: numOf(raw.width),
    height: numOf(raw.height),
    ratio: textOf(raw.ratio) ?? (numOf(raw.width) && numOf(raw.height) ? `${numOf(raw.width)}:${numOf(raw.height)}` : ''),
  }
}

export function normalizeAigcConfig(raw: unknown): AigcConfig {
  const data = isRecord(raw) ? raw : {}
  const sizesRaw = Array.isArray(data.sizes) ? data.sizes : []
  const sizes = sizesRaw.map(normalizeSize).filter((item): item is AigcSize => item !== null)
  return {
    enabled: data.enabled === true,
    model: textOf(data.model),
    sizes:
      sizes.length > 0
        ? sizes
        : [
            { key: 'square', label: '方图', width: 1328, height: 1328, ratio: '1:1' },
            { key: 'landscape', label: '横图', width: 1664, height: 928, ratio: '16:9' },
            { key: 'portrait', label: '竖图', width: 928, height: 1664, ratio: '9:16' },
          ],
    promptMax: numOf(data.prompt_max, 300),
    dailyLimit: numOf(data.daily_limit, 3),
    estSeconds: numOf(data.est_seconds, 60),
  }
}

export function normalizeAigcGeneration(raw: unknown): AigcGeneration | null {
  const data = isRecord(raw) ? raw : null
  if (!data) return null
  const id = textOf(data.id)
  if (!id) return null
  return {
    id,
    prompt: textOf(data.prompt) ?? '',
    size: textOf(data.size) ?? 'square',
    width: data.width == null ? null : numOf(data.width),
    height: data.height == null ? null : numOf(data.height),
    status: normalizeStatus(data.status),
    model: textOf(data.model),
    quotaSource: normalizeQuotaSource(data.quota_source),
    imageUrl: textOf(data.image_url),
    error: textOf(data.error),
    latencyMs: data.latency_ms == null ? null : numOf(data.latency_ms),
    costUsd: data.cost_usd == null ? null : numOf(data.cost_usd),
    createdAt: textOf(data.created_at),
    finishedAt: textOf(data.finished_at),
  }
}

function normalizeGenerationList(raw: unknown): AigcGenerationList {
  const data = isRecord(raw) ? raw : {}
  const items = (Array.isArray(data.items) ? data.items : [])
    .map(normalizeAigcGeneration)
    .filter((item): item is AigcGeneration => item !== null)
  return {
    items,
    total: numOf(data.total, items.length),
    quota: normalizeAigcQuota(data.quota),
  }
}

/* ------------------------------------------------------------------ */
/* 请求                                                                */
/* ------------------------------------------------------------------ */

export async function getAigcConfig(): Promise<AigcConfig> {
  const data = await request({ url: '/api/v1/aigc/config', method: 'get', timeout: 20000 })
  return normalizeAigcConfig(data)
}

export async function getAigcQuota(): Promise<AigcQuota> {
  const data = await request({ url: '/api/v1/aigc/quota', method: 'get', timeout: 20000 })
  return normalizeAigcQuota(data)
}

export async function createAigcGeneration(prompt: string, size: AigcSizeKey | string): Promise<AigcGeneration> {
  const data = await request({
    url: '/api/v1/aigc/generations',
    method: 'post',
    data: { prompt, size },
    timeout: 30000,
  })
  const generation = normalizeAigcGeneration(data)
  if (!generation) throw new Error('创作台返回数据异常')
  return generation
}

export async function getAigcGeneration(id: string): Promise<AigcGeneration | null> {
  const data = await request({ url: `/api/v1/aigc/generations/${encodeURIComponent(id)}`, method: 'get', timeout: 20000 })
  return normalizeAigcGeneration(data)
}

export async function listAigcGenerations(limit = 12): Promise<AigcGenerationList> {
  const data = await request({ url: '/api/v1/aigc/generations', method: 'get', params: { limit }, timeout: 20000 })
  return normalizeGenerationList(data)
}

export async function deleteAigcGeneration(id: string): Promise<void> {
  await request({ url: `/api/v1/aigc/generations/${encodeURIComponent(id)}`, method: 'delete', timeout: 20000 })
}

function authToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('auth_token') || sessionStorage.getItem('auth_token')
}

/**
 * 下载草稿图字节。
 *
 * 该端点需要 Authorization，`<img src>` 无法携带 header，所以必须 fetch 成 Blob，
 * 再由调用方 createObjectURL 给 img（也便于发布时直接复用 Blob 作为 multipart file）。
 */
export async function fetchAigcImageBlob(id: string): Promise<Blob> {
  const token = authToken()
  if (!token) throw new Error('登录状态已失效，请重新登录')
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const response = await fetch(`${base}/api/v1/aigc/generations/${encodeURIComponent(id)}/image`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    throw new Error(response.status === 404 ? '草稿图不存在或已被删除' : '草稿图加载失败')
  }
  return response.blob()
}

/** 发布草稿图为待审 AIGC 作品：复用既有上传接口。 */
export async function publishAigcDraft(payload: PublishAigcPayload): Promise<PublishAigcResult> {
  const formData = new FormData()
  const filename = payload.title.replace(/[\\/:*?"<>|\s]+/g, '-').slice(0, 40) || 'aigc-draft'
  const file = new File([payload.blob], `${filename}.png`, { type: payload.blob.type || 'image/png' })
  formData.append('file', file)
  formData.append('title', payload.title)
  formData.append('aigc_declared', 'true')
  if (payload.prompt) formData.append('aigc_prompt', payload.prompt)
  if (payload.model) formData.append('aigc_model', payload.model)
  if (payload.provider) formData.append('aigc_provider', payload.provider)
  formData.append('aigc_prompt_public', payload.promptPublic ? 'true' : 'false')
  formData.append('enable_ai', 'false')

  const data = await request({
    url: '/api/v1/photos/upload',
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  const record = isRecord(data) ? data : {}
  const id = textOf(record.id) ?? textOf(record.photo_id)
  if (!id) throw new Error('发布失败：服务器未返回作品 ID')
  return { id, status: textOf(record.status), message: textOf(record.message) }
}
