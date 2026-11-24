<template>
  <Teleport to="body">
    <Transition name="admin-lightbox">
      <div
        v-if="show"
        class="admin-lightbox"
        role="dialog"
        aria-modal="true"
        :aria-label="title || '查看大图'"
        @click.self="emit('close')"
      >
        <header class="admin-lightbox__bar">
          <div class="admin-lightbox__meta">
            <strong class="admin-lightbox__title">{{ title || '查看大图' }}</strong>
            <span v-if="note" class="admin-lightbox__note">{{ note }}</span>
          </div>
          <div class="admin-lightbox__tools">
            <button type="button" class="lb-btn" aria-label="缩小" :disabled="zoom <= 0.5" @click="zoomOut">
              <n-icon :component="RemoveOutline" :size="16" />
            </button>
            <span class="lb-zoom mono" aria-live="polite">{{ Math.round(zoom * 100) }}%</span>
            <button type="button" class="lb-btn" aria-label="放大" :disabled="zoom >= 3" @click="zoomIn">
              <n-icon :component="AddOutline" :size="16" />
            </button>
            <button type="button" class="lb-btn" aria-label="还原" @click="resetZoom">
              <n-icon :component="RefreshOutline" :size="15" />
            </button>
            <button type="button" class="lb-btn lb-btn--close" aria-label="关闭" @click="emit('close')">
              <n-icon :component="CloseOutline" :size="18" />
            </button>
          </div>
        </header>

        <div class="admin-lightbox__stage" :class="{ 'is-zoomed': zoom > 1 }">
          <img
            v-if="src"
            class="admin-lightbox__img"
            :src="src"
            :alt="title || '审核图片'"
            :style="{ transform: `scale(${zoom})` }"
            decoding="async"
          />
          <div v-else class="admin-lightbox__empty">没有可预览的原图</div>
        </div>

        <p class="admin-lightbox__hint">
          点击背景或按 Esc 关闭 · +/− 缩放 · 原图只读，保持原始构图未裁切
        </p>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { NIcon } from 'naive-ui'
import { AddOutline, CloseOutline, RefreshOutline, RemoveOutline } from '@vicons/ionicons5'

const props = withDefaults(
  defineProps<{
    show: boolean
    src: string
    title?: string
    note?: string
  }>(),
  { title: '', note: '' },
)

const emit = defineEmits<{ close: [] }>()

const zoom = ref(1)

function zoomIn() {
  zoom.value = Math.min(3, Math.round((zoom.value + 0.25) * 100) / 100)
}

function zoomOut() {
  zoom.value = Math.max(0.5, Math.round((zoom.value - 0.25) * 100) / 100)
}

function resetZoom() {
  zoom.value = 1
}

function onKeydown(event: KeyboardEvent) {
  if (!props.show) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  } else if (event.key === '+' || event.key === '=') {
    event.preventDefault()
    zoomIn()
  } else if (event.key === '-' || event.key === '_') {
    event.preventDefault()
    zoomOut()
  } else if (event.key === '0') {
    resetZoom()
  }
}

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      zoom.value = 1
      document.body.style.overflow = 'hidden'
      window.addEventListener('keydown', onKeydown)
    } else {
      document.body.style.overflow = ''
      window.removeEventListener('keydown', onKeydown)
    }
  },
)

onBeforeUnmount(() => {
  document.body.style.overflow = ''
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.admin-lightbox {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  flex-direction: column;
  background: rgba(74, 43, 53, 0.78);
  backdrop-filter: blur(2px);
}

.admin-lightbox__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px clamp(14px, 3vw, 28px);
  color: #fff;
}

.admin-lightbox__meta {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.admin-lightbox__title {
  overflow: hidden;
  font-size: 15px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-lightbox__note {
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
}

.admin-lightbox__tools {
  display: flex;
  flex: none;
  align-items: center;
  gap: 6px;
}

.lb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: var(--r-pill, 999px);
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  cursor: pointer;
  transition:
    background var(--dur-fast, 160ms) var(--ease-out, ease),
    transform var(--dur-fast, 160ms) var(--ease-out, ease);
}

.lb-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.22);
}

.lb-btn:active:not(:disabled) {
  transform: scale(0.95);
}

.lb-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.lb-btn:focus-visible {
  outline: 3px solid rgba(255, 255, 255, 0.7);
  outline-offset: 2px;
}

.lb-btn--close {
  margin-left: 6px;
  background: rgba(232, 98, 140, 0.4);
  border-color: rgba(232, 98, 140, 0.6);
}

.lb-zoom {
  min-width: 46px;
  text-align: center;
  color: rgba(255, 255, 255, 0.86);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.admin-lightbox__stage {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  overflow: auto;
  padding: 0 clamp(14px, 4vw, 48px) 8px;
}

.admin-lightbox__stage.is-zoomed {
  align-items: flex-start;
}

.admin-lightbox__img {
  max-width: 100%;
  max-height: calc(100vh - 150px);
  border-radius: 8px;
  object-fit: contain;
  transform-origin: center top;
  transition: transform var(--dur, 240ms) var(--ease-out, ease);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
}

.admin-lightbox__empty {
  color: rgba(255, 255, 255, 0.8);
  font-size: 14px;
}

.admin-lightbox__hint {
  margin: 0;
  padding: 4px 16px 14px;
  color: rgba(255, 255, 255, 0.68);
  text-align: center;
  font-size: 12px;
}

.admin-lightbox-enter-active,
.admin-lightbox-leave-active {
  transition: opacity 240ms var(--ease-out, ease);
}

.admin-lightbox-enter-from,
.admin-lightbox-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .admin-lightbox-enter-active,
  .admin-lightbox-leave-active,
  .admin-lightbox__img {
    transition: none;
  }
}

@media (max-width: 640px) {
  .admin-lightbox__note {
    display: none;
  }

  .admin-lightbox__hint {
    font-size: 11px;
  }
}
</style>
