/**
 * Size budget of the built site (web/dist), checked after `vite build` by the CI and deploy workflows:
 *   the map library chunk, the rest of the JavaScript, the CSS, the largest data file and the whole data folder.
 * The budgets leave about a fifth of room over the release of November 2026 (map library 1,054 kB, other JavaScript
 * 471 kB, CSS 165 kB, largest data file 1,328 kB, data 24.4 MB): a jump beyond them is a regression to look at, not
 * a hard limit of the platform. Change a budget here, with the reason, when the growth is wanted.
 *
 *     node web/scripts/check-size.mjs [dist folder]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const KB = 1000;
export const BUDGET = {
  mapChunk: 1300 * KB,
  otherJs: 600 * KB,
  css: 220 * KB,
  dataFile: 1700 * KB,
  data: 32000 * KB,
};

function files(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    const st = fs.statSync(p); // follows the data symbolic link
    if (st.isDirectory()) out.push(...files(p));
    else out.push({ p, size: st.size });
  }
  return out;
}

/** {measures, problems} of a dist folder. */
export function measure(dist) {
  const assets = files(path.join(dist, 'assets'));
  const js = assets.filter((f) => f.p.endsWith('.js'));
  const map = js.filter((f) => /maplibre/.test(path.basename(f.p)));
  const data = fs.existsSync(path.join(dist, 'data')) ? files(path.join(dist, 'data')) : [];
  const largest = data.reduce((a, f) => (f.size > a.size ? f : a), { p: '', size: 0 });
  const m = {
    mapChunk: Math.max(0, ...map.map((f) => f.size)),
    otherJs: js.filter((f) => !map.includes(f)).reduce((a, f) => a + f.size, 0),
    css: assets.filter((f) => f.p.endsWith('.css')).reduce((a, f) => a + f.size, 0),
    dataFile: largest.size,
    data: data.reduce((a, f) => a + f.size, 0),
  };
  const problems = Object.entries(BUDGET)
    .filter(([k, b]) => m[k] > b)
    .map(([k, b]) => `${k}: ${Math.round(m[k] / KB)} kB, over its budget of ${Math.round(b / KB)} kB${k === 'dataFile' ? ` (${path.relative(dist, largest.p)})` : ''}`);
  if (!js.length) problems.push('no JavaScript in assets/: is this a built site?');
  return { m, problems };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const dist = path.resolve(process.argv[2] ?? path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist'));
  const { m, problems } = measure(dist);
  console.log(Object.entries(m).map(([k, v]) => `${k} ${Math.round(v / KB)} kB (budget ${Math.round(BUDGET[k] / KB)})`).join(', '));
  if (problems.length) {
    console.error(`size budget exceeded:\n${problems.join('\n')}`);
    process.exit(1);
  }
  console.log('size budget OK');
}
