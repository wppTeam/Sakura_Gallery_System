/**
 * 「光的一日」时段工具：本地小时 → 晨/昼/暮/夜。
 *
 * 时段定义与后端 `backend/app/services/light_of_day.py` 保持一致
 * （05–09 晨 / 09–15 昼 / 15–19 暮 / 其余 夜），前端只负责选段与兜底。
 */
import type { LightPeriod } from '../../api/collections'

export interface LightPeriodMeta {
  key: string
  label: string
  timeRange: string
  /** 没有 LQIP 主色时的兜底色（tokens 变量，不硬编码 hex） */
  washVar: string
}

export const LIGHT_PERIOD_META: LightPeriodMeta[] = [
  { key: 'dawn', label: '晨', timeRange: '05:00–09:00', washVar: 'var(--spring-pale)' },
  { key: 'noon', label: '昼', timeRange: '09:00–15:00', washVar: 'var(--summer-pale)' },
  { key: 'dusk', label: '暮', timeRange: '15:00–19:00', washVar: 'var(--autumn-pale)' },
  { key: 'night', label: '夜', timeRange: '19:00–05:00', washVar: 'var(--winter-pale)' },
]

/** 本地小时 → 时段 key（与后端一致） */
export function periodKeyForHour(hour: number): string {
  if (hour >= 5 && hour < 9) return 'dawn'
  if (hour >= 9 && hour < 15) return 'noon'
  if (hour >= 15 && hour < 19) return 'dusk'
  return 'night'
}

/** 当前时刻对应的时段 key */
export function currentLightKey(now: Date = new Date()): string {
  return periodKeyForHour(now.getHours())
}

/** 当前时段元信息（label / timeRange / 兜底 wash） */
export function lightMeta(key: string): LightPeriodMeta {
  return LIGHT_PERIOD_META.find((item) => item.key === key) ?? LIGHT_PERIOD_META[0]
}

/**
 * 选段：优先当前时段；为空时按 暮 → 昼 → 夜 → 晨 取第一个有作品的时段。
 * 全空时返回 null（调用方降级为插画）。
 */
export function pickLightPeriod(periods: LightPeriod[], now: Date = new Date()): LightPeriod | null {
  if (!periods.length) return null
  const byKey = new Map(periods.map((item) => [item.key, item]))
  const current = byKey.get(currentLightKey(now))
  if (current && current.photos.length) return current
  for (const key of ['dusk', 'noon', 'night', 'dawn']) {
    const candidate = byKey.get(key)
    if (candidate && candidate.photos.length) return candidate
  }
  return null
}
