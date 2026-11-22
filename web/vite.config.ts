import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';

// The site is served from https://<user>.github.io/commodity-flows-atlas/,
// so all asset URLs are relative. Data files live in /data at the repo root
// and are exposed through web/public/data (a symlink), copied as-is into dist.
export default defineConfig({
  base: './',
  plugins: [preact()],
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: { maplibre: ['maplibre-gl'], uplot: ['uplot'] },
      },
    },
  },
  server: { fs: { allow: ['..'] } },
});
