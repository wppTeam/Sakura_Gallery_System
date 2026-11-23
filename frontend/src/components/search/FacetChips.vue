<script setup lang="ts">
import { computed } from 'vue'
import { NIcon } from 'naive-ui'
import { CloseOutline, FunnelOutline } from '@vicons/ionicons5'
import type { FacetValue, SearchFacets } from '../../api/search'

type FacetKey = 'season' | 'category' | 'campus'

const props = withDefaults(
  defineProps<{
    facets: SearchFacets
    season?: string
    category?: string
    campus?: string
    loading?: boolean
  }>(),
  { season: '', category: '', campus: '', loading: false },
)

const emit = defineEmits<{
  (e: 'update:season', value: string): void
  (e: 'update:category', value: string): void
  (e: 'update:campus', value: string): void
  (e: 'clear'): void
}>()

const groups = computed<Array<{ key: FacetKey; label: string; items: FacetValue[] }>>(() => [
  { key: 'season', label: '季节', items: props.facets.season },
  { key: 'category', label: '类别', items: props.facets.category },
  { key: 'campus', label: '校区', items: props.facets.campus },
])

function activeValue(key: FacetKey): string {
  if (key === 'season') return props.season || ''
  if (key === 'category') return props.category || ''
  return props.campus || ''
}

function facetValueLabel(item: FacetValue): string {
  return item.label?.trim() || item.value
}

function pick(key: FacetKey, value: string) {
  if (key === 'season') emit('update:season', value)
  else if (key === 'category') emit('update:category', value)
  else emit('update:campus', value)
}

const hasActive = computed(() => Boolean(props.season || props.category || props.campus))
</script>

<template>
  <section v-if="facets.season.length || facets.category.length || facets.campus.length" class="facet-chips">
    <div class="facet-head">
      <span class="facet-title">
        <n-icon :component="FunnelOutline" :size="14" />
        筛选
      </span>
      <button v-if="hasActive" class="facet-clear" type="button" @click="emit('clear')">
        <n-icon :component="CloseOutline" :size="12" />
        清除筛选
      </button>
    </div>

    <div
      v-for="group in groups"
      v-show="group.items.length"
      :key="group.key"
      class="facet-row"
    >
      <span class="facet-label">{{ group.label }}</span>
      <div class="facet-values">
        <button
          v-for="item in group.items"
          :key="`${group.key}-${item.value}`"
          type="button"
          class="facet-chip"
          :class="{ 'is-active': activeValue(group.key) === item.value }"
          :aria-pressed="activeValue(group.key) === item.value"
          @click="pick(group.key, item.value)"
        >
          {{ facetValueLabel(item) }}
          <span v-if="item.count > 0" class="facet-count">{{ item.count }}</span>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.facet-chips {
  margin: 20px 0 0;
  padding: 16px 18px;
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-card, 20px);
  box-shadow: 0 2px 10px rgba(201, 58, 99, 0.04);
}

.facet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.facet-title {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
}

.facet-clear {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 9px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-pill, 999px);
  background: var(--surface-warm, #fff9fb);
  color: var(--muted, #63474f);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--dur-fast, 160ms) var(--ease-out, ease);
}

.facet-clear:hover {
  border-color: var(--sakura, #e8628c);
  color: var(--sakura-deep, #c93a63);
}

.facet-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 6px 0;
}

.facet-row + .facet-row {
  border-top: 1px dashed var(--line, #f3dde5);
}

.facet-label {
  flex: none;
  width: 3em;
  padding-top: 5px;
  font-size: 12px;
  color: var(--faint, #947881);
  letter-spacing: 0.08em;
}

.facet-values {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.facet-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: 1px solid var(--line, #f3dde5);
  border-radius: var(--r-pill, 999px);
  background: var(--surface-warm, #fff9fb);
  color: var(--muted, #63474f);
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
  transition:
    background var(--dur-fast, 160ms) var(--ease-out, ease),
    color var(--dur-fast, 160ms) var(--ease-out, ease),
    border-color var(--dur-fast, 160ms) var(--ease-out, ease);
}

.facet-chip:hover {
  border-color: var(--sakura, #e8628c);
  color: var(--sakura-deep, #c93a63);
}

.facet-chip.is-active {
  background: var(--sakura, #e8628c);
  border-color: var(--sakura, #e8628c);
  color: var(--on-accent, #fff);
}

.facet-count {
  font-size: 11px;
  opacity: 0.72;
}

@media (max-width: 640px) {
  .facet-chips {
    padding: 13px 14px;
    border-radius: var(--r-md, 14px);
  }

  .facet-row {
    flex-direction: column;
    gap: 7px;
  }

  .facet-label {
    width: auto;
    padding-top: 0;
  }

  .facet-chip {
    font-size: 12px;
    padding: 5px 10px;
  }
}
</style>
