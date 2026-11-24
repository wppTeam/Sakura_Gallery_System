<template>
  <main class="myc-page">
    <div class="wrap myc-shell">
      <nav class="myc-crumb" aria-label="面包屑">
        <RouterLink class="myc-crumb-link" to="/">首页</RouterLink>
        <span class="myc-crumb-sep" aria-hidden="true">/</span>
        <RouterLink class="myc-crumb-link" to="/profile">个人中心</RouterLink>
        <span class="myc-crumb-sep" aria-hidden="true">/</span>
        <span class="myc-crumb-current">我的策展</span>
      </nav>

      <header class="myc-head">
        <div class="myc-head-copy">
          <p class="eyebrow">MY CURATIONS</p>
          <h1 class="myc-title">我的策展</h1>
          <p class="myc-lead">
            把散落的照片收进一本手账：起标题、写引言、排顺序。发布后，它就是一条属于你的观看路线。
          </p>
        </div>
        <div class="myc-head-actions">
          <RouterLink class="myc-text-link" to="/profile">个人中心</RouterLink>
          <n-button class="myc-create-btn" type="primary" round @click="openCreate">
            <template #icon>
              <n-icon :component="AddOutline" />
            </template>
            新建专辑
          </n-button>
        </div>
      </header>

      <div v-if="loading" class="myc-grid" aria-busy="true" aria-label="正在加载我的专辑">
        <div v-for="index in 6" :key="index" class="myc-card myc-skeleton">
          <div class="myc-skeleton-cover" />
          <div class="myc-skeleton-body">
            <div class="myc-skeleton-line is-title" />
            <div class="myc-skeleton-line" />
          </div>
        </div>
      </div>

      <div v-else-if="error" class="myc-state">
        <EmptyState
          title="我的专辑暂时没有加载出来"
          :description="error"
          action-label="重新加载"
          error
          @action="loadCollections()"
        />
      </div>

      <div v-else-if="!items.length" class="myc-state">
        <EmptyState
          title="还没有策展专辑"
          description="像做一本手账那样，挑几张自己的作品，写下标题和引言，排好顺序。"
          action-label="新建第一本专辑"
          @action="openCreate"
        />
      </div>

      <template v-else>
        <p class="myc-count">共 {{ items.length }} 本专辑</p>
        <ul class="myc-grid">
          <li v-for="item in items" :key="item.id" class="myc-card">
            <RouterLink
              class="myc-cover"
              :to="item.status === 'published' ? `/collections/${item.slug}` : `/my-collections/${item.id}/edit`"
              :aria-label="`打开专辑 ${item.title}`"
            >
              <img
                v-if="coverUrl(item)"
                class="myc-cover-img"
                :src="coverUrl(item)"
                :alt="`${item.title} 封面`"
                loading="lazy"
                decoding="async"
              />
              <span v-else class="myc-cover-empty" aria-hidden="true">
                <n-icon :component="ImagesOutline" :size="34" />
              </span>
              <span class="myc-status" :class="`is-${item.status}`">
                {{ item.status === 'draft' ? '草稿' : '已发布' }}
              </span>
            </RouterLink>

            <div class="myc-body">
              <h2 class="myc-card-title">{{ item.title }}</h2>
              <p v-if="item.subtitle" class="myc-card-sub">{{ item.subtitle }}</p>
              <p class="myc-card-meta">
                {{ item.photoCount }} 张作品
                <span v-if="item.updatedAt" class="myc-card-date">{{ formatDate(item.updatedAt, 'YYYY-MM-DD') }} 更新</span>
              </p>
            </div>

            <div class="myc-actions">
              <n-button size="small" secondary round class="myc-action" @click="editCollection(item)">
                <template #icon>
                  <n-icon :component="PencilOutline" />
                </template>
                编辑
              </n-button>
              <n-button size="small" tertiary round class="myc-action is-danger" @click="askDelete(item)">
                <template #icon>
                  <n-icon :component="TrashOutline" />
                </template>
                删除
              </n-button>
            </div>
          </li>
        </ul>
      </template>
    </div>

    <n-modal
      v-model:show="createOpen"
      preset="card"
      class="myc-modal"
      :bordered="false"
      :mask-closable="!creating"
      title="新建专辑"
    >
      <p class="myc-modal-lead">
        先取个名字，创建后进入编辑页挑作品、排顺序。标题 60 字以内，副标题 100 字，引言 500 字。
      </p>
      <n-form ref="formRef" :model="createForm" :rules="createRules" label-placement="top" require-mark-placement="right-hanging">
        <n-form-item label="标题" path="title">
          <n-input v-model:value="createForm.title" maxlength="60" show-count placeholder="例如：在昌平的四季里散步" />
        </n-form-item>
        <n-form-item label="副标题" path="subtitle">
          <n-input v-model:value="createForm.subtitle" maxlength="100" show-count placeholder="一句话说明这本手账（可选）" />
        </n-form-item>
        <n-form-item label="引言" path="description">
          <n-input
            v-model:value="createForm.description"
            type="textarea"
            :rows="4"
            maxlength="500"
            show-count
            placeholder="为什么把这些画面放在一起？（可选）"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="myc-modal-footer">
          <n-button secondary :disabled="creating" @click="createOpen = false">取消</n-button>
          <n-button type="primary" :loading="creating" @click="submitCreate">创建并继续编辑</n-button>
        </div>
      </template>
    </n-modal>
  </main>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDialog, useMessage, type FormInst, type FormRules } from 'naive-ui'
import { AddOutline, ImagesOutline, PencilOutline, TrashOutline } from '@vicons/ionicons5'
import EmptyState from '../components/public/EmptyState.vue'
import {
  createCollection,
  deleteCollection,
  fetchMyCollections,
  type MyCollection,
} from '../api/collections'
import { formatDate } from '../utils/format'

const DEFAULT_TITLE = '我的策展 · 视觉百花 Sakura Gallery'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const items = ref<MyCollection[]>([])
const loading = ref(true)
const error = ref('')
const createOpen = ref(false)
const creating = ref(false)
const formRef = ref<FormInst | null>(null)

const createForm = reactive({ title: '', subtitle: '', description: '' })
const createRules: FormRules = {
  title: [
    { required: true, message: '请填写专辑标题', trigger: ['input', 'blur'] },
    { max: 60, message: '标题最多 60 个字', trigger: 'input' },
  ],
  subtitle: [{ max: 100, message: '副标题最多 100 个字', trigger: 'input' }],
  description: [{ max: 500, message: '引言最多 500 个字', trigger: 'input' }],
}

function coverUrl(item: MyCollection): string {
  return item.cover?.thumbUrl || item.cover?.imageUrl || ''
}

function describeError(e: unknown): string {
  const status = (e as { response?: { status?: number } })?.response?.status
  if (status === 401) return '登录已过期，请重新登录后再试。'
  if (status === 403) return '没有权限查看这些专辑。'
  if (!status) return '网络连接失败，请检查网络后重试。'
  return `专辑加载失败（HTTP ${status}），请稍后重试。`
}

async function loadCollections() {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchMyCollections()
    items.value = data.items
  } catch (e) {
    error.value = describeError(e)
    console.warn('[my-collections] 加载失败', e)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.title = ''
  createForm.subtitle = ''
  createForm.description = ''
  createOpen.value = true
}

async function submitCreate() {
  if (creating.value) return
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  creating.value = true
  try {
    const created = await createCollection({
      title: createForm.title.trim(),
      subtitle: createForm.subtitle.trim(),
      description: createForm.description.trim(),
    })
    message.success('专辑已创建，去挑作品吧')
    createOpen.value = false
    router.push(`/my-collections/${created.id}/edit`)
  } catch (e) {
    message.error(describeError(e))
    console.warn('[my-collections] 创建失败', e)
  } finally {
    creating.value = false
  }
}

function editCollection(item: MyCollection) {
  router.push(`/my-collections/${item.id}/edit`)
}

function askDelete(item: MyCollection) {
  dialog.warning({
    title: '删除专辑',
    content: `确定删除《${item.title}》吗？专辑里的作品不会被删除，只是不再属于这本手账。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteCollection(item.id)
        items.value = items.value.filter((row) => row.id !== item.id)
        message.success('专辑已删除')
      } catch (e) {
        message.error(describeError(e))
        console.warn('[my-collections] 删除失败', e)
      }
    },
  })
}

onMounted(() => {
  document.title = DEFAULT_TITLE
  void loadCollections()
})

onBeforeUnmount(() => {
  document.title = '视觉百花 Sakura Gallery'
})
</script>

<style scoped>
.myc-page {
  padding: clamp(18px, 3vw, 34px) 0 clamp(56px, 8vw, 100px);
}

.myc-crumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.myc-crumb-link {
  color: var(--muted);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out);
}

.myc-crumb-link:hover {
  color: var(--sakura-deep);
}

.myc-crumb-sep {
  color: var(--faint);
}

.myc-crumb-current {
  color: var(--ink);
}

.myc-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  margin: 22px 0 26px;
}

.myc-title {
  margin: 6px 0 10px;
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(40px, 4.4vw, 58px);
  font-weight: 400;
  letter-spacing: 0.02em;
  line-height: 1.1;
}

.myc-lead {
  max-width: var(--measure);
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-body);
  line-height: var(--lh-body);
}

.myc-head-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.myc-text-link {
  color: var(--muted);
  font-size: var(--fs-sm);
  text-decoration: none;
  transition: color var(--dur-fast) var(--ease-out);
}

.myc-text-link:hover {
  color: var(--sakura-deep);
}

.myc-create-btn {
  height: 44px;
  padding: 0 22px;
  border-radius: var(--r-pill);
  font-weight: 600;
}

.myc-count {
  margin: 0 0 14px;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.myc-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--gap);
  margin: 0;
  padding: 0;
  list-style: none;
}

.myc-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.myc-cover {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 4 / 3;
  padding: 16px;
  background: var(--sakura-wash);
  text-decoration: none;
}

.myc-cover-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: var(--r-sm);
}

.myc-cover-empty {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  border: 1px dashed var(--line-strong);
  border-radius: var(--r-sm);
  color: var(--faint);
}

.myc-status {
  position: absolute;
  top: 12px;
  left: 12px;
  padding: 3px 10px;
  border-radius: var(--r-pill);
  font-size: var(--fs-xs);
  font-weight: 600;
  line-height: 1.4;
}

.myc-status.is-published {
  background: var(--summer-pale);
  color: var(--summer);
}

.myc-status.is-draft {
  background: var(--autumn-pale);
  color: var(--autumn);
}

.myc-body {
  flex: 1;
  padding: 14px 16px 8px;
}

.myc-card-title {
  margin: 0 0 6px;
  overflow: hidden;
  color: var(--ink);
  font-family: var(--display);
  font-size: 22px;
  font-weight: 400;
  line-height: var(--lh-tight);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.myc-card-sub {
  margin: 0 0 8px;
  overflow: hidden;
  color: var(--muted);
  font-size: var(--fs-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.myc-card-meta {
  margin: 0;
  color: var(--faint);
  font-size: var(--fs-xs);
}

.myc-card-date {
  margin-left: 8px;
}

.myc-actions {
  display: flex;
  gap: 8px;
  padding: 10px 16px 16px;
}

.myc-action {
  --n-height: 32px !important;
  padding-inline: 16px !important;
  font-size: var(--fs-xs) !important;
  font-weight: 600 !important;
}

.myc-action:focus-visible,
.myc-text-link:focus-visible,
.myc-crumb-link:focus-visible,
.myc-cover:focus-visible {
  outline: 3px solid var(--sakura);
  outline-offset: 2px;
}

.myc-action.is-danger {
  color: var(--sakura-deep);
}

.myc-state {
  padding: clamp(28px, 5vw, 56px) 0;
}

.myc-modal-lead {
  margin: 0 0 16px;
  color: var(--muted);
  font-size: var(--fs-sm);
  line-height: 1.7;
}

.myc-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.myc-skeleton {
  animation: myc-pulse 1.4s ease-in-out infinite;
}

.myc-skeleton-cover {
  aspect-ratio: 4 / 3;
  background: var(--sakura-mist);
}

.myc-skeleton-body {
  padding: 16px;
}

.myc-skeleton-line {
  height: 12px;
  margin-top: 10px;
  border-radius: var(--r-pill);
  background: var(--surface-warm);
}

.myc-skeleton-line.is-title {
  width: 62%;
  height: 18px;
  margin-top: 0;
}

@keyframes myc-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}

@media (max-width: 1080px) {
  .myc-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .myc-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .myc-head {
    align-items: flex-start;
  }

  .myc-head-actions {
    width: 100%;
    justify-content: space-between;
  }

  .myc-create-btn {
    flex: 1;
    justify-content: center;
  }
}

@media (prefers-reduced-motion: reduce) {
  .myc-skeleton {
    animation: none;
  }
}

/* Naive 按钮统一为樱色（页面内 + teleport 弹窗） */
.myc-page :deep(.n-button.n-button--primary-type),
:global(.myc-modal) .n-button.n-button--primary-type {
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

.myc-page :deep(.n-button.n-button--secondary-type),
:global(.myc-modal) .n-button.n-button--secondary-type {
  --n-text-color: var(--sakura-deep) !important;
  --n-text-color-hover: var(--sakura-deep-hover) !important;
  --n-text-color-pressed: var(--sakura-deep-hover) !important;
  --n-text-color-focus: var(--sakura-deep-hover) !important;
  --n-border: 1px solid var(--line-strong, var(--line)) !important;
  --n-border-hover: 1px solid var(--sakura) !important;
  --n-border-pressed: 1px solid var(--sakura) !important;
  --n-border-focus: 1px solid var(--sakura) !important;
}

/* 弹窗宽度：默认过宽 */
:global(.myc-modal) {
  width: min(92vw, 560px) !important;
}
:global(.myc-modal) .n-card-header__main {
  font-family: var(--display);
  font-size: 22px;
  letter-spacing: 0.01em;
}
:global(.myc-modal) .n-form-item-label {
  font-weight: 600;
}
:global(.myc-modal) .n-input,
:global(.myc-modal) .n-base-selection {
  --n-border-radius: var(--r-sm) !important;
}
</style>
