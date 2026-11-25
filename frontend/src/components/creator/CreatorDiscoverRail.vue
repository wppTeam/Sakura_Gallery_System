<template>
  <section
    v-if="creators.length"
    id="creators"
    class="section cdr-section"
    aria-labelledby="cdr-title"
  >
    <div class="wrap">
      <SectionHeader
        title-id="cdr-title"
        eyebrow="DISCOVER CREATORS"
        title="发现创作者"
        description="顺着一位作者的镜头看下去——他们把校园的光与花，一张一张留在这里。"
        more-label="查看全部"
        more-to="/creators"
      />

      <ul class="cdr-rail" aria-label="创作者">
        <li v-for="creator in creators" :key="creator.username" class="cdr-cell">
          <RouterLink
            class="cdr-card"
            :to="`/u/${creator.username}`"
            :aria-label="`查看创作者 ${creator.displayName}，${creator.worksCount} 件公开作品`"
          >
            <span class="cdr-avatar" aria-hidden="true">{{ monogram(creator.displayName) }}</span>
            <span class="cdr-body">
              <span class="cdr-name">{{ creator.displayName }}</span>
              <span class="cdr-meta">@{{ creator.username }} · {{ creator.worksCount }} 件</span>
            </span>
          </RouterLink>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchCreators, type CreatorCard } from '../../api/public'
import SectionHeader from '../public/SectionHeader.vue'

const creators = ref<CreatorCard[]>([])

function monogram(name: string): string {
  const first = Array.from((name || '').trim())[0]
  return first ? first.toUpperCase() : '@'
}

onMounted(async () => {
  const page = await fetchCreators({ sort: 'works', limit: 6 })
  // 接口失败或没有创作者时整块不渲染，不留空壳
  creators.value = page.error ? [] : page.items.slice(0, 6)
})
</script>

<style scoped>
.cdr-section {
  overflow: hidden;
}

.cdr-rail {
  display: grid;
  grid-auto-columns: minmax(0, 1fr);
  grid-auto-flow: column;
  gap: 12px;
  margin: 0;
  padding: 4px 2px 8px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  list-style: none;
  scrollbar-width: thin;
}

.cdr-cell {
  min-width: 0;
  scroll-snap-align: start;
}

.cdr-card {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 76px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
  color: inherit;
  text-decoration: none;
  transition:
    border-color var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}

.cdr-card:hover {
  border-color: var(--sakura-pale);
  box-shadow: var(--shadow-lift);
}

.cdr-card:focus-visible {
  outline: 3px solid var(--focus-ring);
  outline-offset: 3px;
}

.cdr-avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: linear-gradient(140deg, var(--sakura-pale), var(--spring-pale));
  color: var(--sakura-deep);
  font-family: var(--display);
  font-size: 21px;
  line-height: 1;
}

.cdr-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.cdr-name {
  overflow: hidden;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cdr-meta {
  overflow: hidden;
  color: var(--muted);
  font-size: var(--fs-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 899px) {
  .cdr-rail {
    grid-auto-columns: minmax(220px, 1fr);
  }
}

@media (max-width: 560px) {
  .cdr-rail {
    grid-auto-columns: minmax(200px, 78vw);
    padding-bottom: 6px;
  }

  .cdr-card {
    min-height: 72px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cdr-card {
    transition: none;
  }
}

@media (pointer: coarse) {
  .cdr-card {
    min-height: 44px;
  }
}
</style>
