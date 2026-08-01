import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: '.',
  publicDir: 'public',
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
        // Required so /api/sessions/{id}/tts/stream (WebSocket) tunnels
        // through to the FastAPI backend in dev.
        ws: true,
      },
      '/game-assets': {
        target: 'http://localhost:3001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/game-assets/, '/api/assets'),
      },
    },
  },
  build: {
    outDir: 'dist',
  },
});
