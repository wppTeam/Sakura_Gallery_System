<template>
  <main class="ce-page">
    <div class="wrap ce-shell">
      <nav class="ce-crumb" aria-label="面包屑">
        <RouterLink class="ce-crumb-link" to="/">首页</RouterLink>
        <span class="ce-crumb-sep" aria-hidden="true">/</span>
        <RouterLink class="ce-crumb-link" to="/my-collections">我的策展</RouterLink>
        <span class="ce-crumb-sep" aria-hidden="true">/</span>
        <span class="ce-crumb-current">{{ managed?.title || '编辑专辑' }}</span>
      </nav>

      <header class="ce-head">
        <div class="ce-head-copy">
          <p class="eyebrow">CURATION EDITOR</p>
          <div class="ce-title-row">
            <h1 class="ce-title">编辑专辑</h1>
            <span v-if="managed" class="ce-status" :class="`is-${form.status}`">
              {{ form.status === 'draft' ? '草稿' : '已发布' }}
            </span>
          </div>
          <p class="ce-lead">挑作品、排顺序、写下引言。封面从已选作品里选一张，发布后这条观看路线就属于你了。</p>
        </div>
        <div class="ce-head-actions">
          <RouterLink class="ce-text-link" to="/my-collections">返回列表</RouterLink>
          <n-button secondary :loading="saving" :disabled="!managed || loading" @click="save('draft')">
            <template #icon>
              <n-icon :component="SaveOutline" />
            </template>
            保存草稿
          </n-button>
          <n-button type="primary" :loading="saving" :disabled="!managed || loading" @click="save('published')">
            <template #icon>
              <n-icon :component="CloudUploadOutline" />
            </template>
            发布
          </n-button>
        </div>
      </header>

      <div v-if="loading" class="ce-grid" aria-busy="true" aria-label="正在加载专辑">
        <div class="ce-panel ce-skeleton-panel">
          <div v-for="index in 4" :key="index" class="ce-skeleton-line" :class="{ 'is-title': index === 1 }" />
        </div>
        <div class="ce-panel ce-skeleton-panel">
          <div class="ce-skeleton-cover" />
        </div>
      </div>

      <div v-else-if="loadError" class="ce-state">
        <EmptyState
          title="这张专辑暂时打不开"
          :description="loadError"
          action-label="返回我的策展"
          error
          @action="router.replace('/my-collections')"
        />
      </div>

      <div v-else-if="managed" class="ce-grid">
        <section class="ce-panel ce-form" aria-labelledby="ce-form-title">
          <h2 id="ce-form-title" class="ce-panel-title">专辑信息</h2>

          <label class="ce-field" for="ce-title-input">
            <span class="ce-label">标题 <em>必填</em></span>
            <n-input
              id="ce-title-input"
              v-model:value="form.title"
              maxlength="60"
              show-count
              placeholder="给这本手账起个名字"
            />
            <span v-if="titleError" class="ce-field-error">{{ titleError }}</span>
          </label>

          <label class="ce-field" for="ce-subtitle-input">
            <span class="ce-label">副标题</span>
            <n-input
              id="ce-subtitle-input"
              v-model:value="form.subtitle"
              maxlength="100"
              show-count
              placeholder="一句话说明（可选）"
            />
          </label>

          <label class="ce-field" for="ce-desc-input">
            <span class="ce-label">引言</span>
            <n-input
              id="ce-desc-input"
              v-model:value="form.description"
              type="textarea"
              :rows="5"
              maxlength="500"
              show-count
              placeholder="为什么把这些画面放在一起？（可选）"
            />
          </label>

          <CollectionAssistantPanel @apply="applyAssistantProposal" />

          <div class="ce-field">
            <span class="ce-label">封面</span>
            <p class="ce-hint">从右侧「已选作品」里挑一张作为专辑封面，不裁切、按原始构图展示。</p>
            <div v-if="selected.length" class="ce-cover-options" role="radiogroup" aria-label="选择封面">
              <button
                type="button"
                class="ce-cover-option is-none"
                :class="{ 'is-active': !form.coverPhotoId }"
                role="radio"
                :aria-checked="!form.coverPhotoId"
                @click="setCover(null)"
              >
                不设封面
              </button>
              <button
                v-for="photo in selected"
                :key="photo.id"
                type="button"
                class="ce-cover-option"
                :class="{ 'is-active': form.coverPhotoId === photo.id }"
                role="radio"
                :aria-checked="form.coverPhotoId === photo.id"
                :title="photo.title || '未命名作品'"
                @click="setCover(photo.id)"
              >
                <img :src="photo.thumbUrl" :alt="photo.title || '作品缩略图'" loading="lazy" decoding="async" />
              </button>
            </div>
            <p v-else class="ce-hint is-empty">还没有选作品。先在右侧挑几张，再回来选封面。</p>
          </div>
        </section>

        <section class="ce-panel ce-works" aria-labelledby="ce-works-title">
          <div class="ce-works-head">
            <div>
              <h2 id="ce-works-title" class="ce-panel-title">作品选择</h2>
              <p class="ce-hint">只能选自己已发布的作品。点击缩略图加入或移出；加入后用 ↑ ↓ 调整顺序。</p>
            </div>
            <span class="ce-works-count">已选 {{ selected.length }} 张</span>
          </div>

          <h3 class="ce-subtitle">我的作品（{{ approvedWorks.length }}）</h3>
          <div v-if="worksLoading" class="ce-pick-grid" aria-busy="true">
            <div v-for="index in 8" :key="index" class="ce-pick ce-skeleton-pick" />
          </div>
          <div v-else-if="worksError" class="ce-inline-state">
            <p>{{ worksError }}</p>
            <n-button size="small" secondary @click="loadMyWorks()">重新加载</n-button>
          </div>
          <div v-else-if="!approvedWorks.length" class="ce-inline-state">
            <p>还没有已发布的作品，先去投稿并等待审核通过吧。</p>
            <RouterLink class="ce-text-link" to="/upload">去投稿 →</RouterLink>
          </div>
          <ul v-else class="ce-pick-grid">
            <li v-for="photo in approvedWorks" :key="photo.id">
              <button
                type="button"
                class="ce-pick"
                :class="{ 'is-selected': isSelected(photo.id) }"
                :aria-pressed="isSelected(photo.id)"
                :title="photo.title || '未命名作品'"
                @click="toggleWork(photo)"
              >
                <img
                  :src="photo.thumbUrl"
                  :class="{ 'is-loaded': pickLoaded.has(photo.id) }"
                  :alt="photo.title || '作品缩略图'"
                  loading="lazy"
                  decoding="async"
                  @load="markPickLoaded(photo.id)"
                />
                <span v-if="isSelected(photo.id)" class="ce-pick-check" aria-hidden="true">
                  <n-icon :component="CheckmarkOutline" :size="14" />
                </span>
                <span class="ce-pick-add" aria-hidden="true">
                  <n-icon :component="isSelected(photo.id) ? CloseOutline : AddOutline" :size="14" />
                </span>
              </button>
            </li>
          </ul>

          <h3 class="ce-subtitle">已选作品（{{ selected.length }}）<span class="ce-order-hint">按此顺序展示</span></h3>
          <ol v-if="selected.length" class="ce-order-list">
            <li v-for="(photo, index) in selected" :key="photo.id" class="ce-order-item">
              <span class="ce-order-index">{{ index + 1 }}</span>
              <img class="ce-order-thumb" :src="photo.thumbUrl" :alt="photo.title || '作品缩略图'" loading="lazy" decoding="async" />
              <span class="ce-order-title">{{ photo.title || '未命名作品' }}</span>
              <span class="ce-order-buttons">
                <button type="button" class="ce-icon-btn" :disabled="index === 0" :aria-label="`上移第 ${index + 1} 张`" @click="movePhoto(index, -1)">
                  <n-icon :component="ArrowUpOutline" :size="16" />
                </button>
                <button
                  type="button"
                  class="ce-icon-btn"
                  :disabled="index === selected.length - 1"
                  :aria-label="`下移第 ${index + 1} 张`"
                  @click="movePhoto(index, 1)"
                >
                  <n-icon :component="ArrowDownOutline" :size="16" />
                </button>
                <button type="button" class="ce-icon-btn is-danger" :aria-label="`移除第 ${index + 1} 张`" @click="removePhoto(index)">
                  <n-icon :component="CloseOutline" :size="16" />
                </button>
              </span>
            </li>
          </ol>
          <p v-else class="ce-hint is-empty">还没有选作品。从上方「我的作品」里点几张加入吧。</p>
        </section>
      </div>

      <div class="ce-mobile-actions" v-if="managed && !loading">
        <n-button secondary :loading="saving" @click="save('draft')">保存草稿</n-button>
        <n-button type="primary" :loading="saving" @click="save('published')">发布</n-button>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useDialog, useMessage } from 'naive-ui'
import {
  AddOutline,
  ArrowDownOutline,
  ArrowUpOutline,
  CheckmarkOutline,
  CloseOutline,
  CloudUploadOutline,
  SaveOutline,
} from '@vicons/ionicons5'
import EmptyState from '../components/public/EmptyState.vue'
import CollectionAssistantPanel from '../components/collections/CollectionAssistantPanel.vue'
import {
  fetchManagedCollection,
  replaceCollectionPhotos,
  updateCollection,
  type CollectionAssistantApplyPayload,
  type CollectionStatus,
  type ManagedCollection,
} from '../api/collections'
import { toPublicPhoto, type PublicPhoto } from '../api/public'
import { getMySubmissions } from '../api/photo'
import { displayPhotoTitle } from '../utils/photoDisplay'
import type { Photo } from '../types/photo'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const collectionId = computed(() => String(route.params.id || ''))

const loading = ref(true)
const loadError = ref('')
const saving = ref(false)
const managed = ref<ManagedCollection | null>(null)

const form = reactive({
  title: '',
  subtitle: '',
  description: '',
  coverPhotoId: null as string | null,
  status: 'draft' as CollectionStatus,
})

const titleError = ref('')

const selected = ref<PublicPhoto[]>([])
const approvedWorks = ref<PublicPhoto[]>([])
const worksLoading = ref(false)
/** 图片加载完成后淡入，避免占位格里出现孤立圆点式的空态 */
const pickLoaded = ref<Set<string>>(new Set())

function markPickLoaded(id: string) {
  if (pickLoaded.value.has(id)) return
  const next = new Set(pickLoaded.value)
  next.add(id)
  pickLoaded.value = next
}
const worksError = ref('')

let initialSnapshot = ''

function snapshot(): string {
  return JSON.stringify({
    title: form.title.trim(),
    subtitle: form.subtitle.trim(),
    description: form.description.trim(),
    cover: form.coverPhotoId,
    status: form.status,
    ids: selected.value.map((photo) => photo.id),
  })
}

const isDirty = computed(() => Boolean(managed.value) && snapshot() !== initialSnapshot)

function describeError(e: unknown, fallback: string): string {
  const status = (e as { response?: { status?: number; detail?: string } })?.response?.status
  const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  if (status === 401) return '登录已过期，请重新登录后再试。'
  if (status === 403) return detail || '只有作者本人（或管理员）可以编辑这本专辑。'
  if (status === 404) return '专辑不存在，可能已经被删除了。'
  if (!status) return '网络连接失败，请检查网络后重试。'
  return detail || `${fallback}（HTTP ${status}），请稍后重试。`
}

async function loadCollection() {
  loading.value = true
  loadError.value = ''
  try {
    const data = await fetchManagedCollection(collectionId.value)
    managed.value = data
    form.title = data.title
    form.subtitle = data.subtitle
    form.description = data.description
    form.status = data.status
    form.coverPhotoId = data.cover?.id || null
    selected.value = data.photos
    initialSnapshot = snapshot()
    document.title = `${data.title} · 编辑策展 · 视觉百花 Sakura Gallery`
  } catch (e) {
    loadError.value = describeError(e, '专辑加载失败')
    console.warn('[collection-editor] 加载失败', e)
  } finally {
    loading.value = false
  }
}

async function loadMyWorks() {
  worksLoading.value = true
  worksError.value = ''
  try {
    const page = await getMySubmissions({ limit: 100, status: 'approved' })
    const mapped = (page.items || []).map((photo) => toPublicPhoto(photo as Photo))
    const approved = mapped.filter((photo) => {
      const raw = photo.raw as Photo | undefined
      const status = raw?.status
      return !status || status === 'approved'
    })
    approvedWorks.value = approved
  } catch (e) {
    worksError.value = describeError(e, '我的作品加载失败')
    console.warn('[collection-editor] 我的作品加载失败', e)
  } finally {
    worksLoading.value = false
  }
}

function isSelected(id: string): boolean {
  return selected.value.some((photo) => photo.id === id)
}

function toggleWork(photo: PublicPhoto) {
  if (isSelected(photo.id)) {
    selected.value = selected.value.filter((row) => row.id !== photo.id)
    if (form.coverPhotoId === photo.id) form.coverPhotoId = null
  } else {
    selected.value = [...selected.value, photo]
  }
}

function removePhoto(index: number) {
  const removed = selected.value[index]
  selected.value = selected.value.filter((_, i) => i !== index)
  if (removed && form.coverPhotoId === removed.id) form.coverPhotoId = null
}

function movePhoto(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= selected.value.length) return
  const next = [...selected.value]
  const [row] = next.splice(index, 1)
  next.splice(target, 0, row)
  selected.value = next
}

function setCover(id: string | null) {
  form.coverPhotoId = id
}

/**
 * 应用 AI 提案：只填表单与已选作品，不自动保存/发布。
 * 提案作品都来自「我的作品」，若当前列表还没加载到这些作品则补进去。
 */
function applyAssistantProposal(payload: CollectionAssistantApplyPayload) {
  form.title = payload.title.slice(0, 60)
  form.subtitle = payload.subtitle.slice(0, 100)
  form.description = payload.description.slice(0, 500)
  const knownIds = new Set(approvedWorks.value.map((photo) => photo.id))
  const missing = payload.photos.filter((photo) => !knownIds.has(photo.id))
  if (missing.length) approvedWorks.value = [...missing, ...approvedWorks.value]
  selected.value = [...payload.photos]
  if (form.coverPhotoId && !payload.photos.some((photo) => photo.id === form.coverPhotoId)) {
    form.coverPhotoId = null
  }
  message.success(`已应用 AI 提案：${payload.photos.length} 张作品，确认后记得保存`)
}

async function save(status: CollectionStatus) {
  if (saving.value || !managed.value) return
  titleError.value = ''
  const title = form.title.trim()
  if (!title) {
    titleError.value = '请填写专辑标题'
    message.warning('请先填写专辑标题')
    return
  }
  if (title.length > 60) {
    titleError.value = '标题最多 60 个字'
    return
  }
  const coverId = form.coverPhotoId && isSelected(form.coverPhotoId) ? form.coverPhotoId : null
  saving.value = true
  try {
    const photoIds = selected.value.map((photo) => photo.id)
    const idsChanged = photoIds.join('|') !== managed.value.photoIds.join('|')
    if (idsChanged) {
      await replaceCollectionPhotos(managed.value.id, photoIds)
    }
    const updated = await updateCollection(managed.value.id, {
      title,
      subtitle: form.subtitle.trim(),
      description: form.description.trim(),
      coverPhotoId: coverId,
      status,
    })
    managed.value = updated
    form.status = updated.status
    form.coverPhotoId = coverId
    selected.value = updated.photos
    initialSnapshot = snapshot()
    message.success(status === 'draft' ? '已保存草稿' : '专辑已发布')
    if (status === 'published') {
      router.push('/my-collections')
    }
  } catch (e) {
    message.error(describeError(e, '保存失败'))
    console.warn('[collection-editor] 保存失败', e)
  } finally {
    saving.value = false
  }
}

onBeforeRouteLeave(async () => {
  if (!isDirty.value || saving.value) return true
  return await new Promise<boolean>((resolve) => {
    dialog.warning({
      title: '还有未保存的修改',
      content: '离开后这些修改会丢失。要放弃修改吗？',
      positiveText: '继续编辑',
      negativeText: '放弃修改',
      onPositiveClick: () => resolve(false),
      onNegativeClick: () => resolve(true),
      onClose: () => resolve(true),
    })
  })
})

onMounted(() => {
  void loadCollection()
  void loadMyWorks()
})

onBeforeUnmount(() => {
  document.title = '视觉百花 Sakura Gallery'
})
</script>

<style scoped>
.ce-page {
  padding: clamp(18px, 3vw, 34px) 0 clamp(56px, 8vw, 100px);
}

.ce-crumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.ce-crumb-link {
  color: var(--muted);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out);
}

.ce-crumb-link:hover {
  color: var(--sakura-deep);
}

.ce-crumb-sep {
  color: var(--faint);
}

.ce-crumb-current {
  max-width: 26em;
  overflow: hidden;
  color: var(--ink);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ce-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  margin: 22px 0 24px;
}

.ce-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ce-title {
  margin: 6px 0 8px;
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(38px, 4vw, 54px);
  font-weight: 400;
  letter-spacing: 0.02em;
  line-height: 1.1;
}

.ce-lead {
  max-width: var(--measure);
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-sm);
  line-height: 1.75;
}

.ce-head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.ce-text-link {
  color: var(--sakura-deep);
  font-size: var(--fs-sm);
  text-decoration: none;
}

.ce-text-link:hover {
  text-decoration: underline;
}

.ce-form {
  position: sticky;
  top: 96px;
  align-self: start;
}

.ce-grid {
  display: grid;
  grid-template-columns: minmax(0, 420px) minmax(0, 1fr);
  align-items: start;
  gap: 22px;
}

.ce-panel {
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
  padding: 20px;
}

.ce-panel-title {
  margin: 0 0 6px;
  color: var(--ink);
  font-family: var(--display);
  font-size: 24px;
  font-weight: 400;
}

.ce-hint {
  margin: 0 0 14px;
  color: var(--muted);
  font-size: var(--fs-xs);
  line-height: 1.7;
}

.ce-hint.is-empty {
  margin: 6px 0 0;
  color: var(--faint);
}

.ce-field {
  display: block;
  margin-bottom: 16px;
}

.ce-label {
  display: block;
  margin-bottom: 6px;
  color: var(--ink);
  font-size: var(--fs-sm);
  font-weight: 600;
}

.ce-label em {
  margin-left: 6px;
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  font-style: normal;
  font-weight: 500;
}

.ce-field-error {
  display: block;
  margin-top: 6px;
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
}

.ce-cover-options {
  display: flex;
  gap: 8px;
  padding-bottom: 6px;
  overflow-x: auto;
}

.ce-cover-option {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  padding: 4px;
  overflow: hidden;
  border: 2px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--sakura-wash);
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out);
}

.ce-cover-option img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.ce-cover-option.is-none {
  width: auto;
  padding: 0 12px;
  color: var(--muted);
  font-size: var(--fs-xs);
  white-space: nowrap;
}

.ce-cover-option.is-active {
  border-color: var(--sakura-deep);
}

.ce-cover-option:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 2px;
}

.ce-works-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.ce-works-count {
  color: var(--sakura-deep);
  font-size: var(--fs-sm);
  font-weight: 600;
}

.ce-subtitle {
  margin: 18px 0 10px;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: 600;
}

.ce-order-hint {
  margin-left: 8px;
  color: var(--faint);
  font-size: var(--fs-xs);
  font-weight: 400;
}

.ce-pick-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ce-pick {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 1;
  padding: 0;
  overflow: hidden;
  border: 2px solid transparent;
  border-radius: var(--r-sm);
  background:
    linear-gradient(100deg, var(--sakura-wash) 20%, var(--sakura-mist) 42%, var(--sakura-wash) 62%);
  background-size: 220% 100%;
  animation: ce-pick-shimmer 1.4s linear infinite;
  cursor: pointer;
}

.ce-pick img {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  object-fit: contain;
  opacity: 0;
  transition: opacity var(--dur-slow) var(--ease-out);
}

.ce-pick img.is-loaded {
  opacity: 1;
  animation: none;
}

@keyframes ce-pick-shimmer {
  from {
    background-position: 120% 0;
  }
  to {
    background-position: -120% 0;
  }
}

.ce-pick.is-selected {
  border-color: var(--sakura-deep);
  box-shadow: 0 0 0 2px var(--sakura-pale);
}

.ce-pick:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 2px;
}

.ce-pick-check {
  position: absolute;
  top: 4px;
  left: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--sakura-deep);
  color: var(--on-accent);
}

.ce-pick-add {
  position: absolute;
  right: 4px;
  bottom: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.9);
  color: var(--sakura-deep);
  opacity: 0.9;
}

.ce-order-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ce-order-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--ground);
}

.ce-order-index {
  flex: 0 0 22px;
  color: var(--faint);
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.ce-order-thumb {
  flex: 0 0 52px;
  width: 52px;
  height: 52px;
  border-radius: var(--r-sm);
  background: var(--sakura-wash);
  object-fit: contain;
}

.ce-order-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--ink);
  font-size: var(--fs-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ce-order-buttons {
  display: inline-flex;
  gap: 4px;
}

.ce-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink);
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}

.ce-icon-btn:hover:not(:disabled) {
  border-color: var(--sakura);
  color: var(--sakura-deep);
}

.ce-icon-btn:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}

.ce-icon-btn.is-danger {
  color: var(--sakura-deep);
}

.ce-icon-btn:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 2px;
}

.ce-inline-state {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 18px;
  border: 1px dashed var(--line-strong);
  border-radius: var(--r-sm);
  color: var(--muted);
  font-size: var(--fs-sm);
}

.ce-inline-state p {
  margin: 0;
}

.ce-state {
  padding: clamp(28px, 5vw, 56px) 0;
}

.ce-mobile-actions {
  display: none;
}

.ce-skeleton-panel {
  min-height: 240px;
}

.ce-skeleton-line,
.ce-skeleton-cover {
  border-radius: var(--r-sm);
  background: var(--surface-warm);
  animation: ce-pulse 1.4s ease-in-out infinite;
}

.ce-skeleton-line {
  height: 14px;
  margin-bottom: 18px;
}

.ce-skeleton-line.is-title {
  width: 46%;
  height: 22px;
}

.ce-skeleton-cover {
  height: 220px;
}

.ce-skeleton-pick {
  animation: ce-pulse 1.4s ease-in-out infinite;
  background: var(--sakura-mist);
}

@keyframes ce-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}

@media (max-width: 1080px) {
  .ce-form {
    position: static;
  }

  .ce-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .ce-pick-grid {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .ce-head-actions {
    display: none;
  }

  .ce-mobile-actions {
    position: sticky;
    bottom: 12px;
    display: flex;
    gap: 10px;
    margin-top: 18px;
    padding: 10px;
    border: 1px solid var(--line);
    border-radius: var(--r-card);
    background: var(--surface);
    box-shadow: var(--shadow-card);
  }

  .ce-mobile-actions .n-button {
    flex: 1;
  }

  .ce-pick-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .ce-panel {
    padding: 16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ce-skeleton-line,
  .ce-skeleton-cover,
  .ce-skeleton-pick {
    animation: none;
  }
}

.ce-status {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 10px;
  border-radius: var(--r-pill);
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.02em;
  background: var(--sakura-pale);
  color: var(--sakura-deep);
  white-space: nowrap;
}

.ce-status.is-draft {
  background: var(--autumn-pale);
  color: var(--autumn);
}

/* Naive 按钮统一为樱色 */
.ce-page :deep(.n-button.n-button--primary-type) {
  --n-color: var(--sakura-deep) !important;
  --n-color-hover: var(--sakura-deep-hover) !important;
  --n-color-pressed: var(--sakura-deep-hover) !important;
  --n-color-focus: var(--sakura-deep-hover) !important;
  --n-text-color: var(--on-accent) !important;
  --n-text-color-hover: var(--on-accent) !important;
  --n-text-color-pressed: var(--on-accent) !important;
  --n-text-color-focus: var(--on-accent) !important;
  --n-border: 1px solid var(--sakura-deep) !important;
  --n-border-hover: 1px solid var(--sakura-deep-hover) !important;
  --n-border-pressed: 1px solid var(--sakura-deep-hover) !important;
  --n-border-focus: 1px solid var(--sakura-deep) !important;
}

.ce-page :deep(.n-button.n-button--secondary-type) {
  --n-text-color: var(--sakura-deep) !important;
  --n-text-color-hover: var(--sakura-deep-hover) !important;
  --n-text-color-pressed: var(--sakura-deep-hover) !important;
  --n-text-color-focus: var(--sakura-deep-hover) !important;
  --n-border: 1px solid var(--line-strong, var(--line)) !important;
  --n-border-hover: 1px solid var(--sakura) !important;
  --n-border-pressed: 1px solid var(--sakura) !important;
  --n-border-focus: 1px solid var(--sakura) !important;
}

@media (prefers-reduced-motion: reduce) {
  .ce-pick {
    animation: none;
  }

  .ce-pick img {
    transition: none;
  }
}
</style>
