import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tauri 单入口构建（v0.7 移除了浮动小球，只保留主窗口）
export default defineConfig({
  plugins: [react()],
  // Tauri 要求相对路径，不能用绝对路径
  base: './',
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:7531',
        changeOrigin: true,
      },
    },
  },
})
