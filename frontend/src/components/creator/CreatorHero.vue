<template>
  <header class="cr-hero">
    <div class="cr-glow" aria-hidden="true"></div>

    <div class="cr-identity">
      <div class="cr-avatar" :class="{ 'cr-avatar--image': profile.avatarUrl }">
        <img v-if="profile.avatarUrl" :src="profile.avatarUrl" :alt="`${profile.displayName} 的头像`" />
        <span v-else aria-hidden="true">{{ monogram }}</span>
      </div>
      <div class="cr-meta">
        <p class="cr-eyebrow">CREATOR · 创作者</p>
        <h1 class="cr-name">{{ profile.displayName }}</h1>
        <p class="cr-handle">@{{ profile.username }}</p>
        <p v-if="profile.bio" class="cr-bio">{{ profile.bio }}</p>
      </div>
    </div>

    <ul class="cr-stats" aria-label="创作者公开数据">
      <li class="cr-stat">
        <span class="cr-stat-num">{{ formatNumber(profile.worksCount) }}</span>
        <span class="cr-stat-label">件公开作品</span>
      </li>
      <li class="cr-stat">
        <span class="cr-stat-num">{{ formatNumber(profile.viewsTotal) }}</span>
        <span class="cr-stat-label">次浏览</span>
      </li>
      <li class="cr-stat">
        <span class="cr-stat-num">{{ formatNumber(profile.favoritesTotal) }}</span>
        <span class="cr-stat-label">次收藏</span>
      </li>
      <li v-if="profile.collectionsCount > 0" class="cr-stat">
        <span class="cr-stat-num">{{ formatNumber(profile.collectionsCount) }}</span>
        <span class="cr-stat-label">个作品集</span>
      </li>
    </ul>

    <p class="cr-foot">
      <span v-if="joinedText">{{ joinedText }}</span>
      <span v-if="joinedText" class="cr-dot" aria-hidden="true">·</span>
      <span class="cr-note">公开身份仅显示用户名，不展示学号与真实姓名</span>
    </p>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CreatorProfile } from '../../api/public'

const props = defineProps<{
  profile: CreatorProfile
}>()

/** 头像占位：取展示名第一个字（中文取首字，英文取首字母大写） */
const monogram = computed(() => {
  const name = props.profile.displayName.trim() || props.profile.username
  const first = Array.from(name)[0] ?? '@'
  return first.toUpperCase()
})

const joinedText = computed(() => {
  const raw = props.profile.joinedAt
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getFullYear()} 年 ${date.getMonth() + 1} 月加入`
})

function formatNumber(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0'
  return value.toLocaleString('zh-CN')
}
</script>

<style scoped>
.cr-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--sp-8) var(--sp-12);
  padding: var(--sp-8) var(--sp-8) var(--sp-6);
  margin: var(--sp-6) 0 var(--sp-12);
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: linear-gradient(150deg, var(--surface) 0%, var(--sakura-mist) 100%);
  box-shadow: var(--shadow-soft);
}

.cr-glow {
  position: absolute;
  top: -120px;
  right: -80px;
  width: 360px;
  height: 360px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--sakura-pale) 0%, transparent 68%);
  opacity: 0.85;
  pointer-events: none;
}

.cr-identity {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--sp-6);
  min-width: 0;
}

.cr-avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 96px;
  height: 96px;
  border-radius: 50%;
  border: 1px solid var(--line);
  background: linear-gradient(140deg, var(--sakura-pale), var(--spring-pale));
  color: var(--sakura-deep);
  font-family: var(--display);
  font-size: 42px;
  line-height: 1;
  box-shadow: 0 6px 18px rgba(201, 58, 99, 0.12);
  overflow: hidden;
}

.cr-avatar--image {
  background: var(--surface);
}

.cr-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.cr-bio {
  margin: 8px 0 0;
  max-width: 46em;
  color: var(--ink-soft);
  font-size: var(--fs-sm);
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.cr-meta {
  min-width: 0;
}

.cr-eyebrow {
  margin: 0;
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-eyebrow);
}

.cr-name {
  margin: 6px 0 2px;
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(38px, 4.6vw, 56px);
  font-weight: 400;
  line-height: 1.08;
  letter-spacing: 0.02em;
  overflow-wrap: anywhere;
}

.cr-handle {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-sm);
  font-variant-numeric: tabular-nums;
}

.cr-stats {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-6) var(--sp-8);
  margin: 0;
  padding: var(--sp-2) 0 0;
  list-style: none;
}

.cr-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 64px;
}

.cr-stat-num {
  color: var(--ink);
  font-size: var(--fs-28);
  font-weight: 600;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.cr-stat-label {
  color: var(--muted);
  font-size: var(--fs-xs);
}

.cr-foot {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2);
  margin: var(--sp-4) 0 0;
  color: var(--faint);
  font-size: var(--fs-xs);
}

.cr-dot {
  color: var(--line-strong);
}

@media (max-width: 959px) {
  .cr-hero {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--sp-6);
  }

  .cr-stats {
    gap: var(--sp-4) var(--sp-6);
  }
}

@media (max-width: 719px) {
  .cr-hero {
    padding: var(--sp-6) var(--sp-5);
    margin-bottom: var(--sp-8);
    border-radius: var(--r-card);
  }

  .cr-avatar {
    width: 72px;
    height: 72px;
    font-size: 32px;
  }

  .cr-identity {
    gap: var(--sp-4);
  }

  .cr-name {
    font-size: 36px;
  }

  .cr-stats {
    gap: var(--sp-3) var(--sp-5);
  }

  .cr-foot {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .cr-dot {
    display: none;
  }

  .cr-stat {
    min-width: 56px;
  }

  .cr-stat-num {
    font-size: 22px;
  }
}
</style>
