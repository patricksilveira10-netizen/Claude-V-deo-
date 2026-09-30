import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        // IP explícito: Node 17+ pode resolver "localhost" para ::1 (IPv6), e a API escuta só em 127.0.0.1.
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // Uploads/downloads longos: sem timeout no proxy.
        timeout: 0,
        proxyTimeout: 0,
      },
    },
  },
})
