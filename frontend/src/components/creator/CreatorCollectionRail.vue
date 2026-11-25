<template>
  <section class="ccr" aria-labelledby="ccr-title">
    <div class="ccr-head">
      <div>
        <p class="eyebrow">COLLECTIONS</p>
        <h2 id="ccr-title" class="ccr-title">作品集</h2>
      </div>
      <p class="ccr-count">共 {{ collections.length }} 个</p>
    </div>

    <ul class="ccr-rail" role="list">
      <li v-for="item in collections" :key="item.slug" class="ccr-item">
        <router-link
          class="ccr-card"
          :to="`/collections/${item.slug}`"
          :aria-label="`查看作品集《${item.title}》，${item.photoCount} 张作品`"
        >
          <figure class="ccr-cover">
            <img
              v-if="coverSrc(item)"
              class="ccr-cover-img"
              :src="coverSrc(item)"
              :alt="`《${item.title}》封面`"
              loading="lazy"
              decoding="async"
            />
            <span v-else class="ccr-cover-fallback" aria-hidden="true">
              {{ firstChar(item.title) }}
            </span>
            <span class="ccr-cover-count">{{ item.photoCount }} 张</span>
          </figure>
          <div class="ccr-body">
            <p class="ccr-card-title">{{ item.title }}</p>
            <p v-if="item.subtitle" class="ccr-card-sub">{{ item.subtitle }}</p>
          </div>
        </router-link>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import type { CreatorCollection } from '../../api/public'

defineProps<{
  collections: CreatorCollection[]
}>()

function coverSrc(item: CreatorCollection): string {
  return item.cover?.thumbUrl || item.cover?.imageUrl || ''
}

function firstChar(title: string): string {
  return Array.from(title.trim())[0] ?? '集'
}
</script>

<style scoped>
.ccr {
  margin-top: var(--sp-16);
}

.ccr-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-4);
  margin-bottom: var(--sp-5);
}

.ccr-title {
  margin: 6px 0 0;
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(28px, 3.2vw, 40px);
  font-weight: 400;
  line-height: 1.15;
  letter-spacing: 0.02em;
}

.ccr-count {
  margin: 0;
  color: var(--faint);
  font-size: var(--fs-sm);
  font-variant-numeric: tabular-nums;
}

.ccr-rail {
  display: flex;
  gap: var(--gap);
  margin: 0 calc(-1 * var(--margin)) 0 0;
  padding: 2px var(--margin) 8px 0;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scroll-snap-type: x proximity;
  scrollbar-width: none;
}

.ccr-rail::-webkit-scrollbar {
  display: none;
}

.ccr-item {
  flex: 0 0 264px;
  scroll-snap-align: start;
}

.ccr-card {
  display: block;
  height: 100%;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-card);
  color: inherit;
  text-decoration: none;
  transition:
    border-color var(--dur-base, 200ms) var(--ease-out, ease),
    box-shadow var(--dur-base, 200ms) var(--ease-out, ease);
}

.ccr-card:hover {
  border-color: var(--line-strong);
  box-shadow: var(--shadow-lift);
}

.ccr-card:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: 3px;
}

.ccr-cover {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 4 / 3;
  margin: 0;
  overflow: hidden;
  background: var(--sakura-mist);
}

.ccr-cover-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  transition: transform var(--dur-base, 200ms) var(--ease-out, ease);
}

.ccr-card:hover .ccr-cover-img {
  transform: scale(1.015);
}

.ccr-cover-fallback {
  color: var(--sakura);
  font-family: var(--display);
  font-size: 64px;
  line-height: 1;
  opacity: 0.6;
}

.ccr-cover-count {
  position: absolute;
  right: 10px;
  bottom: 10px;
  padding: 3px 10px;
  border-radius: var(--r-pill);
  background: rgba(255, 246, 249, 0.9);
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.ccr-body {
  padding: var(--sp-4) var(--sp-5) var(--sp-5);
}

.ccr-card-title {
  margin: 0;
  color: var(--ink);
  font-size: var(--fs-16);
  font-weight: 600;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ccr-card-sub {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: var(--fs-sm);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (max-width: 719px) {
  .ccr {
    margin-top: var(--sp-12);
  }

  .ccr-item {
    flex-basis: 220px;
  }

  .ccr-card-title {
    font-size: var(--fs-sm);
  }

  .ccr-cover-count {
    right: 8px;
    bottom: 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ccr-card,
  .ccr-cover-img {
    transition: none;
  }

  .ccr-card:hover .ccr-cover-img {
    transform: none;
  }
}
</style>
