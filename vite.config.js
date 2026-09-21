import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { versionedData } from './build/versionedData.js';
import { thirdPartyNotices } from './build/thirdPartyNotices.js';

export default defineConfig({
  base: '/JP_Market_Vis/',
  plugins: [react(), versionedData(), thirdPartyNotices()],
  server: {
    port: 5184,
  },
  // graph.js が top-level await で public/ のデータを fetch するため
  build: { target: 'esnext' },
  esbuild: { target: 'esnext' },
  optimizeDeps: { esbuildOptions: { target: 'esnext' } },
});
