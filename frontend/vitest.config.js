import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/__tests__/**/*.{test,spec}.{js,mjs}', 'src/**/*.{test,spec}.{js,mjs}'],
    globals: true,
    setupFiles: []
  }
})
