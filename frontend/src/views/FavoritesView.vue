<template>
  <main class="favorites-page">
    <div class="wrap">
      <nav class="fav-crumb" aria-label="面包屑">
        <RouterLink class="fav-crumb-link" to="/">
          <n-icon :component="ArrowBackOutline" :size="14" />
          首页
        </RouterLink>
        <span class="fav-crumb-sep" aria-hidden="true">/</span>
        <span class="fav-crumb-current">我的收藏</span>
      </nav>

      <SectionHeader
        title-id="favorites-title"
        eyebrow="MY FAVORITES"
        title="我的收藏"
        description="你在视觉百花收藏过的作品都收在这里，按收藏时间从新到旧排列。"
        :count="loading ? undefined : total"
      />

      <div v-if="error" class="fav-state">
        <EmptyState
          title="收藏暂时没有加载出来"
          :description="error"
          action-label="重新加载"
          error
          @action="loadFavorites(true)"
        />
      </div>

      <div v-else-if="loading" class="fav-loading">
        <MasonryGrid :items="[]" :max-columns="4" :skeleton-rows="2" loading />
      </div>

      <div v-else-if="!photos.length" class="fav-state">
        <EmptyState
          title="还没有收藏"
          description="在作品详情页点一下「收藏」，喜欢的作品就会出现在这里。"
          action-label="去探索"
          @action="goExplore"
        />
      </div>

      <template v-else>
        <MasonryGrid :items="photos" :max-columns="4" :skeleton-rows="2" />

        <div class="fav-more">
          <button
            v-if="loadMoreError"
            type="button"
            class="btn"
            @click="loadMore"
          >
            加载失败，点击重试
          </button>
          <button
            v-else-if="hasMore"
            type="button"
            class="btn btn--primary"
            :disabled="loadingMore"
            @click="loadMore"
          >
            {{ loadingMore ? '加载中…' : '加载更多' }}
          </button>
          <p v-else class="fav-end">已经到底啦</p>
        </div>
      </template>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import { getMyFavorites } from '../api/photo'
import { toPublicPhoto, type PublicPhoto } from '../api/public'
import SectionHeader from '../components/public/SectionHeader.vue'
import MasonryGrid from '../components/public/MasonryGrid.vue'
import EmptyState from '../components/public/EmptyState.vue'

const PAGE_SIZE = 20

const router = useRouter()

const photos = ref<PublicPhoto[]>([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')
const loadMoreError = ref('')
const skip = ref(0)

const hasMore = computed(() => photos.value.length < total.value)

function describeError(cause: unknown): string {
  const status = (cause as { response?: { status?: number } } | undefined)?.response?.status
  if (status === 401) return '登录状态已过期，请重新登录后再试。'
  if (status === 403) return '当前账号没有查看收藏的权限。'
  if (!status) return '网络连接失败，请检查网络后重试。'
  return `服务暂时不可用（${status}），请稍后重试。`
}

async function loadFavorites(reset = false) {
  if (reset) {
    loading.value = true
    error.value = ''
    skip.value = 0
  }
  loadMoreError.value = ''
  try {
    const page = await getMyFavorites({ skip: skip.value, limit: PAGE_SIZE })
    const mapped = (page.items || []).map(toPublicPhoto)
    photos.value = reset ? mapped : [...photos.value, ...mapped]
    total.value = page.total ?? photos.value.length
    skip.value = photos.value.length
  } catch (cause) {
    if (reset || !photos.value.length) {
      photos.value = []
      total.value = 0
      error.value = describeError(cause)
    } else {
      loadMoreError.value = '加载更多失败，请重试。'
    }
    console.warn('[favorites] 收藏列表加载失败', cause)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function loadMore() {
  if (loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  void loadFavorites(false)
}

function goExplore() {
  router.push('/explore')
}

onMounted(() => {
  document.title = '我的收藏 · 视觉百花 Sakura Gallery'
  void loadFavorites(true)
})

onBeforeUnmount(() => {
  document.title = '视觉百花 Sakura Gallery'
})
</script>

<style scoped>
.favorites-page {
  padding: clamp(18px, 3vw, 34px) 0 clamp(56px, 7vw, 96px);
}

.fav-crumb {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.fav-crumb-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out);
}

.fav-crumb-link:hover {
  color: var(--sakura-deep);
}

.fav-crumb-sep {
  color: var(--faint);
}

.fav-crumb-current {
  color: var(--ink);
}

.fav-state {
  padding: clamp(40px, 6vw, 72px) 0;
}

.fav-loading {
  padding-top: clamp(8px, 1.4vw, 16px);
}

.fav-more {
  display: flex;
  justify-content: center;
  margin-top: clamp(28px, 3.4vw, 44px);
}

.fav-more .btn {
  min-width: 168px;
}

.fav-end {
  color: var(--faint);
  font-size: var(--fs-sm);
  letter-spacing: 0.06em;
}

@media (max-width: 560px) {
  .favorites-page {
    padding-top: 14px;
  }

  .fav-more .btn {
    width: 100%;
  }
}
</style>
