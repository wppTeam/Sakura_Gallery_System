import { formatDate } from '../../utils/format'
import { displayCategory, displaySeason } from '../../api/search'
import {
  DECISION_LABELS,
  REVIEW_STATUS_LABELS,
  RULE_LABELS,
  type AigcDeclarationEvidence,
  type ModerationDecision,
  type ModerationPhoto,
  type ModerationReview,
  type ModerationTier,
  type RuleSeverity,
} from '../../api/moderation'

type TagType = 'default' | 'success' | 'warning' | 'error' | 'info' | 'primary'

export const TIER_FULL_LABELS: Record<ModerationTier, string> = {
  L0: 'L0 免审即发',
  L1: 'L1 人工精选',
  L2: 'L2 强制前审',
}

export const TIER_DESCRIPTIONS: Record<ModerationTier, string> = {
  L0: '低风险，可自动发布',
  L1: '进入精选/加权需人工确认',
  L2: '涉及人物/版权/深伪，强制前审',
}

export function tierLabel(tier: ModerationTier | null): string {
  return tier ? TIER_FULL_LABELS[tier] : '未定级'
}

export function tierTagType(tier: ModerationTier | null): TagType {
  if (tier === 'L0') return 'success'
  if (tier === 'L1') return 'warning'
  if (tier === 'L2') return 'error'
  return 'default'
}

export function tierShort(tier: ModerationTier | null): string {
  return tier || '—'
}

export function severityLabel(severity: RuleSeverity | ''): string {
  if (severity === 'block') return '硬拦'
  if (severity === 'warn') return '警告'
  return '提示'
}

export function severityTagType(severity: RuleSeverity | ''): TagType {
  if (severity === 'block') return 'error'
  if (severity === 'warn') return 'warning'
  return 'info'
}

export function ruleLabel(code: string): string {
  return RULE_LABELS[code] || code
}

export function reviewStatusLabel(status: string): string {
  return REVIEW_STATUS_LABELS[status] || status || '未知状态'
}

export function reviewStatusTagType(status: string): TagType {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'running') return 'info'
  if (status === 'queued') return 'warning'
  return 'default'
}

export function decisionLabel(decision: ModerationDecision | null): string {
  return decision ? DECISION_LABELS[decision] || decision : '未终判'
}

export function decisionTagType(decision: ModerationDecision | null): TagType {
  if (decision === 'approve') return 'success'
  if (decision === 'reject') return 'error'
  if (decision === 'hold') return 'warning'
  return 'default'
}

export function percentText(value: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const normalized = value > 1 ? value : value * 100
  return `${Math.round(normalized)}%`
}

export function formatLatency(ms: number): string {
  if (!ms || !Number.isFinite(ms) || ms <= 0) return '—'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)} s`
  return `${Math.round(ms)} ms`
}

export function formatCost(usd: number): string {
  if (!Number.isFinite(usd) || usd <= 0) return '$0.0000'
  if (usd < 0.0001) return '<$0.0001'
  return `$${usd.toFixed(4)}`
}

export function formatInteger(value: number): string {
  if (!Number.isFinite(value)) return '0'
  return Math.round(value).toLocaleString('zh-CN')
}

export function formatDateTime(value: string): string {
  if (!value) return '—'
  try {
    return formatDate(value, 'YYYY-MM-DD HH:mm')
  } catch {
    return value
  }
}

export function formatRelativeMinutes(value: string): string {
  if (!value) return ''
  const timestamp = new Date(value).getTime()
  if (Number.isNaN(timestamp)) return ''
  const diffMinutes = Math.floor((Date.now() - timestamp) / 60000)
  if (diffMinutes < 1) return '刚刚'
  if (diffMinutes < 60) return `${diffMinutes} 分钟前`
  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours} 小时前`
  return `${Math.floor(diffHours / 24)} 天前`
}

export function photoStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: '待审核',
    approved: '已发布',
    rejected: '已驳回',
    draft: '草稿',
    processing: '处理中',
    failed: '处理失败',
  }
  return labels[status] || status || '未知'
}

export function photoStatusTagType(status: string): TagType {
  if (status === 'approved') return 'success'
  if (status === 'rejected') return 'error'
  if (status === 'pending') return 'warning'
  return 'default'
}

/** 管理端展示上传者：只用展示名/用户名，绝不使用真实姓名与学号 */
export function uploaderLabel(photo: ModerationPhoto | null): string {
  if (!photo) return '匿名创作者'
  return photo.displayName || photo.username || '匿名创作者'
}

/** 管理端照片元数据中文化：后端存英文枚举，展示中文 */
export function photoSeasonLabel(photo: ModerationPhoto | null): string {
  return photo?.season ? displaySeason(photo.season) : ''
}

export function photoCategoryLabel(photo: ModerationPhoto | null): string {
  return photo?.category ? displayCategory(photo.category) : ''
}

/** Agent 摘要：给队列卡片一眼看懂的一句话 */
export function agentSummary(review: ModerationReview): string {
  if (review.status === 'failed') return review.error ? 'AI 审核失败，需人工兜底' : 'AI 审核失败'
  if (review.rules?.blocked) {
    const codes = review.rules.hits.filter((hit) => hit.severity === 'block').map((hit) => ruleLabel(hit.code))
    return codes.length ? `规则硬拦：${codes.slice(0, 2).join('、')}` : '规则硬拦，需人工确认'
  }
  if (review.status === 'queued') return '已入队，等待 AI 审核'
  if (review.status === 'running') return 'AI 正在审核…'
  const tier = review.finalTier || review.tier
  const source = review.escalation ? '快筛 + 复核' : review.prefilter ? 'VLM 快筛' : '规则前置'
  const confidence = review.escalation?.confidence ?? review.prefilter?.confidence ?? null
  const suggestion = tier ? `建议 ${tier}` : '未给出分级'
  return `${source}${suggestion}${confidence !== null ? ` · 置信度 ${percentText(confidence)}` : ''}`
}

/** AIGC 声明证据（review.rules.aigc_declaration）的标签色 */
export function aigcDeclarationTagType(decl: AigcDeclarationEvidence | null): TagType {
  if (!decl) return 'default'
  if (!decl.declared) return 'warning'
  if ((decl.faceSwap || decl.sourceWorkId) && !decl.consentConfirmed) return 'error'
  return 'success'
}

/** 一句话概括 AIGC 申报，给审核员快速判断 */
export function aigcDeclarationSummary(decl: AigcDeclarationEvidence | null): string {
  if (!decl) return '本条审核无 AIGC 声明记录'
  if (!decl.declared) return '投稿声明不含 AIGC 内容；若模型判断疑似 AIGC，需人工核实'
  const parts = ['已声明 AI 生成']
  if (decl.model) parts.push(decl.model)
  if (decl.faceSwap) parts.push('人脸替换 · L2')
  else if (decl.sourceWorkId) parts.push('图生图 · L2')
  return parts.join(' · ')
}

/** 图生图 / 换脸但未确认被摄者同意：应驳回或挂起补充授权 */
export function aigcConsentMissing(decl: AigcDeclarationEvidence | null): boolean {
  if (!decl) return false
  return decl.declared && (decl.faceSwap || Boolean(decl.sourceWorkId)) && !decl.consentConfirmed
}

export interface RiskFlag {
  label: string
  tone: TagType
  detail?: string
}

/** 快筛风险项 → 徽标 */
export function riskFlags(review: ModerationReview): RiskFlag[] {
  const flags: RiskFlag[] = []
  const prefilter = review.prefilter
  if (!prefilter) return flags
  if (prefilter.hasIdentifiablePerson) flags.push({ label: '可识别人物', tone: 'error', detail: '涉肖像权，需被摄者同意' })
  if (prefilter.likelyAigc) flags.push({ label: '疑似 AIGC', tone: 'warning', detail: '需显式与隐式 AIGC 标识' })
  if (prefilter.sensitiveContent) flags.push({ label: '敏感内容', tone: 'error' })
  if (prefilter.copyrightRisk === 'high') flags.push({ label: '版权风险：高', tone: 'error' })
  else if (prefilter.copyrightRisk === 'medium') flags.push({ label: '版权风险：中', tone: 'warning' })
  else if (prefilter.copyrightRisk === 'low') flags.push({ label: '版权风险：低', tone: 'info' })
  if (prefilter.watermark) flags.push({ label: '画面含水印', tone: 'warning' })
  if (prefilter.textInImage) flags.push({ label: '画面含文字', tone: 'info' })
  return flags
}

export function hasAgentOutput(review: ModerationReview): boolean {
  return Boolean(review.rules && review.rules.checked) || Boolean(review.prefilter) || Boolean(review.escalation)
}
