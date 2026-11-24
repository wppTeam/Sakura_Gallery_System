/**
 * 后台「举报处理」管理 API。
 *
 * 契约：GET /api/v1/admin/reports（auditor/admin）、GET /api/v1/admin/reports/stats、
 * POST /api/v1/admin/reports/{id}/resolve。
 */
import request from './index'

export type ReportStatus = 'pending' | 'accepted' | 'rejected'
export type ReportTargetType = 'photo' | 'collection'
export type ReportReasonCode =
  | 'copyright'
  | 'portrait'
  | 'illegal'
  | 'misinformation'
  | 'spam'
  | 'other'
export type ReportDecision = 'accept' | 'reject'
export type ReportAction = 'takedown' | 'none'

export interface ReportReporter {
  username: string | null
  displayName: string | null
}

export interface AdminReportItem {
  id: string
  targetType: ReportTargetType
  targetId: string
  targetTitle: string
  targetUrl: string | null
  reasonCode: ReportReasonCode | string
  reasonLabel: string
  reasonText: string
  contact: string | null
  reporter: ReportReporter | null
  reporterIp: string | null
  status: ReportStatus
  handledBy: string | null
  handledAt: string | null
  resolutionNote: string | null
  actionTaken: string | null
  createdAt: string | null
  raw: Record<string, unknown>
}

export interface AdminReportStats {
  total: number
  pending: number
  accepted: number
  rejected: number
  byReason: Record<string, number>
  last7Days: number
}

export interface AdminReportQuery {
  status?: ReportStatus
  targetType?: ReportTargetType
  limit?: number
  offset?: number
}

export interface AdminReportPage {
  items: AdminReportItem[]
  total: number
  limit: number
  offset: number
}

export interface ResolveReportPayload {
  decision: ReportDecision
  note?: string
  action: ReportAction
}

export interface ResolveReportResult {
  ok: boolean
  id: string
  status: ReportStatus | string
  actionTaken: string | null
}

export const REPORT_REASON_LABELS: Record<string, string> = {
  copyright: '侵犯著作权',
  portrait: '侵犯肖像权',
  illegal: '违法违规',
  misinformation: '虚假信息',
  spam: '垃圾广告',
  other: '其他问题',
}

export const REPORT_STATUS_LABELS: Record<ReportStatus, string> = {
  pending: '待处理',
  accepted: '已受理',
  rejected: '已驳回',
}

export const REPORT_TARGET_LABELS: Record<ReportTargetType, string> = {
  photo: '作品',
  collection: '专题',
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function textOf(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const text = textOf(value)
    if (text) return text
  }
  return ''
}

function numOf(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function normalizeTargetType(value: unknown): ReportTargetType {
  return textOf(value) === 'collection' ? 'collection' : 'photo'
}

function normalizeStatus(value: unknown): ReportStatus {
  const text = textOf(value)
  if (text === 'accepted' || text === 'rejected') return text
  return 'pending'
}

function normalizeReporter(raw: unknown): ReportReporter | null {
  if (!isRecord(raw)) return null
  const username = firstString(raw.username, raw.user_name, raw.name)
  const displayName = firstString(raw.display_name, raw.displayName, raw.full_name, raw.fullName)
  if (!username && !displayName) return null
  return { username: username || null, displayName: displayName || null }
}

function normalizeItem(raw: unknown): AdminReportItem {
  const item = isRecord(raw) ? raw : {}
  const reasonCode = firstString(item.reason_code, item.reasonCode)
  const reasonLabel = firstString(item.reason_label, item.reasonLabel) || REPORT_REASON_LABELS[reasonCode] || reasonCode || '其他问题'
  return {
    id: firstString(item.id, item.report_id),
    targetType: normalizeTargetType(item.target_type ?? item.targetType),
    targetId: firstString(item.target_id, item.targetId),
    targetTitle: firstString(item.target_title, item.targetTitle) || '未命名内容',
    targetUrl: firstString(item.target_url, item.targetUrl) || null,
    reasonCode: reasonCode || 'other',
    reasonLabel,
    reasonText: textOf(item.reason_text ?? item.reasonText),
    contact: firstString(item.contact) || null,
    reporter: normalizeReporter(item.reporter),
    reporterIp: firstString(item.reporter_ip, item.reporterIp) || null,
    status: normalizeStatus(item.status),
    handledBy: firstString(item.handled_by, item.handledBy) || null,
    handledAt: firstString(item.handled_at, item.handledAt) || null,
    resolutionNote: textOf(item.resolution_note ?? item.resolutionNote) || null,
    actionTaken: firstString(item.action_taken, item.actionTaken) || null,
    createdAt: firstString(item.created_at, item.createdAt) || null,
    raw: isRecord(raw) ? raw : {},
  }
}

function extractItems(raw: Record<string, unknown>): unknown[] {
  const list = raw.items ?? raw.reports ?? raw.results ?? raw.data
  return Array.isArray(list) ? list : []
}

export async function fetchReports(query: AdminReportQuery = {}): Promise<AdminReportPage> {
  const data = await request.get<Record<string, unknown>>('/api/v1/admin/reports', {
    params: {
      status: query.status,
      target_type: query.targetType,
      limit: query.limit ?? 20,
      offset: query.offset ?? 0,
    },
  })
  const items = extractItems(data).map(normalizeItem)
  return {
    items,
    total: numOf(data.total) || items.length,
    limit: numOf(data.limit) || query.limit || 20,
    offset: numOf(data.offset) || query.offset || 0,
  }
}

export async function fetchReportStats(days = 7): Promise<AdminReportStats> {
  const data = await request.get<Record<string, unknown>>('/api/v1/admin/reports/stats', {
    params: { days },
  })
  const byReasonRaw = isRecord(data.by_reason) ? data.by_reason : isRecord(data.byReason) ? data.byReason : {}
  const byReason: Record<string, number> = {}
  for (const [key, value] of Object.entries(byReasonRaw)) {
    byReason[key] = numOf(value)
  }
  return {
    total: numOf(data.total),
    pending: numOf(data.pending),
    accepted: numOf(data.accepted),
    rejected: numOf(data.rejected),
    byReason,
    last7Days: numOf(data.last_7_days ?? data.last7Days),
  }
}

export async function resolveReport(id: string, payload: ResolveReportPayload): Promise<ResolveReportResult> {
  const data = await request.post<Record<string, unknown>>(`/api/v1/admin/reports/${id}/resolve`, {
    decision: payload.decision,
    note: payload.note?.trim() || undefined,
    action: payload.action,
  })
  return {
    ok: data.ok !== false,
    id: firstString(data.id) || id,
    status: firstString(data.status) || (payload.decision === 'accept' ? 'accepted' : 'rejected'),
    actionTaken: firstString(data.action_taken, data.actionTaken) || null,
  }
}
