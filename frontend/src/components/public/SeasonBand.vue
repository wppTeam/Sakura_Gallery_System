<template>
  <section
    class="season-band"
    :class="[`season-band--${season.key}`, { 'season-band--flip': flip }]"
    :aria-labelledby="headingId"
  >
    <div class="wrap band-inner">
      <div class="band-copy">
        <p class="eyebrow band-eyebrow">
          <span class="band-index">{{ String(index).padStart(2, '0') }}</span>
          SEASON · {{ season.en }}
        </p>

        <h2 :id="headingId" class="band-heading">
          <span class="band-char">{{ season.char }}</span>
          <span class="band-title">{{ copy.title }}</span>
        </h2>

        <p class="band-lead">{{ copy.lead }}</p>

        <ul class="term-list" :aria-label="`${season.label}的六个节气`">
          <li
            v-for="term in season.terms"
            :key="term"
            class="term"
            :class="{ 'is-now': term === nowTermName }"
          >
            {{ term }}
            <span v-if="term === nowTermName" class="term-now">此刻</span>
          </li>
        </ul>

        <p v-if="season.key === 'spring'" class="bloom-line">
          <span class="bloom-label">花信</span>
          <span class="bloom-text">{{ bloomLine(5) }}</span>
        </p>

        <figure class="band-art">
          <img
            :src="`/art/${season.key}.webp`"
            :alt="`${season.label}季相插画：${copy.title}`"
            width="1472"
            height="1140"
            loading="lazy"
            decoding="async"
          />
          <figcaption>季相插画 · AI 生成</figcaption>
        </figure>

        <RouterLink
          class="link-arrow band-link"
          :to="{ path: '/explore', query: { season: season.label } }"
        >
          看{{ season.label }}的作品
          <span v-if="count" class="band-count">{{ count }}</span>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M3 8h9M8.5 3.8 12.7 8l-4.2 4.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </RouterLink>
      </div>

      <div class="band-feed">
        <MasonryGrid
          v-if="photos.length || loading"
          :items="photos"
          :loading="loading"
          :max-columns="2"
          :skeleton-rows="2"
          variant="compact"
        />
        <div v-else class="band-empty">
          <EmptyState
            :title="`${season.label}还没有作品`"
            description="这一季的光正等着被拍下来。"
            action-label="去投稿"
            @action="$router.push('/upload')"
          />
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PublicPhoto } from '../../api/public'
import { bloomLine, currentTerm, type SeasonMeta } from '../../constants/public'
import EmptyState from './EmptyState.vue'
import MasonryGrid from './MasonryGrid.vue'

const props = withDefaults(
  defineProps<{
    season: SeasonMeta
    index: number
    photos: PublicPhoto[]
    count?: number
    loading?: boolean
    /** 偶数块可左右翻转，形成编辑式节奏 */
    flip?: boolean
  }>(),
  { count: 0, loading: false, flip: false },
)

const headingId = computed(() => `season-${props.season.key}`)
const nowTermName = computed(() => {
  const term = currentTerm()
  return term.season === props.season.key ? term.name : ''
})

/** 每季一句编辑文案：来自项目四季主题，不是演示数据 */
const COPY: Record<SeasonMeta['key'], { title: string; lead: string }> = {
  spring: {
    title: '春日迟迟',
    lead: '三月到五月，花信一枝接一枝。玉兰先白，樱花后粉，校园从第一朵花开始热闹。',
  },
  summer: {
    title: '夏木阴阴',
    lead: '镜湖的荷风穿过长廊，树影把正午拉得很长。这是一年里绿色最浓的两个月。',
  },
  autumn: {
    title: '秋水长天',
    lead: '银杏落满小路，晚霞把教学楼染成金色。秋天的北化，适合把光留住。',
  },
  winter: {
    title: '初雪覆顶',
    lead: '第一场雪落下，红墙、枯枝与脚印都安静下来。冬天的校园只剩轮廓与呼吸。',
  },
}

const copy = computed(() => COPY[props.season.key])
</script>

<style scoped>
.season-band {
  --band-pale: var(--spring-pale);
  --band-accent: var(--spring);
  position: relative;
  padding-block: clamp(52px, 6vw, 88px);
  background: var(--band-pale);
  color: var(--ink);
}

.season-band--spring {
  --band-pale: var(--spring-pale);
  --band-accent: var(--spring);
}

.season-band--summer {
  --band-pale: var(--summer-pale);
  --band-accent: var(--summer);
}

.season-band--autumn {
  --band-pale: var(--autumn-pale);
  --band-accent: var(--autumn);
}

.season-band--winter {
  --band-pale: var(--winter-pale);
  --band-accent: var(--winter);
}

.band-inner {
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  gap: clamp(32px, 4.5vw, 72px);
  align-items: start;
}

.band-copy {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.band-eyebrow {
  color: var(--ink);
  opacity: 0.62;
  letter-spacing: var(--tracking-eyebrow);
}

.band-index {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

.band-heading {
  display: flex;
  align-items: baseline;
  gap: 16px;
  margin-top: 14px;
}

.band-char {
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(64px, 7vw, 104px);
  line-height: 0.95;
  letter-spacing: 0;
}

.band-title {
  color: var(--ink);
  font-family: var(--font);
  font-size: clamp(22px, 2.2vw, 30px);
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: var(--lh-tight);
}

.band-lead {
  max-width: 22em;
  margin-top: 18px;
  color: var(--ink);
  font-size: var(--fs-sm);
  line-height: 1.85;
  opacity: 0.82;
}

.term-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 20px;
}

.term {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 13px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.46);
  color: var(--ink);
  font-size: var(--fs-xs);
  line-height: 1;
}

.term.is-now {
  background: var(--surface);
  box-shadow: 0 2px 8px rgba(74, 43, 53, 0.06);
}

.term-now {
  color: var(--band-accent);
  font-weight: 700;
}

.bloom-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-top: 14px;
  color: var(--ink);
  font-size: var(--fs-xs);
  opacity: 0.82;
}

.bloom-label {
  flex-shrink: 0;
  padding-right: 10px;
  border-right: 1px solid rgba(74, 43, 53, 0.22);
  font-weight: 700;
  letter-spacing: 0.08em;
}

.band-art {
  width: 100%;
  margin: 26px 0 0;
  overflow: hidden;
  border-radius: var(--r-card);
  background: var(--surface);
}

.band-art img {
  width: 100%;
  aspect-ratio: 3 / 1;
  object-fit: cover;
}

.band-art figcaption {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.band-link {
  margin-top: 22px;
  color: var(--ink);
  font-weight: 500;
}

.band-link:hover {
  color: var(--ink);
  text-decoration: underline;
  text-decoration-color: var(--band-accent);
  text-decoration-thickness: 2px;
  text-underline-offset: 5px;
}

.band-count {
  color: var(--ink);
  opacity: 0.5;
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
}

.band-feed {
  min-width: 0;
}

.band-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
  border-radius: var(--r-card);
  background: rgba(255, 255, 255, 0.5);
}

/* 偶数块媒体在左，形成节奏 */
.season-band--flip .band-copy {
  order: 2;
}

.season-band--flip .band-feed {
  order: 1;
}

@media (max-width: 900px) {
  .band-inner {
    grid-template-columns: minmax(0, 1fr);
    gap: 32px;
  }

  .season-band--flip .band-copy,
  .season-band--flip .band-feed {
    order: initial;
  }

  .band-char {
    font-size: clamp(56px, 12vw, 80px);
  }

  .band-art {
    display: none;
  }
}
</style>
