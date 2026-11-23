<template>
  <div class="sk-card" :class="{ 'sk-card--bare': !showCaption }" aria-hidden="true">
    <div class="sk-thumb" :style="{ aspectRatio: String(aspectRatio) }" />
    <template v-if="showCaption">
      <div class="sk-line sk-line--title" />
      <div class="sk-line sk-line--meta" />
    </template>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 宽 / 高 */
    aspectRatio?: number
    showCaption?: boolean
  }>(),
  { aspectRatio: 4 / 3, showCaption: true },
)
</script>

<style scoped>
.sk-card {
  overflow: hidden;
  border: 1px solid rgba(243, 221, 229, 0.7);
  border-radius: var(--r-card);
  background: var(--surface);
  padding: 10px 10px 14px;
}

.sk-thumb {
  position: relative;
  overflow: hidden;
  width: 100%;
  border-radius: var(--r-photo);
  background: var(--sakura-mist);
}

.sk-thumb::after {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--surface);
  animation: ph-pulse 1.7s var(--ease-soft) infinite;
}

.sk-line {
  position: relative;
  height: 10px;
  margin-top: 12px;
  overflow: hidden;
  border-radius: 5px;
  background: var(--sakura-mist);
}

.sk-line::after {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--surface);
  animation: ph-pulse 1.7s var(--ease-soft) infinite;
}

.sk-line--title {
  width: 62%;
}

.sk-line--meta {
  width: 38%;
  height: 8px;
  margin-top: 9px;
  opacity: 0.7;
}

.sk-card--bare {
  padding: 0;
  border: 0;
  background: transparent;
}

.sk-card--bare .sk-thumb {
  border-radius: var(--r-photo);
}
</style>
