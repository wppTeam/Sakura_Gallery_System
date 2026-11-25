<template>
  <section class="note-card" aria-labelledby="picture-note-title">
    <div class="note-head">
      <p class="note-eyebrow">
        <n-icon :component="BookOutline" :size="13" aria-hidden="true" />
        画面笔记
      </p>
      <h2 id="picture-note-title" class="note-title">AI 辅助描述</h2>
    </div>

    <blockquote class="note-body">
      <n-icon class="note-quote" :component="SparklesOutline" :size="16" aria-hidden="true" />
      <p class="note-text">{{ caption }}</p>
    </blockquote>

    <p class="note-disclaimer">由 AI 根据画面生成，仅供参考</p>

    <div v-if="visibleTags.length" class="note-tags" aria-label="画面关键词">
      <button
        v-for="tag in visibleTags"
        :key="tag"
        type="button"
        class="note-tag"
        @click="goSearch(tag)"
      >
        {{ tag }}
      </button>
      <span v-if="restCount > 0" class="note-tag-more">+{{ restCount }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { BookOutline, SparklesOutline } from '@vicons/ionicons5'

const props = defineProps<{
  /** AI 画面描述正文（调用方用 v-if 保证非空；≤300 字） */
  caption: string
  /** 合并去重后的标签列表，卡片内最多展示 6 个 */
  tags: string[]
}>()

const MAX_TAGS = 6

const router = useRouter()

const visibleTags = computed(() =>
  props.tags
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0)
    .slice(0, MAX_TAGS),
)

const restCount = computed(() => {
  const total = props.tags.filter((tag) => tag.trim().length > 0).length
  return Math.max(total - MAX_TAGS, 0)
})

function goSearch(tag: string) {
  void router.push({ path: '/search', query: { q: tag, mode: 'fast' } })
}
</script>

<style scoped>
.note-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px 18px 15px;
  border: 1px dashed var(--sakura-line, rgba(232, 98, 140, 0.34));
  border-radius: var(--r-photo, 16px);
  background:
    linear-gradient(180deg, var(--sakura-wash, rgba(255, 246, 249, 0.9)), var(--surface, #fff));
}

.note-head {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.note-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.16em;
  color: var(--sakura-deep, #c93a63);
}

.note-title {
  margin: 0;
  font-family: var(--display, inherit);
  font-size: 17px;
  line-height: 1.4;
  color: var(--ink, #4a2b35);
  letter-spacing: 0.01em;
}

.note-body {
  position: relative;
  margin: 0;
  padding: 0 0 0 22px;
}

.note-quote {
  position: absolute;
  top: 2px;
  left: 0;
  color: var(--sakura, #e8628c);
  opacity: 0.7;
}

.note-text {
  margin: 0;
  color: var(--ink-soft, #63474f);
  font-size: 15px;
  line-height: 1.85;
  letter-spacing: 0.01em;
  word-break: break-word;
}

.note-disclaimer {
  margin: 0;
  padding-left: 22px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--faint, #9a8590);
}

.note-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
  padding-top: 2px;
}

.note-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 4px 12px;
  border: 1px solid var(--line, rgba(201, 58, 99, 0.16));
  border-radius: 999px;
  background: var(--surface, #fff);
  color: var(--sakura-deep, #c93a63);
  font-size: 12.5px;
  line-height: 1.4;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 160ms var(--ease-out, ease), color 160ms var(--ease-out, ease),
    background-color 160ms var(--ease-out, ease);
}

.note-tag:hover {
  border-color: var(--sakura, #e8628c);
  background: var(--sakura-mist, #ffeef4);
  color: var(--sakura-deep-hover, #a92c52);
}

.note-tag:focus-visible {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.45));
  outline-offset: 2px;
}

.note-tag-more {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--sakura-pale, #ffd7e4);
  color: var(--sakura-deep, #c93a63);
  font-size: 12px;
  line-height: 1.4;
}

@media (max-width: 560px) {
  .note-card {
    padding: 14px 14px 13px;
  }

  .note-text {
    font-size: 14.5px;
  }
}

/* 触屏：chip 至少 44px 高（可点区域） */
@media (pointer: coarse) {
  .note-tag {
    min-height: 44px;
    padding: 8px 14px;
  }

  .note-tag-more {
    min-height: 44px;
    padding: 8px 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .note-tag {
    transition: none;
  }
}
</style>
