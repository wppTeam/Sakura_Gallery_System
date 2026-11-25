<template>
  <main class="notif-page">
    <div class="wrap">
      <nav class="notif-crumb" aria-label="面包屑">
        <RouterLink class="notif-crumb-link" to="/">
          <n-icon :component="ArrowBackOutline" :size="14" aria-hidden="true" />
          首页
        </RouterLink>
        <span class="notif-crumb-sep" aria-hidden="true">/</span>
        <span class="notif-crumb-current">通知</span>
      </nav>

      <SectionHeader
        title-id="notifications-title"
        eyebrow="NOTIFICATIONS"
        title="通知"
        description="作品审核结果、复核进度与权限变更都会在这里提醒你。"
        :count="countLabel"
      />

      <div class="notif-toolbar">
        <div class="notif-tabs" role="tablist" aria-label="通知筛选">
          <button
            v-for="tabItem in tabs"
            :key="tabItem.key"
            class="notif-tab"
            :class="{ 'is-active': tab === tabItem.key }"
            type="button"
            role="tab"
            :aria-selected="tab === tabItem.key"
            :aria-controls="'notifications-panel'"
            :id="'notif-tab-' + tabItem.key"
            @click="switchTab(tabItem.key)"
          >
            {{ tabItem.label }}
            <span class="notif-tab-count">{{ tabItem.key === 'all' ? allTotal : unreadCount }}</span>
          </button>
        </div>

        <button
          v-if="unreadCount > 0"
          class="notif-readall"
          type="button"
          :disabled="markingAll"
          @click="handleReadAll"
        >
          {{ markingAll ? '处理中…' : '全部标为已读' }}
        </button>
      </div>

      <section
        id="notifications-panel"
        role="tabpanel"
        :aria-labelledby="'notif-tab-' + tab"
        aria-live="polite"
      >
        <div v-if="error" class="notif-state">
          <EmptyState
            title="通知暂时没有加载出来"
            :description="error"
            action-label="重新加载"
            error
            @action="load(true)"
          />
        </div>

        <div v-else-if="loading" class="notif-loading" aria-hidden="true">
          <div v-for="n in 5" :key="'notif-sk-' + n" class="notif-item notif-item--skeleton">
            <span class="sk-ico" />
            <span class="sk-lines">
              <span class="sk-line sk-line--xs" />
              <span class="sk-line sk-line--lg" />
              <span class="sk-line sk-line--md" />
            </span>
          </div>
        </div>

        <div v-else-if="!items.length" class="notif-state">
          <EmptyState
            :title="emptyTitle"
            :description="emptyDescription"
            :action-label="emptyActionLabel"
            @action="handleEmptyAction"
          />
        </div>

        <template v-else>
          <ul class="notif-list">
            <li v-for="item in items" :key="item.id">
              <button
                class="notif-item"
                :class="{ 'is-unread': !item.is_read }"
                type="button"
                :aria-label="item.is_read ? item.title : '未读：' + item.title"
                @click="handleOpen(item)"
              >
                <span class="notif-ico" :class="'tone--' + metaOf(item.type).tone" aria-hidden="true">
                  <n-icon :component="metaOf(item.type).icon" :size="18" />
                </span>

                <span class="notif-body">
                  <span class="notif-row">
                    <span class="notif-type" :class="'tone-text--' + metaOf(item.type).tone">
                      {{ metaOf(item.type).label }}
                    </span>
                    <span class="notif-time">{{ relativeTime(item.created_at) }}</span>
                  </span>
                  <span class="notif-title">{{ item.title }}</span>
                  <span v-if="item.content" class="notif-content">{{ item.content }}</span>
                  <span class="notif-foot">
                    <span class="notif-abs">{{ formatAbsoluteTime(item.created_at) }}</span>
                    <span v-if="item.related_id" class="notif-go">
                      查看作品
                      <span aria-hidden="true">→</span>
                    </span>
                  </span>
                </span>

                <span v-if="!item.is_read" class="notif-dot" aria-hidden="true" />
              </button>
            </li>
          </ul>

          <div class="notif-more">
            <button
              v-if="loadMoreError"
              type="button"
              class="btn notif-more-btn"
              @click="loadMore"
            >
              加载失败，点击重试
            </button>
            <button
              v-else-if="hasMore"
              type="button"
              class="btn notif-more-btn"
              :disabled="loadingMore"
              @click="loadMore"
            >
              {{ loadingMore ? '加载中…' : '加载更多' }}
            </button>
            <p v-else class="notif-end">已经到底啦</p>
          </div>
        </template>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowBackOutline } from '@vicons/ionicons5'
import {
  getNotifications,
  markAllRead as markAllReadApi,
  markAsRead,
  type NotificationItem,
} from '../api/notification'
import {
  formatAbsoluteTime,
  notificationMeta,
  notificationPath,
  relativeTime,
} from '../utils/notification'
import SectionHeader from '../components/public/SectionHeader.vue'
import EmptyState from '../components/public/EmptyState.vue'

type TabKey = 'all' | 'unread'

const PAGE_SIZE = 20

const router = useRouter()

const tab = ref<TabKey>('all')
const items = ref<NotificationItem[]>([])
const total = ref(0)
const allTotal = ref(0)
const unreadCount = ref(0)
const loading = ref(false)
const loadingMore = ref(false)
const markingAll = ref(false)
const error = ref('')
const loadMoreError = ref('')
const hasMore = computed(() => items.value.length < total.value)
const countLabel = computed(() =>
  loading.value && !items.value.length ? undefined : `${allTotal.value} 条`,
)

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'unread', label: '未读' },
]

const emptyTitle = computed(() =>
  tab.value === 'unread' ? '没有未读通知' : '还没有收到通知',
)
const emptyDescription = computed(() =>
  tab.value === 'unread'
    ? '所有通知都读完啦，新的审核结果与消息会出现在这里。'
    : '作品审核结果、复核进度与权限变更都会在这里提醒你。',
)
const emptyActionLabel = computed(() =>
  tab.value === 'unread' ? '查看全部通知' : '去探索',
)

let selfChange = false

function metaOf(type: string) {
  return notificationMeta(type)
}

function notifyChanged() {
  selfChange = true
  window.dispatchEvent(new CustomEvent('notifications:changed'))
  selfChange = false
}

function onNotificationsChanged() {
  if (selfChange) return
  void load(true)
}

async function load(reset: boolean) {
  if (reset) {
    loading.value = true
    error.value = ''
    loadMoreError.value = ''
  } else {
    loadingMore.value = true
    loadMoreError.value = ''
  }

  try {
    const res = await getNotifications({
      skip: reset ? 0 : items.value.length,
      limit: PAGE_SIZE,
      unread_only: tab.value === 'unread',
    })
    items.value = reset ? res.notifications : [...items.value, ...res.notifications]
    total.value = res.total
    if (tab.value === 'all') allTotal.value = res.total
    unreadCount.value = res.unread_count
  } catch {
    if (reset) error.value = '请检查网络后重试。'
    else loadMoreError.value = '加载失败'
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function switchTab(next: TabKey) {
  if (next === tab.value) return
  tab.value = next
  items.value = []
  total.value = 0
  void load(true)
}

function handleEmptyAction() {
  if (tab.value === 'unread') switchTab('all')
  else void router.push('/explore')
}

async function handleOpen(item: NotificationItem) {
  if (!item.is_read) {
    item.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    if (tab.value === 'unread') {
      items.value = items.value.filter((row) => row.id !== item.id)
      total.value = Math.max(0, total.value - 1)
    }
    try {
      await markAsRead(item.id)
    } catch {
      /* 失败时由服务端轮询纠正，不阻断跳转 */
    }
    notifyChanged()
  }

  const target = notificationPath(item.related_id)
  if (target) await router.push(target)
}

async function handleReadAll() {
  if (markingAll.value) return
  markingAll.value = true
  try {
    await markAllReadApi()
    unreadCount.value = 0
    if (tab.value === 'unread') {
      items.value = []
      total.value = 0
    } else {
      items.value.forEach((item) => {
        item.is_read = true
      })
    }
    notifyChanged()
  } catch {
    error.value = '操作失败，请稍后重试。'
  } finally {
    markingAll.value = false
  }
}

function loadMore() {
  if (loadingMore.value) return
  void load(false)
}

onMounted(() => {
  void load(true)
  window.addEventListener('notifications:changed', onNotificationsChanged)
})

onBeforeUnmount(() => {
  window.removeEventListener('notifications:changed', onNotificationsChanged)
})
</script>

<style scoped>
.notif-page {
  min-height: 100vh;
  padding-block: var(--sp-8) var(--sp-16);
  background: var(--ground);
}

.notif-crumb {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-5);
  color: var(--muted);
  font-size: var(--fs-12);
}

.notif-crumb-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--muted);
  text-decoration: none;
}

.notif-crumb-link:hover {
  color: var(--sakura-deep);
}

.notif-crumb-link:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: 2px;
}

.notif-crumb-sep {
  color: var(--faint);
}

.notif-crumb-current {
  color: var(--ink);
}

.notif-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  margin-bottom: var(--sp-5);
  padding-bottom: var(--sp-3);
  border-bottom: 1px solid var(--line);
}

.notif-tabs {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
}

.notif-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid transparent;
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--muted);
  font-family: var(--font);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition:
    background-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out);
}

.notif-tab:hover {
  background: var(--sakura-mist);
  color: var(--ink);
}

.notif-tab.is-active {
  border-color: var(--line-strong);
  background: var(--surface);
  color: var(--ink);
  box-shadow: var(--shadow-inset);
}

.notif-tab:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: 2px;
}

.notif-tab-count {
  min-width: 18px;
  padding: 0 5px;
  border-radius: var(--r-pill);
  background: var(--sakura-pale);
  color: var(--sakura-deep);
  font-size: 11px;
  line-height: 18px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.notif-tab.is-active .notif-tab-count {
  background: var(--sakura-deep);
  color: var(--on-accent);
}

.notif-readall {
  flex: none;
  padding: 7px 14px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--sakura-deep);
  font-family: var(--font);
  font-size: var(--fs-xs);
  cursor: pointer;
  transition: background-color var(--dur-fast) var(--ease-out);
}

.notif-readall:hover {
  background: var(--sakura-pale);
}

.notif-readall:disabled {
  color: var(--faint);
  cursor: default;
}

.notif-readall:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: 2px;
}

.notif-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.notif-item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  width: 100%;
  padding: var(--sp-4);
  border: 1px solid var(--line);
  border-radius: var(--r-card);
  background: var(--surface);
  color: var(--ink);
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out);
}

.notif-item:hover {
  border-color: var(--line-strong);
  background: var(--surface-soft);
}

.notif-item:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: 2px;
}

.notif-item.is-unread {
  border-color: var(--sakura-pale);
  background: var(--surface);
}

.notif-item.is-unread::before {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 3px;
  border-radius: var(--r-card) 0 0 var(--r-card);
  background: var(--sakura-deep);
  content: '';
}

.notif-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 38px;
  height: 38px;
  border-radius: 50%;
}

.notif-body {
  display: block;
  flex: 1;
  min-width: 0;
}

.notif-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-2);
}

.notif-type {
  font-size: var(--fs-xs);
  font-weight: 500;
  letter-spacing: var(--tracking-wide);
}

.notif-time {
  flex: none;
  color: var(--faint);
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
}

.notif-title {
  display: block;
  margin-top: 3px;
  color: var(--ink);
  font-size: var(--fs-16);
  font-weight: 600;
  line-height: var(--lh-snug);
  word-break: break-word;
}

.notif-content {
  display: -webkit-box;
  margin-top: 4px;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  color: var(--muted);
  font-size: var(--fs-sm);
  line-height: var(--lh-body);
  word-break: break-word;
}

.notif-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  margin-top: 8px;
}

.notif-abs {
  color: var(--faint);
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
}

.notif-go {
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
}

.notif-dot {
  flex: none;
  align-self: center;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--sakura-deep);
}

.notif-state {
  padding-block: var(--sp-8);
}

.notif-loading {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.notif-item--skeleton {
  cursor: default;
  border-color: var(--line);
}

.sk-ico {
  flex: none;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--sakura-mist);
}

.sk-lines {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  padding-top: 3px;
}

.sk-line {
  display: block;
  height: 11px;
  border-radius: var(--r-pill);
  background: linear-gradient(90deg, var(--sakura-mist), var(--ground-deep), var(--sakura-mist));
  background-size: 200% 100%;
  animation: notif-shimmer 1.4s ease-in-out infinite;
}

.sk-line--xs {
  width: 22%;
}

.sk-line--lg {
  width: 58%;
  height: 15px;
}

.sk-line--md {
  width: 84%;
}

@keyframes notif-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.notif-more {
  display: flex;
  justify-content: center;
  margin-top: var(--sp-6);
}

.notif-more-btn {
  min-width: 160px;
}

.notif-end {
  margin: 0;
  color: var(--faint);
  font-size: var(--fs-xs);
}

/* 类型色调 */
.tone--approved {
  background: var(--summer-pale);
  color: var(--summer-accent);
}

.tone--rejected {
  background: var(--sakura-pale);
  color: var(--sakura-deep);
}

.tone--appeal {
  background: var(--winter-pale);
  color: var(--winter-accent);
}

.tone--permission {
  background: var(--autumn-pale);
  color: var(--autumn-accent);
}

.tone--system {
  background: var(--sakura-mist);
  color: var(--muted);
}

.tone-text--approved {
  color: var(--summer-accent);
}

.tone-text--rejected {
  color: var(--sakura-deep);
}

.tone-text--appeal {
  color: var(--winter-accent);
}

.tone-text--permission {
  color: var(--autumn-accent);
}

.tone-text--system {
  color: var(--muted);
}

@media (pointer: coarse) {
  .notif-tab,
  .notif-readall,
  .notif-crumb-link {
    min-height: 44px;
  }

  .notif-item {
    min-height: 44px;
  }
}

@media (max-width: 720px) {
  .notif-page {
    padding-block: var(--sp-4) var(--sp-12);
  }

  .notif-toolbar {
    flex-wrap: wrap;
    align-items: flex-start;
    gap: var(--sp-2);
  }

  .notif-tabs {
    width: 100%;
  }

  .notif-tab {
    flex: 1;
    justify-content: center;
  }

  .notif-readall {
    margin-left: auto;
  }

  .notif-item {
    padding: var(--sp-3);
    gap: 10px;
  }

  .notif-ico {
    width: 32px;
    height: 32px;
  }

  .notif-title {
    font-size: var(--fs-sm);
  }

  .notif-foot {
    align-items: flex-start;
    flex-direction: column;
    gap: 2px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sk-line {
    animation: none;
  }

  .notif-tab,
  .notif-readall,
  .notif-item {
    transition: none;
  }
}
</style>
