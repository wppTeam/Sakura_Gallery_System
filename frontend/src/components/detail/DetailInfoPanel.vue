<template>
  <aside class="info">

    <!-- 人像隐私说明卡：sensitive 作品（默认隐藏，非作者只看脱敏图） -->
    <section
      v-if="detail.privacyLevel === 'sensitive'"
      class="privacy-card"
      :class="{ 'is-author': isAuthor }"
      aria-label="人像隐私说明"
    >
      <div class="privacy-head">
        <span class="privacy-seal">
          <n-icon :component="detail.isRedacted ? LockClosedOutline : PersonCircleOutline" :size="13" />
          {{ detail.isRedacted ? '人像 · 已脱敏' : '人像作品' }}
        </span>
        <span class="privacy-kicker">
          {{ detail.isRedacted ? '隐私保护 · 默认隐藏' : isAuthor ? '作者视角 · 原图可见' : '审核视角 · 原图可见' }}
        </span>
      </div>

      <template v-if="detail.isRedacted">
        <p class="privacy-lead">
          这类作品含可识别人像，默认不在公共列表展示。你现在看到的是<strong>脱敏图</strong>：强模糊 + 像素化处理，只缩不裁。
        </p>
        <ul class="privacy-list">
          <li>原图仅作者本人与站点管理员（审核员）可查看；</li>
          <li>下载与原图查看对普通访问者关闭，脱敏图仅用于浏览；</li>
          <li>如需原图或使用授权，请联系作者 <strong>{{ detail.author }}</strong> 或站点管理员。</li>
        </ul>
      </template>

      <template v-else-if="isAuthor">
        <p class="privacy-lead">
          这是你的作品，原图仅你与站点管理员可见；其他访问者看到的是脱敏图。下载按钮仍可用。
        </p>
        <p class="privacy-foot">如需调整隐私级别，可在「我的投稿」中修改，或联系管理员。</p>
      </template>

      <template v-else>
        <p class="privacy-lead">
          你以审核视角查看该人像作品，可查看原图；普通访问者默认看到脱敏图。
        </p>
      </template>
    </section>

    <!-- AI 生成声明摘要卡：法定显式标识（仅 AIGC 作品渲染） -->
    <section v-if="detail.aigc" class="aigc-summary-card" aria-label="AI 生成声明">
      <div class="aigc-summary-head">
        <span class="aigc-seal">
          <n-icon :component="SparklesOutline" :size="13" />
          AI 生成
        </span>
        <span class="aigc-summary-kicker">依法标注 · 显式标识</span>
      </div>
      <p class="aigc-summary-lead">
        本作品包含 AI 生成合成内容，已按《人工智能生成合成内容标识办法》展示显式标识；下载副本含 XMP 隐式标识。
      </p>
      <dl class="aigc-facts">
        <div v-if="detail.aigc.model" class="aigc-fact">
          <dt>生成模型</dt>
          <dd>{{ detail.aigc.model }}</dd>
        </div>
        <div v-if="detail.aigc.provider" class="aigc-fact">
          <dt>服务提供方</dt>
          <dd>{{ detail.aigc.provider }}</dd>
        </div>
        <div v-if="detail.aigc.sourceWorkId" class="aigc-fact">
          <dt>图生图源作品</dt>
          <dd class="is-mono">{{ detail.aigc.sourceWorkId }}</dd>
        </div>
        <div v-if="detail.aigc.faceSwap" class="aigc-fact">
          <dt>人脸替换</dt>
          <dd>是（已获被摄者书面同意）</dd>
        </div>
        <div v-if="detail.aigc.declaredAt" class="aigc-fact">
          <dt>声明时间</dt>
          <dd>{{ detail.aigc.declaredAt }}</dd>
        </div>
      </dl>
      <div v-if="detail.aigc.prompt" class="aigc-prompt">
        <button
          type="button"
          class="aigc-prompt-toggle"
          :aria-expanded="promptExpanded"
          @click="promptExpanded = !promptExpanded"
        >
          公开提示词
          <n-icon :component="promptExpanded ? ChevronUpOutline : ChevronDownOutline" :size="13" />
        </button>
        <p class="aigc-prompt-text" :class="{ 'is-collapsed': !promptExpanded }">{{ detail.aigc.prompt }}</p>
      </div>
      <p class="aigc-summary-foot">
        <n-icon :component="ShieldCheckmarkOutline" :size="13" />
        <span>下载副本含 XMP 隐式标识 · 请勿用于伪造真实人物或误导性传播</span>
      </p>
    </section>
    <div class="info-head">
      <div class="info-tags">
        <span class="tag tag-kind" :class="kindClass">{{ kindLabel }}</span>
        <router-link
          v-if="detail.season"
          class="tag tag-season"
          :class="seasonClass"
          :to="{ path: '/search', query: { season: detail.season } }"
        >
          {{ detail.season }}
        </router-link>
        <span v-if="detail.category" class="tag tag-plain">{{ detail.category }}</span>
      </div>

      <h1 class="info-title">{{ detail.title }}</h1>

      <div class="info-byline">
        <span class="author">{{ detail.author }}</span>
        <span v-if="publishedText" class="dot">·</span>
        <span v-if="publishedText" :title="formatDate(detail.publishedAt, 'YYYY-MM-DD HH:mm')">
          {{ publishedText }}
        </span>
        <span v-if="detail.place" class="dot">·</span>
        <span v-if="detail.place" class="place">
          <n-icon :component="LocationOutline" :size="14" />
          {{ detail.place }}
        </span>
      </div>

      <div class="info-stats">
        <span class="stat"><n-icon :component="EyeOutline" :size="15" />{{ detail.views ?? '—' }} 次浏览</span>
        <span v-if="favoriteCount !== null" class="stat">
          <n-icon :component="HeartOutline" :size="15" />{{ favoriteCount }} 人收藏
        </span>
        <span v-if="detail.downloads !== null" class="stat">
          <n-icon :component="DownloadOutline" :size="15" />{{ detail.downloads }} 次下载
        </span>
      </div>
    </div>

    <div class="info-actions">
      <button
        type="button"
        class="btn-fav"
        :class="{ 'is-active': favorited, 'is-busy': favoritePending }"
        :aria-pressed="favorited"
        :disabled="favoritePending"
        @click="$emit('toggle-favorite')"
      >
        <n-icon :component="favorited ? HeartOutline : HeartOutline" :size="18" />
        <span>{{ favorited ? '已收藏' : '收藏' }}</span>
      </button>

      <div v-if="detail.canViewOriginal" ref="menuRef" class="download-wrap">
        <button type="button" class="btn-download" :aria-expanded="menuOpen" @click="menuOpen = !menuOpen">
          <n-icon :component="DownloadOutline" :size="18" />
          <span>下载</span>
          <n-icon :component="ChevronDownOutline" :size="14" />
        </button>
        <Transition name="menu">
          <div v-if="menuOpen" class="download-menu" role="menu">
            <a
              v-for="option in downloadOptions"
              :key="option.url"
              class="download-item"
              :href="option.url"
              :download="option.filename"
              rel="noopener"
              @click="menuOpen = false"
            >
              <span class="download-label">{{ option.label }}</span>
              <span class="download-note">{{ option.note }}</span>
            </a>
            <p class="download-tip">
              <template v-if="detail.aigc">原图下载文件内含「AI 生成」隐藏标识（XMP）；</template>
              原始构图与尺寸不做裁切；转载或商用前请先获得作者授权。
            </p>
          </div>
        </Transition>
      </div>

      <button type="button" class="btn-icon" title="分享作品" aria-label="分享作品" @click="share">
        <n-icon :component="ShareSocialOutline" :size="18" />
      </button>
      <button type="button" class="btn-icon" title="复制作品信息" aria-label="复制作品信息" @click="copyCitation">
        <n-icon :component="CopyOutline" :size="18" />
      </button>
    </div>
    <section v-if="detail.description" class="block">
      <h2 class="block-title">作品简介</h2>
      <p class="description">{{ detail.description }}</p>
    </section>

    <section class="block">
      <h2 class="block-title">作品信息</h2>
      <dl class="spec-list">
        <div v-for="row in specRows" :key="row.label" class="spec-row">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.value }}</dd>
        </div>
      </dl>
    </section>

    <PictureNotes
      v-if="detail.aiCaption"
      :caption="detail.aiCaption"
      :tags="pictureNoteTags"
    />

    <section class="block">
      <div class="block-head">
        <h2 class="block-title">拍摄参数</h2>
        <span class="block-hint">{{ detail.hasExif ? '来自原图 EXIF（已隐藏定位）' : '原图未提供拍摄参数' }}</span>
      </div>
      <dl class="exif-list">
        <div v-for="row in visibleExifRows" :key="row.label" class="exif-row">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.value }}</dd>
        </div>
      </dl>
      <button v-if="collapsibleExif" type="button" class="link-btn" @click="exifExpanded = !exifExpanded">
        {{ exifExpanded ? '收起参数' : `展开全部 ${detail.exifRows.length} 项参数` }}
        <n-icon :component="exifExpanded ? ChevronUpOutline : ChevronDownOutline" :size="14" />
      </button>
    </section>

    <section v-if="allTags.length" class="block">
      <h2 class="block-title">标签</h2>
      <div class="tag-links">
        <router-link
          v-for="tag in allTags"
          :key="tag"
          class="tag-link"
          :to="{ path: '/search', query: { q: tag, mode: 'fast' } }"
        >
          # {{ tag }}
        </router-link>
      </div>
    </section>

    <section v-if="collectionRefs.length" class="block">
      <h2 class="block-title">收录于</h2>
      <div class="collection-links">
        <RouterLink
          v-for="collection in collectionRefs"
          :key="collection.slug"
          class="collection-link"
          :to="`/collections/${collection.slug}`"
        >
          <n-icon :component="AlbumsOutline" :size="14" />
          <span>{{ collection.title }}</span>
        </RouterLink>
      </div>
    </section>

    <section class="block license-block">
      <h2 class="block-title">授权说明</h2>
      <template v-if="detail.license">
        <p class="license-line">
          <n-icon :component="ShieldCheckmarkOutline" :size="16" />
          <span class="license-name">{{ detail.license.name }}</span>
          <a
            v-if="detail.license.url"
            class="license-link"
            :href="detail.license.url"
            target="_blank"
            rel="noopener noreferrer"
          >
            查看协议
            <n-icon :component="OpenOutline" :size="13" />
          </a>
        </p>
        <p class="license-note">使用前请阅读协议全文；以作者在作品说明中额外标注的条款为准。</p>
      </template>
      <p v-else class="license-line license-line-muted">
        <n-icon :component="AlertCircleOutline" :size="16" />
        <span>作者尚未标注授权协议。默认保留所有权利，转载、二次创作或商用前请先联系作者获得许可。</span>
      </p>
    </section>

    <div class="report-row">
      <button type="button" class="report-link" @click="reportOpen = true">
        <n-icon :component="FlagOutline" :size="14" />
        举报 / 侵权投诉
      </button>
      <span class="report-note">平台按「通知—删除」规则处理</span>
    </div>

    <p class="compliance-note">
      作品版权归作者所有。如作品涉及可识别人物，使用者需另行取得肖像权授权；
      若你认为本作品侵犯了你的权益，请通过上方「举报 / 侵权投诉」提交，或联系站点管理员处理。
    </p>

    <ReportDialog
      v-model:show="reportOpen"
      target-type="photo"
      :target-id="detail.id"
      :target-title="detail.title"
    />
  </aside>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NIcon, useMessage } from 'naive-ui'
import { onClickOutside } from '@vueuse/core'
import {
  AlbumsOutline,
  AlertCircleOutline,
  ChevronDownOutline,
  ChevronUpOutline,
  CopyOutline,
  DownloadOutline,
  EyeOutline,
  FlagOutline,
  HeartOutline,
  LocationOutline,
  LockClosedOutline,
  OpenOutline,
  PersonCircleOutline,
  ShareSocialOutline,
  ShieldCheckmarkOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import { formatDate, formatFileSize, getPhotoUrl } from '../../utils/format'
import ReportDialog from './ReportDialog.vue'
import PictureNotes from './PictureNotes.vue'
import type { WorkDetail } from './workDetail'
import { fetchPhotoCollections, type PhotoCollectionRef } from '../../api/collections'

const props = defineProps<{
  detail: WorkDetail
  favorited: boolean
  favoriteCount: number | null
  favoritePending: boolean
  /** 当前登录用户是否是该作品作者（用于人像原图视角提示） */
  isAuthor: boolean
}>()

defineEmits<{ 'toggle-favorite': [] }>()

const message = useMessage()

// ── 收录于专题（失败/为空时不渲染，不阻塞详情页） ──────────
const collectionRefs = ref<PhotoCollectionRef[]>([])

async function loadCollectionRefs(workId: string) {
  if (!workId) {
    collectionRefs.value = []
    return
  }
  collectionRefs.value = await fetchPhotoCollections(workId)
}

watch(
  () => props.detail.id,
  (id) => {
    void loadCollectionRefs(id || '')
  },
  { immediate: true },
)

// ── 举报 / 侵权投诉 ─────────────────────────────────────
const reportOpen = ref(false)

// ── 标签（作者/编辑标签 + 自由标签，去重保序） ─────────
const allTags = computed(() => {
  const seen = new Set<string>()
  const result: string[] = []
  for (const raw of [...props.detail.tags, ...props.detail.freeTags]) {
    const tag = raw.trim()
    if (!tag || seen.has(tag)) continue
    seen.add(tag)
    result.push(tag)
  }
  return result
})

/** 画面笔记底部 chips：与标签区同一套合并结果 */
const pictureNoteTags = allTags

// ── 顶部标签 ────────────────────────────────────────────
const kindLabel = computed(() => {
  const kind = props.detail.kind.toLowerCase()
  if (kind === 'aigc') return 'AI 生成'
  if (kind === 'template') return '模板素材'
  return '摄影作品'
})

const kindClass = computed(() => `kind-${props.detail.kind.toLowerCase() || 'photo'}`)

const seasonClass = computed(() => {
  const label = props.detail.season
  if (label.includes('春')) return 'season-spring'
  if (label.includes('夏')) return 'season-summer'
  if (label.includes('秋')) return 'season-autumn'
  if (label.includes('冬')) return 'season-winter'
  return 'season-spring'
})

const publishedText = computed(() => {
  if (!props.detail.publishedAt) return ''
  return `发布于 ${formatDate(props.detail.publishedAt, 'YYYY-MM-DD')}`
})

// ── 作品信息 ────────────────────────────────────────────
function mimeLabel(mime: string): string {
  const map: Record<string, string> = {
    'image/jpeg': 'JPEG',
    'image/png': 'PNG',
    'image/webp': 'WebP',
    'image/heic': 'HEIC',
    'image/tiff': 'TIFF',
  }
  return map[mime.toLowerCase()] || (mime ? mime.replace('image/', '').toUpperCase() : '')
}

const specRows = computed(() => {
  const rows: { label: string; value: string }[] = []
  const d = props.detail
  if (d.width > 0 && d.height > 0) rows.push({ label: '图像尺寸', value: `${d.width} × ${d.height} 像素` })
  if (d.fileSize > 0) rows.push({ label: '文件大小', value: formatFileSize(d.fileSize) })
  const mime = mimeLabel(d.mimeType)
  if (mime) rows.push({ label: '文件格式', value: mime })
  if (d.capturedAt) rows.push({ label: '拍摄时间', value: formatDate(d.capturedAt, 'YYYY-MM-DD HH:mm') })
  if (d.place) rows.push({ label: '拍摄地点', value: d.place })
  if (d.season) rows.push({ label: '季节', value: d.season })
  if (d.category) rows.push({ label: '类别', value: d.category })
  return rows
})

// ── EXIF 折叠 ──────────────────────────────────────────
const EXIF_PREVIEW_COUNT = 6
const exifExpanded = ref(false)
const collapsibleExif = computed(() => props.detail.exifRows.length > EXIF_PREVIEW_COUNT)
const visibleExifRows = computed(() => {
  if (!collapsibleExif.value || exifExpanded.value) return props.detail.exifRows
  return props.detail.exifRows.slice(0, EXIF_PREVIEW_COUNT)
})

const promptExpanded = ref(false)

// ── 下载 ────────────────────────────────────────────────
interface DownloadOption {
  label: string
  note: string
  url: string
  filename: string
}

const menuRef = ref<HTMLElement | null>(null)
const menuOpen = ref(false)
onClickOutside(menuRef, () => {
  menuOpen.value = false
})

const safeFilename = computed(() => (props.detail.title || '作品').replace(/[\\/:*?"<>|]/g, '_').slice(0, 60))

const downloadOptions = computed<DownloadOption[]>(() => {
  const d = props.detail
  const options: DownloadOption[] = []
  const seen = new Set<string>()

  const push = (label: string, note: string, url: string, suffix: string) => {
    if (!url || seen.has(url)) return
    seen.add(url)
    options.push({ label, note, url, filename: `${safeFilename.value}-${suffix}` })
  }

  push('原图', d.aigc ? '保留原始尺寸与构图；文件含 AI 生成 XMP 标识' : '保留原始尺寸与构图', d.downloadUrl, '原图')
  for (const variant of d.variants) {
    const size = variant.width > 0 ? `长边 ${variant.width}px` : '适配分享'
    push(variant.label, size, variant.url, variant.label)
  }
  push('压缩图', '体积更小，适合网页分享', getPhotoUrl(d.id, 'compressed'), '压缩图')
  push('缩略图', '仅用于预览与索引', getPhotoUrl(d.id, 'thumbnail'), '缩略图')
  return options
})

// ── 分享 / 复制 ─────────────────────────────────────────
function pageUrl(): string {
  return window.location.href
}

async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // 浏览器拒绝剪贴板权限，走下面的兜底
  }
  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(textarea)
    return ok
  } catch {
    return false
  }
}

async function share() {
  const shareData = { title: props.detail.title, text: `${props.detail.title} — ${props.detail.author}`, url: pageUrl() }
  if (typeof navigator.share === 'function') {
    try {
      await navigator.share(shareData)
      return
    } catch {
      // 用户取消分享，继续降级到复制链接
    }
  }
  const ok = await writeClipboard(pageUrl())
  if (ok) message.success('作品链接已复制')
  else message.warning('复制失败，请手动复制地址栏链接')
}

async function copyCitation() {
  const citation = `《${props.detail.title}》 作者：${props.detail.author} · ${pageUrl()}`
  const ok = await writeClipboard(citation)
  if (ok) message.success('作品引用信息已复制')
  else message.warning('复制失败，请手动复制地址栏链接')
}

onBeforeUnmount(() => {
  menuOpen.value = false
})
</script>

<style scoped>
.info {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 26px 26px 30px;
  border-radius: var(--r-card, 20px);
  background: var(--surface, #fff);
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
}

/* ── 头部 ───────────────────────────────────────────── */
.info-head {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 11px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 1.5;
  text-decoration: none;
  letter-spacing: 0.02em;
}

.tag-kind {
  color: #fff;
  background: var(--sakura-deep, #c93a63);
}

.tag-kind.kind-aigc {
  background: var(--sakura-deep, #c93a63);
}

.tag-kind.kind-template {
  background: var(--winter, #5692c8);
}

.tag-plain {
  color: var(--muted, #63474f);
  background: #f7edf1;
}

.tag-season {
  color: var(--ink, #4a2b35);
}

.season-spring {
  background: var(--spring-pale, #ffd7e4);
  color: #a83356;
}

.season-summer {
  background: var(--summer-pale, #d4f0e4);
  color: #1f6a55;
}

.season-autumn {
  background: var(--autumn-pale, #ffdfd6);
  color: #8a4a1f;
}

.season-winter {
  background: var(--winter-pale, #d6e8f7);
  color: #2d6491;
}

.info-title {
  margin: 0;
  /* 站酷庆科黄油体只用在 ≥44px 的标题（见 docs/research/2026-11-23-visual-reference.md §4） */
  font-family: var(--font, 'Noto Sans SC', sans-serif);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.24;
  letter-spacing: 0.01em;
  color: var(--ink, #4a2b35);
  overflow-wrap: anywhere;
}

@media (min-width: 900px) {
  .info-title {
    font-family: var(--display, 'Noto Sans SC', sans-serif);
    font-size: 44px;
    font-weight: 400;
    line-height: 1.22;
    letter-spacing: 0.02em;
  }
}

.info-byline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--muted, #63474f);
}

.author {
  font-weight: 600;
  color: var(--sakura-deep, #c93a63);
}

.dot {
  color: var(--line, #f3dde5);
}

.place {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.info-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 12px;
  color: #8d7078;
}

.stat {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

/* ── 操作区 ─────────────────────────────────────────── */
.info-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 0;
  border-top: 1px solid var(--line, #f3dde5);
  border-bottom: 1px solid var(--line, #f3dde5);
}

.btn-fav,
.btn-download {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 10px 18px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease, transform 0.15s ease;
}

.btn-fav {
  color: var(--sakura-deep, #c93a63);
  background: var(--sakura-pale, #ffe9f0);
  border-color: #f8cdd9;
}

.btn-fav:hover:not(:disabled) {
  background: #ffdde8;
}

.btn-fav.is-active {
  color: #fff;
  background: var(--sakura-deep, #c93a63);
  border-color: transparent;
}

.btn-fav.is-active svg {
  fill: currentColor;
}

.btn-fav:disabled {
  opacity: 0.7;
  cursor: progress;
}

.btn-fav.is-busy {
  animation: fav-pulse 0.9s ease-in-out infinite;
}

@keyframes fav-pulse {
  0%,
  100% {
    opacity: 0.7;
  }
  50% {
    opacity: 1;
  }
}

.btn-download {
  color: #fff;
  background: linear-gradient(135deg, var(--sakura, #e8628c), var(--sakura-deep, #c93a63));
  box-shadow: 0 4px 14px rgba(201, 58, 99, 0.22);
}

.btn-download:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(201, 58, 99, 0.3);
}

.download-wrap {
  position: relative;
}

.download-menu {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 30;
  width: 268px;
  padding: 8px;
  border-radius: 16px;
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  box-shadow: 0 16px 40px rgba(74, 43, 53, 0.16);
}

.download-item {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 9px 12px;
  border-radius: 10px;
  text-decoration: none;
  transition: background 0.18s ease;
}

.download-item:hover {
  background: var(--sakura-pale, #ffe9f0);
}

.download-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.download-note {
  font-size: 11px;
  color: var(--muted, #63474f);
}

.download-tip {
  margin: 6px 6px 2px;
  padding-top: 8px;
  border-top: 1px dashed var(--line, #f3dde5);
  font-size: 11px;
  line-height: 1.6;
  color: #9a7f87;
}

.btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid var(--line, #f3dde5);
  background: transparent;
  color: var(--muted, #63474f);
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-icon:hover {
  color: var(--sakura-deep, #c93a63);
  border-color: #f5c3d2;
  background: var(--sakura-pale, #ffe9f0);
}

.menu-enter-active,
.menu-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.menu-enter-from,
.menu-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ── 通用信息块 ─────────────────────────────────────── */
.block {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.block-title {
  margin: 0;
  font-family: var(--font, 'Noto Sans SC', sans-serif);
  font-size: 16px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.block-hint {
  font-size: 11px;
  color: #a58a92;
  text-align: right;
}

.description {
  margin: 0;
  font-size: 14px;
  line-height: 1.85;
  color: var(--muted, #63474f);
  white-space: pre-line;
}

.spec-list,
.exif-list {
  margin: 0;
  display: grid;
  gap: 2px;
}

.spec-row,
.exif-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 7px 10px;
  border-radius: 8px;
  font-size: 13px;
}

.spec-row:nth-child(odd),
.exif-row:nth-child(odd) {
  background: #fdf6f9;
}

.spec-row dt,
.exif-row dt {
  flex: none;
  width: 5.5em;
  color: #9a7f87;
}

.spec-row dd,
.exif-row dd {
  margin: 0;
  color: var(--ink, #4a2b35);
  overflow-wrap: anywhere;
}

.link-btn {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0;
  border: 0;
  background: none;
  font-size: 12px;
  color: var(--sakura-deep, #c93a63);
  cursor: pointer;
}

.link-btn:hover {
  text-decoration: underline;
}

/* ── AI 生成声明摘要卡 ──────────────────────────────── */
.aigc-summary-card {
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-left: 3px solid var(--sakura-deep);
  border-radius: var(--r-md);
  background: linear-gradient(180deg, var(--sakura-wash), var(--surface));
}

.aigc-summary-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.aigc-seal {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 9px;
  border-radius: var(--r-pill);
  background: var(--sakura-deep);
  color: var(--on-accent);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.aigc-summary-kicker {
  color: var(--faint);
  font-size: 11px;
  letter-spacing: 0.08em;
}

.aigc-summary-lead {
  margin: 9px 0 0;
  color: var(--muted);
  font-size: 12.5px;
  line-height: 1.75;
}

.aigc-facts {
  display: grid;
  gap: 5px;
  margin: 10px 0 0;
  padding: 0;
}

.aigc-fact {
  display: grid;
  grid-template-columns: 5.6em minmax(0, 1fr);
  gap: 8px;
  font-size: 12px;
  line-height: 1.6;
}

.aigc-fact dt {
  color: var(--faint);
}

.aigc-fact dd {
  margin: 0;
  color: var(--ink);
  overflow-wrap: anywhere;
}

.aigc-fact dd.is-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
}

.aigc-prompt {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
}

.aigc-prompt-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--sakura-deep);
  font-size: 12px;
  cursor: pointer;
}

.aigc-prompt-toggle:hover {
  text-decoration: underline;
}

.aigc-prompt-text {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 12.5px;
  line-height: 1.75;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.aigc-prompt-text.is-collapsed {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.aigc-summary-foot {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 10px 0 0;
  padding-top: 9px;
  border-top: 1px dashed var(--line);
  color: var(--sakura-deep);
  font-size: 11.5px;
  line-height: 1.6;
}

/* ── 标签 ───────────────────────────────────────────── */
.tag-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-link {
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12.5px;
  color: var(--sakura-deep, #c93a63);
  background: #fdf1f5;
  border: 1px solid #f7dfe7;
  text-decoration: none;
  transition: all 0.18s ease;
}

.tag-link:hover {
  background: var(--sakura-pale, #ffe9f0);
  border-color: #f2c9d7;
}

/* ── 收录于专题 ─────────────────────────────────────── */
.collection-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.collection-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 13px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-pill, 999px);
  background: var(--surface, #fff);
  color: var(--ink, #4a2b35);
  font-size: 12.5px;
  line-height: 1.4;
  text-decoration: none;
  transition: border-color 0.18s ease, color 0.18s ease, background-color 0.18s ease;
}

.collection-link:hover {
  border-color: var(--sakura, #e8628c);
  background: var(--sakura-wash, #fff6f9);
  color: var(--sakura-deep, #c93a63);
}

.collection-link:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 2px;
}

/* ── 授权 ───────────────────────────────────────────── */
.license-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink, #4a2b35);
}

.license-line-muted {
  color: var(--muted, #63474f);
  font-size: 12.5px;
}

.license-line .n-icon {
  margin-top: 2px;
  color: var(--summer, #3b9c80);
  flex: none;
}

.license-line-muted .n-icon {
  color: var(--autumn, #b5703c);
}

.license-name {
  font-weight: 600;
}

.license-link {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 2px;
  color: var(--sakura-deep, #c93a63);
  font-size: 12px;
  white-space: nowrap;
}

.license-note {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: #a58a92;
}

.compliance-note {
  margin: 0;
  padding-top: 4px;
  font-size: 11px;
  line-height: 1.75;
  color: #b0969d;
  border-top: 1px dashed var(--line, #f3dde5);
  padding-top: 14px;
}

@media (max-width: 768px) {
  .info {
    padding: 18px 16px 22px;
    gap: 18px;
    border-radius: 16px;
    box-shadow: none;
    border: 1px solid var(--line, #f3dde5);
  }

  .info-title {
    font-size: 22px;
  }

  .info-actions {
    flex-wrap: wrap;
    gap: 8px;
  }

  .btn-fav,
  .btn-download {
    padding: 9px 15px;
    font-size: 13px;
  }

  .download-menu {
    width: min(268px, 82vw);
  }

  .spec-row dt,
  .exif-row dt {
    width: 5em;
  }
}

/* ── 人像隐私说明卡 ───────────────────────────── */
.privacy-card {
  margin-bottom: 18px;
  padding: 16px 18px;
  border: 1px solid rgba(201, 58, 99, 0.18);
  border-left: 3px solid var(--sakura-deep, #c93a63);
  border-radius: var(--r-sm, 10px);
  background: linear-gradient(135deg, var(--sakura-wash, #fff1f6), var(--surface, #fff) 70%);
}

.privacy-card.is-author {
  border-left-color: var(--summer, #3b9c80);
  background: linear-gradient(135deg, var(--summer-pale, #d4f0e4), var(--surface, #fff) 70%);
}

.privacy-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.privacy-seal {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--r-pill, 999px);
  background: var(--sakura-deep, #c93a63);
  color: var(--on-accent, #fff);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.privacy-card.is-author .privacy-seal {
  background: var(--summer, #3b9c80);
}

.privacy-kicker {
  color: var(--muted, #63474f);
  font-size: 12px;
  letter-spacing: 0.04em;
}

.privacy-lead {
  margin-top: 10px;
  color: var(--ink, #4a2b35);
  font-size: 13px;
  line-height: 1.75;
}

.privacy-lead strong {
  font-weight: 600;
  color: var(--sakura-deep, #c93a63);
}

.privacy-list {
  margin-top: 8px;
  padding-left: 18px;
  color: var(--ink-soft, #63474f);
  font-size: 13px;
  line-height: 1.8;
  list-style: disc;
}

.privacy-list li::marker {
  color: var(--sakura, #e8628c);
}

.privacy-foot {
  margin-top: 8px;
  color: var(--faint, #a98590);
  font-size: 12px;
  line-height: 1.7;
}

.report-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 14px 0 2px;
}

.report-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--muted);
  font-size: 12.5px;
  line-height: 1.4;
  cursor: pointer;
}

.report-link:hover {
  color: var(--sakura-deep);
  border-color: var(--sakura-mist);
  background: var(--sakura-wash);
}

.report-link:focus-visible {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.38));
  outline-offset: 2px;
}

.report-note {
  font-size: 12px;
  color: var(--faint);
}

@media (max-width: 560px) {
  .report-link {
    min-height: 44px;
  }
}
</style>