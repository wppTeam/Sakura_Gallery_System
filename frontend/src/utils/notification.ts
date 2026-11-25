/**
 * 通知展示辅助：类型 → 文案 / 色调 / 图标 / 深链，以及相对时间。
 * 单一来源，铃铛与通知中心共用，避免两套映射漂移。
 */
import type { Component } from 'vue'
import {
  AlertCircleOutline,
  CheckmarkCircleOutline,
  CloseCircleOutline,
  InformationCircleOutline,
  RefreshCircleOutline,
  ShieldCheckmarkOutline,
} from '@vicons/ionicons5'

export type NotificationType =
  | 'photo_approved'
  | 'photo_rejected'
  | 'photo_appeal_accepted'
  | 'photo_appeal_rejected'
  | 'permission_granted'
  | 'system'

export type NotificationTone = 'approved' | 'rejected' | 'appeal' | 'permission' | 'system'

export interface NotificationMeta {
  label: string
  tone: NotificationTone
  icon: Component
}

const NOTIFICATION_META: Record<NotificationType, NotificationMeta> = {
  photo_approved: { label: '作品过审', tone: 'approved', icon: CheckmarkCircleOutline },
  photo_rejected: { label: '作品驳回', tone: 'rejected', icon: CloseCircleOutline },
  photo_appeal_accepted: { label: '复核通过', tone: 'appeal', icon: RefreshCircleOutline },
  photo_appeal_rejected: { label: '复核未通过', tone: 'appeal', icon: AlertCircleOutline },
  permission_granted: { label: '权限授予', tone: 'permission', icon: ShieldCheckmarkOutline },
  system: { label: '系统通知', tone: 'system', icon: InformationCircleOutline },
}

const FALLBACK_META: NotificationMeta = {
  label: '通知',
  tone: 'system',
  icon: InformationCircleOutline,
}

export function notificationMeta(type: string): NotificationMeta {
  return NOTIFICATION_META[type as NotificationType] ?? FALLBACK_META
}

/** 目前 related_id 均为作品 id；返回 null 表示该通知不可深链。 */
export function notificationPath(relatedId: string | null | undefined): string | null {
  if (!relatedId) return null
  return `/photo/${relatedId}`
}

/** 后端时间为无时区的 UTC 字符串（如 2026-11-25T08:20:00），补 Z 后再转本地时区。 */
export function parseServerTime(value: string | null | undefined): Date | null {
  if (!value) return null
  const normalized = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

/** 绝对时间：2026-11-25 16:20（本地时区）。 */
export function formatAbsoluteTime(value: string | null | undefined): string {
  const date = parseServerTime(value)
  if (!date) return ''
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

/** 相对时间：刚刚 / N 分钟前 / N 小时前 / 昨天 / N 天前 / 日期。 */
export function relativeTime(value: string | null | undefined): string {
  const date = parseServerTime(value)
  if (!date) return ''
  const diff = Date.now() - date.getTime()
  if (diff < 0) return '刚刚'
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 172_800_000) return '昨天'
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`
}
