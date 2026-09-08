import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/JP_Market_Vis/',
  plugins: [react()],
  server: {
    port: 5184,
  },
  // graph.js が top-level await で public/ のデータを fetch するため
  build: { target: 'esnext' },
  esbuild: { target: 'esnext' },
  optimizeDeps: { esbuildOptions: { target: 'esnext' } },
});
