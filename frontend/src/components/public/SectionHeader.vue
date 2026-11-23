<template>
  <header class="sec-head">
    <div class="sec-main">
      <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
      <div class="sec-title-row">
        <h2 :id="titleId" class="sec-title">{{ title }}</h2>
        <span v-if="count !== undefined && count !== ''" class="sec-count">{{ countText }}</span>
      </div>
      <p v-if="description" class="sec-desc">{{ description }}</p>
    </div>
    <div v-if="$slots.default || (moreTo && moreLabel)" class="sec-side">
      <slot />
      <RouterLink v-if="moreTo && moreLabel" :to="moreTo" class="link-arrow">
        {{ moreLabel }}
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M3.2 8h9.2M8.8 4.2 12.6 8l-3.8 3.8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </RouterLink>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

const props = defineProps<{
  title: string
  titleId?: string
  eyebrow?: string
  description?: string
  count?: number | string
  moreLabel?: string
  moreTo?: RouteLocationRaw
}>()

const countText = computed(() => {
  if (typeof props.count === 'number') return `${props.count} 张`
  return props.count
})
</script>

<style scoped>
.sec-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-6);
  margin-bottom: var(--sp-8);
}

.sec-main {
  min-width: 0;
}

.sec-title-row {
  display: flex;
  align-items: baseline;
  gap: var(--sp-4);
  margin-top: var(--sp-2);
}

.sec-title {
  font-size: 44px;
  line-height: var(--lh-tight);
  color: var(--ink);
}

.sec-count {
  color: var(--faint);
  font-family: var(--font);
  font-size: var(--fs-sm);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.sec-desc {
  max-width: 34em;
  margin-top: var(--sp-3);
  color: var(--muted);
  font-size: var(--fs-14);
  line-height: var(--lh-snug);
}

.sec-side {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  flex-shrink: 0;
  padding-bottom: 4px;
}

@media (max-width: 720px) {
  .sec-head {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--sp-4);
    margin-bottom: var(--sp-6);
  }

  .sec-side {
    width: 100%;
    min-width: 0;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--sp-3);
    padding-bottom: 0;
  }

  .sec-side :deep(.topic-row) {
    width: 100%;
    min-width: 0;
  }
}
@media (max-width: 900px) {
  .sec-title {
    /* 站酷庆科黄油体只在 ≥44px 使用，小屏标题回退正文黑体 */
    font-family: var(--font);
    font-size: 32px;
    font-weight: 700;
    letter-spacing: 0;
  }
}

</style>
