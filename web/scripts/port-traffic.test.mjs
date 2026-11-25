/**
 * The computations of the "Weekly port traffic" block of a port page (src/lib/portTraffic.ts) against the files of
 * data/freight/port-traffic, and the sources of the block against the rules of the page: `node web/scripts/port-traffic.test.mjs`.
 *
 * The ports are read from the folder when the test runs (a port can pass from "pending" to a file between two runs): every file is
 * checked, and a case that needs a kind of port (one with few calls, one that imports more than it exports) is skipped with a
 * message when no file is of that kind. The sums of the last 52 weeks are recomputed here by a loop of the test's own; the module's
 * rules (which measure a block opens on, how a tonnage is written, where the chart leaves a gap) are tested on documents the test
 * makes. The test holds no figure of the data.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { SHIP_TYPES, csvRows, defaultMeasure, fmtTonnes, holeGaps, readoutFormatter, rolling52, sameName, sumText, sumWeeks, weekCount, weekEnd, weekStart, weekTimes } from '../src/lib/portTraffic.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const folder = path.join(root, 'data/freight/port-traffic');
const TYPES = ['tanker', 'dry', 'container', 'other'];
const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const files = fs.existsSync(folder) ? fs.readdirSync(folder).filter((f) => /^(port|fso)\d+\.json$/.test(f)).sort() : [];
const docs = files.map((f) => read(path.join(folder, f)));
const skip = (why) => console.log(`skip ${why}`);

/** A document of `weeks` weeks from Monday 6 January 2025; the value of each cell is a function of its place, so that a swapped array shows. */
function make(weeks, { holes = [], calls = (i, j) => (i + j) % 7, tonnes = (k, i, j) => ((i * 3 + j + k) % 11) + 0.5 } = {}) {
  const block = (k) =>
    Object.fromEntries(TYPES.map((t, j) => [t, Array.from({ length: weeks }, (_, i) => (holes.includes(i) ? null : k === 'calls' ? calls(i, j) : tonnes(k === 'exports' ? 1 : 2, i, j)))]));
  const end = new Date(Date.UTC(2025, 0, 6) + (7 * weeks - 1) * 86_400_000).toISOString().slice(0, 10);
  return { id: 'port9', name: 'Nine', s: 'portwatch-port-traffic', y: end, start: '2025-01-06', step: 'week', u: 'kt', dp: 3, calls: block('calls'), exports: block('exports'), imports: block('imports') };
}

/** The sum of the four ship types of a measure over the weeks of an array range, by a loop of the test's own. */
function brute(doc, m, from, to) {
  let v = 0;
  for (let i = from; i < to; i++) for (const t of TYPES) v += doc[m][t][i] ?? 0;
  return v;
}

test('the folder has files to check', () => {
  if (!docs.length) skip('data/freight/port-traffic has no file');
});

test('the sums of the last 52 weeks and of the 52 before, for every file', () => {
  for (const d of docs) {
    const n = d.calls.tanker.length;
    assert.equal(weekCount(d), n);
    const { last, before } = rolling52(d);
    for (const m of ['calls', 'exports', 'imports']) {
      assert.ok(Math.abs(last[m].value - brute(d, m, Math.max(0, n - 52), n)) < 1e-6, `${d.id} ${m} last`);
      assert.equal(last[m].span, Math.min(52, n));
      if (n >= 104) assert.ok(Math.abs(before[m].value - brute(d, m, n - 104, n - 52)) < 1e-6, `${d.id} ${m} before`);
    }
    assert.equal(before === null, n < 104, `${d.id}: the earlier stretch exists only when the file holds a second year`);
  }
});

test('the date of the last week is the Sunday that ends it, and the last day of data is within the week after it', () => {
  for (const d of docs) {
    const n = weekCount(d);
    const [y, m, day] = d.start.split('-').map(Number);
    const sunday = new Date(Date.UTC(y, m - 1, day + 7 * (n - 1) + 6)).toISOString().slice(0, 10);
    assert.equal(weekEnd(d, n - 1), sunday, d.id);
    assert.ok(sunday <= d.y, `${d.id}: the last week ends after the last day of data`);
    assert.ok(new Date(Date.parse(`${sunday}T00:00:00Z`) + 7 * 86_400_000).toISOString().slice(0, 10) > d.y, `${d.id}: a whole week more is in the data and not in the file`);
    assert.equal(new Date(Date.parse(`${weekStart(d, 0)}T00:00:00Z`)).getUTCDay(), 1, `${d.id}: the first week does not start on a Monday`);
    const x = weekTimes(d);
    assert.equal(x.length, n);
    assert.ok(x.every((t, i) => i === 0 || t - x[i - 1] === 7 * 86_400), `${d.id}: the weeks are not seven days apart`);
  }
});

test('the measure a block opens on follows the rule, for every file', () => {
  const seen = { exports: 0, imports: 0, calls: 0 };
  for (const d of docs) {
    const { last } = rolling52(d);
    const want = last.exports.value === 0 && last.imports.value === 0 ? 'calls' : last.exports.value >= last.imports.value ? 'exports' : 'imports';
    assert.equal(defaultMeasure(d), want, d.id);
    seen[want]++;
  }
  for (const [k, v] of Object.entries(seen)) if (docs.length && !v) skip(`no port of the folder opens on ${k} (the rule is tested on documents the test makes)`);
});

test('a port with few calls and a large port are summed like any other', () => {
  if (!docs.length) return skip('no file');
  const calls52 = (d) => brute(d, 'calls', Math.max(0, weekCount(d) - 52), weekCount(d));
  const sorted = [...docs].sort((a, b) => calls52(a) - calls52(b));
  const [few, large] = [sorted[0], sorted[sorted.length - 1]];
  for (const d of [few, large]) {
    const { last } = rolling52(d);
    assert.equal(sumText('calls', last.calls), calls52(d).toLocaleString('en-US'), d.id);
    for (const m of ['exports', 'imports']) assert.equal(sumText(m, last[m]), fmtTonnes(brute(d, m, Math.max(0, weekCount(d) - 52), weekCount(d))), d.id);
  }
  assert.ok(calls52(few) <= calls52(large));
  console.log(`checked ${few.id} (${calls52(few)} calls in 52 weeks) and ${large.id} (${calls52(large)})`);
});

test('the CSV rows hold every value of every file once, and the totals are the sums of the types', () => {
  for (const d of docs) {
    const rows = csvRows(d);
    const n = weekCount(d);
    assert.equal(rows.length, 3 * n * (TYPES.length + 1), d.id);
    for (const m of ['calls', 'exports', 'imports']) {
      const mine = rows.filter((r) => r[2] === (m === 'calls' ? 'port calls' : m === 'exports' ? 'estimated export tonnes' : 'estimated import tonnes'));
      assert.equal(mine.length, n * 5, `${d.id} ${m}`);
      for (const [t, label] of SHIP_TYPES) assert.deepEqual(mine.filter((r) => r[1] === label).map((r) => r[3]), d[m][t], `${d.id} ${m} ${t}`);
      mine.filter((r) => r[1] === 'Total').forEach((r, i) => assert.ok(Math.abs(r[3] - brute(d, m, i, i + 1)) < 1e-6, `${d.id} ${m} total ${i}`));
    }
    assert.ok(rows.every((r) => /^\d{4}-\d{2}-\d{2}$/.test(r[0]) && (r[4] === 'calls/week' || r[4] === `${d.u}/week`)));
  }
});

test('the x of the chart is the Monday that starts the week, for every file', () => {
  for (const d of docs) {
    const x = weekTimes(d);
    for (let i = 0; i < x.length; i++) assert.equal(x[i], Date.parse(`${weekStart(d, i)}T00:00:00Z`) / 1000, `${d.id} week ${i}`);
    assert.equal(new Date(x[x.length - 1] * 1000).getUTCDay(), 1, `${d.id}: the last x is not a Monday`);
  }
  const d = make(5);
  assert.deepEqual(weekTimes(d).map((t) => new Date(t * 1000).toISOString().slice(0, 10)), ['2025-01-06', '2025-01-13', '2025-01-20', '2025-01-27', '2025-02-03']);
});

test('the week_start of every CSV row is the Monday of its week, and the unit of a row follows its measure', () => {
  const UNIT = { 'port calls': () => 'calls/week', 'estimated export tonnes': (d) => `${d.u}/week`, 'estimated import tonnes': (d) => `${d.u}/week` };
  for (const d of [...docs, make(9, { holes: [4] })]) {
    const rows = csvRows(d);
    const n = weekCount(d);
    rows.forEach((r, k) => {
      const i = Math.floor((k % (n * 5)) / 5);
      assert.equal(r[0], weekStart(d, i), `${d.id} row ${k}`);
      assert.equal(new Date(`${r[0]}T00:00:00Z`).getUTCDay(), 1, `${d.id} row ${k}: not a Monday`);
      assert.ok(UNIT[r[2]], `${d.id} row ${k}: unknown measure ${r[2]}`);
      assert.equal(r[4], UNIT[r[2]](d), `${d.id} row ${k}: the unit of "${r[2]}"`);
    });
  }
});

test('the readout of the chart: a zero is "0", calls are whole numbers, tonnes are written by the general format', () => {
  const general = (v) => `g${v}`;
  const calls = readoutFormatter('calls', general);
  assert.equal(calls(0), '0');
  assert.equal(calls(7), '7');
  assert.equal(calls(1234), '1,234');
  assert.equal(calls(44837), '44,837');
  assert.equal(calls(3.4), '3', 'a count of calls is never decimal');
  for (const m of ['exports', 'imports']) {
    const f = readoutFormatter(m, general);
    assert.equal(f(0), '0');
    assert.equal(f(0.62), 'g0.62');
    assert.equal(f(1500), 'g1500');
  }
});

test('how a tonnage is written', () => {
  assert.equal(fmtTonnes(0), '0 kt');
  assert.equal(fmtTonnes(4.14), '4.14 kt');
  assert.equal(fmtTonnes(4.1), '4.1 kt');
  assert.equal(fmtTonnes(0.0004), '0.0004 kt');
  assert.equal(fmtTonnes(310.4), '310 kt');
  assert.equal(fmtTonnes(999.4), '999 kt');
  assert.equal(fmtTonnes(999.6), '1 Mt', 'a value that rounds to 1,000 kt is written in Mt');
  assert.equal(fmtTonnes(1000), '1 Mt');
  assert.equal(fmtTonnes(7094), '7.09 Mt');
  assert.equal(fmtTonnes(511973), '512 Mt');
  assert.equal(fmtTonnes(1234567), '1,230 Mt');
});

test('the rule of the measure a block opens on, on documents the test makes', () => {
  const nil = make(60, { tonnes: () => 0 });
  assert.equal(defaultMeasure(nil), 'calls', 'both nil: the calls');
  const calm = make(60, { tonnes: () => 0, calls: () => 0 });
  assert.equal(defaultMeasure(calm), 'calls');
  const more = (k) => make(60, { tonnes: (kk) => (kk === k ? 5 : 1) });
  assert.equal(defaultMeasure(more(1)), 'exports');
  assert.equal(defaultMeasure(more(2)), 'imports');
  assert.equal(defaultMeasure(make(60, { tonnes: () => 3 })), 'exports', 'equal: the exports');
});

test('stretches: fewer than 52 weeks, between 52 and 103, 104 and more', () => {
  const short = make(30);
  assert.equal(rolling52(short).last.calls.span, 30);
  assert.equal(rolling52(short).before, null);
  assert.equal(rolling52(make(52)).before, null);
  assert.equal(rolling52(make(103)).before, null);
  const two = make(104);
  const r = rolling52(two);
  assert.equal(r.last.calls.value, brute(two, 'calls', 52, 104));
  assert.equal(r.before.calls.value, brute(two, 'calls', 0, 52));
  assert.equal(r.before.end, weekEnd(two, 51));
  assert.equal(r.last.end, weekEnd(two, 103));
});

test('a week without data is not a zero: it is not counted, the chart leaves a gap and the CSV has no value', () => {
  // 110 weeks: the last 52 are 58 to 109, the 52 before 6 to 57
  const d = make(110, { holes: [0, 60, 61, 109] });
  const { last, before } = rolling52(d);
  for (const m of ['calls', 'exports', 'imports']) {
    assert.equal(last[m].span, 52);
    assert.equal(last[m].weeks, 49, 'the holes 60, 61 and 109 are not counted');
    assert.equal(last[m].value, brute(d, m, 58, 110), 'and add nothing');
    assert.equal(before[m].weeks, 52);
  }
  assert.equal(sumWeeks(d, 'calls', 60, 62).weeks, 0);
  assert.equal(sumText('calls', sumWeeks(d, 'calls', 60, 62)), '—', 'no week of the stretch has a value: a dash, not 0');
  const x = weekTimes(d);
  assert.deepEqual(holeGaps(d), [[x[0] - 7 * 86_400, x[1]], [x[59], x[62]], [x[108], x[109] + 7 * 86_400]], 'a gap runs from the week before a stretch of holes to the week after it');
  assert.deepEqual(holeGaps(make(12)), []);
  const rows = csvRows(d);
  const totals = rows.filter((r) => r[1] === 'Total' && r[2] === 'port calls');
  assert.equal(totals[60][3], null);
  assert.equal(totals[59][3], brute(d, 'calls', 59, 60));
  assert.equal(rows.filter((r) => r[3] === null).length, 3 * 4 * 5, 'four holes, five rows each, three measures');
});

test('names: PortWatch\'s port is named when it is not the asset\'s name', () => {
  assert.ok(sameName('Port Hedland', ' port hedland '));
  assert.ok(!sameName('Richards Bay Coal Terminal', 'Richards Bay'));
  assert.ok(!sameName('Surigao', 'Surigao City'));
});

// ---------------------------------------------------------------- the sentences typed on the assets

const ports = read(path.join(root, 'data/infrastructure/ports.geojson')).features;
const table = new Map();
for (const line of fs.readFileSync(path.join(root, 'pipeline/cache/portwatch_ports.csv'), 'utf8').split(/\r?\n/).slice(1)) {
  const m = line.match(/^([^,]+),("(?:[^"]|"")*"|[^,]*),([^,]*),([^,]*),([^,]*),([^,]*),/);
  if (m) table.set(m[1], { name: m[2].replace(/^"|"$/g, '').replace(/""/g, '"'), lat: Number(m[5]), lon: Number(m[6]) });
}
const km = (a, b, c, d) => {
  const r = Math.PI / 180;
  const h = Math.sin(((c - a) * r) / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(((d - b) * r) / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(h));
};
const NOTED = ['rosario-up-river', 'richards-bay', 'ras-lanuf', 'itaqui'];

test('portwatchNote exists only on ports that have a PortWatch id, and on the four that need a sentence', () => {
  const withNote = ports.filter((f) => f.properties.portwatchNote !== undefined);
  assert.ok(withNote.every((f) => f.properties.type === 'port' && typeof f.properties.portwatch === 'string'));
  assert.deepEqual(withNote.map((f) => f.properties.id).sort(), [...NOTED].sort());
  for (const f of withNote) assert.ok(f.properties.portwatchNote.trim() && f.properties.portwatchNote.length <= 400, f.properties.id);
});

test('the sentences name the PortWatch port as the table names it, and print only distances the files give', () => {
  const by = Object.fromEntries(ports.map((f) => [f.properties.id, f]));
  for (const id of NOTED) {
    const pw = table.get(by[id].properties.portwatch);
    assert.ok(pw, `${id}: its PortWatch id is not in the table`);
    const note = by[id].properties.portwatchNote;
    if (id === 'ras-lanuf') assert.ok(note.includes(pw.name.replace(/ \(.*\)$/, '')) || note.includes('of this name'), id);
    else assert.ok(note.includes(`"${pw.name}"`), `${id}: the note does not name "${pw.name}"`);
  }
  // what a sentence takes from the note of its own asset
  const noteOf = (id) => by[id].properties.note;
  assert.ok(/municipal port/.test(noteOf('rosario-up-river')) && /far larger/.test(noteOf('rosario-up-river')), 'the Rosario sentence quotes what the asset\'s note says');
  assert.ok(/Ponta da Madeira/.test(noteOf('itaqui')) && /next to/.test(noteOf('itaqui')), 'the Itaqui sentence takes the terminal from the asset\'s note');
  assert.ok(/Coal Terminal/.test(by['richards-bay'].properties.name));
  // and says nothing of what PortWatch's port covers: no page read does
  for (const id of ['rosario-up-river', 'richards-bay', 'itaqui']) assert.ok(/No page read says/.test(by[id].properties.portwatchNote), `${id}: the sentence must say that no page read settles the extent`);
  for (const id of NOTED) assert.ok(!/, the (whole|municipal) port;/.test(by[id].properties.portwatchNote), `${id}: states the extent of PortWatch's port as a fact`);
  // Ras Lanuf: the two distances to the World Port Index entries, recomputed from the raw copy of the index and the PortWatch table
  const raw = path.join(root, 'raw/nga/UpdatedPub150.csv');
  if (!fs.existsSync(raw)) return skip('raw/nga/UpdatedPub150.csv is not here: the two distances of the Ras Lanuf sentence are not recomputed');
  const pw = table.get(by['ras-lanuf'].properties.portwatch);
  const lines = fs.readFileSync(raw, 'utf8').replace(/^\uFEFF/, '').split(/\r?\n/);
  const head = lines[0].split(',');
  const col = (n) => head.indexOf(n);
  const find = (name) => {
    for (const l of lines.slice(1)) {
      const c = l.match(/("(?:[^"]|"")*"|[^,]*)(?:,|$)/g)?.map((x) => x.replace(/,$/, '').replace(/^"|"$/g, '').trim()) ?? [];
      if (c[col('Main Port Name')]?.replace(/\s+/g, ' ') === name) return km(pw.lat, pw.lon, Number(c[col('Latitude')]), Number(c[col('Longitude')]));
    }
    return null;
  };
  const note = by['ras-lanuf'].properties.portwatchNote;
  const alt = lines.slice(1).map((l) => l.match(/("(?:[^"]|"")*"|[^,]*)(?:,|$)/g)?.map((x) => x.replace(/,$/, '').replace(/^"|"$/g, '').trim()) ?? []).find((c) => c[col('Main Port Name')] === 'Al Burayqah');
  assert.equal(alt?.[col('Alternate Port Name')], 'Marsa Brega', 'the index names its entry "Al Burayqah" and gives "Marsa Brega" as the other name');
  assert.ok(note.includes('"Al Burayqah" (also called Marsa Brega)'));
  const near = find('Al Burayqah');
  const far = find('Ras Lanuf');
  assert.ok(near !== null && far !== null, 'the two entries of the index are not found');
  assert.ok(note.includes(`${near.toFixed(1)} km`), `the note does not say ${near.toFixed(1)} km`);
  assert.ok(note.includes(`${far.toFixed(1)} km`), `the note does not say ${far.toFixed(1)} km`);
});

// ---------------------------------------------------------------- the sources of the block

const src = (f) => fs.readFileSync(path.join(root, 'web/src', f), 'utf8');

test('the block never reads the port\'s own figures, stores nothing, says nothing live and never calls the tonnes an Atlas estimate', () => {
  for (const f of ['components/views/PortTraffic.tsx', 'components/views/PortTrafficSection.tsx', 'lib/portTraffic.ts']) {
    const t = src(f);
    assert.ok(!/\boutput\b|figuresOf|FigureKpi|OUTPUT_LABEL|capacity/.test(t.replace(/\/\*[\s\S]*?\*\//g, '')), `${f}: reads a figure of the port`);
    assert.ok(!/localStorage|sessionStorage|indexedDB|document\.cookie|location\.hash|history\.(push|replace)State/.test(t), `${f}: stores something or touches the address`);
    assert.ok(!/\blive\b/i.test(t), `${f}: says live`);
    assert.ok(!/Atlas estimate|estimated=\{/.test(t), `${f}: calls PortWatch's tonnes an Atlas estimate`);
  }
  const section = src('components/views/PortTrafficSection.tsx');
  assert.ok(/IMF PortWatch's estimate/.test(section), 'the buttons do not say whose estimate the tonnes are');
  assert.ok(/Exports \(est\.\)/.test(section) && /Imports \(est\.\)/.test(section));
});

test('the port page places the block with one import and one line, for a port that has a PortWatch id, and passes it no figure of the port', () => {
  const t = src('components/views/InfraView.tsx');
  assert.equal(t.match(/import PortTraffic from/g)?.length, 1);
  const lines = t.split('\n').filter((l) => /<PortTraffic\b/.test(l));
  assert.equal(lines.length, 1);
  assert.ok(/p\.type === 'port' && p\.portwatch &&/.test(lines[0]), 'the block is for a port that has the id and for no other asset');
  assert.ok(/id=\{p\.portwatch\}/.test(lines[0]) && /note=\{p\.portwatchNote\}/.test(lines[0]) && !/output|figs/.test(lines[0]));
  assert.ok(/lazy\(\(\) => import\('\.\/PortTrafficSection'\)\)/.test(src('components/views/PortTraffic.tsx')), 'the code of the block is loaded when a port with an id opens');
  assert.ok(/\{note && /.test(src('components/views/PortTrafficSection.tsx')), 'the sentence of the asset is printed');
});
