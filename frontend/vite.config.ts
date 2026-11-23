import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // 按需引入 Naive UI：模板里的 <n-xxx> 在构建期自动变成具体组件 import，
    // 从而不再需要 main.ts 里的 `app.use(naive)` 全量注册（它会让 naive-ui
    // 整个 barrel 进主 chunk，2c4g 小机器上首屏 JS 白付 ~200KB gzip）。
    // 已显式 import 的组件不受影响（插件只处理模板中未解析的标签）。
    Components({
      resolvers: [NaiveUiResolver()],
      dts: false,
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // 拆出稳定 vendor，让浏览器的长缓存真正生效：
        // 业务代码变更不再让 naive / echarts / vue 运行时重新下载。
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          // echarts 只在后台 Dashboard 用，单独成 chunk，公共端首屏不下载。
          if (id.includes('echarts') || id.includes('vue-echarts')) return 'vendor-echarts'
          if (id.includes('@vicons')) return 'vendor-icons'
          if (id.includes('/vue/') || id.includes('vue-router') || id.includes('/pinia/')) {
            return 'vendor-vue'
          }
          // naive-ui 及其运行时依赖不手动分组：交给 Rollup 按动态路由切分，
          // 否则会把「只有后台数据表格才用」的组件也塞进公共端首屏 chunk。
          const naiveDeps = ['naive-ui', 'vueuc', 'seemly', 'css-render', '@css-render',
            'async-validator', 'vdirs', 'evtd', 'vooks', 'treemate', 'date-fns']
          if (naiveDeps.some((dep) => id.includes(`/${dep}/`) || id.includes(`\\${dep}\\`)
            || id.includes(`node_modules/${dep}/`))) return
          return 'vendor'
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  // 本地验证生产构建产物用（npm run preview）：同样把 /api 代理到后端，
  // 这样拆包/按需引入的改动能在真实 dist 上验收，而不是只在 dev 下看。
  preview: {
    port: 5175,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
