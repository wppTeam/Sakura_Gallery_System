<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { ArrowForwardOutline, ImageOutline, SparklesOutline } from '@vicons/ionicons5'
import type { SearchWork } from '../../api/search'

const props = withDefaults(
  defineProps<{
    work: SearchWork
    /** 相似度徽标的 tooltip 文案：文本检索 / 以图搜图语义不同 */
    scoreHint?: string
  }>(),
  { scoreHint: '与检索意图的相关度' },
)

const router = useRouter()
const imageFailed = ref(false)
const imageLoaded = ref(false)

watch(
  () => props.work.id,
  () => {
    imageFailed.value = false
    imageLoaded.value = false
  },
)

const title = computed(() => props.work.title?.trim() || '未命名作品')
const author = computed(() => props.work.author?.trim() || '北化创作者')

const width = computed(() => (props.work.width > 0 ? props.work.width : 0))
const height = computed(() => (props.work.height > 0 ? props.work.height : 0))

/** 真实宽高比优先（图片绝不裁切） */
const ratio = computed(() => {
  const { width: w, height: h, aspectRatio } = props.work
  if (w > 0 && h > 0) return `${w} / ${h}`
  const match = String(aspectRatio || '').match(/^(\d+(?:\.\d+)?)\s*[/:×]\s*(\d+(?:\.\d+)?)$/)
  if (match) return `${match[1]} / ${match[2]}`
  return '4 / 3'
})

const metaLine = computed(() =>
  [props.work.season, props.work.category, props.work.campus].filter(Boolean).join(' · '),
)

const scoreText = computed(() => {
  const score = props.work.score
  if (score === null || score === undefined || !Number.isFinite(score) || score <= 0) return ''
  if (score <= 1) return `${Math.round(score * 100)}%`
  if (score <= 100) return `${Math.round(score)}%`
  return ''
})

const visibleTags = computed(() => props.work.tags.slice(0, 3))

/** match_reason 用「；」分隔多个理由，最多取 2 条作为 chip */
const reasonChips = computed(() =>
  String(props.work.matchReason || '')
    .split(/[；;]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 2),
)

function open() {
  void router.push(`/photo/${props.work.id}`)
}
</script>

<template>
  <article
    class="work-card"
    role="link"
    tabindex="0"
    :aria-label="`查看作品：${title}`"
    @click="open"
    @keydown.enter.prevent="open"
    @keydown.space.prevent="open"
  >
    <div class="work-card__media" :style="{ aspectRatio: ratio }">
      <img
        v-if="!imageFailed && work.thumbUrl"
        class="work-card__img"
        :class="{ 'is-loaded': imageLoaded }"
        :src="work.thumbUrl"
        :alt="title"
        :width="width || undefined"
        :height="height || undefined"
        loading="lazy"
        decoding="async"
        @load="imageLoaded = true"
        @error="imageFailed = true"
      />
      <div v-else class="work-card__fallback">
        <n-icon :component="ImageOutline" :size="26" />
        <span>预览暂不可用</span>
      </div>

      <span v-if="work.aigc" class="work-card__badge">
        <n-icon :component="SparklesOutline" :size="12" />
        AI 生成
      </span>
      <span v-if="scoreText" class="work-card__score" :title="scoreHint">{{ scoreText }}</span>

      <div class="work-card__actions" aria-hidden="true">
        <span>查看作品</span>
        <n-icon :component="ArrowForwardOutline" :size="14" />
      </div>
    </div>

    <div class="work-card__body">
      <h3 class="work-card__title">{{ title }}</h3>
      <p class="work-card__author">{{ author }}</p>
      <p v-if="metaLine" class="work-card__meta">{{ metaLine }}</p>
      <ul v-if="reasonChips.length" class="work-card__reasons">
        <li v-for="reason in reasonChips" :key="reason" class="work-card__reason">{{ reason }}</li>
      </ul>
      <ul v-if="visibleTags.length" class="work-card__tags">
        <li v-for="tag in visibleTags" :key="tag"># {{ tag }}</li>
      </ul>
    </div>
  </article>
</template>

<style scoped>
.work-card {
  position: relative;
  display: block;
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-card, 20px);
  overflow: hidden;
  cursor: pointer;
  box-shadow: var(--shadow-soft, 0 6px 24px rgba(201, 58, 99, 0.1));
  outline: none;
}

.work-card:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 2px;
}

.work-card__media {
  position: relative;
  width: 100%;
  background:
    radial-gradient(120% 90% at 20% 0%, var(--sakura-mist, #fff2f7) 0%, transparent 60%),
    var(--sakura-pale, #ffe9f0);
  overflow: hidden;
}

.work-card__img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: var(--surface-soft, #fffbfd);
  opacity: 0;
  transform: scale(1.02);
  transition:
    opacity 420ms var(--ease-out, cubic-bezier(0.22, 0.61, 0.36, 1)),
    transform 420ms var(--ease-out, cubic-bezier(0.22, 0.61, 0.36, 1)),
    filter 180ms var(--ease-out, cubic-bezier(0.22, 0.61, 0.36, 1));
}

.work-card__img.is-loaded {
  opacity: 1;
  transform: scale(1);
}

.work-card:hover .work-card__img.is-loaded,
.work-card:focus-within .work-card__img.is-loaded {
  transform: scale(1.015);
}

.work-card__fallback {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--faint, #947881);
  font-size: var(--fs-xs, 12px);
}

.work-card__badge {
  position: absolute;
  top: 10px;
  left: 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: var(--r-pill, 999px);
  background: rgba(74, 43, 53, 0.72);
  color: #fff;
  font-size: 11px;
  letter-spacing: 0.02em;
  backdrop-filter: blur(6px);
}

.work-card__score {
  position: absolute;
  top: 10px;
  right: 10px;
  padding: 3px 8px;
  border-radius: var(--r-pill, 999px);
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--line, #f3dde5);
  color: var(--sakura-deep, #c93a63);
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* 操作条：仅 hover / focus-within 滑入，不做整卡上浮 */
.work-card__actions {
  position: absolute;
  inset: auto 0 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 26px 14px 11px;
  color: #fff;
  font-size: 12px;
  letter-spacing: 0.04em;
  background: linear-gradient(to top, rgba(74, 43, 53, 0.62), rgba(74, 43, 53, 0));
  opacity: 0;
  transform: translateY(6px);
  transition:
    opacity 180ms var(--ease-out, ease),
    transform 180ms var(--ease-out, ease);
  pointer-events: none;
}

.work-card:hover .work-card__actions,
.work-card:focus-visible .work-card__actions,
.work-card:focus-within .work-card__actions {
  opacity: 1;
  transform: translateY(0);
}

.work-card__body {
  padding: 12px 14px 14px;
}

.work-card__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--ink, #4a2b35);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-card__author {
  margin: 4px 0 0;
  font-size: var(--fs-xs, 12px);
  color: var(--muted, #63474f);
}

.work-card__meta {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--faint, #947881);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-card__reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}

.work-card__reason {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 3px 9px;
  border-radius: var(--r-pill, 999px);
  background: var(--sakura-mist, #fff2f7);
  border: 1px solid var(--sakura-pale, #ffe9f0);
  color: var(--ink-soft, #563842);
  font-size: 11px;
  line-height: 1.6;
}

.work-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 9px 0 0;
  padding: 0;
  list-style: none;
}

.work-card__tags li {
  padding: 2px 8px;
  border-radius: var(--r-pill, 999px);
  background: var(--surface-warm, #fff9fb);
  border: 1px solid var(--line, #f3dde5);
  color: var(--muted, #63474f);
  font-size: 11px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (hover: none) {
  .work-card__actions {
    display: none;
  }

  .work-card:hover .work-card__img.is-loaded {
    transform: scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  /* 无头截图 / reduced-motion 下 opacity 过渡会停在 0，图片永远不显示；直接不淡入 */
  .work-card__img,
  .work-card__actions {
    transition: none;
    transform: none;
  }

  .work-card__img.is-loaded {
    opacity: 1;
  }

  .work-card:hover .work-card__img.is-loaded,
  .work-card:focus-within .work-card__img.is-loaded {
    transform: none;
  }
}

@media (max-width: 480px) {
  .work-card__body {
    padding: 10px 12px 12px;
  }

  .work-card__title {
    font-size: 14px;
  }
}
</style>
