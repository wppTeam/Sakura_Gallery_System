<template>
  <section class="auto-tag-card" aria-label="AI 打标建议">
    <header class="at-head">
      <div class="at-heading">
        <span class="at-index" aria-hidden="true">
          <n-icon :size="13"><PricetagsOutline /></n-icon>
        </span>
        <div>
          <h3 class="at-title">AI 打标建议</h3>
          <p class="at-sub">同一次快筛产出 · 写入作品标签与分类</p>
        </div>
      </div>
      <n-tag size="small" :type="status.tone" :bordered="false" :title="status.hint">
        {{ status.label }}
      </n-tag>
    </header>

    <p v-if="suggestion.caption" class="at-caption">{{ suggestion.caption }}</p>

    <div v-if="appliedTags.length" class="at-group">
      <p class="at-label">
        已写入标签
        <span class="at-count">· {{ appliedTags.length }} 个</span>
      </p>
      <div class="at-chips">
        <span v-for="tag in appliedTags" :key="`applied-${tag}`" class="at-chip is-applied">{{ tag }}</span>
      </div>
    </div>

    <div v-if="rawOnlyTags.length" class="at-group">
      <p class="at-label">
        {{ rawGroupLabel }}
        <span class="at-count">· {{ rawGroupHint }}</span>
      </p>
      <div class="at-chips">
        <span
          v-for="tag in rawOnlyTags"
          :key="`raw-${tag}`"
          class="at-chip is-raw"
          :title="`模型原始建议：${tag}`"
        >{{ tag }}</span>
      </div>
    </div>

    <div v-if="facetList.length" class="at-group">
      <p class="at-label">
        {{ suggestion.applied === true ? '已写入分类' : '建议分类' }}
        <span class="at-count">· {{ facetList.length }} 项</span>
      </p>
      <dl class="at-facets">
        <div v-for="row in facetList" :key="row.key" class="at-facet">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.value }}</dd>
        </div>
      </dl>
    </div>

    <p v-if="suggestion.error" class="at-warn">打标失败：{{ suggestion.error }}</p>

    <p v-if="suggestion.applied === true" class="at-note">
      这些标签与分类已随审核写入作品，可在作品详情页核对实际效果；如需增删请到作品管理页处理。
    </p>
    <p v-else-if="suggestion.applied === false" class="at-note">
      本次审核没有新增标签或分类（作品此前已有则幂等跳过，不影响审核结论）；下列为本次模型输出与实际命中的分类。
    </p>
    <p v-else class="at-note">老审核记录仅有快筛建议，未记录是否写入作品。</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { PricetagsOutline } from '@vicons/ionicons5'
import type { AutoTaggingSuggestion } from '../../api/moderation'
import { autoTaggingStatus, facetRows } from './reviewDisplay'

const props = defineProps<{
  suggestion: AutoTaggingSuggestion
}>()

const status = computed(() => autoTaggingStatus(props.suggestion))

const appliedTags = computed(() => props.suggestion.tags || [])

/** 模型建议里没有被实际写入的标签（去重 + 排除已写入项） */
const rawOnlyTags = computed(() => {
  const applied = new Set(appliedTags.value)
  const raw = props.suggestion.requestedTags || []
  const seen = new Set<string>()
  return raw.filter((tag) => {
    if (!tag || applied.has(tag) || seen.has(tag)) return false
    seen.add(tag)
    return true
  })
})

const facetList = computed(() => facetRows(props.suggestion.facets))

const rawGroupLabel = computed(() =>
  appliedTags.value.length ? '模型原始建议' : '模型建议标签',
)

const rawGroupHint = computed(() => {
  if (appliedTags.value.length) return '未写入 / 未通过清洗'
  if (props.suggestion.applied === false && !props.suggestion.error) return '本次未新增写入'
  return '未写入作品'
})
</script>

<style scoped>
.auto-tag-card {
  margin-top: 12px;
  padding: 13px 14px;
  border: 1px dashed var(--line-strong, #e7c6d2);
  border-radius: var(--r-md, 14px);
  background: var(--surface, #fff);
}

.at-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.at-heading {
  display: flex;
  gap: 8px;
  min-width: 0;
}

.at-index {
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: var(--sakura-deep, #c93a63);
  background: var(--sakura-pale, #ffe9f0);
}

.at-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--ink, #4a2b35);
  line-height: 1.4;
}

.at-sub {
  margin: 1px 0 0;
  font-size: 11px;
  color: var(--faint, #97808a);
}

.at-caption {
  margin: 11px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--muted, #63474f);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.at-group {
  margin-top: 11px;
}

.at-label {
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted, #63474f);
}

.at-count {
  font-weight: 400;
  color: var(--faint, #97808a);
}

.at-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.at-chip {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 9px;
  border-radius: var(--r-pill, 999px);
  font-size: 11.5px;
  line-height: 1;
  white-space: nowrap;
}

.at-chip.is-applied {
  color: var(--sakura-deep, #c93a63);
  background: var(--sakura-wash, #fff0f5);
  border: 1px solid var(--sakura-pale, #ffe9f0);
}

.at-chip.is-raw {
  color: var(--muted, #63474f);
  background: var(--ground, #fff6f9);
  border: 1px dashed var(--line-strong, #e7c6d2);
}

.at-facets {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 16px;
  margin: 0;
}

.at-facet {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 8px;
  border-radius: var(--r-sm, 10px);
  background: var(--ground, #fff6f9);
}

.at-facet dt {
  flex: none;
  font-size: 11px;
  color: var(--faint, #97808a);
}

.at-facet dd {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink, #4a2b35);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.at-warn {
  margin: 9px 0 0;
  padding: 6px 9px;
  border-radius: var(--r-sm, 10px);
  font-size: 11.5px;
  line-height: 1.6;
  color: #b5703c;
  background: var(--autumn-pale, #ffdfd6);
}

.at-note {
  margin: 9px 0 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--faint, #97808a);
}

@media (max-width: 560px) {
  .at-facets {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
