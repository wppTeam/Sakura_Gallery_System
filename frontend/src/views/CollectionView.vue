<template>
  <main class="collection-page">
    <div class="wrap">
      <nav class="cl-crumb" aria-label="面包屑">
        <RouterLink class="cl-crumb-link" to="/">
          <n-icon :component="ArrowBackOutline" :size="14" />
          首页
        </RouterLink>
        <span class="cl-crumb-sep" aria-hidden="true">/</span>
        <RouterLink class="cl-crumb-link" to="/collections">主题专题</RouterLink>
        <span class="cl-crumb-sep" aria-hidden="true">/</span>
        <span class="cl-crumb-current">{{ detail?.title || '专题' }}</span>
      </nav>

      <template v-if="loading">
        <div class="cl-skeleton-head" aria-hidden="true" />
        <div class="cl-skeleton-cover" aria-hidden="true" />
        <div class="cl-skeleton-grid" aria-hidden="true">
          <div v-for="index in 6" :key="index" class="cl-skeleton-card" />
        </div>
      </template>

      <template v-else-if="error">
        <div class="cl-state">
          <EmptyState
            :title="notFound ? '专题不存在或未发布' : '专题暂时没有加载出来'"
            :description="error"
            :action-label="notFound ? '返回主题专题' : '重新加载'"
            :error="!notFound"
            @action="notFound ? router.replace('/collections') : loadCollection()"
          />
        </div>
      </template>

      <template v-else-if="detail">
        <header class="cl-head">
          <p class="eyebrow">CURATED COLLECTION</p>
          <div class="cl-title-row">
            <h1 class="cl-title">{{ detail.title }}</h1>
            <span class="cl-count">{{ detail.photoCount }} 张作品</span>
          </div>
          <p v-if="detail.subtitle" class="cl-sub">{{ detail.subtitle }}</p>
          <p v-if="detail.description" class="cl-desc">{{ detail.description }}</p>
        </header>

        <figure v-if="cover" class="cl-cover" :style="coverStyle">
          <img
            class="cl-cover-img"
            :class="{ 'is-loaded': coverLoaded }"
            :src="coverImageSrc"
            :srcset="coverSrcset || undefined"
            :sizes="COVER_SIZES"
            :alt="`${detail.title} 封面`"
            :width="cover.width || undefined"
            :height="cover.height || undefined"
            decoding="async"
            @load="coverLoaded = true"
          />
        </figure>

        <div class="cl-works-head">
          <h2 class="cl-works-title">作品</h2>
          <span class="cl-works-hint">按策展顺序排列 · 共 {{ detail.photoCount }} 张</span>
        </div>

        <MasonryGrid
          v-if="detail.photos.length"
          :items="detail.photos"
          :max-columns="3"
          :skeleton-rows="2"
        />
        <div v-else class="cl-state">
          <EmptyState
            title="这个专题还没有公开的作品"
            description="策展人可能正在整理，先去看看其他专题吧。"
            action-label="返回主题专题"
            @action="router.push('/collections')"
          />
        </div>

        <nav class="cl-pager" aria-label="专题翻页">
          <RouterLink
            v-if="detail.prevSlug"
            class="cl-pager-btn"
            :to="`/collections/${detail.prevSlug}`"
            aria-label="上一个专题"
            title="上一个专题"
          >
            <n-icon :component="ArrowBackOutline" :size="18" />
          </RouterLink>
          <span v-else class="cl-pager-btn is-disabled" aria-hidden="true">
            <n-icon :component="ArrowBackOutline" :size="18" />
          </span>

          <RouterLink class="cl-pager-all" to="/collections">全部专题</RouterLink>

          <RouterLink
            v-if="detail.nextSlug"
            class="cl-pager-btn"
            :to="`/collections/${detail.nextSlug}`"
            aria-label="下一个专题"
            title="下一个专题"
          >
            <n-icon :component="ArrowForwardOutline" :size="18" />
          </RouterLink>
          <span v-else class="cl-pager-btn is-disabled" aria-hidden="true">
            <n-icon :component="ArrowForwardOutline" :size="18" />
          </span>
        </nav>
      </template>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { ArrowBackOutline, ArrowForwardOutline } from '@vicons/ionicons5'
import { buildSrcset, type PublicPhoto } from '../api/public'
import { fetchCollection, type CollectionDetail } from '../api/collections'
import EmptyState from '../components/public/EmptyState.vue'
import MasonryGrid from '../components/public/MasonryGrid.vue'

const COVER_SIZES = '(max-width: 640px) 100vw, (max-width: 1280px) 88vw, 1180px'

const route = useRoute()
const router = useRouter()

const detail = ref<CollectionDetail | null>(null)
const loading = ref(true)
const error = ref('')
const notFound = ref(false)
const coverLoaded = ref(false)

const slug = computed(() => String(route.params.slug || ''))

const cover = computed<PublicPhoto | null>(() => detail.value?.cover ?? null)
const coverImageSrc = computed(() => cover.value?.imageUrl || cover.value?.thumbUrl || '')
const coverSrcset = computed(() => buildSrcset(cover.value?.variants || [], 'jpeg'))

const coverStyle = computed(() => {
  const style: Record<string, string> = {}
  const lqip = cover.value?.lqip
  if (lqip) {
    style.backgroundImage = `url("${lqip}")`
    style.backgroundSize = 'cover'
    style.backgroundPosition = 'center'
  }
  return style
})

function describeError(e: unknown): { message: string; notFound: boolean } {
  const status = (e as { response?: { status?: number } })?.response?.status
  if (status === 404) {
    return {
      message: '这个专题可能已经下线，或链接有误。可以返回专题列表继续浏览。',
      notFound: true,
    }
  }
  if (!status) {
    return { message: '网络连接失败，请检查网络后重试。', notFound: false }
  }
  return { message: `专题加载失败（HTTP ${status}），请稍后重试。`, notFound: false }
}

async function loadCollection() {
  const target = slug.value
  if (!target) {
    loading.value = false
    notFound.value = true
    error.value = '缺少专题标识。'
    return
  }
  loading.value = true
  error.value = ''
  notFound.value = false
  coverLoaded.value = false
  detail.value = null
  try {
    const data = await fetchCollection(target)
    detail.value = data
    document.title = `${data.title} · 主题专题 · 视觉百花 Sakura Gallery`
  } catch (e) {
    const info = describeError(e)
    error.value = info.message
    notFound.value = info.notFound
    console.warn('[collection] 专题加载失败', e)
  } finally {
    loading.value = false
  }
}

watch(
  slug,
  () => {
    if (slug.value) loadCollection()
  },
  { immediate: true },
)
</script>

<style scoped>
.collection-page {
  padding: clamp(18px, 3vw, 34px) 0 clamp(56px, 8vw, 100px);
}

.cl-crumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.cl-crumb-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out);
}

.cl-crumb-link:hover {
  color: var(--sakura-deep);
}

.cl-crumb-sep {
  color: var(--faint);
}

.cl-crumb-current {
  max-width: 30em;
  overflow: hidden;
  color: var(--ink);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cl-head {
  max-width: 52em;
  margin-top: clamp(20px, 3vw, 34px);
}

.cl-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 14px;
  margin-top: 12px;
}

.cl-title {
  font-family: var(--display);
  font-size: clamp(40px, 5vw, 64px);
  font-weight: 400;
  line-height: 1.08;
  letter-spacing: 0.02em;
}

.cl-count {
  padding: 4px 12px;
  border-radius: var(--r-pill);
  background: var(--sakura-wash);
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
}

.cl-sub {
  margin-top: 12px;
  color: var(--ink-soft);
  font-size: var(--fs-lead);
  line-height: 1.7;
}

.cl-desc {
  max-width: 68em;
  margin-top: 12px;
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: 1.9;
}

.cl-cover {
  display: flex;
  align-items: center;
  justify-content: center;
  max-height: 560px;
  margin: clamp(24px, 3.4vw, 40px) 0 0;
  padding: clamp(10px, 1.6vw, 18px);
  overflow: hidden;
  border-radius: var(--r-card);
  background-color: var(--sakura-wash);
  background-position: center;
  background-size: cover;
}

.cl-cover-img {
  width: 100%;
  max-height: 520px;
  object-fit: contain;
  opacity: 0;
  transform: scale(1.01);
  transition: opacity var(--dur-slow) var(--ease-out), transform var(--dur-slow) var(--ease-out);
}

.cl-cover-img.is-loaded {
  opacity: 1;
  transform: scale(1);
}

.cl-works-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin: clamp(32px, 4.2vw, 52px) 0 clamp(16px, 2vw, 22px);
  padding-bottom: 14px;
  border-bottom: 1px dashed var(--line);
}

.cl-works-title {
  font-family: var(--display);
  font-size: clamp(24px, 2.4vw, 30px);
  font-weight: 400;
  letter-spacing: 0.02em;
}

.cl-works-hint {
  color: var(--muted);
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
}

.cl-state {
  padding: clamp(40px, 6vw, 72px) 0;
}

.cl-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: clamp(14px, 2.4vw, 24px);
  margin-top: clamp(40px, 5vw, 64px);
}

.cl-pager-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--ink);
  box-shadow: var(--shadow-soft);
  transition: border-color var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out);
}

a.cl-pager-btn:hover {
  border-color: var(--sakura);
  color: var(--sakura-deep);
}

a.cl-pager-btn:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 3px;
}

.cl-pager-btn.is-disabled {
  opacity: 0.35;
  box-shadow: none;
}

.cl-pager-all {
  color: var(--muted);
  font-size: var(--fs-sm);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out);
}

.cl-pager-all:hover {
  color: var(--sakura-deep);
}

.cl-skeleton-head {
  height: 180px;
  margin-top: 28px;
  border-radius: var(--r-lg);
  background: linear-gradient(100deg, var(--sakura-wash) 20%, var(--sakura-mist) 42%, var(--sakura-wash) 62%);
  background-size: 220% 100%;
  animation: cl-shimmer 1.4s linear infinite;
}

.cl-skeleton-cover {
  height: clamp(220px, 30vw, 380px);
  margin-top: 28px;
  border-radius: var(--r-card);
  background: linear-gradient(100deg, var(--sakura-wash) 20%, var(--sakura-mist) 42%, var(--sakura-wash) 62%);
  background-size: 220% 100%;
  animation: cl-shimmer 1.4s linear infinite;
}

.cl-skeleton-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--gap);
  margin-top: 36px;
}

.cl-skeleton-card {
  height: 260px;
  border-radius: var(--r-photo);
  background: linear-gradient(100deg, var(--sakura-wash) 20%, var(--sakura-mist) 42%, var(--sakura-wash) 62%);
  background-size: 220% 100%;
  animation: cl-shimmer 1.4s linear infinite;
}

@keyframes cl-shimmer {
  from {
    background-position: 120% 0;
  }
  to {
    background-position: -120% 0;
  }
}

@media (max-width: 900px) {
  .cl-skeleton-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .collection-page {
    padding-top: 14px;
  }

  .cl-title {
    font-size: 40px;
  }

  .cl-cover {
    max-height: 360px;
  }

  .cl-cover-img {
    max-height: 340px;
  }

  .cl-skeleton-grid {
    grid-template-columns: 1fr;
  }

  .cl-pager {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .cl-pager-btn {
    width: 100%;
    height: 44px;
  }

  .cl-pager-all {
    grid-column: 1 / -1;
    order: 3;
    justify-self: center;
    padding-top: 4px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cl-skeleton-head,
  .cl-skeleton-cover,
  .cl-skeleton-card,
  .cl-cover-img {
    animation: none;
    transition: none;
  }
}
</style>
