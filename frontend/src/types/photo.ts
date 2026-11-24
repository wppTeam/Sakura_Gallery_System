/**
 * Photo-related types.
 */

export interface TaxonomyValue {
  facet_key: string
  facet_name: string
  node_id: number
  node_key: string
  node_name: string
  path: string[]
}

/** 单个响应式变体（后端 generate_variants 产出：WebP 主用 + JPEG 兜底） */
export interface PhotoVariantSource {
  webp?: string | null
  jpeg?: string | null
  width?: number | null
  height?: number | null
}

/** 响应式变体字典，键为长边档位（"320"/"640"/"1080"/"1600"/"2400"）；老图为 null */
export type PhotoVariants = Record<string, PhotoVariantSource>

export interface Photo {
  id: string
  uploader_id: string
  filename: string
  title: string | null
  author: string | null
  original_path: string
  processed_path: string | null
  thumb_path: string | null
  width: number | null
  height: number | null
  file_size: number | null
  mime_type: string | null
  season: string | null
  category: string | null
  campus: string | null
  description: string | null
  exif_data: Record<string, any> | null
  status: string
  processing_status: string
  created_at: string
  updated_at: string
  captured_at: string | null
  published_at: string | null
  tags: string[]
  free_tags: string[]
  classifications: Record<string, TaxonomyValue | TaxonomyValue[]>
  uploader_name: string | null
  uploader_student_id: string | null
  /** AIGC 法定标识：是否包含 AI 生成合成内容（显式角标依据） */
  is_aigc?: boolean
  /** works 判别字段：photo | aigc | template */
  kind?: string
  /** 显式标识文案，如「AI 生成」；非 AIGC 为 null */
  aigc_label?: string | null
  /** AIGC 生成信息（prompt 仅作者勾选公开时返回） */
  aigc_meta?: Record<string, unknown> | null
  /** 隐式标识（XMP/EXIF）是否已写入下载文件 */
  label_written?: boolean | null
  /** 响应式变体；缺失/老图为 null，前端回退单图 */
  variants?: PhotoVariants | null
  /** 人像隐私分级：normal 默认展示；sensitive 默认隐藏，非作者只给脱敏图 */
  privacy_level?: 'normal' | 'sensitive' | string | null
  /** 当前响应里的图片是否为脱敏版本（非作者查看 sensitive 作品时为 true） */
  is_redacted?: boolean | null
  /** 首页占位（后端 LQIP） */
  lqip?: string | null
  lqip_color?: string | null
  blurhash?: string | null
}

export interface PhotoUploadResponse {
  id: string
  filename: string
  original_path: string
  thumb_path: string | null
  width: number | null
  height: number | null
  status: string
  message: string
  /** AIGC 法定标识：上传响应用于即时反馈显式标识 */
  is_aigc?: boolean
  aigc_label?: string | null
}

/**
 * 上传时的 AIGC 声明（《人工智能生成合成内容标识办法》第四条：上传时必须声明）。
 * 后端 /photos/upload 对是否声明强制校验；true 时才接收生成信息字段。
 */
export interface AigcUploadDeclaration {
  /** 必填：是否包含 AI 生成合成内容 */
  declared: boolean
  model?: string
  provider?: string
  prompt?: string
  /** 作者是否同意公开提示词（详情页展示） */
  promptPublic?: boolean
  /** 图生图源作品 id；填写后强制进入 L2 人工前审 */
  sourceWorkId?: string
  /** 换脸 / 人脸替换类内容；强制 L2 前审 */
  faceSwap?: boolean
  /** 图生图 / 换脸时必须确认为「已获得被摄者书面同意」 */
  consentConfirmed?: boolean
}

export interface PhotoUpdate {
  title?: string | null
  author?: string | null
  description?: string
  season?: string
  category?: string
  campus?: string
  status?: string
}

export interface SearchInterpretation {
  facet_filters: Record<string, string>
  keywords: string[]
  original_query: string
  method: 'rule' | 'ai' | 'fallback'
  confidence: number
  explanation: string | null
}

export interface PhotoListParams {
  skip?: number
  limit?: number
  /** 公开列表是否纳入人像作品（默认排除；仍受 portrait_visibility 约束，未登录无效） */
  include_sensitive?: boolean
  status?: string
  season?: string
  category?: string
  campus?: string
  building?: string
  source_type?: string
  facility?: string
  landscape?: string
  natural_phenomenon?: string
  technique?: string
  animal?: string
  plant?: string
  gallery_series?: string
  gallery_year?: string
  award_level?: string
  photo_type?: string
  documentary_topic?: string
  search?: string
  tag?: string
  sort_by?: string
  sort_order?: string
  smart?: boolean
}

export interface PhotoListResponse {
  items: Photo[]
  total: number
  page: number
  page_size: number
  search_interpretation?: SearchInterpretation | null
}

export interface PhotoFilters {
  season?: string | null
  category?: string | null
  campus?: string | null
  building?: string | null
  source_type?: string | null
  facility?: string | null
  landscape?: string | null
  natural_phenomenon?: string | null
  technique?: string | null
  animal?: string | null
  plant?: string | null
  gallery_series?: string | null
  gallery_year?: string | null
  award_level?: string | null
  photo_type?: string | null
  documentary_topic?: string | null
  status?: string | null
  search?: string
  tag?: string | null
  sortBy?: string
  sortOrder?: string
}

export function firstTaxonomyValue(value: TaxonomyValue | TaxonomyValue[] | null | undefined): TaxonomyValue | null {
  if (!value) return null
  return Array.isArray(value) ? (value[0] || null) : value
}

export function taxonomyValueName(value: TaxonomyValue | TaxonomyValue[] | null | undefined): string {
  return firstTaxonomyValue(value)?.node_name || ''
}
