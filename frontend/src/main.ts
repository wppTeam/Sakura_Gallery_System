/**
 * 应用入口
 *
 * 样式顺序有依赖关系：先加载旧版全局样式（`assets/styles/main.css`，含 Tailwind 与
 * admin 页面仍在使用的遗留类），再加载公共端设计系统，确保新 token 覆盖旧值；
 * 页面级样式（detail / search / admin-review）由对应视图自行引入。
 */
import { createApp } from 'vue'

import './assets/styles/main.css'
import './styles/fonts.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/motion.css'

import App from './App.vue'
import router from './router'
import pinia from './stores'
import { vPermission } from './directives/permission'
import { vReveal } from './directives/reveal'

const app = createApp(App)

// 全局指令
app.directive('permission', vPermission)
app.directive('reveal', vReveal)

// Naive UI 组件由 unplugin-vue-components + NaiveUiResolver 在构建期按需引入
// （见 vite.config.ts），不再在这里 app.use(naive) 全量注册。
app.use(pinia)
app.use(router)

app.mount('#app')
