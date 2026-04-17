import { defineConfig } from 'vite';

const SERVER_PORT = process.env.PORT_SERVER || '3333';
const TARGET = `http://127.0.0.1:${SERVER_PORT}`;

export default defineConfig({
  root: '.',
  publicDir: 'public',
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: TARGET,
        changeOrigin: true,
      },
      '/game-assets': {
        target: TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/game-assets/, '/api/assets'),
      },
    },
  },
  build: {
    outDir: 'dist',
  },
});
