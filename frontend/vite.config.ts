// 从 'vitest/config' 取 defineConfig，而不是从 'vite' —— 只有前者认识 `test` 字段。
// 用 'vite' 的那个，`vue-tsc`（`npm run build` 的第一步）会在 tsconfig.node.json 下
// 报「'test' 不存在于 UserConfig 类型」：测试写得再对，构建也过不去。
import vue from '@vitejs/plugin-vue'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

// 端口写死在这里，不靠命令行参数 —— 免得默认落到 5173 之外，
// 而 CORS 白名单（api/main.py 的 VITE_DEV_ORIGINS）还写着 5173。
export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  server: {
    port: 5173,
    strictPort: true,          // 被占就报错停下，不要悄悄换端口
    proxy: {
      '/api': {
        target: loadEnv(mode, process.cwd(), 'TFIELD_').TFIELD_API_TARGET || 'http://127.0.0.1:8080',
        changeOrigin: true,
        // 比 Java 的默认计算超时多留 30 秒，让前端收到可读的超时响应。
        proxyTimeout: 630_000,
        timeout: 630_000,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
}))
