import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: ['fx0gkeg8z4cfmv-5173.proxy.runpod.net'],
    hmr: {
      clientPort: 443,
      host: 'fx0gkeg8z4cfmv-5173.proxy.runpod.net',
      protocol: 'wss',
    },
  },
})
