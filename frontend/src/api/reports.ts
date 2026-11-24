/**
 * 内容举报（通知—删除）API。
 *
 * 匿名即可提交；后端限流 10 次/小时/IP，同一 IP 24h 内对同一对象重复提交返回 429。
 * 举报记录只存投诉文本与联系方式，不存证据文件。
 */
import request from './index'

export type ReportTargetType = 'photo' | 'collection'

export type ReportReasonCode =
  | 'copyright'
  | 'portrait'
  | 'illegal'
  | 'misinformation'
  | 'spam'
  | 'other'

export interface ReportReasonOption {
  code: ReportReasonCode
  /** 中文标签（与后端 reason_code 一一对应，前端本地维护） */
  label: string
  /** 给投诉人的一句话解释 */
  hint: string
}

export const REPORT_REASON_OPTIONS: ReportReasonOption[] = [
  {
    code: 'copyright',
    label: '侵犯著作权 / 未经授权转载',
    hint: '作品不是我原创，或未经授权被转载、二改',
  },
  {
    code: 'portrait',
    label: '侵犯肖像权 / 未获被摄者同意',
    hint: '画面中的人物未同意公开，或涉及未成年人',
  },
  {
    code: 'illegal',
    label: '违法违规内容',
    hint: '违反法律法规或公序良俗的内容',
  },
  {
    code: 'misinformation',
    label: '虚假信息 / 误导性内容',
    hint: 'AI 伪造、拼接，或用旧图冒充新事件',
  },
  {
    code: 'spam',
    label: '垃圾广告 / 引流',
    hint: '广告、二维码或联系方式引流',
  },
  {
    code: 'other',
    label: '其他问题',
    hint: '其他需要平台处理的问题',
  },
]

export const REPORT_REASON_LABELS: Record<ReportReasonCode, string> = {
  copyright: '侵犯著作权 / 未经授权转载',
  portrait: '侵犯肖像权 / 未获被摄者同意',
  illegal: '违法违规内容',
  misinformation: '虚假信息 / 误导性内容',
  spam: '垃圾广告 / 引流',
  other: '其他问题',
}

export interface ReportPayload {
  targetType: ReportTargetType
  targetId: string
  reasonCode: ReportReasonCode
  /** 问题说明，5–2000 字 */
  reasonText: string
  /** 联系方式（可选，便于回复处理结果） */
  contact?: string
}

export interface ReportCreated {
  ok: boolean
  id: string
  status: string
  message: string
}

export async function createReport(payload: ReportPayload): Promise<ReportCreated> {
  const data = await request<Record<string, unknown>>({
    url: '/api/v1/reports',
    method: 'post',
    data: {
      target_type: payload.targetType,
      target_id: payload.targetId,
      reason_code: payload.reasonCode,
      reason_text: payload.reasonText,
      contact: payload.contact?.trim() ? payload.contact.trim() : undefined,
    },
  })
  return {
    ok: data?.ok === true,
    id: String(data?.id ?? ''),
    status: String(data?.status ?? 'pending'),
    message: String(data?.message ?? '投诉已提交'),
  }
}
