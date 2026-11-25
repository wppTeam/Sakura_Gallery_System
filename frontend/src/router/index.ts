/**
 * 路由配置。
 *
 * 公开端：`/` 首页、`/explore` 探索、`/photo/:id` 详情、`/search` 搜索、`/login` 登录，
 * 以及兜底的 404。这些页面即使未登录也必须可访问（此前 catch-all 缺少 meta 会被默认
 * 拒绝规则重定向到登录页——这里用显式 `requiresAuth: false` 白名单修正）。
 *
 * 登录后的投稿 / 个人中心 / 标注 / 管理后台保持原有路径与路由名不变，admin 页面依赖
 * 这些 name 做跳转，重写时不要改名。
 */
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/RegisterView.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    component: () => import('../layouts/PublicLayout.vue'),
    children: [
      {
        path: '',
        name: 'Home',
        component: () => import('../views/HomeView.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: 'explore',
        name: 'Explore',
        component: () => import('../views/ExploreView.vue'),
        meta: { requiresAuth: false },
      },
      {
        // 旧入口兼容：/gallery 整体交接给 /explore；带 search 的旧链接直接进搜索结果页
        path: 'gallery',
        name: 'Gallery',
        redirect: (to) =>
          to.query.search
            ? { path: '/search', query: { q: String(to.query.search) } }
            : { path: '/explore', query: to.query },
        meta: { requiresAuth: false },
      },
      {
        path: 'photo/:id',
        name: 'PhotoDetail',
        component: () => import('../views/PhotoDetailView.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: 'collections',
        name: 'Collections',
        component: () => import('../views/CollectionsIndexView.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: 'collections/:slug',
        name: 'CollectionDetail',
        component: () => import('../views/CollectionView.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: 'u/:username',
        name: 'Creator',
        component: () => import('../views/CreatorView.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: 'creators',
        name: 'Creators',
        component: () => import('../views/CreatorsView.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: 'spectrum',
        name: 'Spectrum',
        component: () => import('../views/SpectrumView.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: 'terms',
        name: 'Terms',
        component: () => import('../views/LegalView.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: 'privacy',
        name: 'Privacy',
        component: () => import('../views/LegalView.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: 'search',
        name: 'Search',
        component: () => import('../views/SearchView.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: 'favorites',
        name: 'Favorites',
        component: () => import('../views/FavoritesView.vue'),
        meta: { requiresAuth: true },
      },
      {
        path: 'notifications',
        name: 'Notifications',
        component: () => import('../views/NotificationsView.vue'),
        meta: { requiresAuth: true },
      },
      {
        path: 'my-collections',
        name: 'MyCollections',
        component: () => import('../views/MyCollectionsView.vue'),
        meta: { requiresAuth: true },
      },
      {
        path: 'my-collections/:id/edit',
        name: 'CollectionEdit',
        component: () => import('../views/CollectionEditorView.vue'),
        meta: { requiresAuth: true },
      },
      {
        path: 'create',
        name: 'Create',
        component: () => import('../views/CreateView.vue'),
        meta: { requiresAuth: true },
      },
    ],
  },
  {
    path: '/upload',
    name: 'Upload',
    component: () => import('../views/Upload.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/my-submissions',
    name: 'MySubmissions',
    component: () => import('../views/MySubmissions.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('../views/Profile.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/tagging',
    name: 'TaggingWorkspace',
    component: () => import('../views/TaggingWorkspace.vue'),
    meta: { requiresAuth: true, requiresTagger: true },
  },
  {
    path: '/admin',
    component: () => import('../layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresAuditor: true },
    children: [
      { path: '', redirect: '/admin/dashboard' },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/admin/Dashboard.vue'),
        meta: { requiresAuth: true, requiresAuditor: true },
      },
      {
        path: 'review',
        name: 'PhotoReview',
        component: () => import('../views/admin/PhotoReview.vue'),
        meta: { requiresAuth: true, requiresAuditor: true },
      },
      {
        path: 'reports',
        name: 'Reports',
        component: () => import('../views/admin/Reports.vue'),
        meta: { requiresAuth: true, requiresAuditor: true },
      },
      {
        path: 'appeals',
        name: 'Appeals',
        component: () => import('../views/admin/Appeals.vue'),
        meta: { requiresAuth: true, requiresAuditor: true },
      },
      {
        path: 'ai-usage',
        name: 'AiUsage',
        component: () => import('../views/admin/AiUsage.vue'),
        meta: { requiresAuth: true, requiresAdmin: true },
      },
      {
        path: 'tags',
        name: 'TagManagement',
        component: () => import('../views/admin/TagManagement.vue'),
        meta: { requiresAuth: true, requiresAuditor: true },
      },
      {
        path: 'taxonomy',
        name: 'TaxonomyManagement',
        component: () => import('../views/admin/TaxonomyManagement.vue'),
        meta: { requiresAuth: true, requiresAuditor: true },
      },
      {
        path: 'tagging-tasks',
        name: 'TaggingTaskManagement',
        component: () => import('../views/admin/TaggingTaskManagement.vue'),
        meta: { requiresAuth: true, requiresAuditor: true },
      },
      {
        path: 'import',
        name: 'PhotoImport',
        component: () => import('../views/admin/PhotoImport.vue'),
        meta: { requiresAuth: true, requiresAdmin: true },
      },
      {
        path: 'users',
        name: 'UserManagement',
        component: () => import('../views/admin/UserManagement.vue'),
        meta: { requiresAuth: true, requiresAdmin: true },
      },
      {
        path: 'settings',
        name: 'SystemSettings',
        component: () => import('../views/admin/SystemSettings.vue'),
        meta: { requiresAuth: true, requiresAdmin: true },
      },
      {
        path: 'audit-logs',
        name: 'AuditLog',
        component: () => import('../views/admin/AuditLog.vue'),
        meta: { requiresAuth: true, requiresAdmin: true },
      },
      {
        path: 'database',
        name: 'DatabaseManagement',
        component: () => import('../views/admin/DatabaseManagement.vue'),
        meta: { requiresAuth: true, requiresAdmin: true },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/NotFound.vue'),
    meta: { requiresAuth: false },
  },
]

const ROUTE_TITLES: Record<string, string> = {
  Home: '视觉百花 · 北化学生自建开源创作平台',
  Explore: '探索作品 · 视觉百花',
  Gallery: '探索作品 · 视觉百花',
  PhotoDetail: '作品详情 · 视觉百花',
  Creator: '创作者 · 视觉百花',
  Collections: '策展专题 · 视觉百花',
  CollectionDetail: '策展专题 · 视觉百花',
  Search: '检索 · 视觉百花',
  Creators: '发现创作者 · 视觉百花',
  Spectrum: '樱色光谱 · 视觉百花',
  Terms: '服务条款 · 视觉百花',
  Privacy: '隐私政策 · 视觉百花',
  Favorites: '我的收藏 · 视觉百花',
  Notifications: '通知中心 · 视觉百花',
  MyCollections: '我的策展 · 视觉百花',
  CollectionEdit: '编辑策展 · 视觉百花',
  Create: 'AI 创作 · 视觉百花',
  Upload: '投稿 · 视觉百花',
  MySubmissions: '我的投稿 · 视觉百花',
  Profile: '个人中心 · 视觉百花',
  Login: '登录 · 视觉百花',
  Register: '注册 · 视觉百花',
  TaggingWorkspace: '标注工作台 · 视觉百花后台',
  Dashboard: '仪表盘 · 视觉百花后台',
  PhotoReview: '审核队列 · 视觉百花后台',
  AiUsage: 'AI 成本 · 视觉百花后台',
  Reports: '举报处理 · 视觉百花后台',
  Appeals: '复核申诉 · 视觉百花后台',
  NotFound: '页面未找到 · 视觉百花',
}

const DEFAULT_TITLE = '视觉百花 · 北化学生自建开源创作平台'

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) return savedPosition
    // 站内锚点（四季 / 光的一日 / 樱色光谱 / 最新作品）滚动时给 sticky 顶栏留出空间
    if (to.hash) return { el: to.hash, top: 84 }
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  // 硬刷新/直接打开受保护路由时，本地 token 已存在但用户信息仍在异步回填。
  // 必须先等会话恢复完成，否则 isAdmin/isAuditor 会误判为 false 而把人踢走。
  await authStore.whenReady()

  // 只有显式声明 requiresAuth: false 的页面才允许匿名访问，其余默认需要登录
  const isPublic = to.meta.requiresAuth === false
  const requiresAdmin = to.meta.requiresAdmin === true
  const requiresAuditor = to.meta.requiresAuditor === true
  const requiresTagger = to.meta.requiresTagger === true

  if (!isPublic && !authStore.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (requiresAdmin && !authStore.isAdmin) {
    return authStore.isAuditor ? '/admin/dashboard' : '/'
  }
  if (requiresAuditor && !authStore.isAuditor) {
    return '/'
  }
  if (requiresTagger && !authStore.isTagger) {
    return '/'
  }
  if ((to.path === '/login' || to.path === '/register') && authStore.isAuthenticated) {
    return '/'
  }
  return true
})

router.afterEach((to) => {
  document.title = ROUTE_TITLES[String(to.name)] || DEFAULT_TITLE
})

export default router
