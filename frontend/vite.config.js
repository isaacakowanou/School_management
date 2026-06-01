import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api -> FastAPI backend so the browser stays same-origin
// (the backend has no CORS middleware). Production should serve the build
// behind the same origin / a reverse proxy instead.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
