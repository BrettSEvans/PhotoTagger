import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: true,
      }
    }
  },
  test: {
    // Scoped to src/ only — e2e/ (Playwright) and tests/ (node:test) belong
    // to the other two test runners (npm run test:e2e / test:frontend) and
    // must not be picked up here.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
