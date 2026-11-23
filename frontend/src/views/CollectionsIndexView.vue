<template>
  <main class="collections-page">
    <div class="wrap">
      <nav class="idx-crumb" aria-label="面包屑">
        <RouterLink class="idx-crumb-link" to="/">
          <n-icon :component="ArrowBackOutline" :size="14" />
          首页
        </RouterLink>
        <span class="idx-crumb-sep" aria-hidden="true">/</span>
        <span class="idx-crumb-current">主题专题</span>
      </nav>

      <header class="idx-head">
        <p class="eyebrow">CURATED COLLECTIONS</p>
        <div class="idx-title-row">
          <h1 class="idx-title">主题专题</h1>
          <span v-if="total > 0" class="idx-count">{{ total }} 个专题</span>
        </div>
        <p class="idx-lead">
          年度相册、校园四季，按作者原意策展。每个专题都是一条被认真排过序的观看路线。
        </p>
      </header>

      <div v-if="error" class="idx-state">
        <EmptyState
          title="专题暂时没有加载出来"
          :description="error"
          action-label="重新加载"
          error
          @action="loadCollections()"
        />
      </div>

      <div v-else-if="loading" class="idx-grid" aria-busy="true">
        <div v-for="index in 6" :key="index" class="idx-skeleton" aria-hidden="true" />
      </div>

      <div v-else-if="!collections.length" class="idx-state">
        <EmptyState
          title="还没有公开的专题"
          description="策展人正在整理下一卷年度相册，先去看看最新的作品吧。"
          action-label="去探索"
          @action="router.push('/explore')"
        />
      </div>

      <ul v-else class="idx-grid">
        <li v-for="collection in collections" :key="collection.slug" class="idx-cell">
          <CollectionCard :collection="collection" />
        </li>
      </ul>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NIcon } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import { fetchCollections, type CollectionSummary } from '../api/collections'
import CollectionCard from '../components/public/CollectionCard.vue'
import EmptyState from '../components/public/EmptyState.vue'

const router = useRouter()
const collections = ref<CollectionSummary[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref('')

async function loadCollections() {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchCollections({ limit: 24 })
    collections.value = data.items
    total.value = data.total || data.items.length
  } catch (e) {
    collections.value = []
    total.value = 0
    error.value = '网络或服务暂时不可用，请稍后重试。'
    console.warn('[collections] 专题列表加载失败', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadCollections()
  document.title = '主题专题 · 视觉百花 Sakura Gallery'
})
</script>

<style scoped>
.collections-page {
  padding: clamp(18px, 3vw, 34px) 0 clamp(56px, 7vw, 96px);
}

.idx-crumb {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.idx-crumb-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out);
}

.idx-crumb-link:hover {
  color: var(--sakura-deep);
}

.idx-crumb-sep {
  color: var(--faint);
}

.idx-crumb-current {
  color: var(--ink);
}

.idx-head {
  margin-top: clamp(18px, 2.6vw, 30px);
  padding-bottom: clamp(20px, 2.6vw, 30px);
  border-bottom: 1px dashed var(--line);
}

.idx-title-row {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-top: 10px;
}

.idx-title {
  font-family: var(--display);
  font-size: clamp(40px, 4.4vw, 58px);
  font-weight: 400;
  line-height: 1.1;
  letter-spacing: 0.02em;
}

.idx-count {
  color: var(--muted);
  font-size: var(--fs-sm);
  font-variant-numeric: tabular-nums;
}

.idx-lead {
  max-width: var(--measure-lead);
  margin-top: 12px;
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: var(--lh-lead);
}

.idx-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--gap);
  margin: clamp(24px, 3vw, 36px) 0 0;
  padding: 0;
  list-style: none;
}

.idx-cell {
  min-width: 0;
}

.idx-state {
  padding: clamp(40px, 6vw, 72px) 0;
}

.idx-skeleton {
  height: 300px;
  border-radius: var(--r-card);
  background: linear-gradient(100deg, var(--sakura-wash) 20%, var(--sakura-mist) 42%, var(--sakura-wash) 62%);
  background-size: 220% 100%;
  animation: idx-shimmer 1.4s linear infinite;
}

@keyframes idx-shimmer {
  from {
    background-position: 120% 0;
  }
  to {
    background-position: -120% 0;
  }
}

@media (max-width: 1100px) {
  .idx-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 820px) {
  .idx-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .idx-grid {
    grid-template-columns: 1fr;
  }

  .collections-page {
    padding-top: 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .idx-skeleton {
    animation: none;
  }
}
</style>
