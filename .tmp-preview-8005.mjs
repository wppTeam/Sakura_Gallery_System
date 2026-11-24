import { fileURLToPath } from 'node:url'

export default {
  root: fileURLToPath(new URL('./frontend', import.meta.url)),
  preview: {
    port: 5181,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8005', changeOrigin: true },
    },
  },
}
