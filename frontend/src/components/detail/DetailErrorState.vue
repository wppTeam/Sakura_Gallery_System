<template>
  <div class="error-state">
    <div class="error-illustration" aria-hidden="true">
      <n-icon :component="iconComponent" :size="30" />
    </div>
    <h1 class="error-title">{{ title }}</h1>
    <p class="error-text">{{ message }}</p>
    <div class="error-actions">
      <button type="button" class="error-primary" :disabled="retrying" @click="$emit('retry')">
        <n-icon :component="RefreshOutline" :size="16" />
        {{ retrying ? '重新加载中…' : '重新加载' }}
      </button>
      <router-link class="error-secondary" to="/gallery">返回作品广场</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NIcon } from 'naive-ui'
import { AlertCircleOutline, CloudOfflineOutline, ImageOutline, RefreshOutline } from '@vicons/ionicons5'

const props = withDefaults(
  defineProps<{
    title?: string
    message: string
    tone?: 'not-found' | 'network' | 'error'
    retrying?: boolean
  }>(),
  { title: '作品加载失败', tone: 'error', retrying: false },
)

defineEmits<{ retry: [] }>()

const iconComponent = computed(() => {
  if (props.tone === 'not-found') return ImageOutline
  if (props.tone === 'network') return CloudOfflineOutline
  return AlertCircleOutline
})
</script>

<style scoped>
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 72px 24px;
  text-align: center;
  border-radius: var(--r-card, 20px);
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
}

.error-illustration {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  color: var(--sakura, #e8628c);
  background: var(--sakura-pale, #ffe9f0);
}

.error-title {
  margin: 4px 0 0;
  font-family: var(--display, 'Noto Sans SC', sans-serif);
  font-size: 20px;
  color: var(--ink, #4a2b35);
}

.error-text {
  margin: 0;
  max-width: 26em;
  font-size: 13.5px;
  line-height: 1.85;
  color: var(--muted, #63474f);
}

.error-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  flex-wrap: wrap;
  justify-content: center;
}

.error-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 20px;
  border: 0;
  border-radius: 999px;
  font-size: 13.5px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, var(--sakura, #e8628c), var(--sakura-deep, #c93a63));
  cursor: pointer;
}

.error-primary:disabled {
  opacity: 0.7;
  cursor: progress;
}

.error-secondary {
  font-size: 13.5px;
  color: var(--sakura-deep, #c93a63);
  text-decoration: none;
}

.error-secondary:hover {
  text-decoration: underline;
}

@media (max-width: 480px) {
  .error-state {
    padding: 48px 16px;
  }

  .error-actions {
    flex-direction: column;
    width: 100%;
  }

  .error-primary {
    justify-content: center;
    width: 100%;
  }
}
</style>
