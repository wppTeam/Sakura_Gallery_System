<template>
  <div class="detail-skeleton" aria-busy="true" aria-label="作品加载中">
    <div class="skeleton-stage shimmer" />
    <div class="skeleton-side">
      <div class="skeleton-tags">
        <span class="skeleton-chip shimmer" />
        <span class="skeleton-chip shimmer" />
      </div>
      <div class="skeleton-title shimmer" />
      <div class="skeleton-title skeleton-title-short shimmer" />
      <div class="skeleton-line shimmer" />
      <div class="skeleton-line skeleton-line-short shimmer" />
      <div class="skeleton-actions">
        <span class="skeleton-btn shimmer" />
        <span class="skeleton-btn shimmer" />
      </div>
      <div class="skeleton-block">
        <div class="skeleton-line shimmer" />
        <div class="skeleton-line shimmer" />
        <div class="skeleton-line skeleton-line-short shimmer" />
      </div>
      <div class="skeleton-block">
        <div class="skeleton-line shimmer" />
        <div class="skeleton-line shimmer" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 纯展示骨架屏：尺寸与真实详情页布局对齐，减少加载后的跳动
</script>

<style scoped>
.detail-skeleton {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  gap: 28px;
  align-items: start;
}

.shimmer {
  background: linear-gradient(90deg, #fbeaf1 25%, #fff6f9 37%, #fbeaf1 63%);
  background-size: 400% 100%;
  animation: shimmer-move 1.5s ease infinite;
}

@keyframes shimmer-move {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}

.skeleton-stage {
  width: 100%;
  aspect-ratio: 3 / 2;
  border-radius: var(--r-card, 20px);
}

.skeleton-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 26px;
  border-radius: var(--r-card, 20px);
  background: var(--surface, #fff);
  border: 1px solid var(--line, #f3dde5);
}

.skeleton-tags {
  display: flex;
  gap: 8px;
}

.skeleton-chip {
  width: 72px;
  height: 22px;
  border-radius: 999px;
}

.skeleton-title {
  height: 30px;
  border-radius: 8px;
  width: 92%;
}

.skeleton-title-short {
  width: 64%;
  height: 24px;
}

.skeleton-line {
  height: 13px;
  border-radius: 6px;
  width: 100%;
}

.skeleton-line-short {
  width: 55%;
}

.skeleton-actions {
  display: flex;
  gap: 10px;
  padding: 12px 0;
  margin: 4px 0;
  border-top: 1px solid var(--line, #f3dde5);
  border-bottom: 1px solid var(--line, #f3dde5);
}

.skeleton-btn {
  width: 110px;
  height: 38px;
  border-radius: 999px;
}

.skeleton-block {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding-top: 8px;
  border-top: 1px dashed var(--line, #f3dde5);
}

@media (max-width: 1024px) {
  .detail-skeleton {
    grid-template-columns: 1fr;
  }
}
</style>
