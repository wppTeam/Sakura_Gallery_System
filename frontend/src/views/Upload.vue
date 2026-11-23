<template>
  <div class="upload-page">
    <SiteHeader />

    <main class="upload-main">
      <div class="upload-shell">
        <nav class="upload-crumb" aria-label="面包屑">
          <button type="button" class="crumb-back" @click="handleBack">
            <svg width="15" height="15" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M12.4 4.6 7 10l5.4 5.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            返回
          </button>
          <span class="crumb-sep" aria-hidden="true">/</span>
          <RouterLink class="crumb-link" to="/">首页</RouterLink>
          <span class="crumb-sep" aria-hidden="true">/</span>
          <span class="crumb-current">投稿</span>
        </nav>

        <header class="upload-hero">
          <div class="hero-copy">
            <p class="hero-eyebrow">
              <n-icon :component="SparklesOutline" :size="14" />
              投稿 · 视觉百花
            </p>
            <h1 class="hero-title">分享你的作品</h1>
            <p class="hero-lead">
              校园摄影、AI 生成图像或模板素材，都可以在这里发布。请如实填写作品信息，并完成 AI 生成声明。
            </p>
            <ul class="hero-points">
              <li>
                <n-icon :component="CheckmarkCircleOutline" :size="15" />
                最多 20 张 · 单张 ≤ 20MB
              </li>
              <li>
                <n-icon :component="CheckmarkCircleOutline" :size="15" />
                原图只读，预览不裁切
              </li>
              <li>
                <n-icon :component="CheckmarkCircleOutline" :size="15" />
                AI 生成内容依法声明并标注
              </li>
            </ul>
          </div>

          <ol class="steps" aria-label="投稿步骤">
            <li
              v-for="step in steps"
              :key="step.key"
              class="step"
              :class="`is-${step.state}`"
              :aria-current="step.state === 'active' ? 'step' : undefined"
            >
              <span class="step-no">{{ step.no }}</span>
              <span class="step-body">
                <span class="step-title">{{ step.title }}</span>
                <span class="step-note">{{ step.note }}</span>
              </span>
            </li>
          </ol>
        </header>

        <div class="upload-grid">
          <!-- ── 左：预览舞台 ─────────────────────────────── -->
          <section class="stage-col" aria-label="作品预览">
            <div class="stage-card">
              <n-upload
                class="stage-upload"
                :multiple="true"
                :max="20"
                accept="image/*"
                :show-file-list="false"
                :custom-request="handleUploadRequest"
                @before-upload="handleBeforeUpload"
                @change="handleFileChange"
              >
                <n-upload-dragger class="stage-dragger">
                  <div v-if="!fileList.length" class="drop">
                    <span class="drop-icon" aria-hidden="true">
                      <n-icon :component="CloudUploadOutline" :size="30" />
                    </span>
                    <h2 class="drop-title">点击或拖拽图片到这里</h2>
                    <p class="drop-sub">支持 JPG / PNG / WebP，可一次选择多张；单张不超过 20MB</p>
                    <span class="drop-btn">选择图片</span>
                    <p class="drop-note">原图只读上传，展示时保持原始比例，不做裁切。</p>
                  </div>

                  <div v-else class="stage">
                    <div
                      class="stage-frame"
                      :style="stageFrameStyle"
                      :class="{ 'is-ready': imgLoaded }"
                    >
                      <img
                        v-if="activeItem?.preview"
                        class="stage-blur"
                        :src="activeItem.preview"
                        alt=""
                        aria-hidden="true"
                      />
                      <img
                        v-if="activeItem?.preview"
                        class="stage-img"
                        :src="activeItem.preview"
                        :alt="`预览：${activeItem.file.name}`"
                        @load="imgLoaded = true"
                      />
                      <div class="stage-badges">
                        <span class="stage-chip">{{ dimsText }}</span>
                        <span class="stage-chip">{{ sizeText }}</span>
                        <span class="stage-chip">{{ typeText }}</span>
                      </div>
                      <button
                        type="button"
                        class="stage-remove"
                        aria-label="移除当前图片"
                        @click.stop="removeActive"
                      >
                        <n-icon :component="CloseOutline" :size="16" />
                      </button>
                    </div>
                    <p class="stage-caption">
                      <span>点击预览区继续添加，或拖入更多图片（{{ fileList.length }}/20）</span>
                      <span class="stage-caption-hint">预览按原始比例显示，未裁切</span>
                    </p>
                  </div>
                </n-upload-dragger>
              </n-upload>
            </div>

            <div v-if="fileList.length" class="strip-card">
              <div class="strip-head">
                <span class="strip-title">已选作品 <strong>{{ fileList.length }}</strong> 张</span>
                <div class="strip-stats">
                  <span v-if="pendingCount" class="strip-stat">待上传 {{ pendingCount }}</span>
                  <span v-if="successCount" class="strip-stat is-ok">成功 {{ successCount }}</span>
                  <span v-if="errorCount" class="strip-stat is-error">失败 {{ errorCount }}</span>
                  <button type="button" class="link-btn" @click="clearAll">清空列表</button>
                </div>
              </div>
              <div class="strip-list">
                <button
                  v-for="(item, index) in fileList"
                  :key="item.id"
                  type="button"
                  class="strip-thumb"
                  :class="[`is-${item.status}`, { 'is-active': index === activeIndex }]"
                  :aria-label="`查看第 ${index + 1} 张预览`"
                  :aria-pressed="index === activeIndex"
                  @click="handleThumbClick(index)"
                >
                  <img v-if="item.preview" :src="item.preview" alt="" />
                  <span v-if="item.status === 'pending'" class="strip-state">{{ index + 1 }}</span>
                  <span v-else-if="item.status === 'uploading'" class="strip-state is-uploading">
                    {{ item.progress }}%
                  </span>
                  <span v-else-if="item.status === 'success'" class="strip-state is-ok" aria-label="上传成功">
                    <n-icon :component="CheckmarkOutline" :size="14" />
                  </span>
                  <span v-else class="strip-state is-error" aria-label="上传失败">
                    <n-icon :component="CloseOutline" :size="14" />
                  </span>
                  <span
                    v-if="item.status === 'uploading'"
                    class="strip-progress"
                    :style="{ width: `${item.progress}%` }"
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>


            <div class="tips-card">
              <h2 class="tips-title">投稿之后</h2>
              <ol class="tips-list">
                <li>
                  <span class="tips-no">1</span>
                  <div>
                    <strong>Agent 先审</strong>
                    <p>规则校验 + 视觉快筛，低风险作品免审即发；高风险或图生图 / 换脸进入 L2 人工前审。</p>
                  </div>
                </li>
                <li>
                  <span class="tips-no">2</span>
                  <div>
                    <strong>公开展示</strong>
                    <p>通过后会出现在「探索」与检索结果里，保留署名与授权信息，图片按原始比例展示。</p>
                  </div>
                </li>
                <li>
                  <span class="tips-no">3</span>
                  <div>
                    <strong>合规下载</strong>
                    <p>下载按作者选择的授权协议；AI 生成作品的原图副本会写入 XMP 隐式标识。</p>
                  </div>
                </li>
              </ol>
            </div>

            <div v-if="recentWorks.length" class="recent-card" aria-label="近期发布">
              <div class="recent-head">
                <h2 class="recent-title">近期发布</h2>
                <RouterLink to="/explore" class="recent-more">
                  去探索
                  <n-icon :component="ArrowForwardOutline" :size="13" />
                </RouterLink>
              </div>
              <p class="recent-sub">看看大家刚分享的作品，也许能给你一点灵感。</p>
              <ul class="recent-list">
                <li v-for="work in recentWorks" :key="work.id">
                  <RouterLink class="recent-item" :to="`/photo/${work.id}`">
                    <span class="recent-thumb">
                      <img :src="work.thumbUrl" :alt="work.title" loading="lazy" decoding="async" />
                    </span>
                    <span class="recent-body">
                      <span class="recent-name">{{ work.title }}</span>
                      <span class="recent-meta">
                        <span v-if="work.season" class="recent-season">{{ work.season }}</span>
                        <span class="recent-author">{{ work.author }}</span>
                      </span>
                    </span>
                  </RouterLink>
                </li>
              </ul>
            </div>

            <div v-if="uploading" class="status-card" aria-live="polite">
              <div class="status-head">
                <span class="status-title">正在上传</span>
                <span class="status-count">{{ successCount + errorCount }} / {{ fileList.length }}</span>
              </div>
              <div class="status-bar" role="progressbar" :aria-valuenow="overallProgress" aria-valuemin="0" aria-valuemax="100">
                <span class="status-bar-fill" :style="{ width: `${overallProgress}%` }" />
              </div>
              <p class="status-note">请保持页面打开，单张最大 20MB，上传期间可以继续编辑右侧信息。</p>
            </div>

            <div v-if="allUploaded" class="done-card">
              <span class="done-icon" aria-hidden="true">
                <n-icon :component="CheckmarkCircleOutline" :size="26" />
              </span>
              <div class="done-body">
                <h2 class="done-title">上传完成</h2>
                <p class="done-note">成功上传 {{ successCount }} 张作品，审核通过后会出现在公共页面。</p>
              </div>
              <div class="done-actions">
                <n-button size="large" @click="clearAll">继续投稿</n-button>
                <n-button size="large" type="primary" @click="router.push('/my-submissions')">查看我的投稿</n-button>
                <n-button size="large" quaternary @click="router.push('/explore')">浏览广场</n-button>
              </div>
            </div>
          </section>

          <!-- ── 右：表单 ─────────────────────────────────── -->
          <section class="form-col" aria-label="作品信息与发布声明">
            <section class="form-card">
              <header class="card-head">
                <span class="section-badge">02</span>
                <div class="card-head-copy">
                  <h2 class="card-title">作品信息</h2>
                  <p class="card-sub">批量设置会应用到本次投稿的所有图片。</p>
                </div>
              </header>

              <div class="field-grid">
                <label class="field">
                  <span class="field-label">标题</span>
                  <n-input
                    v-model:value="metadata.title"
                    maxlength="200"
                    show-count
                    placeholder="给作品起个名字（可留空，默认用文件名）"
                  />
                </label>
                <label class="field">
                  <span class="field-label">署名</span>
                  <n-input
                    v-model:value="metadata.author"
                    maxlength="100"
                    placeholder="作者署名（默认用昵称）"
                  />
                </label>
              </div>

              <label class="field">
                <span class="field-label">描述</span>
                <n-input
                  v-model:value="metadata.description"
                  type="textarea"
                  :rows="3"
                  maxlength="500"
                  show-count
                  placeholder="补充拍摄地点、故事或创作说明（可留空）"
                />
              </label>

              <div v-if="taxonomyMetadataFields.length" class="field-grid">
                <label
                  v-for="field in taxonomyMetadataFields"
                  :key="field.key"
                  class="field"
                >
                  <span class="field-label">{{ field.label }}</span>
                  <n-select
                    v-model:value="metadata.classifications[field.key]"
                    :options="classificationOptions(field.key)"
                    :multiple="isMultipleFacet(field.key)"
                    clearable
                    filterable
                    :placeholder="`为所有照片设置${field.label}`"
                  />
                </label>
              </div>

              <n-collapse ghost class="legacy-collapse">
                <n-collapse-item title="旧字段兼容（一般无需填写）" name="legacy">
                  <div class="field-grid">
                    <label class="field">
                      <span class="field-label">旧季节</span>
                      <n-select v-model:value="metadata.season" :options="seasonOptions" clearable placeholder="兼容旧 season 字段" />
                    </label>
                    <label class="field">
                      <span class="field-label">旧类别</span>
                      <n-select v-model:value="metadata.category" :options="categoryOptions" clearable placeholder="兼容旧 category 字段" />
                    </label>
                    <label class="field">
                      <span class="field-label">旧校区</span>
                      <n-select v-model:value="metadata.campus" :options="campusOptions" clearable placeholder="兼容旧 campus 字段" />
                    </label>
                  </div>
                </n-collapse-item>
              </n-collapse>
            </section>

            <section class="form-card aigc-card">
              <header class="card-head">
                <span class="section-badge">03</span>
                <div class="card-head-copy">
                  <h2 class="card-title">
                    发布声明
                    <span class="legal-tag">法定要求</span>
                  </h2>
                  <p class="card-sub">《人工智能生成合成内容标识办法》要求投稿时声明是否包含 AI 生成合成内容。</p>
                </div>
              </header>

              <n-alert type="default" :bordered="false" :show-icon="false" class="aigc-legal">
                <p>
                  声明为「是」的作品会在详情页展示「AI 生成」显式角标，并在下载副本中写入 XMP 隐式标识；
                  未声明将无法提交。图生图 / 换脸类还必须确认已获得被摄者书面同意，并进入 L2 人工前审。
                </p>
              </n-alert>

              <fieldset class="aigc-choices">
                <legend class="field-label">是否包含 AI 生成合成内容？</legend>
                <label class="aigc-choice" :class="{ 'is-checked': aigc.declared === false }">
                  <input
                    class="aigc-input"
                    type="radio"
                    name="aigc-declared"
                    :checked="aigc.declared === false"
                    @change="setAigcDeclared(false)"
                  />
                  <span class="choice-mark" aria-hidden="true">
                    <n-icon v-if="aigc.declared === false" :component="CheckmarkOutline" :size="13" />
                  </span>
                  <span class="choice-body">
                    <strong>否</strong>
                    <small>这是我的原创拍摄 / 设计作品，不含 AI 生成内容</small>
                  </span>
                </label>
                <label class="aigc-choice" :class="{ 'is-checked': aigc.declared === true }">
                  <input
                    class="aigc-input"
                    type="radio"
                    name="aigc-declared"
                    :checked="aigc.declared === true"
                    @change="setAigcDeclared(true)"
                  />
                  <span class="choice-mark" aria-hidden="true">
                    <n-icon v-if="aigc.declared === true" :component="CheckmarkOutline" :size="13" />
                  </span>
                  <span class="choice-body">
                    <strong>是</strong>
                    <small>包含 AI 生成合成内容（AI 绘图、图生图、换脸等）</small>
                  </span>
                </label>
              </fieldset>

              <p v-if="aigc.declared === null" class="field-error">
                请先选择「是 / 否」，否则无法开始上传。
              </p>

              <template v-if="aigc.declared === true">
                <div class="field-grid">
                  <label class="field">
                    <span class="field-label">生成模型</span>
                    <n-input
                      v-model:value="aigc.model"
                      maxlength="100"
                      show-count
                      placeholder="如 qwen-image-3.0-pro / Midjourney v6"
                    />
                  </label>
                  <label class="field">
                    <span class="field-label">服务提供方</span>
                    <n-input
                      v-model:value="aigc.provider"
                      maxlength="100"
                      show-count
                      placeholder="如 阿里云百炼 / OpenAI / 本地部署"
                    />
                  </label>
                </div>

                <label class="field">
                  <span class="field-label">生成提示词</span>
                  <n-input
                    v-model:value="aigc.prompt"
                    type="textarea"
                    :rows="3"
                    maxlength="2000"
                    show-count
                    placeholder="用于生成该作品的提示词（可留空）"
                  />
                </label>

                <div class="switch-row">
                  <div class="switch-copy">
                    <span class="switch-title">公开提示词</span>
                    <p class="switch-hint">开启后提示词会展示在作品详情页，便于他人学习与复现；关闭则仅审核员可见。</p>
                  </div>
                  <n-switch v-model:value="aigc.promptPublic" aria-label="公开提示词" />
                </div>

                <label class="field">
                  <span class="field-label">图生图 / 源作品 ID</span>
                  <n-input
                    v-model:value="aigc.sourceWorkId"
                    maxlength="36"
                    placeholder="源作品 ID（作品详情页 URL 末尾），仅图生图时填写"
                  />
                  <span class="field-hint">填写后该作品进入 L2 人工前审，并必须确认已获得被摄者书面同意。</span>
                </label>

                <div class="switch-row">
                  <div class="switch-copy">
                    <span class="switch-title">换脸 / 人脸替换</span>
                    <p class="switch-hint">换脸 / 人脸替换类内容仅在获得被摄者书面同意后可发布，并强制人工前审（L2）。</p>
                  </div>
                  <n-switch v-model:value="aigc.faceSwap" aria-label="换脸 / 人脸替换" />
                </div>

                <label v-if="aigcConsentRequired" class="consent-row" :class="{ 'is-error': !aigc.consentConfirmed }">
                  <n-checkbox v-model:checked="aigc.consentConfirmed">
                    我确认已获得被摄者书面同意，可发布该图生图 / 换脸内容
                  </n-checkbox>
                  <span v-if="!aigc.consentConfirmed" class="field-error">
                    图生图 / 换脸类必须勾选此项，否则后端会拒绝上传。
                  </span>
                </label>

                <p class="aigc-summary">
                  提交后 Agent 会复核该声明；图生图 / 换脸类作品将进入 L2 人工前审后发布。
                </p>
              </template>
            </section>

            <section v-if="fileList.length && !allUploaded" class="submit-card">
              <div class="submit-info">
                <span class="submit-count">待上传 <strong>{{ pendingCount }}</strong> / {{ fileList.length }} 张</span>
                <span class="submit-size">共 {{ totalSizeText }}</span>
              </div>
              <p v-if="!aigcReady" class="submit-hint">
                <n-icon :component="AlertCircleOutline" :size="14" />
                <span>
                  请先完成 AI 生成声明{{ aigcConsentRequired && !aigc.consentConfirmed ? '，并确认已获得被摄者同意' : '' }}
                </span>
              </p>
              <div class="submit-actions">
                <n-button size="large" quaternary :disabled="uploading || !fileList.length" @click="clearAll">
                  清空
                </n-button>
                <n-button
                  type="primary"
                  size="large"
                  class="submit-btn"
                  :loading="uploading"
                  :disabled="!canUpload"
                  @click="startUpload"
                >
                  <template #icon>
                    <n-icon :component="CloudUploadOutline" />
                  </template>
                  {{ uploading ? '正在上传…' : `开始上传 (${pendingCount}/${fileList.length})` }}
                </n-button>
              </div>
              <p class="submit-tip">
                上传即表示你确认作品为本人创作或已获授权，并同意作品的展示与下载授权规则。
              </p>
            </section>
          </section>
        </div>
      </div>
    </main>

    <SiteFooter />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, type UploadCustomRequestOptions } from 'naive-ui'
import { storeToRefs } from 'pinia'
import {
  AlertCircleOutline,
  ArrowForwardOutline,
  CheckmarkCircleOutline,
  CheckmarkOutline,
  CloseOutline,
  CloudUploadOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import SiteHeader from '../components/layout/SiteHeader.vue'
import SiteFooter from '../components/layout/SiteFooter.vue'
import { useUploadStore, type FileItem } from '../stores/upload'
import { fetchPublicPhotos, type PublicPhoto } from '../api/public'
import { getPublicTaxonomy, type TaxonomyFacet } from '../api/taxonomy'
import { FACET_LABELS, flattenTaxonomyOptions, sanitizeTaxonomySelection } from '../utils/taxonomy'
import { SEASON_OPTIONS, CATEGORY_OPTIONS, CAMPUS_OPTIONS } from '../constants/options'

const router = useRouter()
const message = useMessage()
const uploadStore = useUploadStore()
const {
  fileList,
  uploading,
  metadata,
  aigc,
  aigcReady,
  aigcConsentRequired,
  pendingCount,
  successCount,
  errorCount,
  canUpload,
} = storeToRefs(uploadStore)

const taxonomyFacets = ref<TaxonomyFacet[]>([])

/**
 * 近期发布：给左列底部补一张紧凑卡，避免桌面右侧长表单旁出现大面积空白。
 * 拉取失败或没有数据时整卡不渲染（不显示空态/报错）。
 */
const recentWorks = ref<PublicPhoto[]>([])

async function loadRecentWorks() {
  try {
    const page = await fetchPublicPhotos({ limit: 4, sort_by: 'published_at', sort_order: 'desc' })
    recentWorks.value = page.items.slice(0, 4)
  } catch {
    recentWorks.value = []
  }
}

const taxonomyMetadataKeys = [
  'gallery_series',
  'source_type',
  'campus',
  'photo_type',
  'building',
  'facility',
  'landscape',
  'season',
  'animal',
  'plant',
] as const

const taxonomyMetadataFields = computed(() =>
  taxonomyMetadataKeys
    .filter((key) => classificationOptions(key).length)
    .map((key) => ({ key, label: FACET_LABELS[key] || key })),
)

const seasonOptions = SEASON_OPTIONS
const categoryOptions = CATEGORY_OPTIONS
const campusOptions = CAMPUS_OPTIONS

// ── 步骤引导 ────────────────────────────────────────────
const steps = computed(() => {
  const hasFiles = fileList.value.length > 0
  return [
    {
      no: '01',
      key: 'pick',
      title: '选择作品',
      note: hasFiles ? `已选 ${fileList.value.length} 张` : '拖拽或点击选择图片',
      state: hasFiles ? 'done' : 'active',
    },
    {
      no: '02',
      key: 'info',
      title: '作品信息',
      note: hasFiles ? '标题、描述与分类' : '选择作品后填写',
      state: !hasFiles ? 'todo' : 'active',
    },
    {
      no: '03',
      key: 'declare',
      title: '发布声明',
      note:
        aigc.value.declared === null
          ? 'AI 生成声明（必选）'
          : aigcReady.value
            ? '声明已完成'
            : '请补全声明与同意',
      state: !hasFiles ? 'todo' : aigcReady.value ? 'done' : 'active',
    },
  ]
})

// ── 预览舞台 ────────────────────────────────────────────
const activeIndex = ref(0)
const imgLoaded = ref(false)

const activeItem = computed<FileItem | null>(() => {
  return fileList.value[activeIndex.value] ?? fileList.value[0] ?? null
})

watch(
  () => fileList.value.length,
  (length) => {
    if (!length) activeIndex.value = 0
    else if (activeIndex.value >= length) activeIndex.value = length - 1
  },
)

watch(activeItem, () => {
  imgLoaded.value = false
})

const stageFrameStyle = computed(() => {
  const item = activeItem.value
  if (item?.width && item?.height) {
    return { aspectRatio: `${item.width} / ${item.height}` }
  }
  return { aspectRatio: '4 / 3' }
})

const dimsText = computed(() => {
  const item = activeItem.value
  if (!item) return '—'
  if (item.width && item.height) return `${item.width} × ${item.height}`
  return '读取尺寸中…'
})

const sizeText = computed(() => (activeItem.value ? formatFileSize(activeItem.value.file.size) : ''))

const typeText = computed(() => {
  const name = activeItem.value?.file.name ?? ''
  const ext = name.includes('.') ? name.slice(name.lastIndexOf('.') + 1) : ''
  return ext ? ext.toUpperCase() : '图片'
})

const totalSizeText = computed(() => {
  const total = fileList.value.reduce((sum, item) => sum + item.file.size, 0)
  return formatFileSize(total)
})

const overallProgress = computed(() => {
  if (!fileList.value.length) return 0
  const total = fileList.value.reduce((sum, item) => {
    if (item.status === 'success') return sum + 100
    if (item.status === 'uploading') return sum + item.progress
    return sum
  }, 0)
  return Math.round(total / fileList.value.length)
})

const allUploaded = computed(() => {
  return (
    fileList.value.length > 0 &&
    pendingCount.value === 0 &&
    !uploading.value &&
    successCount.value > 0
  )
})

function setAigcDeclared(value: boolean) {
  aigc.value.declared = value
}

function removeActive() {
  removeFile(activeIndex.value)
}

/** 缩略图：上传失败的点一下直接重试，其余情况切换预览 */
function handleThumbClick(index: number) {
  const item = fileList.value[index]
  if (item?.status === 'error') {
    retryUpload(index)
    return
  }
  activeIndex.value = index
}

// ── 文件选择与上传 ──────────────────────────────────────
function handleBack() {
  if (router.options.history.state.back === '/my-submissions') {
    router.back()
  } else {
    router.push('/')
  }
}

function handleBeforeUpload(options: { file: File }) {
  const { file } = options

  if (!file.type.startsWith('image/')) {
    message.error(`${file.name} 不是图片文件`)
    return false
  }

  if (file.size > 20 * 1024 * 1024) {
    message.error(`${file.name} 大小超过 20MB`)
    return false
  }

  return true
}

function handleFileChange() {
  // 文件由 custom-request 统一收进 store，此处无需额外处理
}

function handleUploadRequest(options: UploadCustomRequestOptions) {
  const { file } = options
  if (file.file) {
    uploadStore.addFiles([file.file as File])
  }
}

function removeFile(index: number) {
  uploadStore.removeFile(index)
}

function clearAll() {
  uploadStore.clearAll()
  activeIndex.value = 0
}

async function startUpload() {
  if (taxonomyFacets.value.length) {
    metadata.value.classifications = sanitizeTaxonomySelection(
      taxonomyFacets.value,
      metadata.value.classifications,
    )
  }
  await uploadStore.startUpload(message)
}

function retryUpload(index: number) {
  uploadStore.retryUpload(index)
}

// ── 分类数据 ────────────────────────────────────────────
function facetByKey(facetKey: string) {
  return taxonomyFacets.value.find((facet) => facet.key === facetKey)
}

function classificationOptions(facetKey: string) {
  const facet = facetByKey(facetKey)
  return facet ? flattenTaxonomyOptions(facet.nodes, (node) => node.id) : []
}

function isMultipleFacet(facetKey: string) {
  return facetByKey(facetKey)?.selection_mode === 'multiple'
}

function formatFileSize(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex++
  }
  return `${size.toFixed(2)} ${units[unitIndex]}`
}

onMounted(async () => {
  void loadRecentWorks()
  try {
    taxonomyFacets.value = await getPublicTaxonomy()
  } catch (error) {
    console.error('加载分类失败:', error)
  }
})
</script>

<style scoped>
.upload-page {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--ground);
}

.upload-main {
  flex: 1 0 auto;
  padding: 20px 0 72px;
  background:
    radial-gradient(60em 26em at 8% -4%, rgba(232, 98, 140, 0.07) 0%, transparent 62%),
    radial-gradient(46em 22em at 96% 6%, rgba(214, 232, 247, 0.42) 0%, transparent 58%);
}

.upload-shell {
  width: min(var(--maxw, 1320px), 100%);
  margin: 0 auto;
  padding: 0 var(--margin, 24px);
}

.upload-crumb {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0 6px;
  color: var(--faint);
  font-size: var(--fs-xs);
}

.crumb-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px 4px 6px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--muted);
  font-size: var(--fs-xs);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out);
}

.crumb-back:hover {
  color: var(--sakura-deep);
  border-color: var(--sakura);
}

.crumb-sep {
  opacity: 0.6;
}

.crumb-link {
  color: var(--muted);
  text-decoration: none;
}

.crumb-link:hover {
  color: var(--sakura-deep);
}

.crumb-current {
  color: var(--ink);
}

/* ── Hero ─────────────────────────────────────────────── */
.upload-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 32px;
  align-items: start;
  margin: 18px 0 26px;
}

.hero-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: var(--sakura-deep);
  font-size: 12px;
  letter-spacing: 0.16em;
}

.hero-title {
  margin: 12px 0 0;
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(44px, 5vw, 60px);
  font-weight: 400;
  line-height: 1.1;
  letter-spacing: 0.02em;
}

.hero-lead {
  max-width: var(--measure-lead, 21em);
  margin: 14px 0 0;
  color: var(--muted);
  font-size: clamp(16px, 1.35vw, 20px);
  line-height: var(--lh-lead, 1.85);
}

.hero-points {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}

.hero-points li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.hero-points :deep(.n-icon) {
  color: var(--sakura-deep);
}

.steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.step {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 13px;
  border: 1px solid var(--line);
  border-radius: var(--r-md, 14px);
  background: var(--surface);
  transition: border-color var(--dur) var(--ease-out), background-color var(--dur) var(--ease-out);
}

.step.is-active {
  border-color: var(--sakura);
  background: var(--sakura-wash);
}

.step.is-done {
  border-color: transparent;
  background: var(--surface-soft);
}

.step-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--surface-soft);
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.step.is-active .step-no {
  background: var(--sakura-deep);
  color: var(--on-accent);
}

.step.is-done .step-no {
  background: var(--sakura-pale);
  color: var(--sakura-deep);
}

.step-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.step-title {
  color: var(--ink);
  font-size: var(--fs-sm);
  font-weight: 600;
}

.step-note {
  color: var(--faint);
  font-size: 11.5px;
}

/* ── 两栏 ─────────────────────────────────────────────── */
.upload-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) 440px;
  gap: 24px;
  align-items: start;
}

.stage-col,
.form-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

/* ── 舞台 ─────────────────────────────────────────────── */
.stage-card {
  padding: 12px;
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.stage-upload {
  display: block;
  width: 100%;
}

.stage-upload :deep(.n-upload-dragger) {
  padding: 0;
  border: 2px dashed var(--line-strong);
  border-radius: calc(var(--r-card) - 6px);
  background: var(--surface-soft);
  transition: border-color var(--dur) var(--ease-out), background-color var(--dur) var(--ease-out);
}

.stage-upload :deep(.n-upload-dragger:hover),
.stage-upload :deep(.n-upload--drag-over .n-upload-dragger) {
  border-color: var(--sakura);
  background: var(--sakura-wash);
}

.drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 62px 24px 54px;
  text-align: center;
}

.drop-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 66px;
  height: 66px;
  border-radius: 50%;
  background: var(--sakura-pale);
  color: var(--sakura-deep);
}

.drop-title {
  margin: 6px 0 0;
  color: var(--ink);
  font-size: var(--fs-16);
  font-weight: 600;
}

.drop-sub {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-sm);
  line-height: 1.7;
}

.drop-btn {
  display: inline-flex;
  align-items: center;
  height: 40px;
  margin-top: 6px;
  padding: 0 22px;
  border-radius: var(--r-pill);
  background: var(--sakura-deep);
  color: var(--on-accent);
  font-size: var(--fs-sm);
  font-weight: 500;
  transition: background-color var(--dur-fast) var(--ease-out);
}

.stage-upload :deep(.n-upload-dragger:hover) .drop-btn {
  background: var(--sakura-deep-hover);
}

.drop-note {
  margin: 8px 0 0;
  color: var(--faint);
  font-size: var(--fs-xs);
}

.stage {
  padding: 12px;
  text-align: left;
}

.stage-frame {
  position: relative;
  width: 100%;
  max-height: 58vh;
  overflow: hidden;
  border-radius: var(--r-photo);
  background: var(--sakura-mist);
}

.stage-blur,
.stage-img {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  /* 图片不裁切：按原始比例完整展示，允许留白 */
}

.stage-blur {
  filter: blur(22px) saturate(1.05);
  opacity: 0.55;
  transform: scale(1.04);
}

.stage-img {
  z-index: 1;
  opacity: 0;
  transform: scale(1.01);
  transition: opacity 420ms var(--ease-out), transform 620ms var(--ease-out);
}

.stage-frame.is-ready .stage-img {
  opacity: 1;
  transform: scale(1);
}

.stage-badges {
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.stage-chip {
  padding: 3px 9px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.92);
  color: var(--ink);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  backdrop-filter: blur(4px);
}

.stage-remove {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.94);
  color: var(--ink);
  box-shadow: 0 4px 12px rgba(74, 43, 53, 0.16);
  cursor: pointer;
  transition: background-color var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}

.stage-remove:hover {
  background: var(--sakura-deep);
  color: var(--on-accent);
}

.stage-caption {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 12px;
  margin: 10px 2px 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}

.stage-caption-hint {
  color: var(--faint);
}

/* ── 缩略图条 ─────────────────────────────────────────── */
.strip-card {
  padding: 14px;
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.strip-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.strip-title {
  color: var(--ink);
  font-size: var(--fs-sm);
  font-weight: 600;
}

.strip-title strong {
  color: var(--sakura-deep);
  font-variant-numeric: tabular-nums;
}

.strip-stats {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--faint);
  font-size: 12px;
}

.strip-stat.is-ok {
  color: var(--summer);
}

.strip-stat.is-error {
  color: var(--sakura-deep);
}

.strip-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(62px, 1fr));
  gap: 8px;
}

.strip-thumb {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  padding: 0;
  border: 2px solid transparent;
  border-radius: var(--r-sm);
  background: var(--surface-soft);
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}

.strip-thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.strip-thumb:hover {
  border-color: var(--sakura);
}

.strip-thumb.is-active {
  border-color: var(--sakura-deep);
  transform: translateY(-1px);
}

.strip-state {
  position: absolute;
  left: 4px;
  top: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.92);
  color: var(--muted);
  font-size: 10.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.strip-state.is-uploading {
  background: var(--sakura-deep);
  color: var(--on-accent);
}

.strip-state.is-ok {
  color: var(--summer);
}

.strip-state.is-error {
  color: var(--sakura-deep);
}

.strip-progress {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 3px;
  background: var(--sakura-deep);
  transition: width 200ms linear;
}

/* ── 状态卡 ───────────────────────────────────────────── */
.status-card {
  padding: 14px 16px;
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.status-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--ink);
  font-size: var(--fs-sm);
  font-weight: 600;
}

.status-count {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.status-bar {
  margin-top: 10px;
  height: 7px;
  overflow: hidden;
  border-radius: var(--r-pill);
  background: var(--sakura-pale);
}

.status-bar-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--sakura-deep);
  transition: width 240ms var(--ease-out);
}

.status-note {
  margin: 8px 0 0;
  color: var(--faint);
  font-size: var(--fs-xs);
  line-height: 1.6;
}

/* ── 完成卡 ───────────────────────────────────────────── */
.done-card {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  padding: 18px;
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.done-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: var(--summer-pale);
  color: var(--summer);
}

.done-body {
  flex: 1 1 200px;
  min-width: 0;
}

.done-title {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-16);
  font-weight: 600;
}

.done-note {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: var(--fs-sm);
  line-height: 1.6;
}

.done-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* ── 表单卡 ───────────────────────────────────────────── */
.form-card {
  padding: 20px;
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.form-card.aigc-card {
  border-top: 3px solid var(--sakura-deep);
}

.card-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 16px;
}

.section-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--sakura-pale);
  color: var(--sakura-deep);
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.card-head-copy {
  min-width: 0;
}

.card-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 2px 0 0;
  color: var(--ink);
  font-size: var(--fs-16);
  font-weight: 600;
}

.card-sub {
  margin: 3px 0 0;
  color: var(--faint);
  font-size: 12px;
  line-height: 1.6;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 14px;
}

.field-grid + .field,
.field + .field-grid,
.field + .field,
.field-grid + .field-grid {
  margin-top: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.field-label {
  color: var(--ink);
  font-size: 13px;
  font-weight: 500;
}

.field-hint {
  color: var(--faint);
  font-size: 11.5px;
  line-height: 1.6;
}

.field-error {
  margin: 6px 0 0;
  color: var(--sakura-deep);
  font-size: 12px;
  line-height: 1.6;
}

.legacy-collapse {
  margin-top: 8px;
  border-top: 1px dashed var(--line);
}

.legacy-collapse :deep(.n-collapse-item__header) {
  color: var(--muted);
  font-size: 12.5px;
}

/* ── AIGC 声明 ────────────────────────────────────────── */
.aigc-legal {
  margin-bottom: 14px;
  border-radius: var(--r-md);
  background: var(--surface-soft);
  color: var(--muted);
}

.aigc-legal p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.75;
}

.aigc-choices {
  display: grid;
  gap: 8px;
  margin: 0 0 6px;
  padding: 0;
  border: 0;
}

.aigc-choices legend {
  padding: 0 0 6px;
}

.aigc-choice {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 13px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out), background-color var(--dur-fast) var(--ease-out);
}

.aigc-choice:hover {
  border-color: var(--sakura);
}

.aigc-choice:focus-within {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.35));
  outline-offset: 2px;
}

.aigc-choice.is-checked {
  border-color: var(--sakura-deep);
  background: var(--sakura-wash);
}

.aigc-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.choice-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  margin-top: 1px;
  border: 1.5px solid var(--line-strong);
  border-radius: 50%;
  background: var(--surface);
  color: var(--on-accent);
  transition: border-color var(--dur-fast) var(--ease-out), background-color var(--dur-fast) var(--ease-out);
}

.aigc-choice.is-checked .choice-mark {
  border-color: var(--sakura-deep);
  background: var(--sakura-deep);
}

.choice-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.choice-body strong {
  color: var(--ink);
  font-size: 13.5px;
  font-weight: 600;
}

.choice-body small {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  border-top: 1px dashed var(--line);
}

.switch-copy {
  min-width: 0;
}

.switch-title {
  color: var(--ink);
  font-size: 13px;
  font-weight: 500;
}

.switch-hint {
  margin: 3px 0 0;
  color: var(--faint);
  font-size: 11.5px;
  line-height: 1.65;
}

.consent-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
  padding: 11px 13px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface-soft);
}

.consent-row.is-error {
  border-color: var(--sakura);
  background: var(--sakura-wash);
}

.consent-row :deep(.n-checkbox__label) {
  font-size: 12.5px;
  line-height: 1.65;
}

.aigc-summary {
  margin: 10px 0 0;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: var(--sakura-wash);
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}


/* ── 提示卡 ───────────────────────────────────────────── */
.tips-card {
  padding: 18px 20px;
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.tips-title {
  margin: 0 0 12px;
  color: var(--ink);
  font-family: var(--display);
  font-size: 22px;
  font-weight: 400;
  letter-spacing: 0.02em;
}

.tips-list {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tips-list li {
  display: flex;
  gap: 10px;
}

.tips-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  margin-top: 2px;
  border-radius: 50%;
  background: var(--sakura-wash);
  color: var(--sakura-deep);
  font-size: 11px;
  font-weight: 600;
}

.tips-list strong {
  display: block;
  color: var(--ink);
  font-size: 13px;
  font-weight: 600;
}

.tips-list p {
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}

/* ── 近期发布（左列底部补位） ─────────────────────────── */
.recent-card {
  padding: 16px 18px 12px;
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.recent-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.recent-title {
  margin: 0;
  color: var(--ink);
  font-family: var(--font);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.recent-more {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  text-decoration: none;
  white-space: nowrap;
}

.recent-more:hover {
  color: var(--sakura);
}

.recent-sub {
  margin: 4px 0 10px;
  color: var(--faint);
  font-size: var(--fs-xs);
  line-height: 1.6;
}

.recent-list {
  display: grid;
  gap: 5px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 6px;
  border-radius: var(--r-sm, 10px);
  text-decoration: none;
  transition: background var(--dur-fast) var(--ease-out);
}

.recent-item:hover,
.recent-item:focus-visible {
  background: var(--sakura-wash);
}

.recent-item:focus-visible {
  outline: 2px solid var(--sakura-deep);
  outline-offset: 1px;
}

.recent-thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 50px;
  height: 50px;
  overflow: hidden;
  border-radius: 10px;
  background: var(--sakura-wash);
}

.recent-thumb img {
  width: 100%;
  height: 100%;
  /* 缩略图按原始比例完整显示，不裁切 */
  object-fit: contain;
}

.recent-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.recent-name {
  overflow: hidden;
  color: var(--ink);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-meta {
  display: flex;
  gap: 8px;
  margin-top: 2px;
  color: var(--faint);
  font-size: 11px;
  line-height: 1.4;
}

.recent-season {
  color: var(--sakura-deep);
}

.legal-tag {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: var(--r-pill);
  background: var(--sakura-wash);
  color: var(--sakura-deep);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
}

/* ── 提交卡 ───────────────────────────────────────────── */
.submit-card {
  padding: 16px 18px 18px;
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.submit-info {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px 12px;
}

.submit-count {
  color: var(--muted);
  font-size: var(--fs-sm);
}

.submit-count strong {
  color: var(--ink);
  font-size: var(--fs-16);
  font-variant-numeric: tabular-nums;
}

.submit-size {
  color: var(--faint);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.submit-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 10px 0 0;
  color: var(--sakura-deep);
  font-size: 12.5px;
  line-height: 1.6;
}

.submit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 14px;
}

.submit-btn {
  min-width: 190px;
}

.submit-tip {
  margin: 10px 0 0;
  color: var(--faint);
  font-size: 11.5px;
  line-height: 1.65;
}

.link-btn {
  padding: 0;
  border: 0;
  background: none;
  color: var(--sakura-deep);
  font-size: 12px;
  cursor: pointer;
}

.link-btn:hover {
  text-decoration: underline;
}


/* ── Naive 主题贴合公共端樱粉（仅在投稿页覆盖，不改全局） ── */
.upload-page :deep(.n-button--primary-type) {
  --n-color: var(--sakura-deep);
  --n-color-hover: var(--sakura-deep-hover);
  --n-color-pressed: var(--sakura-deep-hover);
  --n-color-focus: var(--sakura-deep-hover);
  --n-border: 1px solid var(--sakura-deep);
  --n-border-hover: 1px solid var(--sakura-deep-hover);
  --n-border-pressed: 1px solid var(--sakura-deep-hover);
  --n-border-focus: 1px solid var(--sakura-deep-hover);
  --n-text-color: var(--on-accent);
  --n-text-color-hover: var(--on-accent);
  --n-text-color-pressed: var(--on-accent);
  --n-text-color-focus: var(--on-accent);
  --n-ripple-color: rgba(255, 255, 255, 0.18);
}

.upload-page :deep(.n-button--primary-type.n-button--disabled) {
  opacity: 0.55;
  --n-color: var(--sakura-deep);
  --n-border: 1px solid var(--sakura-deep);
  --n-text-color: var(--on-accent);
}

.upload-page :deep(.n-input) {
  --n-border-focus: 1px solid var(--sakura);
  --n-border-hover: 1px solid var(--sakura);
  --n-box-shadow-focus: 0 0 0 2px rgba(201, 58, 99, 0.16);
}

.upload-page :deep(.n-base-selection) {
  --n-border-focus: 1px solid var(--sakura);
  --n-border-hover: 1px solid var(--sakura);
  --n-box-shadow-focus: 0 0 0 2px rgba(201, 58, 99, 0.16);
}

.upload-page :deep(.n-switch) {
  --n-rail-color-active: var(--sakura-deep);
  --n-rail-color-focus: var(--sakura-deep);
  --n-button-color: var(--surface);
  --n-box-shadow-focus: 0 0 0 2px rgba(201, 58, 99, 0.28);
}

.upload-page :deep(.n-checkbox) {
  --n-checked-color: var(--sakura-deep);
  --n-checked-border-color: var(--sakura-deep);
  --n-border: 1px solid var(--line-strong);
  --n-border-hover: 1px solid var(--sakura);
  --n-box-shadow-focus: 0 0 0 2px rgba(201, 58, 99, 0.2);
}

.upload-page :deep(.n-upload-trigger) {
  display: block;
  width: 100%;
}

/* ── 响应式 ───────────────────────────────────────────── */
@media (max-width: 1100px) {
  .upload-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

/* 移动端隐藏「近期发布」补位卡，避免把页面拉长 */
@media (max-width: 900px) {
  .recent-card {
    display: none;
  }
}

@media (max-width: 860px) {
  .upload-hero {
    grid-template-columns: minmax(0, 1fr);
    gap: 18px;
  }

  .steps {
    flex-direction: row;
    overflow-x: auto;
    padding-bottom: 4px;
  }

  .step {
    flex: 0 0 auto;
  }
}

@media (max-width: 640px) {
  .upload-main {
    padding: 12px 0 48px;
  }

  .upload-shell {
    padding: 0 16px;
  }

  .hero-title {
    font-size: 44px;
  }

  .hero-lead {
    font-size: 16px;
  }

  .drop {
    padding: 44px 16px 40px;
  }

  .stage-frame {
    max-height: 52vh;
  }

  .field-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .strip-list {
    grid-template-columns: repeat(auto-fill, minmax(56px, 1fr));
  }

  .done-card {
    align-items: flex-start;
  }

  .done-actions {
    width: 100%;
  }

  .submit-actions {
    flex-direction: column-reverse;
  }

  .submit-btn {
    width: 100%;
  }

  .switch-row {
    gap: 10px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .stage-img,
  .strip-thumb,
  .status-bar-fill {
    transition: none;
  }
}
</style>
