<script setup lang="ts">
import { computed } from 'vue'
import { NIcon } from 'naive-ui'
import {
  AlertCircleOutline,
  CloudOfflineOutline,
  RefreshOutline,
  SearchOutline,
  SparklesOutline,
} from '@vicons/ionicons5'

type Variant = 'idle' | 'empty' | 'error' | 'timeout'

const props = withDefaults(
  defineProps<{
    variant: Variant
    query?: string
    message?: string
    canClear?: boolean
    suggestions?: string[]
    retrying?: boolean
  }>(),
  { query: '', message: '', canClear: false, suggestions: () => [], retrying: false },
)

const emit = defineEmits<{
  (e: 'retry'): void
  (e: 'clear'): void
  (e: 'pick', value: string): void
}>()

const icon = computed(() => {
  if (props.variant === 'error' || props.variant === 'timeout') return CloudOfflineOutline
  if (props.variant === 'empty') return SearchOutline
  return SparklesOutline
})

const title = computed(() => {
  if (props.variant === 'idle') return '想找什么画面？'
  if (props.variant === 'empty') return '没有找到相关作品'
  if (props.variant === 'timeout') return 'Agent 检索超时'
  return '检索出了问题'
})

const lead = computed(() => {
  if (props.variant === 'idle') {
    return '用一句自然语言描述画面、季节或情绪即可。Agent 会拆解意图、多步检索，并解释为什么这些作品相关。'
  }
  if (props.variant === 'empty') {
    return props.query
      ? `没有找到与「${props.query}」匹配的作品，可以换个说法、减少筛选条件，或试试更宽泛的词。`
      : '暂时没有匹配的作品，可以换个说法或减少筛选条件。'
  }
  if (props.message) return props.message
  if (props.variant === 'timeout') return '本次检索耗时过长。可以稍后重试，或切换到「快速检索」先看结果。'
  return '网络连接异常或服务暂时不可用，请稍后重试。'
})
</script>

<template>
  <section class="search-empty" :class="`search-empty--${variant}`">
    <div class="search-empty__icon">
      <n-icon :component="icon" :size="26" />
    </div>
    <h2 class="search-empty__title">{{ title }}</h2>
    <p class="search-empty__lead">{{ lead }}</p>

    <div
      v-if="(variant === 'idle' || variant === 'empty') && suggestions.length"
      class="search-empty__suggest"
    >
      <span class="search-empty__suggest-label">{{ variant === 'empty' ? '换个词试试' : '试试这些词' }}</span>
      <button
        v-for="suggestion in suggestions"
        :key="suggestion"
        type="button"
        class="search-empty__suggest-chip"
        @click="emit('pick', suggestion)"
      >
        {{ suggestion }}
      </button>
    </div>

    <div class="search-empty__actions">
      <button
        v-if="variant !== 'idle'"
        type="button"
        class="search-empty__primary"
        :disabled="retrying"
        @click="emit('retry')"
      >
        <n-icon :component="RefreshOutline" :size="14" :class="{ 'is-spinning': retrying }" />
        {{ retrying ? '正在重试…' : '重新检索' }}
      </button>
      <button
        v-if="canClear"
        type="button"
        class="search-empty__ghost"
        @click="emit('clear')"
      >
        <n-icon :component="AlertCircleOutline" :size="14" />
        清除筛选条件
      </button>
    </div>
  </section>
</template>

<style scoped>
.search-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  margin: 24px 0 8px;
  padding: clamp(36px, 6vw, 64px) 24px;
  border: 1px dashed var(--line-strong, #eccdd8);
  border-radius: var(--r-card, 20px);
  background:
    radial-gradient(120% 120% at 50% 0%, var(--sakura-mist, #fff2f7) 0%, transparent 58%),
    var(--surface, #fff);
}

.search-empty__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 58px;
  height: 58px;
  border-radius: 50%;
  background: var(--sakura-pale, #ffe9f0);
  color: var(--sakura-deep, #c93a63);
}

.search-empty--error .search-empty__icon,
.search-empty--timeout .search-empty__icon {
  background: var(--autumn-pale, #ffdfd6);
  color: var(--autumn, #b5703c);
}

.search-empty__title {
  margin: 16px 0 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  line-height: 1.4;
}

.search-empty__lead {
  margin: 8px 0 0;
  max-width: var(--measure, 24em);
  color: var(--muted, #63474f);
  font-size: 14px;
  line-height: 1.75;
}

.search-empty__suggest {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 18px;
}

.search-empty__suggest-label {
  font-size: 12px;
  color: var(--faint, #947881);
}

.search-empty__suggest-chip {
  padding: 5px 13px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-pill, 999px);
  background: var(--surface, #fff);
  color: var(--ink-soft, #563842);
  font-size: 13px;
  cursor: pointer;
  transition:
    transform 120ms var(--ease-out, ease),
    border-color 120ms var(--ease-out, ease),
    color 120ms var(--ease-out, ease);
}

.search-empty__suggest-chip:hover {
  border-color: var(--sakura, #e8628c);
  color: var(--sakura-deep, #c93a63);
}

.search-empty__suggest-chip:active {
  transform: scale(0.97);
}

.search-empty__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 20px;
}

.search-empty__primary,
.search-empty__ghost {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border-radius: var(--r-pill, 999px);
  font-size: 14px;
  cursor: pointer;
  transition:
    transform 120ms var(--ease-out, ease),
    opacity 120ms var(--ease-out, ease),
    background 120ms var(--ease-out, ease);
}

.search-empty__primary {
  border: 1px solid var(--sakura-deep, #c93a63);
  background: var(--sakura-deep, #c93a63);
  color: var(--on-accent, #fff);
}

.search-empty__primary:hover {
  background: var(--sakura-deep-hover, #b32c53);
}

.search-empty__primary:active,
.search-empty__ghost:active {
  transform: scale(0.97);
}

.search-empty__primary:disabled {
  opacity: 0.72;
  cursor: progress;
}

.search-empty__ghost {
  border: 1px solid var(--line, #f3dde5);
  background: var(--surface, #fff);
  color: var(--muted, #63474f);
}

.search-empty__ghost:hover {
  border-color: var(--sakura, #e8628c);
  color: var(--sakura-deep, #c93a63);
}

.is-spinning {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .is-spinning {
    animation: none;
  }

  .search-empty__primary,
  .search-empty__ghost,
  .search-empty__suggest-chip {
    transition: opacity 120ms linear;
  }
}

@media (max-width: 640px) {
  .search-empty {
    padding: 32px 16px;
  }

  .search-empty__title {
    font-size: 18px;
  }
}
</style>
