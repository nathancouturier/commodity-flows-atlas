/**
 * The "Data freshness" table of the About window (src/lib/status.ts) against status files made by the test: a source that has not
 * succeeded yet and has failed fewer runs than its alert threshold is retrying, not stale; at the threshold it is failing; a source
 * that succeeded is judged by its last check and its data as before. The status module is bundled with esbuild (a dependency of
 * vite) into a temporary folder, and the file it reads is a stub of `fetch`.
 *
 *     node --test web/scripts/status-freshness.test.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { build } from 'esbuild';

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'status-freshness-'));
const out = path.join(tmp, 'status.mjs');
await build({
  entryPoints: [path.join(here, '../src/lib/status.ts')],
  bundle: true,
  format: 'esm',
  platform: 'node',
  outfile: out,
  logLevel: 'error',
  nodePaths: [path.join(here, '../node_modules')],
});
let n = 0;
// the data loader keeps each file it read: a fresh copy of the module for each status file
const loadFresh = async () => (await import(`${out}?n=${++n}`)).loadStatus;
process.on('exit', () => fs.rmSync(tmp, { recursive: true, force: true }));

const NOW = Date.parse('2026-12-02T12:00:00Z');
/** The row of `key` for a status file holding `entry` under `key`. */
async function row(key, entry) {
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ updated: '2026-12-02T00:00:00Z', sources: entry ? { [key]: entry } : {} }) });
  const st = await (await loadFresh())(NOW);
  return st.rows.find((r) => r.key === key);
}
const KEY = 'portwatch-port-traffic';
const failed = (n, extra = {}) => ({ consecutive_failures: n, last_success: null, last_attempt: '2026-12-02T00:00:00Z', last_error: 'x', data_to: null, alert_after: 3, state: {}, ...extra });

test('a source with no entry has no row', async () => {
  assert.equal(await row(KEY, null), undefined);
});

test('a first scheduled run that fails shows the source as retrying, not stale; at its third failure it is failing', async () => {
  for (const n of [1, 2]) {
    const r = await row(KEY, failed(n));
    assert.equal(r.health, 'ok', `${n} failure(s): ${r.why}`);
    assert.equal(r.retrying, true);
  }
  const r = await row(KEY, failed(3));
  assert.equal(r.health, 'failing');
});

test('an entry that never succeeded and never failed is still stale: nothing says it ran', async () => {
  const r = await row(KEY, failed(0));
  assert.equal(r.health, 'stale');
  assert.match(r.why, /No successful check recorded/);
});

test('a source that succeeded is judged by its last check and its data, failing runs or not', async () => {
  const good = { consecutive_failures: 0, last_success: '2026-11-25T19:30:00Z', data_to: '2026-11-20', state: {} };
  assert.equal((await row(KEY, good)).health, 'ok');
  assert.equal((await row(KEY, { ...good, last_success: '2026-11-01T19:30:00Z' })).health, 'stale');
  assert.equal((await row(KEY, { ...good, data_to: '2026-10-20' })).health, 'stale');
  const retry = await row(KEY, { ...good, consecutive_failures: 1, alert_after: 3 });
  assert.equal(retry.health, 'ok');
  assert.equal(retry.retrying, true);
});
