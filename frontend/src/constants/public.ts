/**
 * 公共端内容常量
 *
 * 来源：设计原型 design/data.js + 后端分类种子 backend/app/services/taxonomy.py
 * —— 十二番花信、北化八景、四季节点都是真实项目分类，不是演示假数据。
 */

export type SeasonKey = 'spring' | 'summer' | 'autumn' | 'winter'

export interface SeasonMeta {
  key: SeasonKey
  /** 中文全称，与后端 taxonomy season 节点一致 */
  label: string
  /** 单字，大字排版用 */
  char: string
  en: string
  /** 该季的节气（真实历法） */
  terms: string[]
}

export const SEASONS: SeasonMeta[] = [
  {
    key: 'spring',
    label: '春季',
    char: '春',
    en: 'SPRING',
    terms: ['立春', '雨水', '惊蛰', '春分', '清明', '谷雨'],
  },
  {
    key: 'summer',
    label: '夏季',
    char: '夏',
    en: 'SUMMER',
    terms: ['立夏', '小满', '芒种', '夏至', '小暑', '大暑'],
  },
  {
    key: 'autumn',
    label: '秋季',
    char: '秋',
    en: 'AUTUMN',
    terms: ['立秋', '处暑', '白露', '秋分', '寒露', '霜降'],
  },
  {
    key: 'winter',
    label: '冬季',
    char: '冬',
    en: 'WINTER',
    terms: ['立冬', '小雪', '大雪', '冬至', '小寒', '大寒'],
  },
]

export const SEASON_BY_LABEL: Record<string, SeasonMeta> = Object.fromEntries(
  SEASONS.map((season) => [season.label, season]),
)

/** 十二番花信（真实物候顺序，全部属春季） */
export interface Bloom {
  name: string
  month: number
  ten: '上旬' | '中旬' | '下旬'
}

export const BLOOMS: Bloom[] = [
  { name: '迎春', month: 3, ten: '上旬' },
  { name: '玉兰', month: 3, ten: '下旬' },
  { name: '杏', month: 3, ten: '下旬' },
  { name: '连翘', month: 4, ten: '上旬' },
  { name: '桃', month: 4, ten: '上旬' },
  { name: '樱花', month: 4, ten: '中旬' },
  { name: '二月兰', month: 4, ten: '中旬' },
  { name: '郁金香', month: 4, ten: '中旬' },
  { name: '海棠', month: 4, ten: '下旬' },
  { name: '紫花地丁', month: 5, ten: '上旬' },
  { name: '牡丹', month: 5, ten: '上旬' },
  { name: '芍药', month: 5, ten: '中旬' },
]

/** 北化八景（与 taxonomy landscape 节点名一一对应） */
export interface SceneryView {
  name: string
  /** 后端 classification 里的完整节点名 */
  node: string
}

const VIEW_NAMES = [
  '化彩三台',
  '馆声凫影',
  '镜湖书柳',
  '小荷听书',
  '花海晴光',
  '平湖跃金',
  '花海聆淙',
  '烟雨玉屏',
]

export const EIGHT_VIEWS: SceneryView[] = VIEW_NAMES.map((name) => ({
  name,
  node: `${name}（北化八景）`,
}))

/** 24 节气近似日期（用于「此刻」定位） */
export interface SolarTerm {
  name: string
  month: number
  day: number
  season: SeasonKey
}

const RAW_TERMS: { name: string; m: number; d: number; season: SeasonKey }[] = [
  { name: '立春', m: 2, d: 4, season: 'spring' },
  { name: '雨水', m: 2, d: 19, season: 'spring' },
  { name: '惊蛰', m: 3, d: 6, season: 'spring' },
  { name: '春分', m: 3, d: 21, season: 'spring' },
  { name: '清明', m: 4, d: 5, season: 'spring' },
  { name: '谷雨', m: 4, d: 20, season: 'spring' },
  { name: '立夏', m: 5, d: 6, season: 'summer' },
  { name: '小满', m: 5, d: 21, season: 'summer' },
  { name: '芒种', m: 6, d: 6, season: 'summer' },
  { name: '夏至', m: 6, d: 21, season: 'summer' },
  { name: '小暑', m: 7, d: 7, season: 'summer' },
  { name: '大暑', m: 7, d: 23, season: 'summer' },
  { name: '立秋', m: 8, d: 8, season: 'autumn' },
  { name: '处暑', m: 8, d: 23, season: 'autumn' },
  { name: '白露', m: 9, d: 8, season: 'autumn' },
  { name: '秋分', m: 9, d: 23, season: 'autumn' },
  { name: '寒露', m: 10, d: 8, season: 'autumn' },
  { name: '霜降', m: 10, d: 24, season: 'autumn' },
  { name: '立冬', m: 11, d: 8, season: 'winter' },
  { name: '小雪', m: 11, d: 22, season: 'winter' },
  { name: '大雪', m: 12, d: 7, season: 'winter' },
  { name: '冬至', m: 12, d: 22, season: 'winter' },
  { name: '小寒', m: 1, d: 6, season: 'winter' },
  { name: '大寒', m: 1, d: 20, season: 'winter' },
]

const TERMS: SolarTerm[] = RAW_TERMS.map(({ name, m, d, season }) => ({
  name,
  month: m,
  day: d,
  season,
}))

const TERMS_BY_DATE = [...TERMS].sort((a, b) => a.month * 100 + a.day - (b.month * 100 + b.day))
const WINTER_SOLSTICE = TERMS_BY_DATE.find((term) => term.name === '冬至') || TERMS_BY_DATE[0]

export function currentTerm(now: Date = new Date()): SolarTerm {
  const md = (now.getMonth() + 1) * 100 + now.getDate()
  const passed = TERMS_BY_DATE.filter((term) => term.month * 100 + term.day <= md)
  // 1 月 1–5 日还没到小寒，仍属上一年的冬至
  if (passed.length === 0) return WINTER_SOLSTICE
  return passed[passed.length - 1]
}

export function currentSeason(now: Date = new Date()): SeasonMeta {
  return SEASON_BY_LABEL[seasonLabelOf(currentTerm(now).season)]
}

export function seasonLabelOf(key: SeasonKey): string {
  return SEASONS.find((season) => season.key === key)?.label || '春季'
}

export function seasonKicker(label: string | null | undefined): SeasonMeta | null {
  if (!label) return null
  return SEASON_BY_LABEL[label] || null
}

const TEN_OFFSET: Record<Bloom['ten'], number> = { 上旬: 5, 中旬: 15, 下旬: 25 }

export function bloomDate(bloom: Bloom): number {
  return bloom.month * 100 + TEN_OFFSET[bloom.ten]
}

const BLOOMS_BY_DATE = [...BLOOMS].sort((a, b) => bloomDate(a) - bloomDate(b))

/** 下一番花信；过了芍药就等来年迎春 */
export function nextBloom(now: Date = new Date()): Bloom {
  const md = (now.getMonth() + 1) * 100 + now.getDate()
  return BLOOMS_BY_DATE.find((bloom) => bloomDate(bloom) >= md) || BLOOMS_BY_DATE[0]
}

export function bloomLabel(bloom: Bloom): string {
  return `${bloom.month}月${bloom.ten}的${bloom.name}`
}

/** 十二番花信文案：迎春 · 玉兰 · 杏 … */
export function bloomLine(limit = 6): string {
  const names = BLOOMS.slice(0, limit).map((bloom) => bloom.name)
  return names.join(' · ')
}
