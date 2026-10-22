import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:18101'

export default defineConfig({
  plugins: [vue()],
  server: { port: 18100, proxy: { '/api': apiProxyTarget } },
  test: { environment: 'jsdom', setupFiles: ['./tests/setup.ts'] },
})
