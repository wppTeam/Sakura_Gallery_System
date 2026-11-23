<template>
  <article class="photo-card" :class="[`photo-card--${variant}`, { 'is-aigc': photo.aigc }]">
    <div class="thumb-wrap" :class="{ 'is-ready': loaded, 'is-broken': broken }">
      <div
        class="thumb media-ph"
        :class="{ 'has-lqip': Boolean(photo.lqip || photo.lqipColor) }"
        :style="thumbStyle"
      >
        <RouterLink
          v-if="!broken"
          class="thumb-link"
          :to="`/photo/${photo.id}`"
          :aria-label="`查看作品：${photo.title}`"
        >
          <img
            class="thumb-img"
            :src="photo.thumbUrl"
            :alt="photo.title"
            :width="photo.width || undefined"
            :height="photo.height || undefined"
            :loading="eager ? 'eager' : 'lazy'"
            :fetchpriority="eager ? 'high' : 'auto'"
            decoding="async"
            @load="loaded = true"
            @error="broken = true"
          />
        </RouterLink>
        <div v-else class="thumb-fallback">
          <svg width="34" height="34" viewBox="0 0 64 64" fill="none" aria-hidden="true">
            <circle cx="32" cy="32" r="30" fill="var(--sakura-pale)" />
            <path d="M0 -3.2c5.6 -6.2 6.2 -12.2 0 -15.4-6.2 3.2-5.6 9.2 0 15.4Z" transform="translate(32 32) rotate(0)" fill="var(--sakura)" opacity="0.6" />
            <path d="M0 -3.2c5.6 -6.2 6.2 -12.2 0 -15.4-6.2 3.2-5.6 9.2 0 15.4Z" transform="translate(32 32) rotate(144)" fill="var(--sakura)" opacity="0.6" />
            <path d="M0 -3.2c5.6 -6.2 6.2 -12.2 0 -15.4-6.2 3.2-5.6 9.2 0 15.4Z" transform="translate(32 32) rotate(288)" fill="var(--sakura)" opacity="0.6" />
            <circle cx="32" cy="32" r="3" fill="var(--sakura-deep)" />
          </svg>
          <span>图片加载失败</span>
          <RouterLink class="fallback-link" :to="`/photo/${photo.id}`">去详情页</RouterLink>
        </div>

        <span v-if="photo.aigc" class="aigc-badge">AI 生成</span>

        <div class="shade" aria-hidden="true" />

        <span v-if="showAuthor" class="author-chip">
          <span class="author-avatar" aria-hidden="true">{{ authorInitial }}</span>
          <span class="author-name">{{ photo.author }}</span>
        </span>

        <div class="card-actions">
          <a
            class="card-act"
            :href="photo.downloadUrl"
            download
            :aria-label="`下载作品：${photo.title}`"
            @click.stop
          >
            <svg width="17" height="17" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M10 3v9m0 0 3.4-3.4M10 12 6.6 8.6M4 15.2h12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </a>
        </div>
      </div>
    </div>

    <div v-if="showCaption" class="meta">
      <h3 class="title">
        <RouterLink :to="`/photo/${photo.id}`" class="title-link">{{ photo.title }}</RouterLink>
      </h3>
      <p class="sub">
        <span v-if="seasonMeta" class="season-tag" :class="`season-tag--${seasonMeta.key}`">
          {{ seasonMeta.label }}
        </span>
        <span v-if="seasonMeta && placeText" class="sep" aria-hidden="true">·</span>
        <span v-if="placeText" class="place">{{ placeText }}</span>
        <span v-if="photo.aigc" class="kind-note">AI 生成</span>
      </p>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PublicPhoto } from '../../api/public'
import { seasonKicker } from '../../constants/public'

const props = withDefaults(
  defineProps<{
    photo: PublicPhoto
    showCaption?: boolean
    showAuthor?: boolean
    eager?: boolean
    variant?: 'default' | 'compact'
  }>(),
  {
    showCaption: true,
    showAuthor: true,
    eager: false,
    variant: 'default',
  },
)

const loaded = ref(false)
const broken = ref(false)

const thumbStyle = computed(() => {
  const style: Record<string, string> = { aspectRatio: String(props.photo.aspectRatio) }
  if (props.photo.lqip) {
    style.backgroundImage = `url("${props.photo.lqip}")`
  } else if (props.photo.lqipColor) {
    // 没有 LQIP 小图时至少用主色占位，避免露出渐变纹理
    style.backgroundImage = 'none'
    style.backgroundColor = props.photo.lqipColor
  }
  return style
})

const seasonMeta = computed(() => seasonKicker(props.photo.season))
const placeText = computed(() => props.photo.place || props.photo.campus || '')
const authorInitial = computed(() => (props.photo.author || '匿').slice(0, 1))
</script>

<style scoped>
.photo-card {
  position: relative;
  min-width: 0;
}

.thumb-wrap {
  position: relative;
  border-radius: var(--r-photo);
  transition: box-shadow var(--dur) var(--ease-out);
}

.photo-card:hover .thumb-wrap {
  box-shadow: var(--shadow-lift);
}

.thumb {
  position: relative;
  overflow: hidden;
  width: 100%;
  border-radius: var(--r-photo);
  background-color: var(--sakura-mist);
  /* LQIP 是 20px 级小图：必须 cover + 不重复，否则慢网下会平铺成圆点花纹 */
  background-repeat: no-repeat;
  background-position: center;
  background-size: cover;
}

/* 有 LQIP 时不再叠白色脉冲，让用户看到模糊预览而不是一块白 */
.thumb.has-lqip::after {
  display: none;
}

.thumb-link {
  position: absolute;
  inset: 0;
  display: block;
  z-index: 1;
}

/* 图片容器 overflow:hidden 会裁掉外描边，焦点态改用内描边兜底（键盘可达性） */
.thumb-link:focus-visible {
  outline: none;
  box-shadow: inset 0 0 0 3px var(--sakura-deep), inset 0 0 0 5px rgba(255, 255, 255, 0.9);
}

.card-act:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.95), 0 0 0 5px var(--sakura-deep);
}

.thumb-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain; /* 容器比例受 clamp 限制时也不裁切原图 */
  opacity: 0;
  transform: scale(1.02);
  transition: opacity 420ms var(--ease-out), transform 620ms var(--ease-out);
}

.is-ready .thumb-img {
  opacity: 1;
  transform: scale(1);
}

.photo-card:hover .thumb-img,
.photo-card:focus-within .thumb-img {
  transform: scale(1.015);
  transition: opacity 420ms var(--ease-out), transform 180ms var(--ease-out);
}

.thumb.media-ph::after {
  transition: opacity var(--dur-slow) var(--ease-out);
}

.is-ready .thumb.media-ph::after,
.is-broken .thumb.media-ph::after {
  animation: none;
  opacity: 0;
}

.thumb-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  min-height: 160px;
  color: var(--muted);
  font-size: var(--fs-xs);
}

.fallback-link {
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* AIGC 显式角标：法定标识，常显 */
.aigc-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 9px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.92);
  color: var(--ink);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  backdrop-filter: blur(4px);
}

.shade {
  position: absolute;
  inset: 0;
  z-index: 1;
  background: linear-gradient(
    180deg,
    rgba(74, 43, 53, 0) 46%,
    rgba(74, 43, 53, 0.34) 100%
  );
  opacity: 0;
  transition: opacity var(--dur) var(--ease-out);
  pointer-events: none;
}

.card-actions {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 3;
  display: flex;
  gap: 6px;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 180ms var(--ease-out), transform 180ms var(--ease-out);
  pointer-events: none;
}

.card-act {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.94);
  color: var(--ink);
  box-shadow: 0 4px 12px rgba(74, 43, 53, 0.14);
  backdrop-filter: blur(4px);
  transition: background-color var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}

.card-act:hover {
  background: var(--sakura-deep);
  color: var(--on-accent);
}

.author-chip {
  position: absolute;
  left: 10px;
  bottom: 10px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  max-width: calc(100% - 20px);
  padding: 3px 10px 3px 3px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.92);
  color: var(--ink);
  font-size: var(--fs-xs);
  opacity: 0;
  transform: translateY(4px);
  transition: opacity var(--dur) var(--ease-out), transform var(--dur) var(--ease-out);
  backdrop-filter: blur(4px);
}

.author-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--sakura-pale);
  color: var(--sakura-deep);
  font-family: var(--font);
  font-size: 12px;
  font-weight: 700;
}

.author-name {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.photo-card:hover .shade,
.photo-card:focus-within .shade {
  opacity: 1;
}

.photo-card:hover .card-actions,
.photo-card:focus-within .card-actions {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.photo-card:hover .author-chip,
.photo-card:focus-within .author-chip {
  opacity: 1;
  transform: translateY(0);
}

/* 触屏没有 hover：作者常显，下载按钮收起（详情页仍可下载），减少噪声 */
@media (hover: none) {
  .author-chip {
    opacity: 1;
    transform: none;
  }

  .card-actions {
    display: none;
  }
}

/* ---------- 说明文字 ---------- */
.meta {
  padding: 10px 4px 0;
}

.title {
  overflow: hidden;
  color: var(--ink);
  font-family: var(--font);
  font-size: var(--fs-14);
  font-weight: 500;
  letter-spacing: 0;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-link:hover {
  color: var(--sakura-deep);
}

.sub {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  overflow: hidden;
  color: var(--faint);
  font-size: var(--fs-xs);
  line-height: 1.4;
  white-space: nowrap;
}

.season-tag {
  flex-shrink: 0;
  padding: 1px 7px;
  border-radius: var(--r-pill);
  color: var(--ink);
  font-size: 11px;
}

.season-tag--spring {
  background: var(--spring-pale);
}

.season-tag--summer {
  background: var(--summer-pale);
}

.season-tag--autumn {
  background: var(--autumn-pale);
}

.season-tag--winter {
  background: var(--winter-pale);
}

.sep {
  opacity: 0.7;
}

.place {
  overflow: hidden;
  text-overflow: ellipsis;
}

.kind-note {
  flex-shrink: 0;
  color: var(--sakura-deep);
}

.photo-card--compact .meta {
  padding-top: 8px;
}

.photo-card--compact .title {
  font-size: 13px;
}

.photo-card--compact .sub {
  margin-top: 3px;
  font-size: 11px;
}
</style>
