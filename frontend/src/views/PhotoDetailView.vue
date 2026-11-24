<template>
  <div class="work-detail-page">
    <div class="work-detail-shell">
      <nav class="detail-topbar" aria-label="面包屑">
        <button type="button" class="detail-back" @click="goBack">
          <n-icon :component="ArrowBackOutline" :size="16" />
          <span>返回</span>
        </button>
        <div class="detail-crumb">
          <router-link class="crumb-link" to="/">首页</router-link>
          <span class="crumb-sep">/</span>
          <router-link class="crumb-link" to="/gallery">作品广场</router-link>
          <span class="crumb-sep">/</span>
          <span class="crumb-current">{{ detail?.title || '作品详情' }}</span>
        </div>
      </nav>

      <div v-if="detail && detail.status === 'pending'" class="work-status-banner" role="status">
        <n-icon :component="HourglassOutline" :size="18" />
        <div class="work-status-copy">
          <b>待审核</b>
          <span>作品已提交，审核通过后会公开展示；审核期间只有你自己能看到这张作品。</span>
        </div>
      </div>

      <DetailSkeleton v-if="loading" />

      <DetailErrorState
        v-else-if="error"
        :title="error.title"
        :message="error.message"
        :tone="error.tone"
        :retrying="retrying"
        @retry="retryLoad"
      />

      <template v-else-if="detail">
        <div class="detail-grid">
          <div class="detail-media">
            <DetailImageStage
              :detail="detail"
              :kind-label="kindLabel"
              @expand="lightboxOpen = true"
              @dblclick="lightboxOpen = true"
            />
            <div class="detail-media-foot">
              <span class="media-note">
                <template v-if="detail.isRedacted">
                  人像作品已脱敏：原图仅作者与管理员可查看，当前为强模糊 + 像素化的脱敏图。
                </template>
                <template v-else>
                  原图仅做尺寸压缩、不裁切构图。</template>
                单击图片查看大图，双击可直接放大；大图内 Esc 关闭、← → 切换、+/− 缩放。
              </span>
              <span class="media-note media-note--touch">双击图片查看大图 · 大图内左右滑切换</span>
              <span v-if="detail.season" class="media-season">{{ detail.season }}作品</span>
            </div>
          </div>

          <DetailInfoPanel
            class="detail-side"
            :detail="detail"
            :favorited="favorited"
            :favorite-count="favoriteCount"
            :favorite-pending="favoritePending"
            :is-author="isAuthor"
            @toggle-favorite="toggleFavorite"
          />
        </div>

        <div class="detail-related">
          <RelatedWorks
            :works="related"
            :loading="relatedLoading"
            :season="detail.season"
            :category="detail.category"
          />
        </div>

        <DetailLightbox :show="lightboxOpen" :detail="detail" @close="lightboxOpen = false" />
      </template>

      <Transition name="backtop">
        <button
          v-if="showBackTop"
          type="button"
          class="back-to-top"
          aria-label="回到页面顶部"
          title="回到顶部"
          @click="scrollToTop"
        >
          <n-icon :component="ArrowUpOutline" :size="18" />
        </button>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon, useMessage } from 'naive-ui'
import { ArrowBackOutline, ArrowUpOutline, HourglassOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'
import { incrementView } from '../api/stats'
import DetailImageStage from '../components/detail/DetailImageStage.vue'
import DetailInfoPanel from '../components/detail/DetailInfoPanel.vue'
import DetailLightbox from '../components/detail/DetailLightbox.vue'
import DetailSkeleton from '../components/detail/DetailSkeleton.vue'
import DetailErrorState from '../components/detail/DetailErrorState.vue'
import RelatedWorks from '../components/detail/RelatedWorks.vue'
import {
  fetchRelatedWorks,
  fetchWorkDetail,
  getFavoriteState,
  toggleFavoriteState,
  type RelatedWork,
  type WorkDetail,
} from '../components/detail/workDetail'
import '../styles/detail.css'

interface LoadError {
  title: string
  message: string
  tone: 'not-found' | 'network' | 'error'
}

const route = useRoute()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const workId = computed(() => String(route.params.id || ''))

const detail = ref<WorkDetail | null>(null)
const loading = ref(true)
const retrying = ref(false)
const error = ref<LoadError | null>(null)

const related = ref<RelatedWork[]>([])
const relatedLoading = ref(false)

const favorited = ref(false)
const favoriteCount = ref<number | null>(null)
const favoritePending = ref(false)

const lightboxOpen = ref(false)

/** 当前用户是否作者：人像作品的原图/隐私视角提示用（服务端仍做最终鉴权） */
const isAuthor = computed(() => {
  if (!detail.value?.uploaderId || !auth.user) return false
  return auth.user.id === detail.value.uploaderId
})

/** 长页回到顶部按钮：滚动超过约两屏才出现 */
const showBackTop = ref(false)
function onScroll() {
  const maxScroll = Math.max(
    0,
    document.documentElement.scrollHeight - window.innerHeight,
  )
  // 长页：约 1.5 屏；短页：滚到底前 120px 也出现（避免阈值高于可滚动距离导致永不出现）
  const threshold = Math.min(window.innerHeight * 1.5, Math.max(0, maxScroll - 120))
  showBackTop.value = window.scrollY > threshold
}
function prefersReduced(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
function scrollToTop() {
  window.scrollTo({ top: 0, behavior: prefersReduced() ? 'auto' : 'smooth' })
}

const kindLabel = computed(() => {
  const kind = detail.value?.kind.toLowerCase() || 'photo'
  if (kind === 'aigc') return 'AI 生成作品'
  if (kind === 'template') return '模板素材'
  return '摄影作品'
})

function describeError(err: unknown): LoadError {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 404 || status === 403) {
    return {
      title: '作品不存在或尚未公开',
      message: '它可能已被作者删除，或仍处于审核流程中。可以回到作品广场看看其他作品。',
      tone: 'not-found',
    }
  }
  if (!status) {
    return {
      title: '网络连接失败',
      message: '暂时无法连接到作品服务，请检查网络后重新加载。',
      tone: 'network',
    }
  }
  return {
    title: '作品加载失败',
    message: `服务暂时没有正常响应（${status}），请稍后重试。`,
    tone: 'error',
  }
}

async function loadRelated(data: WorkDetail) {
  relatedLoading.value = true
  try {
    related.value = await fetchRelatedWorks(data, 8)
  } catch {
    related.value = []
  } finally {
    relatedLoading.value = false
  }
}

async function loadFavorite() {
  if (!auth.isAuthenticated) {
    favorited.value = false
    favoriteCount.value = null
    return
  }
  try {
    const state = await getFavoriteState(workId.value)
    favorited.value = state.favorited
    if (state.favoriteCount !== null) favoriteCount.value = state.favoriteCount
  } catch {
    // 收藏状态属于增强信息，读取失败不打断正文阅读
  }
}

async function load() {
  const id = workId.value
  if (!id) {
    loading.value = false
    error.value = { title: '作品不存在', message: '缺少作品编号，无法加载内容。', tone: 'not-found' }
    return
  }
  loading.value = true
  error.value = null
  detail.value = null
  related.value = []
  lightboxOpen.value = false
  try {
    const data = await fetchWorkDetail(id)
    if (workId.value !== id) return
    detail.value = data
    document.title = `${data.title} · 视觉百花 Sakura Gallery`
    void incrementView(id).catch(() => {
      // 浏览量统计失败不影响阅读
    })
    void loadRelated(data)
    void loadFavorite()
  } catch (err) {
    if (workId.value !== id) return
    error.value = describeError(err)
  } finally {
    if (workId.value === id) loading.value = false
  }
}

async function retryLoad() {
  retrying.value = true
  await load()
  retrying.value = false
}

async function toggleFavorite() {
  if (!auth.isAuthenticated) {
    message.info('登录后即可收藏作品')
    void router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  if (favoritePending.value) return
  favoritePending.value = true
  try {
    const state = await toggleFavoriteState(workId.value)
    favorited.value = state.favorited
    if (state.favoriteCount !== null) favoriteCount.value = state.favoriteCount
    message.success(state.favorited ? '已收藏，可在个人主页查看' : '已取消收藏')
  } catch {
    message.error('收藏失败，请稍后重试')
  } finally {
    favoritePending.value = false
  }
}

function goBack() {
  if (window.history.length > 1) router.back()
  else void router.push('/gallery')
}

watch(workId, () => {
  void load()
})

onMounted(() => {
  void load()
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()
})

onBeforeUnmount(() => {
  document.title = '视觉百花 Sakura Gallery'
  window.removeEventListener('scroll', onScroll)
})
</script>

<style scoped>
/* 作者查看自己的待审稿件时的状态提示（AI 创作台发布后跳转到此页） */
.work-status-banner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin: 4px 0 16px;
  padding: 14px 18px;
  border-radius: var(--r-card, 16px);
  border: 1px solid color-mix(in srgb, var(--sakura-deep, #c93a63) 22%, var(--line, #f3dde5));
  background: var(--sakura-wash, #fff0f5);
  color: var(--ink, #4a2b35);
}

.work-status-banner :deep(.n-icon) {
  margin-top: 1px;
  color: var(--sakura-deep, #c93a63);
  flex-shrink: 0;
}

.work-status-copy {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
  font-size: 13px;
  line-height: 1.7;
}

.work-status-copy b {
  font-size: 14px;
  color: var(--sakura-deep, #c93a63);
}

.work-status-copy span {
  color: var(--muted, #63474f);
}

@media (max-width: 640px) {
  .work-status-banner {
    margin-top: 0;
    padding: 12px 14px;
  }
}
</style>
