import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // host: true expone el dev server fuera del contenedor
    host: true,
    port: 5173,
    strictPort: true,
    // En Linux los eventos inotify del bind mount llegan bien.
    // Si el HMR no reacciona (WSL2, macOS, volúmenes de red),
    // levantar con VITE_USE_POLLING=true
    watch:
      process.env.VITE_USE_POLLING === 'true'
        ? { usePolling: true, interval: 300 }
        : undefined,
  },
})
