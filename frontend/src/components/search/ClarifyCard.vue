<script setup lang="ts">
import { NIcon } from 'naive-ui'
import { ChatbubbleEllipsesOutline, SparklesOutline } from '@vicons/ionicons5'

defineProps<{
  question: string
  options: string[]
  /** 结果非空时弱化为「继续缩小范围」，避免用户误以为检索失败 */
  hasResults?: boolean
}>()

const emit = defineEmits<{ (e: 'pick', value: string): void }>()
</script>

<template>
  <section class="clarify-card" aria-label="Agent 澄清追问">
    <div class="clarify-icon">
      <n-icon :component="ChatbubbleEllipsesOutline" :size="20" />
    </div>
    <div class="clarify-body">
      <p class="clarify-label">
        <n-icon :component="SparklesOutline" :size="13" />
        {{ hasResults ? '结果已出，继续缩小范围？' : 'Agent 想先确认一下' }}
      </p>
      <p class="clarify-question">{{ question }}</p>
      <div v-if="options.length" class="clarify-options">
        <button
          v-for="option in options"
          :key="option"
          type="button"
          class="clarify-option"
          @click="emit('pick', option)"
        >
          {{ option }}
        </button>
      </div>
      <p class="clarify-hint">
        {{ hasResults ? '不是搜索失败——点选下面的方向可以筛得更准，也可以直接改关键词。' : '也可以直接修改上方关键词后重新检索。' }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.clarify-card {
  display: flex;
  gap: 12px;
  margin: 16px 0 0;
  padding: 16px 18px;
  border-radius: var(--r-card, 20px);
  border: 1px solid var(--line, #f3dde5);
  background:
    radial-gradient(120% 140% at 0% 0%, var(--sakura-mist, #fff2f7) 0%, transparent 62%),
    var(--surface, #fff);
  box-shadow: 0 2px 10px rgba(201, 58, 99, 0.05);
}

.clarify-icon {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--sakura-pale, #ffe9f0);
  color: var(--sakura-deep, #c93a63);
}

.clarify-body {
  min-width: 0;
  flex: 1;
}

.clarify-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--sakura-deep, #c93a63);
}

.clarify-question {
  margin: 5px 0 0;
  font-size: 15px;
  font-weight: 500;
  color: var(--ink, #4a2b35);
  line-height: 1.6;
}

.clarify-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 11px;
}

.clarify-option {
  padding: 6px 13px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-pill, 999px);
  background: var(--surface, #fff);
  color: var(--ink-soft, #563842);
  font-size: 13px;
  cursor: pointer;
  transition:
    transform 120ms var(--ease-out, ease),
    background 120ms var(--ease-out, ease),
    border-color 120ms var(--ease-out, ease);
}

.clarify-option:hover {
  border-color: var(--sakura, #e8628c);
  color: var(--sakura-deep, #c93a63);
}

.clarify-option:active {
  transform: scale(0.97);
}

.clarify-hint {
  margin: 10px 0 0;
  font-size: 11px;
  color: var(--faint, #947881);
}

@media (max-width: 640px) {
  .clarify-card {
    padding: 14px;
  }

  .clarify-icon {
    width: 32px;
    height: 32px;
  }
}
</style>
