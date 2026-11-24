<template>
  <Teleport to="body">
    <Transition name="lightbox">
      <div
        v-if="show"
        class="lightbox"
        role="dialog"
        aria-modal="true"
        aria-label="作品大图预览"
        @click.self="close"
      >
        <header class="lightbox-bar">
          <div class="lightbox-caption">
            <strong class="lightbox-title">{{ detail.title }}</strong>
            <span class="lightbox-sub">
              {{ detail.author }} · {{ sizeLabel }}
              <template v-if="detail.isRedacted"> · 已脱敏</template>
            </span>
          </div>
          <div class="lightbox-actions">
            <span v-if="zoom !== 1" class="lightbox-zoom" aria-live="polite">{{ Math.round(zoom * 100) }}%</span>
            <button
              type="button"
              class="lightbox-btn"
              :class="{ 'is-active': isEnlarged }"
              :aria-pressed="isEnlarged"
              :title="isEnlarged ? '适应屏幕' : '按原始尺寸查看'"
              @click="toggleOriginalSize"
            >
              <n-icon :component="isEnlarged ? ContractOutline : ExpandOutline" :size="18" />
              <span>{{ isEnlarged ? '适应屏幕' : '原始尺寸' }}</span>
            </button>
            <a
              v-if="detail.canViewOriginal"
              class="lightbox-btn"
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
          v-if="sources.length > 1"
          type="button"
          class="lightbox-nav lightbox-prev"
          aria-label="上一个版本"
          @click="step(-1)"
        >
          <n-icon :component="ChevronBackOutline" :size="22" />
        </button>
        <button
          v-if="sources.length > 1"
          type="button"
          class="lightbox-nav lightbox-next"
          aria-label="下一个版本"
          @click="step(1)"
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
            :src="currentSource.url"
            :alt="detail.title"
            class="lightbox-img"
            :style="{ transform: `scale(${zoom})` }"
            decoding="async"
            @click="toggleOriginalSize"
          />
        </div>

        <footer v-if="sources.length > 1" class="lightbox-dots" role="tablist" aria-label="图片版本">
          <button
            v-for="(item, index) in sources"
            :key="item.url"
            type="button"
            role="tab"
            :aria-selected="index === activeIndex"
            class="lightbox-dot"
            :class="{ 'is-active': index === activeIndex }"
            @click="activeIndex = index"
          >
            {{ item.label }}
          </button>
        </footer>

        <p class="lightbox-hint" aria-hidden="true">
          <template v-if="detail.isRedacted">这是脱敏大图 · </template>
          双击图片放大 / 再次单击还原 · 点击背景或按 Esc 关闭 · ← → 切换版本 · +/− 缩放
        </p>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NIcon } from 'naive-ui'
import {
  ChevronBackOutline,
  ChevronForwardOutline,
  CloseOutline,
  ContractOutline,
  DownloadOutline,
  ExpandOutline,
} from '@vicons/ionicons5'
import type { WorkDetail } from './workDetail'

const props = defineProps<{
  show: boolean
  detail: WorkDetail
}>()

const emit = defineEmits<{ close: [] }>()

interface LightboxSource {
  label: string
  url: string
}

const activeIndex = ref(0)
const zoomed = ref(false)
const zoom = ref(1)
const isEnlarged = computed(() => zoomed.value || zoom.value > 1)

const ZOOM_MAX = 3
const ZOOM_STEP = 0.5

const sources = computed<LightboxSource[]>(() => {
  const list: LightboxSource[] = []
  const seen = new Set<string>()
  const push = (label: string, url: string) => {
    if (!url || seen.has(url)) return
    seen.add(url)
    list.push({ label, url })
  }
  // 大图预览仍以原图为主：变体现在只用于页面内响应式加载，不在这里列出低清档位
  push('原始尺寸', props.detail.originalUrl)
  push('适配屏幕', props.detail.displayUrl)
  return list
})

const currentSource = computed<LightboxSource>(() => {
  const list = sources.value
  if (!list.length) return { label: '', url: props.detail.displayUrl }
  return list[Math.min(activeIndex.value, list.length - 1)]
})

const sizeLabel = computed(() => (props.detail.width > 0 ? `${props.detail.width} × ${props.detail.height}` : '尺寸未知'))

const downloadName = computed(() => {
  const safe = props.detail.title.replace(/[\\/:*?"<>|]/g, '_').slice(0, 60) || '作品'
  return `${safe}-原图`
})

function step(delta: number) {
  const total = sources.value.length
  if (!total) return
  activeIndex.value = (activeIndex.value + delta + total) % total
}

function close() {
  emit('close')
}

function toggleOriginalSize() {
  zoomed.value = !zoomed.value
  if (!zoomed.value) zoom.value = 1
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
  zoomed.value = false
}

/* 移动端手势：下滑关闭，左右滑切换版本 */
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
    step(dx > 0 ? -1 : 1)
    return
  }
  if (dy > 110 && Math.abs(dy) > Math.abs(dx) * 1.2) close()
}

function handleKeydown(event: KeyboardEvent) {
  if (!props.show) return
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
  } else if (event.key === 'ArrowLeft') {
    step(-1)
  } else if (event.key === 'ArrowRight') {
    step(1)
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

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      activeIndex.value = 0
      zoomed.value = false
      zoom.value = 1
      previousOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      window.addEventListener('keydown', handleKeydown)
    } else {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeydown)
    }
  },
  { immediate: true },
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
  display: flex;
  flex-direction: column;
  background: rgba(28, 16, 21, 0.94);
  backdrop-filter: blur(6px);
  color: #fff;
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
  max-width: 46vw;
}

.lightbox-sub {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.66);
}

.lightbox-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.lightbox-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
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

.lightbox-btn:hover,
.lightbox-btn.is-active {
  background: rgba(232, 98, 140, 0.32);
  border-color: rgba(232, 98, 140, 0.7);
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
  width: 44px;
  height: 44px;
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
  padding: 8px 72px 16px;
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
  transition: transform 0.2s var(--ease-out, cubic-bezier(0.22, 0.61, 0.36, 1));
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.lightbox-canvas.is-zoomed {
  align-items: flex-start;
  justify-content: flex-start;
}

.lightbox-canvas.is-zoomed .lightbox-img {
  transform-origin: top left;
}

.lightbox-canvas.is-zoomed .lightbox-img {
  max-width: none;
  max-height: none;
  cursor: zoom-out;
}

.lightbox-dots {
  flex: none;
  display: flex;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px 18px;
  flex-wrap: wrap;
}

.lightbox-dot {
  padding: 5px 12px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 999px;
  background: transparent;
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.lightbox-dot.is-active {
  background: rgba(232, 98, 140, 0.85);
  border-color: transparent;
  color: #fff;
}

.lightbox-enter-active,
.lightbox-leave-active {
  transition: opacity 0.22s ease;
}

.lightbox-enter-from,
.lightbox-leave-to {
  opacity: 0;
}

@media (max-width: 768px) {
  .lightbox-bar {
    padding: 10px 12px;
  }

  .lightbox-title {
    max-width: 40vw;
    font-size: 15px;
  }

  .lightbox-btn span {
    display: none;
  }

  .lightbox-btn {
    padding: 8px;
  }

  .lightbox-canvas {
    padding: 4px 8px 8px;
  }

  .lightbox-nav {
    width: 36px;
    height: 36px;
  }

  .lightbox-prev {
    left: 8px;
  }

  .lightbox-next {
    right: 8px;
  }
}

.lightbox-hint {
  flex: none;
  padding: 10px 20px 16px;
  color: rgba(255, 255, 255, 0.62);
  font-size: 12px;
  letter-spacing: 0.02em;
  text-align: center;
}

@media (max-width: 640px) {
  .lightbox-hint {
    padding-bottom: 12px;
    font-size: 11px;
  }
}
</style>