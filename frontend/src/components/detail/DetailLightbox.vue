<template>
  <Teleport to="body">
    <Transition name="lightbox">
      <div
        v-if="show"
        ref="dialogEl"
        class="lightbox"
        role="dialog"
        aria-modal="true"
        aria-label="作品大图预览"
        tabindex="-1"
        @click.self="close"
      >
        <header class="lightbox-bar">
          <div class="lightbox-caption">
            <strong class="lightbox-title">{{ detail.title }}</strong>
            <span class="lightbox-sub">
              <template v-if="counterLabel">
                <span class="lightbox-counter">{{ counterLabel }}</span>
                <span class="lightbox-dot-sep">·</span>
              </template>
              <template v-if="contextLabel">
                <span class="lightbox-context">{{ contextLabel }}</span>
                <span class="lightbox-dot-sep">·</span>
              </template>
              {{ detail.author }} · {{ sizeLabel }}
              <template v-if="detail.isRedacted"> · 已脱敏</template>
            </span>
          </div>
          <div class="lightbox-actions">
            <span v-if="zoom !== 1" class="lightbox-zoom" aria-live="polite">{{ Math.round(zoom * 100) }}%</span>
            <button
              type="button"
              class="lightbox-btn lightbox-icon-btn"
              aria-label="缩小图片"
              title="缩小（−）"
              :disabled="zoom <= 1"
              @click="zoomOut"
            >
              <n-icon :component="RemoveOutline" :size="18" />
            </button>
            <button
              type="button"
              class="lightbox-btn lightbox-icon-btn"
              aria-label="放大图片"
              title="放大（+）"
              @click="zoomIn"
            >
              <n-icon :component="AddOutline" :size="18" />
            </button>
            <button
              type="button"
              class="lightbox-btn lightbox-icon-btn lightbox-zoom-reset"
              aria-label="还原缩放"
              title="还原缩放（0）"
              :disabled="zoom === 1"
              @click="resetZoom"
            >
              1×
            </button>
            <label class="lightbox-size-wrap">
              <span class="lightbox-sr-only">图片尺寸</span>
              <select v-model="activeSize" class="lightbox-size" aria-label="图片尺寸">
                <option v-for="option in sizeOptions" :key="option.key" :value="option.key">{{ option.label }}</option>
              </select>
            </label>
            <a
              v-if="detail.canViewOriginal"
              class="lightbox-btn lightbox-download"
              :href="detail.downloadUrl"
              :download="downloadName"
              title="下载原图"
            >
              <n-icon :component="DownloadOutline" :size="18" />
              <span>下载原图</span>
            </a>
            <button type="button" class="lightbox-btn lightbox-close" aria-label="关闭预览" @click="close">
              <n-icon :component="CloseOutline" :size="20" />
            </button>
          </div>
        </header>

        <button
          v-if="hasPrev"
          type="button"
          class="lightbox-nav lightbox-prev"
          aria-label="上一张作品"
          @click="goPrev"
        >
          <n-icon :component="ChevronBackOutline" :size="22" />
        </button>
        <button
          v-if="hasNext"
          type="button"
          class="lightbox-nav lightbox-next"
          aria-label="下一张作品"
          @click="goNext"
        >
          <n-icon :component="ChevronForwardOutline" :size="22" />
        </button>

        <div
          class="lightbox-canvas"
          :class="{ 'is-zoomed': isEnlarged }"
          @touchstart.passive="onTouchStart"
          @touchend.passive="onTouchEnd"
        >
          <img
            :src="currentUrl"
            :alt="detail.author ? `${detail.title} · ${detail.author}` : detail.title"
            class="lightbox-img"
            :class="{ 'is-loaded': imgLoaded }"
            :style="{ transform: `scale(${zoom})` }"
            decoding="async"
            @load="imgLoaded = true"
            @error="imgLoaded = true"
            @dblclick.prevent="toggleZoom"
          />
        </div>

        <footer v-if="stripItems.length > 1" class="lightbox-strip" role="list" aria-label="同序列作品">
          <button
            v-for="(item, index) in stripItems"
            :key="item.id"
            type="button"
            role="listitem"
            class="strip-item"
            :class="{ 'is-active': item.id === currentId }"
            :aria-current="item.id === currentId ? 'true' : undefined"
            :aria-label="`第 ${index + 1} 张作品：${item.title}`"
            :data-strip-id="item.id"
            @click="pick(item.id)"
          >
            <img :src="item.thumbUrl" :alt="item.title" loading="lazy" decoding="async" />
            <span v-if="item.isAigc" class="strip-aigc" aria-hidden="true">AI</span>
          </button>
        </footer>

        <p class="lightbox-hint" aria-hidden="true">
          <template v-if="detail.isRedacted">这是脱敏大图 · </template>
          双击图片放大 / 再次单击还原 · 点击背景或按 Esc 关闭 · ← → 切换作品 · +/− 缩放
        </p>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { NIcon } from 'naive-ui'
import {
  AddOutline,
  ChevronBackOutline,
  ChevronForwardOutline,
  CloseOutline,
  DownloadOutline,
  RemoveOutline,
} from '@vicons/ionicons5'
import type { WorkDetail } from './workDetail'
import type { PhotoNeighbors } from '../../api/public'

const props = withDefaults(
  defineProps<{
    show: boolean
    detail: WorkDetail
    /** 当前作品的序列上下文（上一张 / 下一张、胶片条） */
    neighbors?: PhotoNeighbors | null
    /** 当前作品 id（用于高亮胶片条） */
    currentId?: string
  }>(),
  {
    neighbors: null,
    currentId: '',
  },
)

const emit = defineEmits<{ close: []; navigate: [id: string] }>()

interface SizeOption {
  key: string
  label: string
  url: string
}

const activeSize = ref('fit')
const zoom = ref(1)
const imgLoaded = ref(false)
const isEnlarged = computed(() => zoom.value > 1)

const ZOOM_MAX = 3
const ZOOM_STEP = 0.5

/** 尺寸档位：适配 / 原始（可看原图时）+ 已生成的响应式变体 */
const sizeOptions = computed<SizeOption[]>(() => {
  const list: SizeOption[] = []
  const seen = new Set<string>()
  const push = (key: string, label: string, url: string) => {
    if (!url || seen.has(url)) return
    seen.add(url)
    list.push({ key, label, url })
  }
  push('fit', '适配屏幕', props.detail.displayUrl)
  if (props.detail.canViewOriginal) push('original', '原始尺寸', props.detail.originalUrl)
  for (const variant of props.detail.variants) {
    push(`v-${variant.label}`, variant.label, variant.url)
  }
  return list
})

const currentUrl = computed(() => {
  const option = sizeOptions.value.find((item) => item.key === activeSize.value)
  return option?.url || props.detail.displayUrl
})

const sizeLabel = computed(() =>
  props.detail.width > 0 ? `${props.detail.width} × ${props.detail.height}` : '尺寸未知',
)

const downloadName = computed(() => {
  const safe = props.detail.title.replace(/[\\/:*?"<>|]/g, '_').slice(0, 60) || '作品'
  return `${safe}-原图`
})

const counterLabel = computed(() => {
  const context = props.neighbors?.context
  if (!context) return ''
  return `${context.position} / ${context.total}`
})

const contextLabel = computed(() => {
  const context = props.neighbors?.context
  if (!context) return ''
  return context.kind === 'collection' ? context.title : '最新发布'
})

const stripItems = computed(() => props.neighbors?.items || [])
const hasPrev = computed(() => Boolean(props.neighbors?.prev))
const hasNext = computed(() => Boolean(props.neighbors?.next))

function goPrev() {
  const prev = props.neighbors?.prev
  if (prev) emit('navigate', prev)
}

function goNext() {
  const next = props.neighbors?.next
  if (next) emit('navigate', next)
}

function pick(id: string) {
  if (!id || id === props.currentId) return
  emit('navigate', id)
}

function close() {
  emit('close')
}

function toggleZoom() {
  zoom.value = zoom.value === 1 ? 2 : 1
}

function zoomIn() {
  zoom.value = Math.min(ZOOM_MAX, Number((zoom.value + ZOOM_STEP).toFixed(2)))
}

function zoomOut() {
  const next = Number((zoom.value - ZOOM_STEP).toFixed(2))
  zoom.value = next < 1 ? 1 : next
}

function resetZoom() {
  zoom.value = 1
}

/** z 键：在「适配屏幕」与「原始尺寸」之间切换（不可看原图时无效果） */
function toggleOriginalSize() {
  if (!props.detail.canViewOriginal) return
  activeSize.value = activeSize.value === 'original' ? 'fit' : 'original'
}

/* 移动端手势：下滑关闭，左右滑切换作品 */
let touchStartX = 0
let touchStartY = 0
let touchStartAt = 0

function onTouchStart(event: TouchEvent) {
  const touch = event.touches[0]
  if (!touch) return
  touchStartX = touch.clientX
  touchStartY = touch.clientY
  touchStartAt = Date.now()
}

function onTouchEnd(event: TouchEvent) {
  const touch = event.changedTouches[0]
  if (!touch) return
  const dx = touch.clientX - touchStartX
  const dy = touch.clientY - touchStartY
  const elapsed = Date.now() - touchStartAt
  if (elapsed > 700) return
  if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.2) {
    if (dx > 0) goPrev()
    else goNext()
    return
  }
  if (dy > 110 && Math.abs(dy) > Math.abs(dx) * 1.2) close()
}

function handleKeydown(event: KeyboardEvent) {
  if (!props.show) return
  if (event.key === 'Tab') {
    trapFocus(event)
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
  } else if (event.key === 'ArrowLeft') {
    if (!hasPrev.value) return
    event.preventDefault()
    goPrev()
  } else if (event.key === 'ArrowRight') {
    if (!hasNext.value) return
    event.preventDefault()
    goNext()
  } else if (event.key === '+' || event.key === '=') {
    event.preventDefault()
    zoomIn()
  } else if (event.key === '-' || event.key === '_') {
    event.preventDefault()
    zoomOut()
  } else if (event.key === '0') {
    event.preventDefault()
    resetZoom()
  } else if (event.key === 'z' || event.key === 'Z') {
    event.preventDefault()
    toggleOriginalSize()
  }
}

let previousOverflow = ''
let lastFocused: HTMLElement | null = null

const dialogEl = ref<HTMLElement | null>(null)

/** Tab 焦点陷阱：键盘焦点只在灯箱内部循环 */
function trapFocus(event: KeyboardEvent) {
  const root = dialogEl.value
  if (!root) return
  const nodes = [
    ...root.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea, [tabindex]:not([tabindex="-1"])',
    ),
  ].filter((el) => el.offsetParent !== null || el === document.activeElement)
  if (!nodes.length) {
    event.preventDefault()
    root.focus()
    return
  }
  const first = nodes[0]
  const last = nodes[nodes.length - 1]
  const active = document.activeElement as HTMLElement | null
  if (event.shiftKey && (active === first || !root.contains(active))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || !root.contains(active))) {
    event.preventDefault()
    first.focus()
  }
}

/** 胶片条打开时把当前项滚进可视区 */
function scrollActiveIntoView() {
  const root = dialogEl.value
  if (!root) return
  const active = root.querySelector<HTMLElement>('.strip-item.is-active')
  active?.scrollIntoView({ block: 'nearest', inline: 'center' })
}

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      lastFocused = (document.activeElement as HTMLElement | null) ?? null
      activeSize.value = 'fit'
      zoom.value = 1
      imgLoaded.value = false
      previousOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      window.addEventListener('keydown', handleKeydown)
      nextTick(() => {
        dialogEl.value?.focus()
        scrollActiveIntoView()
      })
    } else {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeydown)
      if (lastFocused && typeof lastFocused.focus === 'function') {
        lastFocused.focus()
      }
      lastFocused = null
    }
  },
  { immediate: true },
)

watch(
  () => props.currentId,
  () => {
    activeSize.value = 'fit'
    zoom.value = 1
    imgLoaded.value = false
    nextTick(scrollActiveIntoView)
  },
)

watch(
  () => stripItems.value.length,
  () => {
    if (props.show) nextTick(scrollActiveIntoView)
  },
)

onBeforeUnmount(() => {
  document.body.style.overflow = previousOverflow
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 3000;
  outline: none;
  display: flex;
  flex-direction: column;
  background: rgba(28, 16, 21, 0.94);
  backdrop-filter: blur(6px);
  color: #fff;
}

.lightbox-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.lightbox-bar {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.45), transparent);
}

.lightbox-caption {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.lightbox-title {
  font-family: var(--display, 'Noto Sans SC', sans-serif);
  font-size: 17px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 42vw;
}

.lightbox-sub {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 4px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.66);
}

.lightbox-counter {
  color: #fff;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}

.lightbox-context {
  color: rgba(255, 255, 255, 0.82);
}

.lightbox-dot-sep {
  color: rgba(255, 255, 255, 0.4);
}

.lightbox-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}

.lightbox-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  padding: 6px 12px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  font-family: inherit;
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, opacity 0.2s ease;
}

.lightbox-btn:hover:not(:disabled) {
  background: rgba(232, 98, 140, 0.32);
  border-color: rgba(232, 98, 140, 0.7);
}

.lightbox-btn:disabled {
  cursor: default;
  opacity: 0.42;
}

.lightbox-btn:focus-visible {
  outline: 3px solid rgba(232, 98, 140, 0.75);
  outline-offset: 2px;
}

.lightbox-icon-btn {
  padding: 6px 9px;
}

.lightbox-zoom-reset {
  min-width: 36px;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

.lightbox-zoom {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(232, 98, 140, 0.28);
  border: 1px solid rgba(232, 98, 140, 0.55);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}

.lightbox-size-wrap {
  display: inline-flex;
}

.lightbox-size {
  min-height: 36px;
  padding: 6px 28px 6px 12px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  background-color: rgba(255, 255, 255, 0.08);
  color: #fff;
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  appearance: none;
  background-image: linear-gradient(45deg, transparent 50%, rgba(255, 255, 255, 0.7) 50%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.7) 50%, transparent 50%);
  background-position: calc(100% - 16px) 50%, calc(100% - 11px) 50%;
  background-size: 5px 5px, 5px 5px;
  background-repeat: no-repeat;
}

.lightbox-size:focus-visible {
  outline: 3px solid rgba(232, 98, 140, 0.75);
  outline-offset: 2px;
}

.lightbox-size option {
  background: #2a1c22;
  color: #fff;
}

.lightbox-close {
  padding: 8px;
}

.lightbox-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  cursor: pointer;
  transition: background 0.2s ease;
}

.lightbox-nav:hover {
  background: rgba(232, 98, 140, 0.5);
}

.lightbox-nav:focus-visible {
  outline: 3px solid rgba(232, 98, 140, 0.75);
  outline-offset: 2px;
}

.lightbox-prev {
  left: 20px;
}

.lightbox-next {
  right: 20px;
}

.lightbox-canvas {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 80px 12px;
  overflow: auto;
}

.lightbox-img {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  border-radius: 8px;
  cursor: zoom-in;
  transform-origin: center center;
  transition: transform 0.2s var(--ease-out, cubic-bezier(0.22, 0.61, 0.36, 1)), opacity 0.24s ease;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  opacity: 0.01;
}

.lightbox-img.is-loaded {
  opacity: 1;
}

.lightbox-canvas.is-zoomed {
  align-items: flex-start;
  justify-content: flex-start;
}

.lightbox-canvas.is-zoomed .lightbox-img {
  max-width: none;
  max-height: none;
  cursor: zoom-out;
  transform-origin: top left;
}

/* 胶片条：同序列作品缩略图，当前项高亮 */
.lightbox-strip {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px 4px;
  overflow-x: auto;
  scrollbar-width: thin;
}

.strip-item {
  position: relative;
  flex: none;
  width: 76px;
  height: 54px;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
  cursor: pointer;
  opacity: 0.62;
  transition: opacity 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.strip-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.strip-item:hover {
  opacity: 0.92;
}

.strip-item.is-active {
  opacity: 1;
  border-color: rgba(232, 98, 140, 0.95);
  transform: translateY(-1px);
}

.strip-item:focus-visible {
  outline: 3px solid rgba(232, 98, 140, 0.75);
  outline-offset: 2px;
}

.strip-aigc {
  position: absolute;
  left: 4px;
  bottom: 4px;
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  color: #4a2b35;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.4;
}

.lightbox-enter-active,
.lightbox-leave-active {
  transition: opacity 0.22s ease;
}

.lightbox-enter-from,
.lightbox-leave-to {
  opacity: 0;
}

.lightbox-hint {
  flex: none;
  padding: 8px 20px 14px;
  color: rgba(255, 255, 255, 0.62);
  font-size: 12px;
  letter-spacing: 0.02em;
  text-align: center;
}

@media (max-width: 900px) {
  .lightbox-download span,
  .lightbox-icon-btn[aria-label='还原缩放'] {
    display: none;
  }
}

@media (max-width: 768px) {
  .lightbox-bar {
    padding: 10px 12px;
    gap: 10px;
  }

  .lightbox-title {
    max-width: 38vw;
    font-size: 15px;
  }

  .lightbox-btn {
    min-height: 34px;
    padding: 6px 9px;
  }

  .lightbox-size {
    min-height: 34px;
    max-width: 7.5em;
  }

  .lightbox-canvas {
    padding: 4px 12px 8px;
  }

  .lightbox-nav {
    width: 40px;
    height: 40px;
  }

  .lightbox-prev {
    left: 8px;
  }

  .lightbox-next {
    right: 8px;
  }

  .lightbox-strip {
    padding: 8px 12px 2px;
  }

  .strip-item {
    width: 62px;
    height: 44px;
  }

  .lightbox-hint {
    padding-bottom: 10px;
    font-size: 11px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .lightbox-enter-active,
  .lightbox-leave-active,
  .lightbox-img,
  .strip-item {
    transition: none;
  }
}
</style>
