<template>
  <div class="empty-state" :class="{ 'empty-state--error': error }">
    <div class="empty-mark" aria-hidden="true">
      <slot name="icon">
        <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
          <circle cx="32" cy="32" r="30" fill="var(--sakura-pale)" />
          <g transform="translate(32 32)">
            <path
              v-for="(rotate, index) in [0, 72, 144, 216, 288]"
              :key="rotate"
              d="M0 -3.2c5.6 -6.2 6.2 -12.2 0 -15.4-6.2 3.2-5.6 9.2 0 15.4Z"
              :transform="`rotate(${rotate})`"
              fill="var(--sakura)"
              opacity="0.65"
              :style="{ opacity: error ? 0.4 : 0.55 + index * 0.05 }"
            />
            <circle r="3.1" fill="var(--sakura-deep)" />
          </g>
        </svg>
      </slot>
    </div>
    <h3 class="empty-title">{{ title }}</h3>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <div v-if="$slots.default || actionLabel" class="empty-actions">
      <slot>
        <button v-if="actionLabel" type="button" class="btn btn--primary" @click="emit('action')">
          {{ actionLabel }}
        </button>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
  actionLabel?: string
  error?: boolean
}>()

const emit = defineEmits<{ (e: 'action'): void }>()
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: clamp(48px, 8vw, 96px) var(--sp-6);
  text-align: center;
}

.empty-mark {
  margin-bottom: var(--sp-5);
}

.empty-title {
  font-size: var(--fs-h3);
  color: var(--ink);
}

.empty-desc {
  max-width: 26em;
  margin-top: var(--sp-3);
  color: var(--muted);
  font-size: var(--fs-14);
  line-height: var(--lh-snug);
}

.empty-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--sp-3);
  margin-top: var(--sp-6);
}

.empty-state--error .empty-title {
  color: var(--sakura-deep);
}
</style>
