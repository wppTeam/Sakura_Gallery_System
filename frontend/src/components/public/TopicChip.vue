<template>
  <button
    type="button"
    class="topic-chip"
    :class="[season ? `topic-chip--${season}` : 'topic-chip--all', { 'is-active': active }]"
    :aria-pressed="active"
    @click="emit('select')"
  >
    <span v-if="season" class="chip-dot" aria-hidden="true" />
    {{ label }}
    <span v-if="count !== undefined" class="chip-count">{{ count }}</span>
  </button>
</template>

<script setup lang="ts">
import type { SeasonKey } from '../../constants/public'

defineProps<{
  label: string
  active?: boolean
  /** 传入季节 key 时使用该季淡底 + 强调色 */
  season?: SeasonKey | null
  count?: number
}>()

const emit = defineEmits<{ (e: 'select'): void }>()
</script>

<style scoped>
.topic-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 40px;
  padding: 0 18px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--muted);
  font-size: var(--fs-14);
  font-weight: 500;
  white-space: nowrap;
  transition: transform var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out);
}

.topic-chip:hover {
  border-color: var(--chip-accent, var(--sakura));
  color: var(--ink);
}

.topic-chip--all {
  --chip-accent: var(--sakura);
  --chip-pale: var(--sakura-pale);
}

.topic-chip--spring {
  --chip-accent: var(--spring);
  --chip-pale: var(--spring-pale);
}

.topic-chip--summer {
  --chip-accent: var(--summer);
  --chip-pale: var(--summer-pale);
}

.topic-chip--autumn {
  --chip-accent: var(--autumn);
  --chip-pale: var(--autumn-pale);
}

.topic-chip--winter {
  --chip-accent: var(--winter);
  --chip-pale: var(--winter-pale);
}

.chip-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--chip-accent);
  opacity: 0.85;
}

.topic-chip.is-active {
  border-color: var(--chip-accent);
  background: var(--chip-pale);
  color: var(--ink);
}

.topic-chip--all.is-active {
  border-color: var(--sakura-deep);
  background: var(--sakura-deep);
  color: var(--on-accent);
}

.topic-chip--all.is-active .chip-dot {
  background: var(--on-accent);
}

.chip-count {
  color: var(--faint);
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
}

.topic-chip--all.is-active .chip-count {
  color: rgba(255, 255, 255, 0.78);
}

.topic-chip:active {
  transform: scale(0.98);
}
</style>
