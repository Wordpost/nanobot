import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'

export default defineConfig({
  plugins: [preact()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:2004',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../static_dist',
    emptyOutDir: true,
  },
})
