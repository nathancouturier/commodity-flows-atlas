/**
 * Tests of scripts/guard-data.mjs: an unchanged or normally updated file passes; a truncated table, a file that shrank,
 * a price that jumped or was revised by more than half, a weekly port traffic file that lost weeks or rewrote old ones,
 * and a folder that lost files are refused, in a small git repository built for the test.
 *
 *     node web/scripts/guard-data.test.mjs
 */
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { PORT_DEEP_WEEKS, compareCoverage, compareFile, comparePortTraffic, comparePrice, guardRepo } from './guard-data.mjs';

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
  assert.match(p[0], /moved from 12 \(2026-03\) to 30 \(2026-04\), outside ×0\.50 to ×1\.50/);
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

// the real months of the two deviation series (data/prices/igrea-m.json, gscpi-m.json): Dallas Fed IGREA, % deviation
// from trend, Dec 2021 54.158143 then Jan 2022 6.208315; New York Fed GSCPI, standard deviations from average, Jan 2023
// 1.072012 then Feb 2023 -0.236029. Both cross zero, so a move is not proportional to their level.
const igrea = (v) => ({ id: 'igrea-m', freq: 'M', start: '2021-10', v });
const gscpi = (v) => ({ id: 'gscpi-m', freq: 'M', start: '2022-11', v });
ok('a deviation series is checked on its shape only: a real month that moved by more than half passes', () => {
  const unit = '% deviation from trend';
  assert.deepEqual(comparePrice('prices/igrea-m.json', igrea([40.1, 52.3, 54.158143]), igrea([40.1, 52.3, 54.158143, 6.208315]), unit), []);
  assert.deepEqual(comparePrice('prices/igrea-m.json', igrea([40.1, 52.3, 54.158143]), igrea([38.7, 49.9, 50.2, 6.2]), unit), []);
  const sd = 'standard deviations from average';
  assert.deepEqual(comparePrice('prices/gscpi-m.json', gscpi([1.5, 1.2, 1.072012]), gscpi([1.5, 1.2, 1.072012, -0.236029]), sd), []);
  // without its unit the same month is a refused move: the unit is what exempts it
  assert.equal(comparePrice('prices/igrea-m.json', igrea([40.1, 52.3, 54.158143]), igrea([40.1, 52.3, 54.158143, 6.208315])).length, 1);
});
ok('a deviation series that lost a month, or whose frequency changed, is refused', () => {
  const unit = '% deviation from trend';
  const p = comparePrice('prices/igrea-m.json', igrea([40.1, 52.3, 54.158143]), igrea([40.1, 52.3]), unit);
  assert.ok(p.some((x) => /1 value\(s\) of the last commit are missing \(from 2021-12/.test(x)), p.join('\n'));
  const hole = comparePrice('prices/igrea-m.json', igrea([40.1, 52.3, 54.158143]), igrea([40.1, null, 54.1, 6.2]), unit);
  assert.ok(hole.some((x) => /missing \(from 2021-11/.test(x)), hole.join('\n'));
  assert.ok(comparePrice('prices/igrea-m.json', igrea([1, 2, 3]), { ...igrea([1, 2, 3, 4]), freq: 'A' }, unit)[0].includes('frequency changed'));
  const bad = comparePrice('prices/x-d.json', daily([1, 2, 3], [5, 6, 7]), daily([1, 3, 2, 4], [5, 6, 7, 8]));
  assert.ok(bad[0].includes('days are no longer one per value'), bad.join('\n'));
});
ok('a step test that follows the series own scale: a volatile price may move as far as it has before, never ten times', () => {
  // Henry Hub, the week of 20 Jan 2026 (data/prices/hh-d.json): 3.06 then 4.00, 4.96, 8.42, 30.72, after a history whose
  // largest day was 3.15 to 13.20 (12 Jan 2024)
  const hist = daily([1, 2, 3, 4], [2.75, 3.15, 13.2, 3.06]);
  assert.deepEqual(comparePrice('prices/hh-d.json', hist, daily([1, 2, 3, 4, 8, 9, 10, 11], [2.75, 3.15, 13.2, 3.06, 4, 4.96, 8.42, 30.72]), 'USD/MMBtu'), []);
  // the same week ten times too large, or ten times too small, is refused whatever the history
  assert.equal(comparePrice('prices/hh-d.json', hist, daily([1, 2, 3, 4, 8, 9, 10, 11], [2.75, 3.15, 13.2, 3.06, 40, 49.6, 84.2, 307.2]), 'USD/MMBtu').length, 1);
  assert.equal(comparePrice('prices/hh-d.json', hist, daily([1, 2, 3, 4, 8, 9, 10, 11], [2.75, 3.15, 13.2, 3.06, 0.4, 0.496, 0.842, 3.072]), 'USD/MMBtu').length, 1);
  // a quiet index (largest past month +4%) keeps the range of a half: 100 to 40 is refused
  const ppi = (v) => ({ id: 'freight-ppi-m', freq: 'M', start: '2026-01', v });
  assert.equal(comparePrice('prices/freight-ppi-m.json', ppi([100, 104, 100]), ppi([100, 104, 100, 40]), 'index (Jun 1988 = 100)').length, 1);
  assert.deepEqual(comparePrice('prices/freight-ppi-m.json', ppi([100, 104, 100]), ppi([100, 104, 100, 120]), 'index (Jun 1988 = 100)'), []);
});
ok('steps that touch a zero or a negative value are not tested; the rest of the series is', () => {
  // WTI, 20 and 21 Apr 2020: 1.0 to -36.98 to 8.91
  const wti = (d, v) => ({ id: 'wti-d', freq: 'D', d, v });
  assert.deepEqual(comparePrice('prices/wti-d.json', wti([1, 2], [18.31, 1.0]), wti([1, 2, 3, 4], [18.31, 1.0, -36.98, 8.91]), 'USD/bbl'), []);
  assert.equal(comparePrice('prices/wti-d.json', wti([1, 2, 3, 4], [18.31, 1.0, -36.98, 8.91]), wti([1, 2, 3, 4, 5], [18.31, 1.0, -36.98, 8.91, 89.1]), 'USD/bbl').length, 1);
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
write('data/prices/igrea-m.json', igrea([40.1, 52.3, 54.158143]));
write('data/prices/index.json', [{ id: 'x-m', unit: 'USD/t' }, { id: 'igrea-m', unit: '% deviation from trend' }]);
for (let i = 0; i < 12; i++) write(`data/countries/profiles/C${i}.json`, { c: `C${i}` });
write('data/_status/log.jsonl', 'x\n'.repeat(100));
g('add', '-A');
g('commit', '-q', '-m', 'previous data');
ok('an update that only adds data passes, a deviation series read as such from data/prices/index.json', () => {
  write('data/prices/x-m.json', monthly([10, 11, 12, 12.4]));
  write('data/prices/igrea-m.json', igrea([40.1, 52.3, 54.158143, 6.208315]));
  write('data/_status/log.jsonl', 'x\n');
  assert.deepEqual(guardRepo(repo), []);
});
ok('a truncated table and a removed folder of files are refused by the command, which exits 1', () => {
  write('data/commodities/wheat.json', table(3));
  for (let i = 0; i < 6; i++) fs.rmSync(path.join(repo, `data/countries/profiles/C${i}.json`));
  const p = guardRepo(repo);
  assert.ok(p.some((x) => x.startsWith('commodities/wheat.json: $.production lost 37')), p.join('\n'));
  assert.ok(p.some((x) => x.startsWith('data/countries/profiles/: 6 of its 12 files were removed')), p.join('\n'));
  // restricted to the paths a job owns (the check after a discard), the other folders are not compared
  assert.deepEqual(guardRepo(repo, ['data/prices', 'data/_status', 'web/public/changes.atom']), []);
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

// the coverage file: a page that lost a block of the floor is refused, a rebuild that only changes reasons or improves a page is not
const realCoverage = fs.readFileSync(path.resolve(here, '../../data/coverage.json'), 'utf8');
const cov = (cells) => JSON.stringify({ version: 1, release: 7, blocks: [], reasons: {}, pages: Object.entries(cells).map(([id, c]) => ({ id, cells: c })), work: {} });
const floor = JSON.stringify({ version: 1, present: { copper: ['price', 'assets'], wheat: ['trade'] } });
const full = { copper: { price: 'p', assets: 'p', monthly: 'm' }, wheat: { trade: 'p' } };
ok('a rebuilt coverage file that keeps every block of the floor passes, and so does one that gains a block', () => {
  assert.deepEqual(compareCoverage(cov(full), floor, cov(full)), []);
  assert.deepEqual(compareCoverage(cov({ ...full, copper: { ...full.copper, monthly: 'p' } }), floor, cov(full)), []);
});
ok('a page that lost a block of the floor is refused, by name', () => {
  const lost = { ...full, copper: { ...full.copper, price: 'm' } };
  const p = compareCoverage(cov(lost), floor, cov(full));
  assert.equal(p.length, 1);
  assert.match(p[0], /page copper lost the block price that pipeline\/commodities\/coverage_floor\.json lists/);
  // a page that has no row any more is a loss of every block of the floor
  assert.equal(compareCoverage(cov({ wheat: full.wheat }), floor, cov(full)).length, 2);
  // a block that turned into a reason is a loss too: a typed reason does not hide it
  assert.equal(compareCoverage(cov({ ...full, wheat: { trade: 'na:crop' } }), floor, cov(full)).length, 1);
});
ok('a loss that the last commit already holds is not refused again', () => {
  const lost = { ...full, copper: { ...full.copper, price: 'm' } };
  assert.deepEqual(compareCoverage(cov(lost), floor, cov(lost)), []);
  // a new file has no last commit: the floor alone decides
  assert.equal(compareCoverage(cov(lost), floor, null).length, 1);
});
ok('files that do not read give no finding: the shape is the validator\'s', () => {
  assert.deepEqual(compareCoverage('not json', floor, cov(full)), []);
  assert.deepEqual(compareCoverage(cov(full), 'not json', cov(full)), []);
});
ok('the real coverage file with fewer reasons or another order of reasons is not refused: reasons are an object, not a list', () => {
  const doc = JSON.parse(realCoverage);
  const ids = Object.keys(doc.reasons);
  assert.ok(ids.length >= 10, 'the real file has a table of reasons of ten entries or more');
  const fewer = { ...doc, reasons: Object.fromEntries(Object.entries(doc.reasons).slice(0, ids.length - 4)) };
  assert.deepEqual(compareFile('coverage.json', realCoverage, JSON.stringify(fewer, null, 1)), []);
  // every cell stays one short string whatever its state: the file does not shrink when pages improve or fall
  const gain = JSON.parse(realCoverage);
  for (const row of gain.pages) for (const b of Object.keys(row.cells)) row.cells[b] = 'p';
  gain.work = {};
  assert.deepEqual(compareFile('coverage.json', realCoverage, JSON.stringify(gain, null, 1)), []);
});

// the same through the command, in a small repository: HEAD holds the last build and the floor
const crepo = fs.mkdtempSync(path.join(os.tmpdir(), 'guard-coverage-'));
const cg = (...a) => execFileSync('git', a, { cwd: crepo, stdio: 'ignore' });
const cwrite = (rel, text) => {
  fs.mkdirSync(path.dirname(path.join(crepo, rel)), { recursive: true });
  fs.writeFileSync(path.join(crepo, rel), text);
};
cg('init', '-q');
cg('config', 'user.email', 'test@example.invalid');
cg('config', 'user.name', 'test');
cg('config', 'commit.gpgsign', 'false');
cwrite('data/coverage.json', cov(full));
cwrite('pipeline/commodities/coverage_floor.json', floor);
cg('add', '-A');
cg('commit', '-q', '-m', 'last build');
fs.mkdirSync(path.join(crepo, 'web', 'scripts'), { recursive: true });
fs.copyFileSync(path.join(here, 'guard-data.mjs'), path.join(crepo, 'web', 'scripts', 'guard-data.mjs'));
const guardCmd = (env = {}, ...paths) =>
  spawnSync(process.execPath, [path.join(crepo, 'web', 'scripts', 'guard-data.mjs'), ...paths], { encoding: 'utf8', env: { ...process.env, ...env } });
ok('a rebuild that took a block of the floor from a page is refused by the command, with the paths of the job, and the override accepts it', () => {
  cwrite('data/coverage.json', cov({ ...full, copper: { ...full.copper, price: 'm' } }));
  const r = guardCmd({}, 'data/commodities', 'data/coverage.json', 'data/_status');
  assert.equal(r.status, 1, r.stdout + r.stderr);
  assert.match(r.stderr, /page copper lost the block price/);
  const off = guardCmd({ DATA_GUARD: 'off' }, 'data/commodities', 'data/coverage.json', 'data/_status');
  assert.equal(off.status, 0, off.stdout + off.stderr);
  assert.match(off.stderr, /accepted by hand/);
  assert.match(off.stderr, /page copper lost the block price/);
  // a job that does not own the file is not asked about it
  assert.equal(guardCmd({}, 'data/prices', 'data/_status').status, 0);
});
ok('after the discard of the job the previous coverage file is back and the guard passes', () => {
  cg('checkout', '--', 'data/coverage.json');
  const r = guardCmd({}, 'data/coverage.json');
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.equal(fs.readFileSync(path.join(crepo, 'data/coverage.json'), 'utf8'), cov(full));
});
ok('a loss that was accepted and committed does not stop the next rebuild, which only gains', () => {
  const lost = { ...full, copper: { ...full.copper, price: 'm' } };
  cwrite('data/coverage.json', cov(lost));
  cg('add', '-A');
  cg('commit', '-q', '-m', 'accepted loss');
  cwrite('data/coverage.json', cov({ ...lost, copper: { ...lost.copper, monthly: 'p' } }));
  const r = guardCmd({}, 'data/coverage.json');
  assert.equal(r.status, 0, r.stdout + r.stderr);
});
fs.rmSync(crepo, { recursive: true, force: true });
// a weekly port traffic file: twelve arrays of n weeks from the Monday 2025-01-06
const weeklyPort = (n, { id = 'port1', y, tweak = {} } = {}) => {
  const arr = (k, t) => Array.from({ length: n }, (_, i) => (tweak[`${k}.${t}.${i}`] ?? ((i * 7 + t.length + k.length) % 50)));
  const body = Object.fromEntries(['calls', 'exports', 'imports'].map((k) => [k, Object.fromEntries(['tanker', 'dry', 'container', 'other'].map((t) => [t, arr(k, t)]))]));
  const start = new Date(Date.UTC(2025, 0, 6));
  const last = new Date(start.getTime() + (7 * n - 1) * 864e5);
  return { id, name: 'Port', s: 'portwatch-port-traffic', y: y ?? last.toISOString().slice(0, 10), start: '2025-01-06', step: 'week', u: 'kt', dp: 3, ...body };
};
const portText = (...a) => JSON.stringify(weeklyPort(...a));
const FILE = 'freight/port-traffic/port1.json';
ok('the weekly port file the job extends by a week, or whose last weeks it rewrites, passes', () => {
  assert.deepEqual(compareFile(FILE, portText(120), portText(121)), []);
  assert.deepEqual(compareFile(FILE, portText(120), portText(121, { tweak: { 'calls.tanker.119': 99, 'exports.dry.70': 5 } })), []);
  // the deep pass rewrites the weeks from PORT_DEEP_WEEKS before the last stored week, and no older one
  const first = 120 - PORT_DEEP_WEEKS - 1;
  assert.deepEqual(compareFile(FILE, portText(120), portText(121, { tweak: { [`calls.tanker.${first}`]: 99 } })), []);
});
ok('a weekly port file that rewrote a week older than the weeks a run reads again is refused, by the week', () => {
  const first = 120 - PORT_DEEP_WEEKS - 1;
  const p = compareFile(FILE, portText(120), portText(121, { tweak: { [`imports.other.${first - 1}`]: 99 } }));
  assert.equal(p.length, 1, p.join('\n'));
  assert.match(p[0], new RegExp(`week ${first} \\(imports other\\) is older than the ${PORT_DEEP_WEEKS} weeks a run reads again`));
});
ok('a weekly port file that lost a week, an array\'s last week, its first week or a day of data is refused', () => {
  const lost = compareFile(FILE, portText(120), portText(119));
  assert.ok(lost.some((x) => /lost weeks \(120 before, 119 now\)/.test(x)), lost.join('\n'));
  const one = weeklyPort(121);
  one.exports.dry = one.exports.dry.slice(0, 100);
  assert.ok(compareFile(FILE, portText(120), JSON.stringify(one)).some((x) => /lost weeks/.test(x)));
  const moved = weeklyPort(120);
  moved.start = '2025-01-13';
  assert.ok(compareFile(FILE, portText(120), JSON.stringify(moved)).some((x) => /the first week moved from 2025-01-06 to 2025-01-13/.test(x)));
  const back = compareFile(FILE, portText(120), portText(120, { y: '2025-03-01' }));
  assert.ok(back.some((x) => /the last day of data went back/.test(x)), back.join('\n'));
});
ok('the guard of the weekly port files is for those files only, and a document that is not one gives no finding', () => {
  assert.deepEqual(comparePortTraffic(FILE, { a: 1 }, { a: 2 }), []);
  assert.deepEqual(comparePortTraffic(FILE, weeklyPort(60), 'x'), []);
  // the same shape under another name is held to the usual rules only
  assert.deepEqual(compareFile('freight/other/port1.json', portText(120), portText(119)).filter((x) => /lost weeks/.test(x)), []);
});
ok('index.json of the port files may lose entries as the ports are read, any other list still may not', () => {
  const idx = (pending) => JSON.stringify({ checked: '2026-11-25', none: [], pending });
  const ids = (n) => Array.from({ length: n }, (_, i) => `port${i + 100}`);
  assert.deepEqual(compareFile('freight/port-traffic/index.json', idx(ids(30)), idx(ids(12))), []);
  assert.ok(compareFile('freight/other/index.json', idx(ids(30)), idx(ids(12))).some((x) => /lost 18 of its 30 rows/.test(x)));
});

// the same through the command, in a small repository whose HEAD holds the last weekly files
const prepo = fs.mkdtempSync(path.join(os.tmpdir(), 'guard-ports-'));
const pg = (...a) => execFileSync('git', a, { cwd: prepo, stdio: 'ignore' });
const pwrite = (rel, text) => {
  fs.mkdirSync(path.dirname(path.join(prepo, rel)), { recursive: true });
  fs.writeFileSync(path.join(prepo, rel), text);
};
pg('init', '-q');
pg('config', 'user.email', 'test@example.invalid');
pg('config', 'user.name', 'test');
pg('config', 'commit.gpgsign', 'false');
const ports = ['port1', 'port2', 'port3'];
for (const id of ports) pwrite(`data/freight/port-traffic/${id}.json`, portText(120, { id }));
pwrite('data/freight/portwatch/hormuz.json', JSON.stringify({ id: 'hormuz', v: [1, 2, 3] }));
pg('add', '-A');
pg('commit', '-q', '-m', 'first load');
fs.mkdirSync(path.join(prepo, 'web', 'scripts'), { recursive: true });
fs.copyFileSync(path.join(here, 'guard-data.mjs'), path.join(prepo, 'web', 'scripts', 'guard-data.mjs'));
const portGuard = (env = {}, ...paths) =>
  spawnSync(process.execPath, [path.join(prepo, 'web', 'scripts', 'guard-data.mjs'), ...paths], { encoding: 'utf8', env: { ...process.env, ...env } });
const JOB = ['data/freight/portwatch', 'data/freight/port-traffic', 'data/_status'];
ok('a weekly run that extended the files passes the command, with the paths of the job', () => {
  for (const id of ports) pwrite(`data/freight/port-traffic/${id}.json`, portText(121, { id, tweak: { 'calls.tanker.119': 77 } }));
  pwrite('data/freight/portwatch/hormuz.json', JSON.stringify({ id: 'hormuz', v: [1, 2, 3, 4] }));
  const r = portGuard({}, ...JOB);
  assert.equal(r.status, 0, r.stdout + r.stderr);
});
ok('a port file that lost weeks is refused by the command, the other files of the job with it, and the override accepts it', () => {
  pwrite('data/freight/port-traffic/port2.json', portText(100, { id: 'port2' }));
  const r = portGuard({}, ...JOB);
  assert.equal(r.status, 1, r.stdout + r.stderr);
  assert.match(r.stderr, /freight\/port-traffic\/port2\.json: lost weeks \(120 before, 100 now\)/);
  const off = portGuard({ DATA_GUARD: 'off' }, ...JOB);
  assert.equal(off.status, 0, off.stdout + off.stderr);
  assert.match(off.stderr, /accepted by hand/);
  // the job that does not own the folder is not asked about it
  assert.equal(portGuard({}, 'data/freight/portwatch', 'data/_status').status, 0);
});
ok('a port file that was removed is refused by the command, whatever the size of the folder', () => {
  pg('checkout', '--', 'data/freight/port-traffic/port2.json');
  fs.rmSync(path.join(prepo, 'data/freight/port-traffic/port3.json'));
  const r = portGuard({}, ...JOB);
  assert.equal(r.status, 1, r.stdout + r.stderr);
  assert.match(r.stderr, /freight\/port-traffic\/port3\.json: the port file was removed/);
  pg('checkout', '--', 'data/freight/port-traffic/port3.json');
  assert.equal(portGuard({}, ...JOB).status, 0);
});
fs.rmSync(prepo, { recursive: true, force: true });
console.log(`guard-data: ${n} checks passed`);
