import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')
  return {
    plugins: [react()],
    server: {
      port: 5298,
      // Shared brand styles/theme come from the brand-common submodule at the repo root,
      // outside this Vite project, so the dev server must be allowed to serve it.
      fs: {
        allow: ['.', '../../brand-common'],
      },
      // Media URLs are origin-relative (/media/...) so they work in the bundled app and
      // headless server, where the backend serves the frontend. In dev the frontend comes
      // from Vite instead, so forward /media to the backend.
      proxy: {
        '/media': {
          target: env.VITE_API_URL || 'http://localhost:8128',
          changeOrigin: true,
        },
      },
    },
  }
})
