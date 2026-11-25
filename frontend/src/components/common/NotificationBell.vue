<template>
  <n-popover
    v-if="auth.isAuthenticated"
    v-model:show="open"
    trigger="click"
    placement="bottom-end"
    :show-arrow="false"
    raw
    :width="panelWidth"
    @update:show="onOpenChange"
  >
    <template #trigger>
      <button
        class="bell-btn"
        type="button"
        :aria-label="unreadDescription"
        aria-haspopup="dialog"
        :aria-expanded="open"
      >
        <n-icon :component="NotificationsOutline" :size="20" aria-hidden="true" />
        <span v-if="unreadCount > 0" class="bell-badge" aria-hidden="true">{{ unreadBadge }}</span>
      </button>
    </template>

    <div class="bell-panel" role="dialog" aria-label="通知">
      <header class="bell-head">
        <div class="bell-head-main">
          <p class="bell-title">通知</p>
          <span v-if="unreadCount > 0" class="bell-unread">{{ unreadCount }} 条未读</span>
        </div>
        <button
          v-if="unreadCount > 0"
          class="bell-all-read"
          type="button"
          :disabled="markingAll"
          @click="handleMarkAllRead"
        >
          {{ markingAll ? '处理中…' : '全部已读' }}
        </button>
      </header>

      <div class="bell-body">
        <template v-if="loading && !items.length">
          <div v-for="n in 3" :key="'bell-sk-' + n" class="bell-item bell-item--skeleton" aria-hidden="true">
            <span class="sk-dot" />
            <span class="sk-lines">
              <span class="sk-line sk-line--sm" />
              <span class="sk-line sk-line--lg" />
            </span>
          </div>
        </template>

        <p v-else-if="error" class="bell-state">
          <span>{{ error }}</span>
          <button class="bell-retry" type="button" @click="loadLatest">重新加载</button>
        </p>

        <p v-else-if="!items.length" class="bell-state">暂时没有新通知</p>

        <ul v-else class="bell-list">
          <li v-for="item in items" :key="item.id">
            <button
              class="bell-item"
              :class="{ 'is-unread': !item.is_read }"
              type="button"
              @click="handleOpenItem(item)"
            >
              <span class="bell-dot" aria-hidden="true" />
              <span class="bell-ico" :class="'tone--' + metaOf(item.type).tone" aria-hidden="true">
                <n-icon :component="metaOf(item.type).icon" :size="15" />
              </span>
              <span class="bell-main">
                <span class="bell-meta">
                  <span class="bell-type" :class="'tone-text--' + metaOf(item.type).tone">
                    {{ metaOf(item.type).label }}
                  </span>
                  <span class="bell-time">{{ relativeTime(item.created_at) }}</span>
                </span>
                <span class="bell-item-title">{{ item.title }}</span>
              </span>
            </button>
          </li>
        </ul>
      </div>

      <footer class="bell-foot">
        <RouterLink class="bell-more" to="/notifications" @click="open = false">
          查看全部通知
          <span aria-hidden="true">→</span>
        </RouterLink>
      </footer>
    </div>
  </n-popover>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NotificationsOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../../stores/auth'
import {
  getNotifications,
  getUnreadCount,
  markAllRead as markAllReadApi,
  markAsRead,
  type NotificationItem,
} from '../../api/notification'
import {
  notificationMeta,
  notificationPath,
  relativeTime,
} from '../../utils/notification'

const auth = useAuthStore()
const router = useRouter()

const open = ref(false)
const loading = ref(false)
const markingAll = ref(false)
const error = ref('')
const items = ref<NotificationItem[]>([])
const unreadCount = ref(0)
const viewportWidth = ref(typeof window === 'undefined' ? 1440 : window.innerWidth)

let pollTimer: ReturnType<typeof setInterval> | null = null

const panelWidth = computed(() => Math.min(380, Math.max(280, viewportWidth.value - 24)))
const unreadBadge = computed(() => (unreadCount.value > 99 ? '99+' : String(unreadCount.value)))
const unreadDescription = computed(() =>
  unreadCount.value > 0 ? `${unreadCount.value} 条未读通知` : '没有未读通知',
)

function metaOf(type: string) {
  return notificationMeta(type)
}

async function fetchUnread() {
  if (!auth.isAuthenticated) return
  try {
    const res = await getUnreadCount()
    unreadCount.value = res.unread_count
  } catch {
    /* 未登录/网络异常时静默，不打扰用户 */
  }
}

async function loadLatest() {
  if (!auth.isAuthenticated) return
  loading.value = true
  error.value = ''
  try {
    const res = await getNotifications({ limit: 6 })
    items.value = res.notifications
    unreadCount.value = res.unread_count
  } catch {
    error.value = '通知加载失败了'
  } finally {
    loading.value = false
  }
}

function onOpenChange(show: boolean) {
  open.value = show
  if (show) void loadLatest()
}

async function handleOpenItem(item: NotificationItem) {
  const target = notificationPath(item.related_id)
  if (!item.is_read) {
    item.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    if (target) {
      // 深链前先标已读：导航会卸载当前页，不等待结果以免丢失跳转
      void markAsRead(item.id).catch(() => {
        /* 失败时由 60s 轮询/下次打开纠正 */
      })
    } else {
      try {
        await markAsRead(item.id)
      } catch {
        /* 同上 */
      }
    }
    notifyChanged()
  }
  open.value = false
  if (target) void router.push(target)
}

async function handleMarkAllRead() {
  if (markingAll.value) return
  markingAll.value = true
  try {
    await markAllReadApi()
    unreadCount.value = 0
    items.value.forEach((item) => {
      item.is_read = true
    })
    notifyChanged()
  } catch {
    error.value = '操作失败，请稍后重试'
  } finally {
    markingAll.value = false
  }
}

function notifyChanged() {
  window.dispatchEvent(new CustomEvent('notifications:changed'))
}

function onViewportResize() {
  viewportWidth.value = window.innerWidth
}

function onNotificationsChanged() {
  void fetchUnread()
  if (open.value) void loadLatest()
}

watch(
  () => auth.isAuthenticated,
  (value) => {
    if (value) {
      void fetchUnread()
      if (open.value) void loadLatest()
    } else {
      open.value = false
      items.value = []
      unreadCount.value = 0
    }
  },
)

onMounted(() => {
  void fetchUnread()
  pollTimer = setInterval(fetchUnread, 60_000)
  window.addEventListener('resize', onViewportResize, { passive: true })
  window.addEventListener('notifications:changed', onNotificationsChanged)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  window.removeEventListener('resize', onViewportResize)
  window.removeEventListener('notifications:changed', onNotificationsChanged)
})
</script>

<style scoped>
.bell-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid transparent;
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--ink);
  cursor: pointer;
  transition:
    background-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out);
}

.bell-btn:hover {
  background: var(--sakura-mist);
  border-color: var(--line);
  color: var(--sakura-deep);
}

.bell-btn:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: 2px;
}

.bell-badge {
  position: absolute;
  top: 1px;
  right: 0;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: var(--r-pill);
  background: var(--sakura-deep);
  color: var(--on-accent);
  font-family: var(--font);
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  box-shadow: 0 0 0 2px var(--ground);
}

.bell-panel {
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-lift);
  color: var(--ink);
}

.bell-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
}

.bell-head-main {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  min-width: 0;
}

.bell-title {
  margin: 0;
  color: var(--ink);
  font-family: var(--font);
  font-size: var(--fs-14);
  font-weight: 600;
}

.bell-unread {
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
}

.bell-all-read {
  padding: 4px 8px;
  border: none;
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--sakura-deep);
  font-family: var(--font);
  font-size: var(--fs-xs);
  cursor: pointer;
}

.bell-all-read:hover {
  background: var(--sakura-pale);
}

.bell-all-read:disabled {
  color: var(--faint);
  cursor: default;
}

.bell-body {
  max-height: 360px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.bell-list {
  margin: 0;
  padding: 4px 0;
  list-style: none;
}

.bell-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 10px 14px;
  border: none;
  border-left: 2px solid transparent;
  background: transparent;
  color: var(--ink);
  text-align: left;
  cursor: pointer;
}

.bell-item:hover {
  background: var(--sakura-mist);
}

.bell-item:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: -3px;
}

.bell-item.is-unread {
  background: var(--sakura-wash);
  border-left-color: var(--sakura);
}

.bell-item.is-unread:hover {
  background: var(--sakura-pale);
}

.bell-dot {
  flex: none;
  width: 6px;
  height: 6px;
  margin-top: 7px;
  border-radius: 50%;
  background: transparent;
}

.bell-item.is-unread .bell-dot {
  background: var(--sakura-deep);
}

.bell-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 28px;
  height: 28px;
  border-radius: 50%;
}

.bell-main {
  display: block;
  min-width: 0;
  flex: 1;
}

.bell-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-2);
}

.bell-type {
  font-size: 11px;
  letter-spacing: 0.02em;
}

.bell-time {
  flex: none;
  color: var(--faint);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.bell-item-title {
  display: -webkit-box;
  margin-top: 2px;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  color: var(--ink);
  font-size: var(--fs-sm);
  line-height: var(--lh-snug);
  word-break: break-word;
}

.bell-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-2);
  margin: 0;
  padding: 28px 16px;
  color: var(--muted);
  font-size: var(--fs-sm);
  text-align: center;
}

.bell-retry {
  padding: 4px 10px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  cursor: pointer;
}

.bell-foot {
  padding: 9px 14px;
  border-top: 1px solid var(--line);
  background: var(--surface-soft);
}

.bell-more {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--sakura-deep);
  font-size: var(--fs-xs);
  text-decoration: none;
}

.bell-more:hover {
  color: var(--sakura-deep-hover);
}

.bell-more:focus-visible {
  outline: 3px solid var(--sakura-deep);
  outline-offset: 2px;
}

/* 色调（类型图标与标签） */
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

/* 骨架 */
.bell-item--skeleton {
  cursor: default;
  border-left-color: transparent;
}

.sk-dot {
  flex: none;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--sakura-mist);
}

.sk-lines {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
  padding-top: 2px;
}

.sk-line {
  display: block;
  height: 10px;
  border-radius: var(--r-pill);
  background: linear-gradient(90deg, var(--sakura-mist), var(--ground-deep), var(--sakura-mist));
  background-size: 200% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
}

.sk-line--sm {
  width: 34%;
}

.sk-line--lg {
  width: 82%;
}

@keyframes sk-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@media (pointer: coarse) {
  .bell-btn {
    width: 44px;
    height: 44px;
  }

  .bell-all-read,
  .bell-more,
  .bell-retry {
    min-height: 44px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sk-line {
    animation: none;
  }

  .bell-btn {
    transition: none;
  }
}
</style>
