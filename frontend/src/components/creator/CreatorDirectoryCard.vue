<template>
  <RouterLink
    class="cd-card"
    :to="`/u/${creator.username}`"
    :aria-label="`查看创作者 ${creator.displayName}（@${creator.username}），${creator.worksCount} 件公开作品`"
  >
    <div class="cd-head">
      <span class="cd-avatar" aria-hidden="true">{{ monogram }}</span>
      <span class="cd-id">
        <span class="cd-name">{{ creator.displayName }}</span>
        <span class="cd-handle">@{{ creator.username }}</span>
      </span>
      <span class="cd-arrow" aria-hidden="true">→</span>
    </div>

    <p class="cd-stats">
      <span class="cd-stat">{{ formatNumber(creator.worksCount) }} 件作品</span>
      <span class="cd-stat-dot" aria-hidden="true">·</span>
      <span class="cd-stat">{{ formatNumber(creator.viewsTotal) }} 次浏览</span>
    </p>

    <div v-if="creator.covers.length" class="cd-covers" :aria-label="`${creator.displayName} 的最近作品封面`">
      <span
        v-for="cover in creator.covers"
        :key="cover.id"
        class="cd-cover"
        :style="coverStyle(cover)"
      >
        <img
          class="cd-cover-img"
          :src="cover.thumbUrl"
          :alt="`${creator.displayName} 的作品封面：${cover.title || '未命名作品'}`"
          loading="lazy"
          decoding="async"
        />
        <span v-if="cover.isAigc" class="cd-cover-aigc">{{ cover.aigcLabel || 'AI 生成' }}</span>
      </span>
    </div>
    <div v-else class="cd-covers cd-covers--empty" aria-hidden="true">
      <span v-for="slot in 3" :key="slot" class="cd-cover cd-cover--placeholder" />
    </div>
  </RouterLink>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { CreatorCard, CreatorCover } from '../../api/public'

const props = defineProps<{
  creator: CreatorCard
}>()

/** 头像占位：取展示名第一个字（中文取首字，英文取首字母大写） */
const monogram = computed(() => {
  const name = props.creator.displayName.trim() || props.creator.username
  const first = Array.from(name)[0] ?? '@'
  return first.toUpperCase()
})

function formatNumber(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0'
  return value.toLocaleString('zh-CN')
}

/** 封面条按真实宽高比声明，默认底色用 LQIP 主色，不裁切图片 */
function coverStyle(cover: CreatorCover): Record<string, string> {
  return {
    background: cover.lqipColor || 'var(--sakura-pale)',
    '--cd-ratio': String(cover.aspectRatio),
  }
}
</script>

<style scoped>
.cd-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--sp-5) var(--sp-5) var(--sp-4);
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
  color: inherit;
  text-decoration: none;
  transition:
    transform var(--dur) var(--ease-out),
    box-shadow var(--dur) var(--ease-out),
    border-color var(--dur) var(--ease-out);
}

.cd-card:hover {
  border-color: var(--sakura-pale);
  box-shadow: var(--shadow-lift);
  transform: translateY(-3px);
}

.cd-card:focus-visible {
  outline: 3px solid var(--focus-ring);
  outline-offset: 3px;
}

.cd-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  min-width: 0;
}

.cd-avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: linear-gradient(140deg, var(--sakura-pale), var(--spring-pale));
  color: var(--sakura-deep);
  font-family: var(--display);
  font-size: 24px;
  line-height: 1;
}

.cd-id {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.cd-name {
  overflow: hidden;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cd-handle {
  overflow: hidden;
  color: var(--muted);
  font-size: var(--fs-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cd-arrow {
  margin-left: auto;
  color: var(--faint);
  font-size: 18px;
  transition:
    color var(--dur) var(--ease-out),
    transform var(--dur) var(--ease-out);
}

.cd-card:hover .cd-arrow {
  color: var(--sakura-deep);
  transform: translateX(3px);
}

.cd-stats {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: var(--sp-4) 0 var(--sp-4);
  color: var(--muted);
  font-size: var(--fs-sm);
}

.cd-stat-dot {
  color: var(--faint);
}

.cd-covers {
  display: flex;
  gap: 8px;
  height: 96px;
  margin-top: auto;
}

.cd-cover {
  position: relative;
  display: grid;
  flex: 0 1 auto;
  place-items: center;
  width: auto;
  min-width: 0;
  max-width: 34%;
  height: 100%;
  overflow: hidden;
  border-radius: var(--r-photo);
  aspect-ratio: var(--cd-ratio, 4 / 3);
}

.cd-cover-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.cd-cover-aigc {
  position: absolute;
  top: 5px;
  left: 5px;
  padding: 1px 6px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.86);
  color: var(--sakura-deep);
  font-size: 10px;
  line-height: 1.5;
  white-space: nowrap;
}

.cd-covers--empty {
  align-items: stretch;
}

.cd-cover--placeholder {
  flex: 1 1 0;
  max-width: none;
  background: var(--sakura-wash);
  border: 1px dashed var(--line-strong);
}

@media (max-width: 719px) {
  .cd-card {
    padding: var(--sp-4);
  }

  .cd-avatar {
    width: 46px;
    height: 46px;
    font-size: 21px;
  }

  .cd-name {
    font-size: var(--fs-body);
  }

  .cd-covers {
    height: 84px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cd-card,
  .cd-arrow {
    transition: none;
  }

  .cd-card:hover {
    transform: none;
  }

  .cd-card:hover .cd-arrow {
    transform: none;
  }
}

@media (pointer: coarse) {
  .cd-card {
    min-height: 44px;
  }
}
</style>
