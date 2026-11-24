<template>
  <aside class="review-detail" :class="{ 'is-loading': loading && !review }" aria-label="审核详情">
    <div v-if="loading && !review" class="detail-skeleton" aria-busy="true">
      <span class="sk-block sk-head" />
      <span class="sk-block sk-photo" />
      <span class="sk-block sk-card" />
      <span class="sk-block sk-card is-tall" />
    </div>

    <div v-else-if="error && !review" class="detail-error">
      <n-icon :size="30" color="#c9a6b2"><CloudOfflineOutline /></n-icon>
      <p class="detail-error-title">审核详情加载失败</p>
      <p class="detail-error-hint">{{ error }}</p>
      <n-button size="small" secondary @click="emit('retry')">重新加载</n-button>
    </div>

    <div v-else-if="!review" class="detail-empty">
      <n-icon :size="30" color="#c9a6b2"><EyeOutline /></n-icon>
      <p class="detail-empty-title">选择左侧一条记录</p>
      <p class="detail-empty-hint">查看 Agent 三层依据，并给出人工终判。</p>
    </div>

    <template v-else>
      <header class="detail-head">
        <div class="detail-title-wrap">
          <div class="detail-badges">
            <n-tag size="small" :type="photoStatusTagType(photo?.status || '')" :bordered="false">
              {{ photoStatusLabel(photo?.status || '') }}
            </n-tag>
            <n-tag size="small" :type="tierTagType(review.finalTier || review.tier)" :bordered="false">
              {{ tierShort(review.finalTier || review.tier) }}
            </n-tag>
            <n-tag size="small" :type="reviewStatusTagType(review.status)" :bordered="false">
              {{ reviewStatusLabel(review.status) }}
            </n-tag>
          </div>
          <h2 class="detail-title" :title="photoTitle">{{ photoTitle }}</h2>
          <p class="detail-sub">
            <span>{{ uploaderLabel(photo) }}</span>
            <span class="sub-dot">·</span>
            <span>{{ formatDateTime(photo?.createdAt || review.createdAt) }}</span>
            <span v-if="photo?.category"> · {{ photoCategoryLabel(photo) }}</span>
            <span v-if="photo?.season"> · {{ photoSeasonLabel(photo) }}</span>
          </p>
        </div>
        <div class="detail-head-actions">
          <n-button v-if="!finalized" size="small" secondary @click="jumpToDecision">
            <template #icon>
              <n-icon><CheckmarkCircleOutline /></n-icon>
            </template>
            人工终判
          </n-button>
          <n-button
            size="small"
            :loading="running"
            :disabled="running || loading"
            @click="emit('run')"
          >
            <template #icon>
              <n-icon><ReloadOutline /></n-icon>
            </template>
            {{ running ? '已入队' : '重新审核' }}
          </n-button>
          <n-button
            v-if="dismissible"
            size="small"
            quaternary
            circle
            aria-label="关闭详情"
            @click="emit('close')"
          >
            <template #icon>
              <n-icon><CloseOutline /></n-icon>
            </template>
          </n-button>
        </div>
      </header>

      <section class="photo-preview">
        <div
          class="photo-frame is-clickable"
          :style="{ aspectRatio: previewAspect }"
          role="button"
          tabindex="0"
          title="点击查看大图（可缩放，Esc 关闭）"
          @click="emit('preview')"
          @keydown.enter.prevent="emit('preview')"
          @keydown.space.prevent="emit('preview')"
        >
          <img
            v-if="!imageFailed && imageSrc"
            :src="imageSrc"
            :alt="photoTitle"
            decoding="async"
            @error="onImageError"
          />
          <div v-else class="photo-fallback">
            <n-icon :size="26" color="#c9a6b2"><ImageOutline /></n-icon>
            <span>预览加载失败，可打开原图查看</span>
          </div>
          <span class="photo-zoom-hint" aria-hidden="true">
            <n-icon :size="14"><EyeOutline /></n-icon>
            点击查看大图
          </span>
          <a
            v-if="photo"
            class="photo-open"
            :href="originalUrl"
            target="_blank"
            rel="noopener noreferrer"
            @click.stop
          >
            <n-icon :size="14"><OpenOutline /></n-icon>
            在新标签页查看原图
          </a>
        </div>
        <p class="photo-caption">
          <span v-if="photo?.width && photo?.height" class="mono">{{ photo.width }} × {{ photo.height }}</span>
          <span v-if="photo?.filename" class="caption-file" :title="photo.filename">{{ photo.filename }}</span>
          <span class="caption-note">原图只读、保持原始构图，未裁切</span>
        </p>
      </section>

      <AgentConclusionCard :review="review" />

      <section ref="humanZone" class="human-zone">
        <div class="human-zone-head">
          <span class="human-line" />
          <span class="human-label">人工终判 · 与 Agent 意见分区</span>
          <span class="human-line" />
        </div>
        <DecisionPanel :review="review" :deciding="deciding" @submit="emit('submit-decision', $event)" />
      </section>

      <footer class="detail-foot">
        <span class="mono">review {{ (review.id || '—').slice(0, 8) }}</span>
        <span>更新于 {{ formatDateTime(review.updatedAt || review.createdAt) }}</span>
      </footer>
    </template>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  CheckmarkCircleOutline,
  CloseOutline,
  CloudOfflineOutline,
  EyeOutline,
  ImageOutline,
  OpenOutline,
  ReloadOutline,
} from '@vicons/ionicons5'
import { isFinalized as reviewIsFinalized } from '../../api/moderation'
import type { DecisionPayload, ModerationReview } from '../../api/moderation'
import { getPhotoUrl } from '../../utils/format'
import AgentConclusionCard from './AgentConclusionCard.vue'
import DecisionPanel from './DecisionPanel.vue'
import {
  formatDateTime,
  photoCategoryLabel,
  photoSeasonLabel,
  photoStatusLabel,
  photoStatusTagType,
  reviewStatusLabel,
  reviewStatusTagType,
  tierShort,
  tierTagType,
  uploaderLabel,
} from './reviewDisplay'

const props = defineProps<{
  review: ModerationReview | null
  loading: boolean
  error: string
  running: boolean
  deciding: boolean
  dismissible: boolean
}>()

const emit = defineEmits<{
  run: []
  retry: []
  close: []
  preview: []
  'submit-decision': [payload: DecisionPayload]
}>()

const imageFailed = ref(false)
const imageOverride = ref('')
const humanZone = ref<HTMLElement | null>(null)

const finalized = computed(() => (props.review ? reviewIsFinalized(props.review) : false))

function jumpToDecision() {
  humanZone.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const photo = computed(() => props.review?.photo || null)
const photoTitle = computed(() => photo.value?.title || '未命名作品')
const originalUrl = computed(() => (photo.value ? getPhotoUrl(photo.value.id, 'original') : ''))
const imageSrc = computed(() => {
  if (imageOverride.value) return imageOverride.value
  return photo.value ? getPhotoUrl(photo.value.id, 'compressed') : ''
})

const previewAspect = computed(() => {
  const width = photo.value?.width || 0
  const height = photo.value?.height || 0
  if (!width || !height) return '4 / 3'
  return `${width} / ${height}`
})

const fallbackThumb = computed(() => photo.value?.thumbUrl || '')

function onImageError() {
  const thumb = fallbackThumb.value
  if (!imageOverride.value && thumb && thumb !== imageSrc.value) {
    imageOverride.value = thumb
    return
  }
  imageFailed.value = true
}

watch(
  () => props.review?.photoId,
  () => {
    imageFailed.value = false
    imageOverride.value = ''
  },
)
</script>

<style scoped>
.review-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.detail-skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sk-block {
  display: block;
  border-radius: var(--r-md, 14px);
  background: linear-gradient(90deg, var(--sakura-pale, #ffe9f0) 25%, #fff 50%, var(--sakura-pale, #ffe9f0) 75%);
  background-size: 200% 100%;
  animation: detail-shimmer 1.4s ease-in-out infinite;
}

.sk-head { height: 68px; }
.sk-photo { height: 220px; }
.sk-card { height: 140px; }
.sk-card.is-tall { height: 260px; }

@keyframes detail-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

.detail-error,
.detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 56px 20px;
  text-align: center;
  border: 1px dashed var(--line-strong, #ecc9d6);
  border-radius: var(--r-card, 20px);
  background: var(--surface, #fff);
}

.detail-error-title,
.detail-empty-title {
  margin: 4px 0 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.detail-error-hint,
.detail-empty-hint {
  margin: 0 0 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--muted, #63474f);
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-card, 20px);
  background: var(--surface, #fff);
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
}

.detail-title-wrap {
  min-width: 0;
}

.detail-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 6px;
}

.detail-title {
  margin: 0;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--ink, #4a2b35);
}

.detail-sub {
  margin: 4px 0 0;
  font-size: 11.5px;
  color: var(--faint, #97808a);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sub-dot {
  margin: 0 3px;
  opacity: 0.6;
}

.detail-head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}

.photo-frame.is-clickable {
  cursor: zoom-in;
}

.photo-frame.is-clickable:hover .photo-zoom-hint,
.photo-frame.is-clickable:focus-visible .photo-zoom-hint {
  opacity: 1;
}

.photo-frame.is-clickable:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 3px;
}

.photo-zoom-hint {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: var(--r-pill, 999px);
  background: rgba(74, 43, 53, 0.72);
  color: #fff;
  font-size: 12px;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--dur-fast, 160ms) var(--ease-out, ease);
}

.photo-preview {
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-card, 20px);
  background: var(--surface, #fff);
  padding: 10px;
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
}

.photo-frame {
  position: relative;
  width: 100%;
  max-height: 320px;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: var(--r-photo, 16px);
  background:
    linear-gradient(0deg, rgba(255, 246, 249, 0.6), rgba(255, 246, 249, 0.6)),
    repeating-conic-gradient(#f7e6ed 0% 25%, #fdf5f8 0% 50%) 50% / 18px 18px;
}

.photo-frame img {
  width: 100%;
  height: 100%;
  max-height: 320px;
  object-fit: contain;
}

.photo-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--faint, #97808a);
  padding: 24px;
  text-align: center;
}

.photo-open {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 11px;
  color: #fff;
  background: rgba(74, 43, 53, 0.72);
  text-decoration: none;
  transition: background-color 120ms var(--ease-out, ease);
}

.photo-open:hover {
  background: var(--sakura-deep, #c93a63);
}

.photo-open:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 2px;
}

.photo-caption {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px 10px;
  margin: 7px 2px 0;
  font-size: 11px;
  color: var(--faint, #97808a);
}

.mono {
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-variant-numeric: tabular-nums;
}

.caption-file {
  max-width: 42%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.caption-note {
  margin-left: auto;
  color: var(--summer, #3b9c80);
}

.human-zone {
  margin-top: 2px;
}

.human-zone-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 4px 0 10px;
}

.human-line {
  flex: 1;
  border-top: 1px dashed var(--line-strong, #ecc9d6);
}

.human-label {
  flex: none;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--sakura-deep, #c93a63);
  white-space: nowrap;
}

.detail-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 4px;
  font-size: 10.5px;
  color: var(--faint, #97808a);
}

@media (max-width: 768px) {
  .detail-head,
  .photo-frame.is-clickable {
  cursor: zoom-in;
}

.photo-frame.is-clickable:hover .photo-zoom-hint,
.photo-frame.is-clickable:focus-visible .photo-zoom-hint {
  opacity: 1;
}

.photo-frame.is-clickable:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 3px;
}

.photo-zoom-hint {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: var(--r-pill, 999px);
  background: rgba(74, 43, 53, 0.72);
  color: #fff;
  font-size: 12px;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--dur-fast, 160ms) var(--ease-out, ease);
}

.photo-preview {
    padding: 11px;
    border-radius: var(--r-md, 14px);
  }

  .detail-title {
    font-size: 15.5px;
  }

  .photo-frame {
    max-height: 260px;
  }

  .photo-caption {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }

  .caption-file {
    max-width: 100%;
  }

  .caption-note {
    margin-left: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sk-block {
    animation: none;
  }
}
</style>
