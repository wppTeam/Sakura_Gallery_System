<template>
  <header class="site-header" :class="{ 'is-scrolled': scrolled }">
    <div class="wrap header-inner">
      <RouterLink class="brand" to="/" aria-label="视觉百花 · 回到首页">
        <img
          class="brand-logo"
          src="/brand/logo-combo-zh.png"
          alt="视觉百花"
          width="360"
          height="90"
        />
      </RouterLink>

      <nav class="desktop-nav" aria-label="主导航">
        <RouterLink class="nav-link" :class="{ 'is-active': isExplore }" to="/explore">探索</RouterLink>
        <RouterLink class="nav-link" :to="{ path: '/', hash: '#seasons' }">四季</RouterLink>
        <RouterLink class="nav-link" to="/spectrum">光谱</RouterLink>
        <RouterLink class="nav-link" :class="{ 'is-active': isCreate }" to="/create">创作</RouterLink>
      </nav>

      <div class="header-actions">
        <form class="header-search" role="search" @submit.prevent="submitSearch">
          <svg class="search-icon" width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="9" cy="9" r="5.6" stroke="currentColor" stroke-width="1.6" />
            <path d="m13.4 13.4 3.1 3.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          </svg>
          <label class="sr-only" for="header-search-input">搜索作品、标题或标签</label>
          <input
            id="header-search-input"
            v-model="keyword"
            class="search-input"
            type="search"
            placeholder="搜标题、标签或作者"
            autocomplete="off"
            enterkeyhint="search"
          />
        </form>

        <RouterLink class="btn btn--primary header-submit" to="/upload">投稿</RouterLink>

        <NotificationBell />

        <div v-if="auth.isAuthenticated" ref="userMenuRef" class="user-menu">
          <button
            class="user-trigger"
            type="button"
            :aria-expanded="menuOpen"
            aria-haspopup="menu"
            aria-label="账户菜单"
            @click="menuOpen = !menuOpen"
          >
            <span class="avatar" aria-hidden="true">{{ userInitial }}</span>
            <svg class="chevron" width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="m4 6 4 4 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <div v-if="menuOpen" class="user-pop" role="menu">
            <p class="user-name">{{ userName }}</p>
            <RouterLink class="user-item" role="menuitem" to="/my-submissions" @click="menuOpen = false">我的投稿</RouterLink>
            <RouterLink class="user-item" role="menuitem" to="/profile" @click="menuOpen = false">个人中心</RouterLink>
            <RouterLink
              v-if="auth.isAuditor"
              class="user-item"
              role="menuitem"
              to="/admin/dashboard"
              @click="menuOpen = false"
            >
              管理后台
            </RouterLink>
            <button class="user-item user-item--danger" type="button" role="menuitem" @click="handleLogout">
              退出登录
            </button>
          </div>
        </div>

        <div v-else class="guest-actions">
          <RouterLink class="register-cta" to="/register">免费注册</RouterLink>
          <RouterLink class="login-link" to="/login">登录</RouterLink>
        </div>

        <button
          ref="menuTriggerRef"
          class="menu-trigger"
          type="button"
          :aria-expanded="drawerOpen"
          aria-label="打开菜单"
          @click="drawerOpen = true"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M3 6h14M3 10h14M3 14h14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </div>
  </header>

  <Teleport to="body">
    <Transition name="sheet">
      <div
        v-if="drawerOpen"
        ref="drawerEl"
        class="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="站点菜单"
        @keydown.esc="closeDrawer"
        @keydown.tab="trapDrawerFocus"
      >
        <div class="drawer-head wrap">
          <img class="drawer-logo" src="/brand/logo-combo-zh.png" alt="视觉百花" width="360" height="90" />
          <button class="drawer-close" type="button" aria-label="关闭菜单" @click="closeDrawer">
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
              <path d="m5 5 12 12M17 5 5 17" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
            </svg>
          </button>
        </div>

        <nav class="drawer-nav wrap" aria-label="移动端导航">
          <RouterLink class="drawer-link" to="/explore" @click="closeDrawer">
            <span class="drawer-num">01</span>探索
          </RouterLink>
          <RouterLink class="drawer-link" :to="{ path: '/', hash: '#seasons' }" @click="closeDrawer">
            <span class="drawer-num">02</span>四季
          </RouterLink>
          <RouterLink class="drawer-link" to="/spectrum" @click="closeDrawer">
            <span class="drawer-num">03</span>光谱
          </RouterLink>
          <RouterLink class="drawer-link" to="/create" @click="closeDrawer">
            <span class="drawer-num">04</span>创作
          </RouterLink>
          <RouterLink class="drawer-link" to="/upload" @click="closeDrawer">
            <span class="drawer-num">05</span>投稿
          </RouterLink>
        </nav>

        <div class="drawer-foot wrap">
          <form class="drawer-search" role="search" @submit.prevent="submitSearch">
            <label class="sr-only" for="drawer-search-input">搜索作品、标题或标签</label>
            <input
              id="drawer-search-input"
              v-model="keyword"
              class="drawer-search-input"
              type="search"
              placeholder="搜标题、标签或作者"
              autocomplete="off"
              enterkeyhint="search"
            />
            <button class="btn btn--primary" type="submit">搜索</button>
          </form>

          <div class="drawer-auth">
            <template v-if="auth.isAuthenticated">
              <span class="drawer-user">{{ userName }}</span>
              <RouterLink class="drawer-auth-link" to="/notifications" @click="closeDrawer">通知中心</RouterLink>
              <RouterLink class="drawer-auth-link" to="/my-submissions" @click="closeDrawer">我的投稿</RouterLink>
              <RouterLink class="drawer-auth-link" to="/profile" @click="closeDrawer">个人中心</RouterLink>
              <button class="drawer-auth-link" type="button" @click="handleLogout">退出登录</button>
            </template>
            <template v-else>
              <RouterLink class="btn btn--primary" to="/login" @click="closeDrawer">登录 / 注册</RouterLink>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import NotificationBell from '../common/NotificationBell.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const keyword = ref('')
const scrolled = ref(false)
const menuOpen = ref(false)
const drawerOpen = ref(false)
const userMenuRef = ref<HTMLElement | null>(null)
const menuTriggerRef = ref<HTMLElement | null>(null)
const drawerEl = ref<HTMLElement | null>(null)

const isExplore = computed(() => route.path.startsWith('/explore'))
const isCreate = computed(() => route.path.startsWith('/create'))
const userName = computed(() => auth.user?.full_name || auth.user?.email?.split('@')[0] || '同学')
const userInitial = computed(() => userName.value.slice(0, 1))

function submitSearch() {
  const q = keyword.value.trim()
  menuOpen.value = false
  drawerOpen.value = false
  router.push(q ? { path: '/search', query: { q } } : { path: '/search' })
}

function handleLogout() {
  auth.logout()
  menuOpen.value = false
  drawerOpen.value = false
  router.push('/')
}

/* 滚动后顶栏收紧：只改内边距与阴影，不改高度，避免布局抖动 */
function onScroll() {
  scrolled.value = window.scrollY > 12
}

/* 账户菜单：点击外部 / Esc 关闭 */
function onDocumentClick(event: MouseEvent) {
  if (!menuOpen.value) return
  const root = userMenuRef.value
  if (root && !root.contains(event.target as Node)) menuOpen.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    menuOpen.value = false
    if (drawerOpen.value) closeDrawer()
  }
}

function closeDrawer() {
  drawerOpen.value = false
  // 无障碍：关闭后把焦点还给打开抽屉的按钮
  window.setTimeout(() => menuTriggerRef.value?.focus(), 0)
}

/* 焦点陷阱：Tab / Shift+Tab 在抽屉内循环，不落到背后的页面 */
function trapDrawerFocus(event: KeyboardEvent) {
  const root = drawerEl.value
  if (!root) return
  const focusable = [
    ...root.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ].filter((el) => el.offsetParent !== null || el === document.activeElement)
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const active = document.activeElement as HTMLElement | null
  if (event.shiftKey && (active === first || !root.contains(active))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || !root.contains(active))) {
    event.preventDefault()
    first.focus()
  }
}

watch(drawerOpen, async (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
  if (open) {
    await nextTick()
    const first = document.querySelector<HTMLElement>('.drawer-link')
    first?.focus()
  }
})

watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false
    drawerOpen.value = false
  },
)

watch(menuOpen, async (open) => {
  if (!open) return
  await nextTick()
  document.querySelector<HTMLElement>('.user-pop .user-item')?.focus()
})

onMounted(() => {
  onScroll()
  window.addEventListener('scroll', onScroll, { passive: true })
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.site-header {
  position: sticky;
  top: 0;
  z-index: var(--z-nav);
  background: rgba(255, 246, 249, 0.84);
  border-bottom: 1px solid transparent;
  backdrop-filter: blur(12px) saturate(1.1);
  -webkit-backdrop-filter: blur(12px) saturate(1.1);
  transition: background-color var(--dur) var(--ease-out), border-color var(--dur) var(--ease-out);
}

.site-header.is-scrolled {
  background: rgba(255, 246, 249, 0.92);
  border-bottom-color: var(--line);
}

.header-inner {
  display: flex;
  align-items: center;
  gap: 24px;
  height: var(--nav-h);
}

.brand {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.brand-logo {
  width: auto;
  height: 30px;
  transition: height var(--dur) var(--ease-out), opacity var(--dur-fast) var(--ease-out);
}

.site-header.is-scrolled .brand-logo {
  height: 26px;
}

.brand:hover .brand-logo {
  opacity: 0.82;
}

.desktop-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
}

.nav-link {
  position: relative;
  padding: 8px 14px;
  border-radius: var(--r-pill);
  color: var(--ink);
  font-size: var(--fs-sm);
  font-weight: 500;
  transition: color var(--dur-fast) var(--ease-out), background-color var(--dur-fast) var(--ease-out);
}

.nav-link::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 2px;
  width: 16px;
  height: 2px;
  border-radius: 2px;
  background: var(--sakura);
  opacity: 0;
  transform: translateX(-50%) scaleX(0.4);
  transition: opacity var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}

.nav-link:hover {
  color: var(--sakura-deep);
  background: var(--sakura-mist);
}

.nav-link.is-active {
  color: var(--sakura-deep);
}

.nav-link.is-active::after,
.nav-link:hover::after {
  opacity: 1;
  transform: translateX(-50%) scaleX(1);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.header-search {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 232px;
  height: 40px;
  padding: 0 14px;
  border: 1px solid transparent;
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--muted);
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}

.header-search:focus-within {
  border-color: var(--sakura);
  box-shadow: var(--focus-ring);
}

.search-icon {
  flex-shrink: 0;
  color: var(--faint);
}

.search-input {
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-size: var(--fs-sm);
  outline: none;
}

.search-input::placeholder {
  color: var(--faint);
}

.search-input::-webkit-search-cancel-button {
  display: none;
}

.header-submit {
  min-height: 38px;
  padding: 0 20px;
}

/* 触屏上按钮高度提到 44px，保证可点性 */
@media (pointer: coarse) {
  .header-submit {
    min-height: 44px;
  }
}

.login-link {
  padding: 8px 12px;
  color: var(--ink);
  font-size: var(--fs-sm);
  font-weight: 500;
}

.login-link:hover {
  color: var(--sakura-deep);
}

/* 开放注册后，游客在顶栏直接看到注册入口（移动端收进抽屉） */
.guest-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.register-cta {
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  padding: 0 16px;
  border-radius: var(--r-pill);
  background: var(--sakura);
  color: #fff;
  font-size: var(--fs-sm);
  font-weight: 600;
  letter-spacing: 0.01em;
  transition:
    background-color var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out);
}

.register-cta:hover {
  background: var(--sakura-deep);
  transform: translateY(-1px);
}

@media (pointer: coarse) {
  .register-cta {
    min-height: 44px;
  }
}

.user-menu {
  position: relative;
}

.user-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px 3px 3px;
  border-radius: var(--r-pill);
  color: var(--muted);
  transition: background-color var(--dur-fast) var(--ease-out);
}

.user-trigger:hover {
  background: var(--sakura-mist);
}

.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--sakura-pale);
  color: var(--sakura-deep);
  font-family: var(--display);
  font-size: 15px;
}

.chevron {
  color: var(--faint);
}

.user-pop {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  min-width: 180px;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-lift);
  animation: pop-in 180ms var(--ease-out) both;
}

@keyframes pop-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.user-name {
  padding: 8px 12px 10px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 6px;
  overflow: hidden;
  color: var(--muted);
  font-size: var(--fs-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-item {
  display: block;
  width: 100%;
  padding: 9px 12px;
  border-radius: var(--r-sm);
  color: var(--ink);
  font-size: var(--fs-sm);
  text-align: left;
  transition: background-color var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}

.user-item:hover,
.user-item:focus-visible {
  background: var(--sakura-mist);
  color: var(--sakura-deep);
}

.user-item--danger {
  color: var(--muted);
}

.menu-trigger {
  display: none;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  color: var(--ink);
}

.menu-trigger:hover {
  background: var(--sakura-mist);
}

/* ---------- 移动端全屏抽屉 ---------- */
.drawer {
  position: fixed;
  inset: 0;
  z-index: var(--z-drawer);
  display: flex;
  flex-direction: column;
  background: var(--ground);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--nav-h);
}

.drawer-logo {
  width: auto;
  height: 28px;
}

.drawer-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  color: var(--ink);
}

.drawer-close:hover {
  background: var(--sakura-mist);
}

.drawer-nav {
  display: flex;
  flex-direction: column;
  padding-top: 12px;
}

.drawer-link {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 18px 0;
  border-bottom: 1px solid var(--line);
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(30px, 8vw, 40px);
  letter-spacing: var(--tracking-wide);
  line-height: 1.15;
}

.drawer-link:hover {
  color: var(--sakura-deep);
}

.drawer-num {
  color: var(--sakura);
  font-family: var(--font);
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.08em;
}

.drawer-foot {
  margin-top: auto;
  padding-bottom: calc(28px + env(safe-area-inset-bottom, 0px));
}

.drawer-search {
  display: flex;
  gap: 10px;
  margin-top: 28px;
}

.drawer-search-input {
  flex: 1;
  min-width: 0;
  height: 46px;
  padding: 0 18px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--ink);
  font-size: var(--fs-sm);
  outline: none;
}

.drawer-search-input:focus {
  border-color: var(--sakura);
  box-shadow: var(--focus-ring);
}

.drawer-auth {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 20px;
  margin-top: 22px;
}

.drawer-user {
  color: var(--muted);
  font-size: var(--fs-sm);
}

.drawer-auth-link {
  padding: 6px 0;
  color: var(--ink);
  font-size: var(--fs-sm);
}

.drawer-auth-link:hover {
  color: var(--sakura-deep);
}

.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out);
}

.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
  transform: translateY(-12px);
}

/* ---------- 响应式 ---------- */
@media (max-width: 960px) {
  .header-search {
    width: 190px;
  }

  .desktop-nav {
    display: none;
  }

  .menu-trigger {
    display: inline-flex;
  }
}

@media (max-width: 720px) {
  .header-inner {
    gap: 12px;
  }

  .header-actions {
    gap: 8px;
  }

  .header-search,
  .login-link,
  .guest-actions,
  .header-submit {
    display: none;
  }

  .menu-trigger {
    display: inline-flex;
  }

  .brand-logo {
    height: 26px;
  }

  .site-header.is-scrolled .brand-logo {
    height: 24px;
  }
}
</style>
