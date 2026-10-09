/**
 * Author: Joonyoung Ki
 *
 * Vite build and dev-server configuration.
 *
 * Enables React and Tailwind CSS v4 and proxies the backend API routes to FastAPI during development.
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/** Origin of the local FastAPI backend that the dev server proxies API calls to. */
const backend = 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Same-origin proxy for the API routes, so that no CORS setup is needed in development.
    proxy: {
      '/stats': backend,
      '/process-resume': backend,
      '/match': backend,
      '/auth': backend,
      '/wishlist': backend,
    },
  },
})
