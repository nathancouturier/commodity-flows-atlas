/**
 * Tests of the rules of the weekly port traffic files (scripts/port-traffic-rules.mjs): a good document passes, and each
 * rule has a document that breaks only it. The same documents are given to the Python rules by
 * pipeline/tests/test_portwatch_port_traffic.py, so the two cannot drift. When data/freight/port-traffic exists, every
 * file of it and its index.json are checked here too.
 *
 *     node web/scripts/port-traffic-rules.test.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { portTrafficProblems, portTrafficIndexProblems, problemCodes, PORT_TRAFFIC_SOURCE } from './port-traffic-rules.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const data = path.resolve(here, '../../data');
const TYPES = ['tanker', 'dry', 'container', 'other'];
let n = 0;
const ok = (name, fn) => {
  fn();
  n++;
  console.log(`ok   ${name}`);
};

/** A document of `weeks` weeks from Monday 6 January 2025, values that are all different enough to catch a swapped array;
 * `frac` adds a fraction to the tonnes (a value of 2.5 or 12.5 is allowed, 102.5 is not). */
function good(weeks = 60, frac = 0) {
  const block = (k) => Object.fromEntries(TYPES.map((t, j) => [t, Array.from({ length: weeks }, (_, i) => (k === 'calls' ? (i + j) % 7 : ((i * 3 + j) % 11) + frac))]));
  const end = new Date(Date.UTC(2025, 0, 6) + (7 * weeks - 1) * 86_400_000).toISOString().slice(0, 10);
  return { id: 'port9', name: 'Nine', s: PORT_TRAFFIC_SOURCE, y: end, start: '2025-01-06', step: 'week', u: 'kt', dp: 3, calls: block('calls'), exports: block('exports'), imports: block('imports') };
}
const codes = (doc, opts = { id: 'port9', sources: new Set([PORT_TRAFFIC_SOURCE]) }) => problemCodes(portTrafficProblems(doc, opts));
const broken = (edit, opts) => {
  const d = good();
  edit(d);
  return codes(d, opts);
};

ok('a good document passes, with and without decimals, and with a hole in all twelve arrays', () => {
  assert.deepEqual(codes(good()), []);
  assert.deepEqual(codes(good(60, 0.5)), []);
  const d = good();
  for (const k of ['calls', 'exports', 'imports']) for (const t of TYPES) d[k][t][5] = null;
  assert.deepEqual(codes(d), []);
  assert.deepEqual(codes(good(1)), []);
});
ok('the document may have the exact keys and no others (never a daily value)', () => {
  assert.deepEqual(broken((d) => (d.daily = [1])), ['shape']);
  assert.deepEqual(broken((d) => delete d.step), ['shape']);
  assert.deepEqual(codes([1, 2]), ['shape']);
  assert.deepEqual(codes(null), ['shape']);
});
ok('the id is the file name, the name is not empty, the source is the registry id', () => {
  assert.deepEqual(broken((d) => (d.id = 'port10')), ['id']);
  assert.deepEqual(broken((d) => (d.id = 'harbour')), ['id']);
  assert.deepEqual(broken((d) => (d.name = ' ')), ['name']);
  assert.deepEqual(broken((d) => (d.s = 'portwatch')), ['source']);
  assert.deepEqual(broken(() => {}, { id: 'port9', sources: new Set() }), ['source']);
  assert.deepEqual(codes(good(), {}), []);
});
ok('the dates are real days, start is a Monday and step is week', () => {
  assert.deepEqual(broken((d) => (d.y = '2026-02-30')), ['date']);
  assert.deepEqual(broken((d) => (d.start = 'soon')), ['date']);
  assert.deepEqual(broken((d) => ((d.start = '2025-01-07'), (d.y = '2026-03-30'))), ['monday']);
  assert.deepEqual(broken((d) => (d.step = 'day')), ['step']);
});
ok('the unit is kt and dp, the most decimals of a value, is 3', () => {
  assert.deepEqual(broken((d) => (d.u = 't')), ['unit']);
  assert.deepEqual(broken((d) => (d.dp = 5)), ['unit']);
  assert.deepEqual(broken((d) => (d.dp = 0)), ['unit']);
  assert.deepEqual(broken((d) => (d.dp = 2.5)), ['unit']);
  assert.deepEqual(broken((d) => (d.dp = '3')), ['unit']);
});
ok('each block is four arrays of the same length, at least one week', () => {
  assert.deepEqual(broken((d) => delete d.calls.other), ['series']);
  assert.deepEqual(broken((d) => (d.exports = [1])), ['series']);
  assert.deepEqual(broken((d) => d.imports.dry.pop()), ['series']);
  assert.deepEqual(broken((d) => TYPES.forEach((t) => ['calls', 'exports', 'imports'].forEach((k) => (d[k][t] = [])))), ['series']);
});
ok('calls are non-negative integers, tonnes non-negative numbers with the decimals their size allows, null is allowed', () => {
  assert.deepEqual(broken((d) => (d.calls.dry[4] = -1)), ['calls']);
  assert.deepEqual(broken((d) => (d.calls.dry[4] = 1.5)), ['calls']);
  assert.deepEqual(broken((d) => (d.calls.dry[4] = '3')), ['calls']);
  assert.deepEqual(broken((d) => (d.calls.dry[4] = true)), ['calls']);
  assert.deepEqual(broken((d) => (d.exports.tanker[2] = -3)), ['tonnes']);
  assert.deepEqual(broken((d) => (d.imports.other[2] = 1.5)), ['tonnes']);
  assert.deepEqual(broken((d) => (d.imports.other[2] = '1')), ['tonnes']);
});
ok('the decimals of a value follow its size: whole from 100, one from 10, two from 1, three below, never finer than a tonne', () => {
  const only = (v) => {
    const d = good();
    d.imports.other[2] = v;
    return codes(d);
  };
  for (const v of [0, 0.001, 0.999, 1, 1.01, 9.99, 10, 10.1, 99.9, 100, 999, 1000, 123456]) assert.deepEqual(only(v), [], String(v));
  for (const v of [0.0004, 0.9995, 1.005, 9.995, 10.05, 99.95, 100.5, 1000.1, 100.4999]) assert.deepEqual(only(v), ['tonnes'], String(v));
  assert.deepEqual(only(-0.001), ['tonnes']);
});
ok('a week that is missing is missing in all twelve arrays', () => {
  assert.deepEqual(broken((d) => (d.exports.dry[7] = null)), ['holes']);
  assert.deepEqual(broken((d) => ((d.calls.tanker[3] = null), (d.calls.dry[4] = null))), ['holes']);
});
ok('the last week ends on or before y', () => {
  assert.deepEqual(broken((d) => (d.y = '2026-02-01')), ['end']);
  const d = good();
  d.y = '2026-03-02';
  assert.deepEqual(codes(d), []);
});

const ids = ['port1', 'port2', 'port3'];
const index = (doc, files) => problemCodes(portTrafficIndexProblems(doc, { ids, files }));
ok('index.json: every id of the port assets has a file or is in none, and nothing else', () => {
  assert.deepEqual(index({ checked: '2026-11-25', none: ['port3'] }, ['port1', 'port2']), []);
  assert.deepEqual(index({ checked: '2026-11-25', none: [] }, ['port1', 'port2', 'port3']), []);
  assert.deepEqual(index({ checked: '2026-11-25', none: [] }, ['port1', 'port2']), ['index-missing']);
  assert.deepEqual(index({ checked: '2026-11-25', none: ['port2', 'port3'] }, ['port1', 'port2']), ['index-both']);
  assert.deepEqual(index({ checked: '2026-11-25', none: ['port3', 'port9'] }, ['port1', 'port2']), ['index-orphan']);
  assert.deepEqual(index({ checked: '2026-11-25', none: [] }, ['port1', 'port2', 'port3', 'port9']), ['index-orphan']);
  assert.deepEqual(index({ checked: '2026-11-25', none: ['port3', 'port2'] }, ['port1']), ['index-none']);
  assert.deepEqual(index({ checked: '2026-11-25', none: ['port3', 'port3'] }, ['port1', 'port2']), ['index-none']);
  assert.deepEqual(index({ checked: 'yesterday', none: ['port3'] }, ['port1', 'port2']), ['index-date']);
  assert.deepEqual(index({ none: [] }, ids), ['index-shape']);
  assert.deepEqual(index(null, ids), ['index-shape']);
  assert.deepEqual(index({ checked: '2026-11-25', none: [1] }, ids), ['index-none']);
});
ok('index.json: a pending id has no file and is not in none; it may be left out of the document; an id in neither list is still missing', () => {
  assert.deepEqual(index({ checked: '2026-11-25', none: [], pending: ['port3'] }, ['port1', 'port2']), []);
  assert.deepEqual(index({ checked: '2026-11-25', none: ['port2'], pending: ['port3'] }, ['port1']), []);
  assert.deepEqual(index({ checked: '2026-11-25', none: [], pending: [] }, ['port1', 'port2', 'port3']), []);
  assert.deepEqual(index({ checked: '2026-11-25', none: [], pending: ['port3'] }, ['port1']), ['index-missing']);
  assert.deepEqual(index({ checked: '2026-11-25', none: [], pending: ['port2', 'port3'] }, ['port1', 'port2']), ['index-both']);
  assert.deepEqual(index({ checked: '2026-11-25', none: ['port3'], pending: ['port3'] }, ['port1', 'port2']), ['index-both']);
  assert.deepEqual(index({ checked: '2026-11-25', none: [], pending: ['port3', 'port9'] }, ['port1', 'port2']), ['index-orphan']);
  assert.deepEqual(index({ checked: '2026-11-25', none: [], pending: ['port3', 'port2'] }, ['port1']), ['index-pending']);
  assert.deepEqual(index({ checked: '2026-11-25', none: [], pending: ['port3', 'port3'] }, ['port1', 'port2']), ['index-pending']);
  assert.deepEqual(index({ checked: '2026-11-25', none: [], pending: 'port3' }, ['port1', 'port2']), ['index-pending']);
  assert.deepEqual(index({ checked: '2026-11-25', none: [], pending: [], other: [] }, ids), ['index-shape']);
});

const folder = path.join(data, 'freight', 'port-traffic');
if (fs.existsSync(folder)) {
  ok('every published port file and index.json pass', () => {
    const sources = new Set(JSON.parse(fs.readFileSync(path.join(data, 'sources.json'), 'utf8')).map((s) => s.id));
    const files = fs.readdirSync(folder).filter((f) => f.endsWith('.json') && f !== 'index.json').map((f) => f.slice(0, -5));
    for (const f of files) assert.deepEqual(portTrafficProblems(JSON.parse(fs.readFileSync(path.join(folder, `${f}.json`), 'utf8')), { id: f, sources }), [], f);
    const portwatch = JSON.parse(fs.readFileSync(path.join(data, 'infrastructure', 'ports.geojson'), 'utf8')).features.map((x) => x.properties.portwatch).filter(Boolean);
    const idx = JSON.parse(fs.readFileSync(path.join(folder, 'index.json'), 'utf8'));
    assert.deepEqual(portTrafficIndexProblems(idx, { ids: [...new Set(portwatch)], files }), []);
  });
} else {
  console.log('note data/freight/port-traffic does not exist yet: no published file to check');
}
console.log(`${n} checks passed`);
