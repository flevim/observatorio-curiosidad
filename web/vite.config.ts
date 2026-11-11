import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, /api y /reporte se redirigen a la API FastAPI (puerto 8010).
const api = process.env.OBSERVATORIO_API ?? 'http://127.0.0.1:8010'

export default defineConfig({
  // Ruta base del sitio publicado (GitHub Pages: '/<repositorio>/'). En local, '/'.
  base: process.env.VITE_BASE ?? '/',
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: { '/api': api, '/reporte': api },
  },
  build: {
    // El globo (three.js) es un chunk aparte que se carga de forma diferida.
    chunkSizeWarningLimit: 2100,
  },
})
