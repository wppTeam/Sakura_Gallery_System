/**
 * AI 成本与用量观测 API
 *
 * 仅超级管理员可访问（后端 `GET /api/v1/admin/ai/usage`）。
 * 数据来自 `ai_usage_events`：只含模型调用的元信息（token / 成本 / 延迟 / 成败），
 * 不含 prompt 或图片内容。
 */
import request from './index'

const BASE_URL = '/api/v1/admin/ai'

/** 总量指标 */
export interface AiUsageTotals {
    calls: number
    success: number
    failed: number
    promptTokens: number
    completionTokens: number
    totalTokens: number
    costUsd: number
    avgLatencyMs: number
}

/** 按日 / 按链路 / 按模型的聚合桶 */
export interface AiUsageBucket {
    key: string
    calls: number
    totalTokens: number
    costUsd: number
}

/** 最近一次 AI 调用事件 */
export interface AiUsageEvent {
    id: string
    operation: string
    provider: string | null
    modelId: string | null
    refType: string | null
    refId: string | null
    totalTokens: number
    costUsd: number
    latencyMs: number
    success: boolean
    error: string | null
    createdAt: string
}

/** `GET /api/v1/admin/ai/usage` 的响应（已做 camelCase 归一化） */
export interface AiUsageResponse {
    days: number
    since: string | null
    generatedAt: string | null
    totals: AiUsageTotals
    byDay: AiUsageBucket[]
    byOperation: AiUsageBucket[]
    byModel: AiUsageBucket[]
    recent: AiUsageEvent[]
}

export interface AiUsageQuery {
    days?: number
    recentLimit?: number
}

/** 常见的 AI 链路 → 中文文案；未知 key 原样展示 */
export const OPERATION_LABELS: Record<string, string> = {
    'moderation.prefilter': '审核 · 快筛 VLM',
    'moderation.escalation': '审核 · 复核推理',
    'moderation.tagging': '审核 · 自动打标',
    'agent_search.plan': '检索 · 意图规划',
    'agent_search.explain': '检索 · 结果解释',
    'agent_search.suggest': '检索 · 联想词',
}

export function operationLabel(key: string | null | undefined): string {
    if (!key) return '未知链路'
    return OPERATION_LABELS[key] || key
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null
}

function toNumber(value: unknown, fallback = 0): number {
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string') {
        const parsed = Number(value)
        if (Number.isFinite(parsed)) return parsed
    }
    return fallback
}

function toText(value: unknown, fallback = ''): string {
    return typeof value === 'string' ? value : fallback
}

function nullableText(value: unknown): string | null {
    return typeof value === 'string' && value.trim() !== '' ? value : null
}

function normalizeBucket(raw: unknown): AiUsageBucket | null {
    if (!isRecord(raw)) return null
    const key = toText(raw.key) || toText(raw.operation) || toText(raw.model_id) || 'unknown'
    return {
        key,
        calls: toNumber(raw.calls),
        totalTokens: toNumber(raw.total_tokens ?? raw.totalTokens),
        costUsd: toNumber(raw.cost_usd ?? raw.costUsd),
    }
}

function normalizeBuckets(raw: unknown): AiUsageBucket[] {
    if (!Array.isArray(raw)) return []
    return raw
        .map(normalizeBucket)
        .filter((item): item is AiUsageBucket => item !== null)
}

function normalizeTotals(raw: unknown): AiUsageTotals {
    const source = isRecord(raw) ? raw : {}
    return {
        calls: toNumber(source.calls),
        success: toNumber(source.success),
        failed: toNumber(source.failed),
        promptTokens: toNumber(source.prompt_tokens ?? source.promptTokens),
        completionTokens: toNumber(source.completion_tokens ?? source.completionTokens),
        totalTokens: toNumber(source.total_tokens ?? source.totalTokens),
        costUsd: toNumber(source.cost_usd ?? source.costUsd),
        avgLatencyMs: toNumber(source.avg_latency_ms ?? source.avgLatencyMs),
    }
}

function normalizeEvent(raw: unknown): AiUsageEvent | null {
    if (!isRecord(raw)) return null
    return {
        id: toText(raw.id),
        operation: toText(raw.operation, 'unknown'),
        provider: nullableText(raw.provider),
        modelId: nullableText(raw.model_id ?? raw.modelId),
        refType: nullableText(raw.ref_type ?? raw.refType),
        refId: nullableText(raw.ref_id ?? raw.refId),
        totalTokens: toNumber(raw.total_tokens ?? raw.totalTokens),
        costUsd: toNumber(raw.cost_usd ?? raw.costUsd),
        latencyMs: toNumber(raw.latency_ms ?? raw.latencyMs),
        success: raw.success !== false,
        error: nullableText(raw.error),
        createdAt: toText(raw.created_at ?? raw.createdAt),
    }
}

/**
 * 获取 AI 用量聚合（总量 + 按日 / 按链路 / 按模型 + 最近事件）
 * @param days 统计最近多少天，1–90
 * @param recentLimit 最近事件条数，1–100
 */
export async function getAiUsage(query: AiUsageQuery = {}): Promise<AiUsageResponse> {
    const days = Math.min(90, Math.max(1, Math.round(query.days ?? 7)))
    const recentLimit = Math.min(100, Math.max(1, Math.round(query.recentLimit ?? 20)))
    const response = await request.get<unknown>(`${BASE_URL}/usage`, {
        params: { days, recent_limit: recentLimit },
    })
    const source = isRecord(response) ? response : {}
    return {
        days: toNumber(source.days, days),
        since: nullableText(source.since),
        generatedAt: nullableText(source.generated_at ?? source.generatedAt),
        totals: normalizeTotals(source.totals),
        byDay: normalizeBuckets(source.by_day ?? source.byDay),
        byOperation: normalizeBuckets(source.by_operation ?? source.byOperation),
        byModel: normalizeBuckets(source.by_model ?? source.byModel),
        recent: Array.isArray(source.recent)
            ? source.recent
                .map(normalizeEvent)
                .filter((item): item is AiUsageEvent => item !== null)
            : [],
    }
}

/** 花费格式化：保留 4 位小数（0 显示 $0.0000） */
export function formatCostUsd(value: number): string {
    if (!Number.isFinite(value)) return '$0.0000'
    return `$${value.toFixed(4)}`
}

/** 整数千分位 */
export function formatCount(value: number): string {
    if (!Number.isFinite(value)) return '0'
    return Math.round(value).toLocaleString('zh-CN')
}

/** 延迟：<1s 显示 ms，否则秒 */
export function formatLatency(value: number): string {
    if (!Number.isFinite(value) || value <= 0) return '0 ms'
    if (value < 1000) return `${Math.round(value)} ms`
    return `${(value / 1000).toFixed(2)} s`
}
