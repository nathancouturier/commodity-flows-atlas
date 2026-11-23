/**
 * Tests of scripts/guard-data.mjs: an unchanged or normally updated file passes; a truncated table, a file that shrank,
 * a price that jumped or was revised by more than half, and a folder that lost files are refused, in a small git
 * repository built for the test.
 *
 *     node web/scripts/guard-data.test.mjs
 */
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compareFile, comparePrice, guardRepo } from './guard-data.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const table = (n) => ({ id: 'wheat', production: Array.from({ length: n }, (_, i) => ({ c: `C${i}`, v: 100 - i, y: 2024, s: 'usda-psd' })) });
const monthly = (v) => ({ id: 'x-m', freq: 'M', start: '2026-01', v });
const daily = (d, v) => ({ id: 'x-d', freq: 'D', d, v });
let n = 0;
const ok = (name, fn) => {
  fn();
  n++;
  console.log(`ok   ${name}`);
};

ok('an unchanged table passes', () => assert.deepEqual(compareFile('commodities/wheat.json', JSON.stringify(table(40)), JSON.stringify(table(40))), []));
ok('a table that gains rows, or loses fewer than a tenth, passes', () => {
  assert.deepEqual(compareFile('commodities/wheat.json', JSON.stringify(table(40)), JSON.stringify(table(45))), []);
  assert.deepEqual(compareFile('commodities/wheat.json', JSON.stringify(table(40)), JSON.stringify(table(37))), []);
});
ok('a truncated table is refused', () => {
  const p = compareFile('commodities/wheat.json', JSON.stringify(table(40)), JSON.stringify(table(20)));
  assert.ok(p.some((x) => x.includes('$.production lost 20 of its 40 rows')), p.join('\n'));
});
ok('an emptied GeoJSON file is refused', () => {
  const fc = (k) => JSON.stringify({ type: 'FeatureCollection', features: Array.from({ length: k }, (_, i) => ({ type: 'Feature', properties: { id: i }, geometry: { type: 'Point', coordinates: [i, i] } })) });
  const p = compareFile('infrastructure/ports.geojson', fc(50), fc(0));
  assert.ok(p.some((x) => x.includes('$.features lost 50')), p.join('\n'));
  assert.ok(p.some((x) => x.includes('shrank')), p.join('\n'));
});
ok('small lists are not compared', () => assert.deepEqual(compareFile('a.json', JSON.stringify(table(5)), JSON.stringify(table(1))), []));
ok('a price whose last value doubles is refused; a normal move passes', () => {
  assert.equal(comparePrice('prices/x-m.json', monthly([10, 11, 12]), monthly([10, 11, 12, 12.5])).length, 0);
  const p = comparePrice('prices/x-m.json', monthly([10, 11, 12]), monthly([10, 11, 12, 30]));
  assert.equal(p.length, 1);
  assert.match(p[0], /last value moved from 12 to 30/);
});
ok('a series revised by a factor of ten at its previous last date is refused', () => {
  const p = comparePrice('prices/x-m.json', monthly([10, 11, 12]), monthly([100, 110, 120, 125]));
  assert.ok(p.some((x) => /value of 2026-03 was revised from 12 to 120/.test(x)), p.join('\n'));
});
ok('a daily series is compared on its days; an annual one only on revisions', () => {
  assert.equal(comparePrice('prices/x-d.json', daily([1, 2, 3], [50, 51, 52]), daily([1, 2, 3, 8], [50, 51, 52, 53])).length, 0);
  assert.equal(comparePrice('prices/x-d.json', daily([1, 2, 3], [50, 51, 52]), daily([1, 2, 3, 8], [50, 51, 52, 5])).length, 1);
  const annual = (v) => ({ id: 'li-a', freq: 'A', start: '2020', v });
  assert.equal(comparePrice('prices/li-a.json', annual([10, 20, 40]), annual([10, 20, 40, 10])).length, 0);
});

// the command on a small repository: HEAD holds the previous data, the working tree the update
const repo = fs.mkdtempSync(path.join(os.tmpdir(), 'guard-data-'));
const g = (...a) => execFileSync('git', a, { cwd: repo, stdio: 'ignore' });
const write = (rel, doc) => {
  fs.mkdirSync(path.dirname(path.join(repo, rel)), { recursive: true });
  fs.writeFileSync(path.join(repo, rel), typeof doc === 'string' ? doc : JSON.stringify(doc, null, 1));
};
g('init', '-q');
g('config', 'user.email', 'test@example.invalid');
g('config', 'user.name', 'test');
g('config', 'commit.gpgsign', 'false');
write('data/commodities/wheat.json', table(40));
write('data/prices/x-m.json', monthly([10, 11, 12]));
for (let i = 0; i < 12; i++) write(`data/countries/profiles/C${i}.json`, { c: `C${i}` });
write('data/_status/log.jsonl', 'x\n'.repeat(100));
g('add', '-A');
g('commit', '-q', '-m', 'previous data');
ok('an update that only adds data passes', () => {
  write('data/prices/x-m.json', monthly([10, 11, 12, 12.4]));
  write('data/_status/log.jsonl', 'x\n');
  assert.deepEqual(guardRepo(repo), []);
});
ok('a truncated table and a removed folder of files are refused by the command, which exits 1', () => {
  write('data/commodities/wheat.json', table(3));
  for (let i = 0; i < 6; i++) fs.rmSync(path.join(repo, `data/countries/profiles/C${i}.json`));
  const p = guardRepo(repo);
  assert.ok(p.some((x) => x.startsWith('commodities/wheat.json: $.production lost 37')), p.join('\n'));
  assert.ok(p.some((x) => x.startsWith('data/countries/profiles/: 6 of its 12 files were removed')), p.join('\n'));
  // the command itself, run in the test repository through a copy of the script
  fs.mkdirSync(path.join(repo, 'web', 'scripts'), { recursive: true });
  fs.copyFileSync(path.join(here, 'guard-data.mjs'), path.join(repo, 'web', 'scripts', 'guard-data.mjs'));
  const r = spawnSync(process.execPath, [path.join(repo, 'web', 'scripts', 'guard-data.mjs')], { encoding: 'utf8' });
  assert.equal(r.status, 1, r.stdout + r.stderr);
  assert.match(r.stderr, /change\(s\) refused against the last commit/);
  const off = spawnSync(process.execPath, [path.join(repo, 'web', 'scripts', 'guard-data.mjs')], { encoding: 'utf8', env: { ...process.env, DATA_GUARD: 'off' } });
  assert.equal(off.status, 0, off.stdout + off.stderr);
});
fs.rmSync(repo, { recursive: true, force: true });
console.log(`guard-data: ${n} checks passed`);
