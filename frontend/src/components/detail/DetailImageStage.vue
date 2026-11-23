<template>
  <figure class="stage" :style="stageStyle">
    <!-- 低清占位：模糊缩略图铺底，避免加载时白屏跳动 -->
    <div
      v-if="detail.thumbUrl"
      class="stage-lqip"
      :class="{ 'is-gone': loaded }"
      :style="{ backgroundImage: `url('${detail.thumbUrl}')` }"
      aria-hidden="true"
    />

    <div v-if="!failed" class="stage-frame">
      <!-- 响应式大图：WebP 优先 + JPEG srcset，浏览器按容器宽度选档；无变体时退回单图 -->
      <picture class="stage-picture">
        <source
          v-if="responsive && webpSrcset"
          type="image/webp"
          :srcset="webpSrcset"
          :sizes="SRC_SIZES"
        />
        <img
          :src="src"
          :srcset="responsive ? jpegSrcset || undefined : undefined"
          :sizes="responsive && jpegSrcset ? SRC_SIZES : undefined"
          :alt="detail.title"
          :width="detail.width || undefined"
          :height="detail.height || undefined"
          class="stage-img"
          :class="{ 'is-loaded': loaded }"
          decoding="async"
          @load="handleLoad"
          @error="handleError"
        />
      </picture>
      <div v-if="!loaded" class="stage-loading" aria-hidden="true">
        <div class="stage-loading-bar" />
      </div>
    </div>

    <div v-else class="stage-error" role="alert">
      <span class="stage-error-title">图片加载失败</span>
      <span class="stage-error-hint">可能是原作者刚替换了文件，或网络中途断开。</span>
      <button type="button" class="stage-retry" @click="retry">重新加载</button>
    </div>

    <!-- AI 生成内容显式标识（合规要求：展示层必须有） -->
    <span v-if="detail.aigc" class="stage-badge">AI 生成</span>

    <figcaption class="stage-meta">
      <span class="stage-meta-item">{{ detail.width }} × {{ detail.height }}</span>
      <span v-if="detail.fileSize > 0" class="stage-meta-item">{{ formatFileSize(detail.fileSize) }}</span>
      <span class="stage-meta-item stage-meta-kind">{{ kindLabel }}</span>
    </figcaption>

    <button
      type="button"
      class="stage-expand"
      aria-label="查看大图"
      title="查看大图"
      @click="$emit('expand')"
    >
      <n-icon :component="ExpandOutline" :size="18" />
      <span>查看原图</span>
    </button>
  </figure>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NIcon } from 'naive-ui'
import { ExpandOutline } from '@vicons/ionicons5'
import type { WorkDetail } from './workDetail'
import { formatFileSize } from '../../utils/format'

const props = defineProps<{
  detail: WorkDetail
  kindLabel?: string
}>()

defineEmits<{ expand: [] }>()

const attempt = ref(0)
const loaded = ref(false)
const failed = ref(false)

const src = computed(() => {
  const base = attempt.value === 0 ? props.detail.displayUrl : props.detail.originalUrl
  if (attempt.value === 0) return base
  // 原图兜底时加缓存穿透参数，避免浏览器复用失败结果
  return base.includes('?') ? `${base}&fallback=1` : `${base}?fallback=1`
})

const kindLabel = computed(() => props.kindLabel || '摄影作品')

/** 与 .detail-grid 两栏宽度匹配：窄屏满宽，桌面约 62vw（1320 容器下 ≈ 892px） */
const SRC_SIZES = '(max-width: 960px) 100vw, 62vw'

/** 回退到原图（attempt>0）时不再使用 srcset，避免浏览器继续命中失败档位 */
const responsive = computed(() => attempt.value === 0)

const webpSrcset = computed(() =>
  props.detail.variants
    .filter((variant) => variant.webpUrl && variant.width > 0)
    .map((variant) => `${variant.webpUrl} ${variant.width}w`)
    .join(', '),
)

const jpegSrcset = computed(() =>
  props.detail.variants
    .filter((variant) => variant.url && variant.width > 0)
    .map((variant) => `${variant.url} ${variant.width}w`)
    .join(', '),
)

const stageStyle = computed(() => ({
  aspectRatio: props.detail.aspectRatio || '4 / 3',
}))

function handleLoad() {
  loaded.value = true
}

function handleError() {
  if (attempt.value === 0) {
    attempt.value = 1
  } else {
    failed.value = true
  }
}

function retry() {
  failed.value = false
  loaded.value = false
  attempt.value = 0
}

watch(
  () => props.detail.id,
  () => {
    attempt.value = 0
    loaded.value = false
    failed.value = false
  },
)
</script>

<style scoped>
.stage {
  position: relative;
  margin: 0;
  width: 100%;
  max-height: 82vh;
  border-radius: var(--r-card, 20px);
  overflow: hidden;
  background: linear-gradient(150deg, var(--sakura-pale, #ffe9f0), #fdf3f7 55%, #f7eef9);
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
  isolation: isolate;
}

.stage::after {
  /* 细边框：让白色或浅色作品在粉色底上仍有边界 */
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: inset 0 0 0 1px rgba(201, 58, 99, 0.08);
  pointer-events: none;
  z-index: 3;
}

.stage-lqip {
  position: absolute;
  inset: -6%;
  background-size: cover;
  background-position: center;
  filter: blur(26px) saturate(1.15);
  opacity: 0.55;
  transform: scale(1.04);
  z-index: 0;
  transition: opacity 0.45s ease;
  pointer-events: none;
}

/* 大图加载完成后彻底退场：不依赖 z-index 兜底，避免无头/特殊合成路径下盖住照片 */
.stage-lqip.is-gone {
  opacity: 0;
}

/* 无障碍/无头浏览器下尊重减少动效：直接切换，不做过渡，避免占位层因动画冻结而残留 */
@media (prefers-reduced-motion: reduce) {
  .stage-lqip,
  .stage-img {
    transition: none;
  }
}

.stage-picture {
  /* 让 img 仍按 .stage-frame 的 flex 居中规则布局 */
  display: contents;
}

.stage-frame {
  position: absolute;
  inset: 0;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  box-sizing: border-box;
}

.stage-img {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  border-radius: var(--r-photo, 16px);
  opacity: 0;
  transform: scale(0.995);
  transition: opacity 0.45s ease, transform 0.45s ease;
}

.stage-img.is-loaded {
  opacity: 1;
  transform: scale(1);
}

.stage-loading {
  position: absolute;
  left: 50%;
  top: 50%;
  width: min(240px, 60%);
  height: 8px;
  transform: translate(-50%, -50%);
  border-radius: 999px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.6);
}

.stage-loading-bar {
  width: 40%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, transparent, var(--sakura, #e8628c), transparent);
  animation: stage-slide 1.15s ease-in-out infinite;
}

@keyframes stage-slide {
  0% {
    transform: translateX(-120%);
  }
  100% {
    transform: translateX(320%);
  }
}

.stage-error {
  position: absolute;
  inset: 0;
  z-index: 1;
  min-height: 260px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  text-align: center;
}

.stage-error-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.stage-error-hint {
  font-size: 13px;
  color: var(--muted, #63474f);
  max-width: 22em;
  line-height: 1.7;
}

.stage-retry {
  margin-top: 8px;
  padding: 7px 18px;
  border-radius: 999px;
  border: 1px solid var(--sakura, #e8628c);
  background: var(--surface, #fff);
  color: var(--sakura-deep, #c93a63);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}

.stage-retry:hover {
  background: var(--sakura, #e8628c);
  color: #fff;
}

.stage-badge {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 2;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: #fff;
  background: linear-gradient(135deg, var(--sakura, #e8628c), var(--sakura-deep, #c93a63));
  box-shadow: 0 4px 14px rgba(201, 58, 99, 0.28);
}

.stage-meta {
  position: absolute;
  left: 16px;
  bottom: 16px;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 0.25s ease, transform 0.25s ease;
  pointer-events: none;
}

.stage:hover .stage-meta,
.stage:focus-within .stage-meta {
  opacity: 1;
  transform: translateY(0);
}

.stage-meta-item {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--ink, #4a2b35);
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(8px);
  box-shadow: 0 2px 10px rgba(74, 43, 53, 0.08);
}

.stage-expand {
  position: absolute;
  right: 16px;
  bottom: 16px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 999px;
  font-size: 13px;
  color: #fff;
  background: rgba(74, 43, 53, 0.55);
  backdrop-filter: blur(10px);
  cursor: pointer;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 0.25s ease, transform 0.25s ease, background 0.2s ease;
}

.stage:hover .stage-expand,
.stage:focus-within .stage-expand {
  opacity: 1;
  transform: translateY(0);
}

.stage-expand:hover {
  background: rgba(201, 58, 99, 0.85);
}

/* 触屏设备不依赖 hover，常驻显示操作 */
@media (hover: none) {
  .stage-meta,
  .stage-expand {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 768px) {
  .stage {
    max-height: 64vh;
    border-radius: 16px;
  }

  .stage-frame {
    padding: 8px;
  }

  .stage-meta {
    left: 10px;
    bottom: 10px;
  }

  .stage-meta-kind {
    display: none;
  }

  .stage-expand {
    right: 10px;
    bottom: 10px;
    padding: 7px 12px;
  }

  .stage-expand span {
    display: none;
  }
}
</style>
