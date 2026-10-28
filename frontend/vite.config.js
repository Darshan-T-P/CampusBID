import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// The browser calls the backend under /api (so page URLs like /listings/5 never collide with
// API URLs like /listings/5). In dev this proxy strips the prefix and forwards to FastAPI.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_TARGET || 'http://localhost:8000'
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': { target, changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, '') },
      },
    },
    test: { environment: 'node' },
  }
})
