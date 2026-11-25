<template>
  <main class="creators-page">
    <div class="wrap">
      <nav class="crv-crumb" aria-label="面包屑">
        <RouterLink class="crv-crumb-link" to="/">
          <n-icon :component="ArrowBackOutline" :size="14" />
          首页
        </RouterLink>
        <span class="crv-crumb-sep" aria-hidden="true">/</span>
        <span class="crv-crumb-current">创作者</span>
      </nav>

      <header class="crv-head">
        <p class="eyebrow">DISCOVER · 创作者</p>
        <div class="crv-title-row">
          <h1 class="crv-title">发现创作者</h1>
          <span class="crv-count" aria-live="polite">{{ totalText }}</span>
        </div>
        <p class="crv-lead">
          他们把校园的光与花留在这里。按作品数或浏览量找到一位作者，顺着 ta 的镜头继续看下去。
        </p>

        <div class="crv-toolbar">
          <div class="crv-sort" role="group" aria-label="创作者排序方式">
            <button
              v-for="option in SORT_OPTIONS"
              :key="option.key"
              type="button"
              class="crv-sort-btn"
              :class="{ 'is-active': sort === option.key }"
              :aria-pressed="sort === option.key"
              @click="selectSort(option.key)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
      </header>

      <div v-if="loading && !items.length" class="crv-grid" aria-busy="true" aria-label="正在加载创作者">
        <div v-for="index in 6" :key="index" class="crv-skeleton" aria-hidden="true">
          <span class="crv-skel-head">
            <span class="crv-skel-avatar" />
            <span class="crv-skel-lines">
              <span class="crv-skel-line crv-skel-line--name" />
              <span class="crv-skel-line crv-skel-line--handle" />
            </span>
          </span>
          <span class="crv-skel-line crv-skel-line--stats" />
          <span class="crv-skel-covers">
            <span v-for="slot in 3" :key="slot" class="crv-skel-cover" />
          </span>
        </div>
      </div>

      <div v-else-if="error" class="crv-state">
        <EmptyState
          title="创作者列表暂时没有加载出来"
          description="网络或服务打了个盹，请稍后重试。"
          action-label="重新加载"
          error
          @action="load(true)"
        />
      </div>

      <div v-else-if="!items.length" class="crv-state">
        <EmptyState
          title="还没有公开的创作者"
          description="等第一位作者发出公开作品后，这里就会热闹起来。先去看看最新的校园作品吧。"
        >
          <RouterLink class="btn btn--primary" to="/explore">去探索作品</RouterLink>
          <RouterLink class="btn btn--ghost" to="/upload">开始投稿</RouterLink>
        </EmptyState>
      </div>

      <template v-else>
        <ul class="crv-grid" aria-label="创作者列表">
          <li v-for="creator in items" :key="creator.username" class="crv-cell">
            <CreatorDirectoryCard :creator="creator" />
          </li>
        </ul>

        <div class="crv-more">
          <button
            v-if="hasMore"
            type="button"
            class="btn btn--ghost crv-more-btn"
            :disabled="loadingMore"
            @click="loadMore"
          >
            {{ loadingMore ? '正在加载…' : `加载更多创作者（还有 ${Math.max(total - items.length, 0)} 位）` }}
          </button>
          <p v-else class="crv-end">已经看完全部 {{ total }} 位创作者。</p>

          <p v-if="moreError" class="crv-more-error" role="alert">
            {{ moreError }}
            <button type="button" class="crv-more-retry" @click="loadMore">重试</button>
          </p>
        </div>
      </template>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import { fetchCreators, type CreatorCard, type CreatorSort } from '../api/public'
import CreatorDirectoryCard from '../components/creator/CreatorDirectoryCard.vue'
import EmptyState from '../components/public/EmptyState.vue'

const PAGE_SIZE = 12

const SORT_OPTIONS: Array<{ key: CreatorSort; label: string }> = [
  { key: 'works', label: '作品最多' },
  { key: 'views', label: '浏览最多' },
]

const route = useRoute()
const router = useRouter()

function normalizeSort(value: unknown): CreatorSort {
  return value === 'views' ? 'views' : 'works'
}

const sort = ref<CreatorSort>(normalizeSort(route.query.sort))
const items = ref<CreatorCard[]>([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')
const moreError = ref('')

const hasMore = computed(() => items.value.length < total.value)

const totalText = computed(() => {
  if (loading.value && !items.value.length) return '正在整理…'
  if (!items.value.length) return ''
  return `共 ${total.value} 位创作者`
})

async function load(reset = true) {
  if (reset) {
    loading.value = true
    error.value = ''
    moreError.value = ''
  } else {
    loadingMore.value = true
    moreError.value = ''
  }
  const page = await fetchCreators({
    sort: sort.value,
    limit: PAGE_SIZE,
    offset: reset ? 0 : items.value.length,
  })
  if (page.error) {
    if (reset) {
      items.value = []
      total.value = 0
      error.value = '网络或服务暂时不可用，请稍后重试。'
    } else {
      moreError.value = '加载更多失败，请重试。'
    }
  } else if (reset) {
    items.value = page.items
    total.value = page.total
  } else {
    // 翻页期间若有人新投稿，offset 可能漂移：按 username 去重后再追加
    const seen = new Set(items.value.map((item) => item.username))
    items.value = [...items.value, ...page.items.filter((item) => !seen.has(item.username))]
    total.value = page.total
  }
  loading.value = false
  loadingMore.value = false
}

function loadMore() {
  if (loading.value || loadingMore.value || !hasMore.value) return
  load(false)
}

function selectSort(next: CreatorSort) {
  if (sort.value === next) return
  sort.value = next
  void router.replace({ query: { ...route.query, sort: next } })
  load(true)
}

// 浏览器前进/后退或直接改地址时排序跟着 URL 走
watch(
  () => route.query.sort,
  (value) => {
    const next = normalizeSort(value)
    if (next === sort.value) return
    sort.value = next
    load(true)
  },
)

onMounted(() => {
  load(true)
})
</script>

<style scoped>
.creators-page {
  padding: clamp(18px, 3vw, 34px) 0 clamp(56px, 7vw, 96px);
}

.crv-crumb {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.crv-crumb-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out);
}

.crv-crumb-link:hover {
  color: var(--sakura-deep);
}

.crv-crumb-sep {
  color: var(--faint);
}

.crv-crumb-current {
  color: var(--ink);
}

.crv-head {
  margin-top: clamp(18px, 2.6vw, 30px);
  padding-bottom: clamp(18px, 2.4vw, 28px);
  border-bottom: 1px dashed var(--line);
}

.crv-title-row {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-top: 10px;
}

.crv-title {
  font-family: var(--display);
  font-size: clamp(40px, 4.4vw, 58px);
  font-weight: 400;
  line-height: 1.1;
  letter-spacing: 0.02em;
}

.crv-count {
  color: var(--muted);
  font-size: var(--fs-sm);
  white-space: nowrap;
}

.crv-lead {
  max-width: 36em;
  margin-top: 12px;
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: 1.75;
}

.crv-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: clamp(18px, 2.4vw, 26px);
}

.crv-sort {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--sakura-mist);
}

.crv-sort-btn {
  min-height: 36px;
  padding: 6px 18px;
  border: 0;
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--muted);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition:
    background-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out);
}

.crv-sort-btn:hover {
  color: var(--sakura-deep);
}

.crv-sort-btn.is-active {
  background: var(--surface);
  color: var(--sakura-deep);
  font-weight: 600;
  box-shadow: var(--shadow-soft);
}

.crv-sort-btn:focus-visible {
  outline: 3px solid var(--focus-ring);
  outline-offset: 2px;
}

.crv-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--gap);
  margin: clamp(24px, 3vw, 36px) 0 0;
  padding: 0;
  list-style: none;
}

.crv-cell {
  min-width: 0;
}

/* ---------- 骨架：与真实卡片同形，避免 CLS ---------- */
.crv-skeleton {
  display: flex;
  flex-direction: column;
  min-height: 214px;
  padding: var(--sp-5) var(--sp-5) var(--sp-4);
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
}

.crv-skel-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.crv-skel-avatar {
  flex: none;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--sakura-wash);
}

.crv-skel-lines {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.crv-skel-line {
  display: block;
  height: 12px;
  border-radius: var(--r-pill);
  background: linear-gradient(90deg, var(--sakura-wash), var(--sakura-pale), var(--sakura-wash));
  background-size: 200% 100%;
  animation: crv-shimmer 1.4s var(--ease-soft) infinite;
}

.crv-skel-line--name {
  width: 44%;
}

.crv-skel-line--handle {
  width: 30%;
  height: 10px;
}

.crv-skel-line--stats {
  width: 52%;
  margin: var(--sp-4) 0 var(--sp-4);
}

.crv-skel-covers {
  display: flex;
  gap: 8px;
  height: 96px;
  margin-top: auto;
}

.crv-skel-cover {
  flex: 1;
  border-radius: var(--r-photo);
  background: var(--sakura-wash);
}

.crv-state {
  margin-top: clamp(24px, 3vw, 36px);
}

.crv-more {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin-top: clamp(28px, 3.4vw, 40px);
}

.crv-more-btn {
  min-width: 240px;
  min-height: 46px;
}

.crv-more-btn:disabled {
  opacity: 0.62;
  cursor: default;
}

.crv-end {
  color: var(--muted);
  font-size: var(--fs-sm);
}

.crv-more-error {
  color: var(--sakura-deep);
  font-size: var(--fs-sm);
}

.crv-more-retry {
  margin-left: 6px;
  padding: 2px 8px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  cursor: pointer;
}

@keyframes crv-shimmer {
  from {
    background-position: 100% 0;
  }

  to {
    background-position: -100% 0;
  }
}

@media (max-width: 900px) {
  .crv-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .creators-page {
    padding-top: 14px;
  }

  .crv-grid {
    grid-template-columns: 1fr;
  }

  .crv-skeleton {
    min-height: 206px;
  }

  .crv-sort-btn {
    min-height: 44px;
  }
}

@media (pointer: coarse) {
  .crv-sort-btn {
    min-height: 44px;
  }

  .crv-more-btn {
    min-height: 48px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .crv-skel-line {
    animation: none;
  }
}
</style>
