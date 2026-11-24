<template>
  <div
    class="queue-item"
    :class="{
      'is-active': active,
      'is-failed': review.status === 'failed',
      'is-selected': selected,
    }"
    role="button"
    tabindex="0"
    :aria-current="active ? 'true' : undefined"
    :aria-label="`${photoTitle}，${reviewStatusLabel(review.status)}，${agentSummary(review)}`"
    @click="emit('select', review)"
    @keydown.enter.prevent="emit('select', review)"
    @keydown.space.prevent="emit('select', review)"
  >
    <label
      v-if="selectable"
      class="queue-select"
      :title="selected ? '取消选择' : '选择用于批量操作'"
      @click.stop
    >
      <input
        type="checkbox"
        class="queue-check"
        :checked="selected"
        :aria-label="`选择 ${photoTitle}`"
        @change.stop="emit('toggle-select', review.photoId)"
        @click.stop
        @keydown.stop
      />
      <span class="queue-check-box" aria-hidden="true" />
    </label>

    <div class="queue-thumb">
      <img
        v-if="review.photo?.thumbUrl && !thumbFailed"
        :src="review.photo.thumbUrl"
        alt=""
        loading="lazy"
        decoding="async"
        @error="thumbFailed = true"
      />
      <n-icon v-else :size="22" color="#c9a6b2"><ImageOutline /></n-icon>
      <span v-if="review.photo?.width && review.photo?.height" class="queue-ratio">
        {{ review.photo.width }}×{{ review.photo.height }}
      </span>
    </div>

    <div class="queue-main">
      <div class="queue-title-row">
        <span class="queue-title">{{ photoTitle }}</span>
        <n-tag
          v-if="review.finalDecision"
          size="tiny"
          :type="decisionTagType(review.finalDecision)"
          :bordered="false"
        >
          人工已{{ decisionLabel(review.finalDecision) }}
        </n-tag>
        <n-tag v-else-if="review.status === 'failed'" size="tiny" type="error" :bordered="false">AI 失败</n-tag>
        <n-tag v-else size="tiny" :type="reviewStatusTagType(review.status)" :bordered="false">
          {{ reviewStatusLabel(review.status) }}
        </n-tag>
      </div>

      <p v-if="caption" class="queue-caption" :title="caption">{{ caption }}</p>

      <p class="queue-summary" :title="agentSummary(review)">{{ agentSummary(review) }}</p>

      <div class="queue-meta">
        <span>{{ uploaderLabel(review.photo) }}</span>
        <span class="meta-dot">·</span>
        <span>{{ formatRelativeMinutes(review.createdAt) || formatDateTime(review.createdAt) }}</span>
        <span v-if="review.photo?.status" class="meta-dot">·</span>
        <span v-if="review.photo?.status">{{ photoStatusLabel(review.photo.status) }}</span>
      </div>
    </div>

    <div class="queue-side">
      <n-tag size="tiny" :type="tierTagType(review.finalTier || review.tier)" :bordered="false" class="queue-tier">
        {{ tierShort(review.finalTier || review.tier) }}
      </n-tag>
      <span v-if="review.latencyMs > 0" class="queue-latency">{{ formatLatency(review.latencyMs) }}</span>
      <span v-if="confidence !== null" class="queue-confidence">{{ percentText(confidence) }}</span>
      <n-icon :size="14" color="#c9a6b2" class="queue-chevron"><ChevronForwardOutline /></n-icon>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronForwardOutline, ImageOutline } from '@vicons/ionicons5'
import type { ModerationReview } from '../../api/moderation'
import {
  agentSummary,
  autoTaggingCaption,
  decisionLabel,
  decisionTagType,
  formatDateTime,
  formatLatency,
  formatRelativeMinutes,
  percentText,
  photoStatusLabel,
  reviewStatusLabel,
  reviewStatusTagType,
  tierShort,
  tierTagType,
  uploaderLabel,
} from './reviewDisplay'

const props = withDefaults(
  defineProps<{
    review: ModerationReview
    active: boolean
    selectable?: boolean
    selected?: boolean
  }>(),
  { selectable: false, selected: false },
)

const emit = defineEmits<{
  select: [review: ModerationReview]
  'toggle-select': [photoId: string]
}>()

const thumbFailed = ref(false)

const photoTitle = computed(() => props.review.photo?.title || '未命名作品')

/** 队列卡片一行 AI 画面描述（有才渲染，便于快速扫读） */
const caption = computed(() => autoTaggingCaption(props.review))

const confidence = computed(() => {
  const value = props.review.escalation?.confidence ?? props.review.prefilter?.confidence ?? null
  return typeof value === 'number' ? value : null
})
</script>

<style scoped>
.queue-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 12px;
  border: 1px solid var(--line, #f3dde5);
  border-left: 3px solid transparent;
  border-radius: var(--r-md, 14px);
  background: var(--surface, #ffffff);
  cursor: pointer;
  transition:
    background-color 120ms var(--ease-out, ease),
    border-color 120ms var(--ease-out, ease);
  outline: none;
}

.queue-item:hover {
  background: var(--sakura-wash, #fffafc);
  border-color: var(--line-strong, #ecc9d6);
}

.queue-item:focus-visible {
  outline: 3px solid var(--sakura, #e8628c);
  outline-offset: 2px;
}

.queue-item.is-active {
  border-left-color: var(--sakura-deep, #c93a63);
  border-color: var(--line-strong, #ecc9d6);
  background: var(--sakura-wash, #fffafc);
}

.queue-item.is-failed {
  border-left-color: var(--sakura-deep, #c93a63);
}

.queue-thumb {
  position: relative;
  width: 64px;
  height: 64px;
  flex: none;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: var(--r-sm, 10px);
  background: var(--sakura-pale, #ffe9f0);
}

.queue-thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.queue-ratio {
  position: absolute;
  inset: auto 0 0 0;
  padding: 1px 4px;
  font-size: 9px;
  line-height: 1.4;
  text-align: center;
  color: #fff;
  background: rgba(74, 43, 53, 0.62);
  font-variant-numeric: tabular-nums;
}

.queue-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.queue-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.queue-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.queue-title-row :deep(.n-tag) {
  flex: none;
}

.queue-summary {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--muted, #63474f);
}

.queue-caption {
  margin: 3px 0 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--faint, #97808a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}


.queue-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--faint, #97808a);
  white-space: nowrap;
  overflow: hidden;
}

.meta-dot {
  opacity: 0.6;
}

.queue-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex: none;
  text-align: right;
}

.queue-tier {
  margin-bottom: 1px;
}

.queue-latency,
.queue-confidence {
  font-size: 10.5px;
  color: var(--faint, #97808a);
  font-variant-numeric: tabular-nums;
  line-height: 1.4;
}

.queue-chevron {
  display: none;
}

@media (hover: none) {
  .queue-chevron {
    display: block;
  }
}

@media (max-width: 768px) {
  .queue-item {
    padding: 10px;
    gap: 10px;
  }

  .queue-thumb {
    width: 54px;
    height: 54px;
  }

  .queue-chevron {
    display: block;
  }

  .queue-summary {
    font-size: 11.5px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .queue-item {
    transition: none;
  }
}
</style>


<style scoped>
.queue-select {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  cursor: pointer;
}

.queue-check {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  opacity: 0;
}

.queue-check-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: 1.5px solid var(--line-strong, #eccdd8);
  border-radius: 6px;
  background: var(--surface, #fff);
  transition:
    background var(--dur-fast, 160ms) var(--ease-out, ease),
    border-color var(--dur-fast, 160ms) var(--ease-out, ease);
}

.queue-check-box::after {
  content: '';
  width: 8px;
  height: 4.5px;
  border-bottom: 2px solid var(--on-accent, #fff);
  border-left: 2px solid var(--on-accent, #fff);
  transform: rotate(-45deg) scale(0.6);
  opacity: 0;
  transition: opacity var(--dur-fast, 160ms) var(--ease-out, ease);
}

.queue-check:checked + .queue-check-box {
  border-color: var(--sakura-deep, #c93a63);
  background: var(--sakura-deep, #c93a63);
}

.queue-check:checked + .queue-check-box::after {
  opacity: 1;
}

.queue-check:focus-visible + .queue-check-box {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.4));
  outline-offset: 2px;
}

.queue-item.is-selected {
  border-color: var(--sakura, #e8628c);
  background: var(--sakura-wash, #fff5f8);
}
</style>
