import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * 手动分包：把体量最大的两个运行时依赖拆出主包，避免单 chunk 超过 500 kB。
 * echarts 仅被 DivergencePanel 使用，配合路由懒加载后不会进入首屏。
 */
function manualChunks(id) {
  if (!id.includes('node_modules')) return undefined
  if (id.includes('echarts') || id.includes('zrender')) return 'vendor-echarts'
  if (id.includes('antd') || id.includes('@ant-design') || id.includes('/rc-')) return 'vendor-antd'
  if (id.includes('react-router') || id.includes('/react/') || id.includes('react-dom') || id.includes('scheduler')) {
    return 'vendor-react'
  }
  return 'vendor'
}

export default defineConfig({
  plugins: [react()],
  base: '/app/',
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: { manualChunks },
    },
  },
})
