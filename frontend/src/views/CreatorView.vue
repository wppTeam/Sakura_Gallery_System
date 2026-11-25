<template>
  <main class="creator-page">
    <div class="wrap">
      <nav class="cr-crumb" aria-label="面包屑">
        <RouterLink class="cr-crumb-link" to="/">
          <n-icon :component="ArrowBackOutline" :size="14" />
          首页
        </RouterLink>
        <span class="cr-crumb-sep" aria-hidden="true">/</span>
        <span class="cr-crumb-current">{{ crumbCurrent }}</span>
      </nav>

      <p v-if="loading" class="sr-only" role="status">正在加载创作者主页…</p>

      <div v-if="notFound" class="cr-state">
        <EmptyState
          title="没有找到这位创作者"
          description="这个用户名可能还没在视觉百花留下公开作品，或者账号已停用。"
          action-label="去探索页看看"
          @action="goExplore"
        />
      </div>

      <div v-else-if="error" class="cr-state">
        <EmptyState
          title="创作者主页暂时打不开"
          :description="error"
          action-label="重新加载"
          error
          @action="reload"
        />
      </div>

      <template v-else-if="loading">
        <div class="cr-skeleton" aria-hidden="true">
          <div class="cr-skeleton-hero">
            <span class="cr-skeleton-avatar"></span>
            <div class="cr-skeleton-lines">
              <span class="cr-skeleton-line cr-skeleton-line--xs"></span>
              <span class="cr-skeleton-line cr-skeleton-line--title"></span>
              <span class="cr-skeleton-line cr-skeleton-line--sm"></span>
            </div>
            <div class="cr-skeleton-stats">
              <span class="cr-skeleton-line cr-skeleton-line--stat"></span>
              <span class="cr-skeleton-line cr-skeleton-line--stat"></span>
              <span class="cr-skeleton-line cr-skeleton-line--stat"></span>
            </div>
          </div>
          <MasonryGrid :items="[]" :max-columns="gridColumns" :skeleton-rows="2" loading />
        </div>
      </template>

      <template v-else-if="profile">
        <CreatorHero :profile="profile" />

        <section class="cr-works" aria-labelledby="cr-works-title">
          <SectionHeader
            title-id="cr-works-title"
            eyebrow="PORTFOLIO"
            title="作品"
            :count="worksCountLabel"
            :description="worksDescription"
          />

          <div v-if="!works.length" class="cr-state cr-state--works">
            <EmptyState
              title="还没有公开作品"
              description="ta 的作品可能还在审核中，过一会儿再来看看。"
              action-label="去探索页看看"
              @action="goExplore"
            />
          </div>

          <template v-else>
            <MasonryGrid
              :items="works"
              :max-columns="gridColumns"
              :skeleton-rows="2"
              :show-author="false"
              eager
            />

            <div class="cr-more">
              <p v-if="endOfAll" class="cr-end">已经看完全部作品</p>
              <button
                v-else
                type="button"
                class="btn btn--primary cr-more-btn"
                :disabled="loadingMore"
                @click="loadMore"
              >
                {{ loadingMore ? '加载中…' : `加载更多（还有 ${remaining} 件）` }}
              </button>
              <p v-if="moreError" class="cr-more-error" role="alert">
                加载失败了，<button type="button" class="cr-retry" @click="loadMore">点这里重试</button>
              </p>
            </div>
          </template>
        </section>

        <CreatorCollectionRail v-if="collections.length" :collections="collections" />
      </template>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import {
  CreatorRequestError,
  fetchCreator,
  fetchCreatorWorks,
  type CreatorCollection,
  type CreatorProfile,
  type PublicPhoto,
} from '../api/public'
import CreatorHero from '../components/creator/CreatorHero.vue'
import CreatorCollectionRail from '../components/creator/CreatorCollectionRail.vue'
import MasonryGrid from '../components/public/MasonryGrid.vue'
import SectionHeader from '../components/public/SectionHeader.vue'
import EmptyState from '../components/public/EmptyState.vue'

const PAGE_SIZE = 12

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const notFound = ref(false)
const error = ref('')
const profile = ref<CreatorProfile | null>(null)
const works = ref<PublicPhoto[]>([])
const worksTotal = ref(0)
const collections = ref<CreatorCollection[]>([])
const loadingMore = ref(false)
const moreError = ref(false)
const narrow = ref(false)

let mediaQuery: MediaQueryList | null = null
let loadToken = 0

function currentUsername(): string {
  const raw = route.params.username
  return (Array.isArray(raw) ? raw[0] : raw) ?? ''
}

const crumbCurrent = computed(() => {
  if (profile.value) return `@${profile.value.username}`
  const handle = currentUsername()
  return handle ? `@${handle}` : '创作者'
})

const gridColumns = computed(() => (narrow.value ? 1 : 4))
const remaining = computed(() => Math.max(0, worksTotal.value - works.value.length))
const endOfAll = computed(() => !loadingMore.value && !moreError.value && remaining.value === 0)
const worksCountLabel = computed(() => `共 ${worksTotal.value.toLocaleString('zh-CN')} 件`)
const worksDescription = computed(() => {
  const name = profile.value?.displayName || profile.value?.username || '这位创作者'
  return `${name} 公开展出的作品，按发布时间从新到旧排列；点开可以看画面笔记与拍摄信息。`
})

function isNotFound(err: unknown): boolean {
  return err instanceof CreatorRequestError && err.status === 404
}

function describeError(err: unknown): string {
  if (err instanceof CreatorRequestError) {
    if (err.status === 0) return err.message
    return `服务暂时不可用（HTTP ${err.status}），请稍后重试。`
  }
  return '加载创作者主页时出了点问题，请稍后重试。'
}

function updateTitle(name: string) {
  document.title = name ? `${name} · 创作者 · 视觉百花` : '创作者 · 视觉百花'
}

async function load() {
  const handle = currentUsername()
  const token = ++loadToken
  loading.value = true
  notFound.value = false
  error.value = ''
  loadingMore.value = false
  moreError.value = false
  profile.value = null
  works.value = []
  worksTotal.value = 0
  collections.value = []

  if (!handle) {
    if (token !== loadToken) return
    loading.value = false
    notFound.value = true
    updateTitle('')
    return
  }

  try {
    const data = await fetchCreator(handle, { worksLimit: PAGE_SIZE, collectionsLimit: 12 })
    if (token !== loadToken) return
    profile.value = data.profile
    works.value = data.works.items
    worksTotal.value = data.works.total || data.profile.worksCount
    collections.value = data.collections
    updateTitle(data.profile.displayName || `@${data.profile.username}`)
  } catch (err) {
    if (token !== loadToken) return
    if (isNotFound(err)) {
      notFound.value = true
      updateTitle('')
    } else {
      error.value = describeError(err)
    }
  } finally {
    if (token === loadToken) loading.value = false
  }
}

async function loadMore() {
  if (loadingMore.value || remaining.value <= 0) return
  const handle = currentUsername()
  if (!handle) return
  loadingMore.value = true
  moreError.value = false
  try {
    const page = await fetchCreatorWorks(handle, { limit: PAGE_SIZE, offset: works.value.length })
    const seen = new Set(works.value.map((item) => item.id))
    works.value = [...works.value, ...page.items.filter((item) => !seen.has(item.id))]
    worksTotal.value = Math.max(page.total, works.value.length)
  } catch {
    moreError.value = true
  } finally {
    loadingMore.value = false
  }
}

function reload() {
  void load()
}

function goExplore() {
  void router.push('/explore')
}

function handleNarrowChange(event: MediaQueryListEvent | MediaQueryList) {
  narrow.value = event.matches
}

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 719px)')
  handleNarrowChange(mediaQuery)
  mediaQuery.addEventListener('change', handleNarrowChange)
  void load()
})

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener('change', handleNarrowChange)
  loadToken += 1
})

watch(
  () => route.params.username,
  (next, prev) => {
    if (String(next ?? '') === String(prev ?? '')) return
    if (route.name !== 'Creator') return
    void load()
  },
)
</script>

<style scoped>
.creator-page {
  padding: clamp(18px, 3vw, 34px) 0 clamp(56px, 7vw, 96px);
}

.cr-crumb {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.cr-crumb-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--muted);
  text-decoration: none;
  border-radius: var(--r-sm);
}

.cr-crumb-link:hover {
  color: var(--sakura-deep);
}

.cr-crumb-sep {
  color: var(--line-strong);
}

.cr-crumb-current {
  color: var(--ink-soft);
  font-weight: 600;
}

.cr-state {
  margin-top: var(--sp-8);
}

.cr-state--works {
  margin-top: var(--sp-4);
}

.cr-works {
  margin-top: var(--sp-4);
}

.cr-more {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-3);
  margin-top: var(--sp-8);
}

.cr-more-btn {
  min-width: 200px;
  min-height: 46px;
}

.cr-end {
  margin: 0;
  color: var(--faint);
  font-size: var(--fs-sm);
}

.cr-more-error {
  margin: 0;
  color: var(--sakura-deep);
  font-size: var(--fs-sm);
}

.cr-retry {
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.cr-retry:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: 2px;
  border-radius: 4px;
}

/* ---------- 首屏骨架：形状对齐真实 hero，避免加载时跳动 ---------- */
.cr-skeleton {
  margin-top: var(--sp-6);
}

.cr-skeleton-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-6);
  padding: var(--sp-8);
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
}

.cr-skeleton-avatar {
  flex: none;
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: var(--sakura-pale);
  animation: cr-pulse 1.6s ease-in-out infinite;
}

.cr-skeleton-lines {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  flex: 1 1 220px;
}

.cr-skeleton-line {
  display: block;
  height: 14px;
  border-radius: var(--r-pill);
  background: var(--sakura-mist);
  animation: cr-pulse 1.6s ease-in-out infinite;
}

.cr-skeleton-line--xs {
  width: 96px;
  height: 10px;
}

.cr-skeleton-line--title {
  width: min(220px, 70%);
  height: 34px;
}

.cr-skeleton-line--sm {
  width: 120px;
}

.cr-skeleton-line--stat {
  width: 72px;
  height: 30px;
}

.cr-skeleton-stats {
  display: flex;
  gap: var(--sp-6);
  flex: 0 0 auto;
}

@keyframes cr-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}

@media (max-width: 719px) {
  .creator-page {
    padding-top: 14px;
  }

  .cr-skeleton-hero {
    padding: var(--sp-6) var(--sp-5);
  }

  .cr-skeleton-avatar {
    width: 72px;
    height: 72px;
  }

  .cr-more-btn {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cr-skeleton-avatar,
  .cr-skeleton-line {
    animation: none;
  }
}
</style>
