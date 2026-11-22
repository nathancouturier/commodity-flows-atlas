import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';
import { execSync } from 'node:child_process';

// Commit and date of the build, shown in the About window (data freshness). Empty when git is not available.
function buildCommit(): string {
  try {
    return execSync('git rev-parse --short HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
  } catch {
    return '';
  }
}

// The site is served from https://<user>.github.io/commodity-flows-atlas/,
// so all asset URLs are relative. Data files live in /data at the repo root
// and are exposed through web/public/data (a symlink), copied as-is into dist.
export default defineConfig({
  base: './',
  plugins: [preact()],
  define: {
    __BUILD_COMMIT__: JSON.stringify(buildCommit()),
    __BUILD_DATE__: JSON.stringify(new Date().toISOString()),
  },
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
