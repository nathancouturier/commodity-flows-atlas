import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

// Commit and date of the build, shown in the About window (data freshness). Empty when git is not available.
function buildCommit(): string {
  try {
    return execSync('git rev-parse --short HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
  } catch {
    return '';
  }
}

// Number and date of the published release (release.json at the repository root). Empty when the file is missing or unreadable:
// the site then draws no release line; a test of the checks fails on the file.
function release(): { number: string; date: string } {
  try {
    const r = JSON.parse(readFileSync(new URL('../release.json', import.meta.url), 'utf8'));
    return Number.isInteger(r.release) && typeof r.date === 'string' ? { number: String(r.release), date: r.date } : { number: '', date: '' };
  } catch {
    return { number: '', date: '' };
  }
}
const RELEASE = release();

// The site is served from https://<user>.github.io/commodity-flows-atlas/,
// so all asset URLs are relative. Data files live in /data at the repo root
// and are exposed through web/public/data (a symlink), copied as-is into dist.
export default defineConfig({
  base: './',
  plugins: [preact()],
  define: {
    __BUILD_COMMIT__: JSON.stringify(buildCommit()),
    __BUILD_DATE__: JSON.stringify(new Date().toISOString()),
    __RELEASE_NUMBER__: JSON.stringify(RELEASE.number),
    __RELEASE_DATE__: JSON.stringify(RELEASE.date),
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
