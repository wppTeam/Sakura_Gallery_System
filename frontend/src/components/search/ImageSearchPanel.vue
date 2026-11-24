<script setup lang="ts">
/**
 * 以图搜图面板
 *
 * 拖拽 / 选择一张探针图 → 本地预览 → 自动上传 → 返回相似作品。
 * 探针图只在后端内存计算，不落盘；前端也不保存任何文件。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { NAlert, NIcon, NModal } from 'naive-ui'
import { CloseOutline, ImageOutline, RefreshOutline, SearchOutline } from '@vicons/ionicons5'
import {
  searchByImage,
  visualSearchErrorMessage,
  type VisualSearchResponse,
} from '../../api/search'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{
  (event: 'update:show', value: boolean): void
  (event: 'result', value: VisualSearchResponse): void
}>()

const MAX_BYTES = 8 * 1024 * 1024
const MAX_PIXELS = 40_000_000
const MIN_EDGE = 64
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp']

const fileInput = ref<HTMLInputElement | null>(null)
const dropActive = ref(false)
const uploading = ref(false)
const progress = ref(0)
const error = ref('')
const localError = ref('')
const previewUrl = ref('')
const fileName = ref('')
const fileSize = ref(0)
const imageWidth = ref(0)
const imageHeight = ref(0)
const pendingFile = ref<File | null>(null)

const sizeText = computed(() => {
  if (!fileSize.value) return ''
  if (fileSize.value >= 1024 * 1024) return `${(fileSize.value / 1024 / 1024).toFixed(2)} MB`
  return `${Math.max(1, Math.round(fileSize.value / 1024))} KB`
})

const dimensionText = computed(() =>
  imageWidth.value > 0 && imageHeight.value > 0
    ? `${imageWidth.value} × ${imageHeight.value}`
    : '',
)

const canReplace = computed(() => !uploading.value)

function close() {
  if (uploading.value) return
  emit('update:show', false)
}

function resetState() {
  uploading.value = false
  progress.value = 0
  error.value = ''
  localError.value = ''
  dropActive.value = false
  pendingFile.value = null
  if (previewUrl.value.startsWith('blob:')) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  fileName.value = ''
  fileSize.value = 0
  imageWidth.value = 0
  imageHeight.value = 0
}

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      resetState()
      void nextTick(() => fileInput.value?.focus())
    } else {
      resetState()
    }
  },
)

function pickFile() {
  if (!canReplace.value) return
  localError.value = ''
  fileInput.value?.click()
}

function onFileInput(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) void selectFile(file)
}

function onDrop(event: DragEvent) {
  dropActive.value = false
  if (!canReplace.value) return
  const file = event.dataTransfer?.files?.[0]
  if (file) void selectFile(file)
}

function validate(file: File): string {
  if (!ACCEPTED.includes(file.type)) {
    return '仅支持 JPEG / PNG / WebP 图片'
  }
  if (file.size > MAX_BYTES) {
    return '图片不能超过 8MB，请压缩后再试'
  }
  return ''
}

function readDimensions(url: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight })
    image.onerror = () => reject(new Error('image-decode-failed'))
    image.src = url
  })
}

async function selectFile(file: File) {
  localError.value = ''
  error.value = ''
  const denied = validate(file)
  if (denied) {
    localError.value = denied
    return
  }

  if (previewUrl.value.startsWith('blob:')) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(file)
  fileName.value = file.name || '未命名图片'
  fileSize.value = file.size
  pendingFile.value = file

  try {
    const { width, height } = await readDimensions(previewUrl.value)
    imageWidth.value = width
    imageHeight.value = height
    if (width > 0 && height > 0) {
      if (Math.max(width, height) < MIN_EDGE) {
        localError.value = '图片太小了，长边至少需要 64 像素'
        return
      }
      if (width * height > MAX_PIXELS) {
        localError.value = '图片像素过大（超过 4000 万），请压缩后再试'
        return
      }
    }
  } catch {
    localError.value = '图片无法解析，请换一张试试'
    return
  }

  void runSearch()
}

async function runSearch() {
  const file = pendingFile.value
  if (!file || uploading.value) return
  uploading.value = true
  progress.value = 0
  error.value = ''
  try {
    const response = await searchByImage(file, 12, (percent) => {
      progress.value = percent
    })
    progress.value = 100
    emit('result', response)
    emit('update:show', false)
  } catch (reason) {
    error.value = visualSearchErrorMessage(reason)
  } finally {
    uploading.value = false
  }
}

function replaceFile() {
  if (!canReplace.value) return
  pickFile()
}

defineExpose({ focus: () => fileInput.value?.focus() })
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    class="isp-modal"
    :mask-closable="!uploading"
    :close-on-esc="!uploading"
    :bordered="false"
    :style="{ width: 'min(92vw, 620px)' }"
    @update:show="(value: boolean) => emit('update:show', value)"
  >
    <template #header>
      <div class="isp-header">
        <span class="isp-header__icon" aria-hidden="true">
          <n-icon :component="ImageOutline" :size="18" />
        </span>
        <div>
          <p class="isp-title">以图搜图</p>
          <p class="isp-sub">上传一张图，找出站内视觉相似的作品</p>
        </div>
      </div>
    </template>

    <input
      ref="fileInput"
      class="isp-file"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      @change="onFileInput"
    />

    <div
      v-if="!previewUrl"
      class="isp-drop"
      :class="{ 'is-active': dropActive }"
      role="button"
      tabindex="0"
      aria-label="选择或拖入一张图片"
      @click="pickFile"
      @keydown.enter.prevent="pickFile"
      @keydown.space.prevent="pickFile"
      @dragover.prevent="dropActive = true"
      @dragleave.prevent="dropActive = false"
      @drop.prevent="onDrop"
    >
      <n-icon :component="SearchOutline" :size="26" />
      <p class="isp-drop__title">拖入图片，或点击选择</p>
      <p class="isp-drop__hint">支持 JPEG / PNG / WebP，不超过 8MB</p>
      <p class="isp-drop__privacy">图片只在内存中比对，不会保存</p>
    </div>

    <div v-else class="isp-preview">
      <div class="isp-preview__frame">
        <img class="isp-preview__img" :src="previewUrl" :alt="`待搜索图片 ${fileName}`" />
        <span v-if="uploading" class="isp-preview__busy" aria-hidden="true">
          <span class="isp-spinner" />
        </span>
      </div>
      <div class="isp-meta">
        <p class="isp-meta__name" :title="fileName">{{ fileName }}</p>
        <p class="isp-meta__detail">
          <span v-if="dimensionText">{{ dimensionText }}</span>
          <span v-if="dimensionText && sizeText"> · </span>
          <span v-if="sizeText">{{ sizeText }}</span>
        </p>
      </div>

      <div v-if="uploading" class="isp-progress" role="status" aria-live="polite">
        <div class="isp-progress__track">
          <div class="isp-progress__bar" :style="{ width: `${Math.max(progress, 8)}%` }" />
        </div>
        <p class="isp-progress__text">正在比对视觉特征…{{ progress > 0 ? ` ${progress}%` : '' }}</p>
      </div>

      <div class="isp-actions">
        <button type="button" class="isp-btn" :disabled="uploading" @click="replaceFile">
          <n-icon :component="ImageOutline" :size="15" />
          换一张
        </button>
        <button
          v-if="error"
          type="button"
          class="isp-btn is-primary"
          :disabled="uploading"
          @click="runSearch"
        >
          <n-icon :component="RefreshOutline" :size="15" />
          重试
        </button>
      </div>
    </div>

    <n-alert v-if="localError" class="isp-alert" type="warning" :bordered="false">
      {{ localError }}
    </n-alert>
    <n-alert v-else-if="error" class="isp-alert" type="error" :bordered="false">
      {{ error }}
    </n-alert>

    <p class="isp-foot">
      与上传图几乎一样的作品不会重复推荐；结果按色调、构图比例与画面结构综合排序。
    </p>

    <template #footer>
      <div class="isp-footer">
        <button type="button" class="isp-btn" :disabled="uploading" @click="close">
          <n-icon :component="CloseOutline" :size="15" />
          取消
        </button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.isp-modal {
  border-radius: var(--r-lg, 28px);
}

.isp-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.isp-header__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--sakura-wash, #fff0f5);
  color: var(--sakura-deep, #c93a63);
}

.isp-title {
  margin: 0;
  font-family: var(--display, 'ZCOOL QingKe HuangYou', sans-serif);
  font-size: var(--fs-22, 22px);
  line-height: var(--lh-tight, 1.1);
  color: var(--ink, #4a2b35);
}

.isp-sub {
  margin: 2px 0 0;
  font-size: var(--fs-xs, 12px);
  color: var(--muted, #63474f);
}

.isp-file {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.isp-drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 208px;
  padding: 26px 18px;
  border: 2px dashed var(--line-strong, #e6c6d2);
  border-radius: var(--r-card, 20px);
  background: var(--surface-soft, #fffbfd);
  color: var(--muted, #63474f);
  cursor: pointer;
  transition:
    border-color 160ms var(--ease-out, ease),
    background 160ms var(--ease-out, ease);
}

.isp-drop:hover,
.isp-drop.is-active,
.isp-drop:focus-visible {
  border-color: var(--sakura, #e8628c);
  background: var(--sakura-wash, #fff0f5);
  outline: none;
}

.isp-drop:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 2px;
}

.isp-drop__title {
  margin: 4px 0 0;
  font-size: var(--fs-body, 16px);
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.isp-drop__hint {
  margin: 0;
  font-size: var(--fs-sm, 14px);
}

.isp-drop__privacy {
  margin: 4px 0 0;
  font-size: var(--fs-xs, 12px);
  color: var(--faint, #947881);
}

.isp-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.isp-preview__frame {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 220px;
  border-radius: var(--r-photo, 16px);
  background:
    repeating-conic-gradient(var(--surface-soft, #fffbfd) 0% 25%, var(--sakura-mist, #fff2f7) 0% 50%)
    50% / 18px 18px;
  overflow: hidden;
}

.isp-preview__img {
  display: block;
  max-width: 100%;
  max-height: 220px;
  object-fit: contain;
}

.isp-preview__busy {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 246, 249, 0.55);
}

.isp-spinner {
  width: 26px;
  height: 26px;
  border: 3px solid var(--sakura-pale, #ffe9f0);
  border-top-color: var(--sakura-deep, #c93a63);
  border-radius: 50%;
  animation: isp-spin 0.8s linear infinite;
}

@keyframes isp-spin {
  to {
    transform: rotate(360deg);
  }
}

.isp-meta {
  min-width: 0;
}

.isp-meta__name {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-sm, 14px);
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.isp-meta__detail {
  margin: 2px 0 0;
  font-size: var(--fs-xs, 12px);
  color: var(--muted, #63474f);
  font-variant-numeric: tabular-nums;
}

.isp-progress__track {
  height: 6px;
  border-radius: 999px;
  background: var(--sakura-mist, #fff2f7);
  overflow: hidden;
}

.isp-progress__bar {
  height: 100%;
  border-radius: 999px;
  background: var(--sakura, #e8628c);
  transition: width 180ms var(--ease-out, ease);
}

.isp-progress__text {
  margin: 6px 0 0;
  font-size: var(--fs-xs, 12px);
  color: var(--muted, #63474f);
}

.isp-actions {
  display: flex;
  gap: 10px;
}

.isp-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-pill, 999px);
  background: var(--surface, #fff);
  color: var(--ink, #4a2b35);
  font-size: var(--fs-sm, 14px);
  cursor: pointer;
  transition:
    border-color 160ms var(--ease-out, ease),
    color 160ms var(--ease-out, ease),
    background 160ms var(--ease-out, ease);
}

.isp-btn:hover:not(:disabled) {
  border-color: var(--sakura, #e8628c);
  color: var(--sakura-deep, #c93a63);
}

.isp-btn:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 2px;
}

.isp-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.isp-btn.is-primary {
  border-color: var(--sakura-deep, #c93a63);
  background: var(--sakura-deep, #c93a63);
  color: var(--on-accent, #fff);
}

.isp-btn.is-primary:hover:not(:disabled) {
  background: var(--sakura-deep-hover, #b03257);
  color: var(--on-accent, #fff);
}

.isp-alert {
  margin-top: 12px;
}

.isp-foot {
  margin: 14px 0 0;
  font-size: var(--fs-xs, 12px);
  line-height: 1.7;
  color: var(--faint, #947881);
}

.isp-footer {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 560px) {
  .isp-preview__frame {
    height: 180px;
  }

  .isp-preview__img {
    max-height: 180px;
  }

  .isp-actions {
    flex-direction: column;
  }

  .isp-btn {
    width: 100%;
  }
}

@media (pointer: coarse) {
  .isp-btn {
    min-height: 44px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .isp-progress__bar,
  .isp-drop,
  .isp-btn {
    transition: none;
  }

  .isp-spinner {
    animation: none;
  }
}
</style>
