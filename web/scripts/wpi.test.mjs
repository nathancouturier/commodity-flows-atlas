/**
 * The rows of the World Port Index block of a port page (src/lib/wpi.ts): `node web/scripts/wpi.test.mjs`.
 *
 * Two parts. The depth key is checked against itself and on fixtures built from it (a band floor prints as its band, the top band
 * as "or more", a value off the floors as it is, zero not at all). The rows of every entry of data/infrastructure/wpi.json are then
 * checked against the file: no number is printed that the file (or a band edge of the key) does not hold, no row stands for a
 * figure the file does not give, the labels are the fixed list, and the ports whose maximum vessel the cache holds back have no
 * row for it. The test holds no figure of the data: it derives what it expects from the file.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { WPI_DEPTH_KEY, dayText, depthText as depthTextNb, harbourText, vesselText as vesselTextNb, wpiEntryText, wpiRows as wpiRowsNb, wpiWhen } from '../src/lib/wpi.ts';

// a figure and its unit are joined by a no-break space (the panel never breaks a row inside a figure); the texts are compared with a plain one
const flat = (t) => (typeof t === 'string' ? t.replace(/\u00a0/g, ' ') : t);
const depthText = (v) => flat(depthTextNb(v));
const vesselText = (...a) => flat(vesselTextNb(...a));
const wpiRows = (e) => wpiRowsNb(e).map((r) => ({ ...r, value: flat(r.value) }));

const here = path.dirname(fileURLToPath(import.meta.url));
const file = JSON.parse(fs.readFileSync(path.join(here, '../../data/infrastructure/wpi.json'), 'utf8'));
const meta = JSON.parse(fs.readFileSync(path.join(here, '../../pipeline/cache/wpi_meta.json'), 'utf8'));
const entries = Object.entries(file.ports);

const LABELS = [
  'Channel depth', 'Anchorage depth', 'Cargo pier depth', 'Oil terminal depth', 'LNG terminal depth',
  'Maximum vessel', 'Offshore maximum vessel', 'Tidal range', 'Harbour', 'Pilotage', 'Tide restricts entry',
];
// the four depths of the publication's key are bands; the LNG terminal depth is a column the key does not cover and is printed as given
const BAND_FIELDS = { 'Channel depth': 'chan', 'Anchorage depth': 'anch', 'Cargo pier depth': 'pier', 'Oil terminal depth': 'oil' };
const DEPTH_FIELDS = { ...BAND_FIELDS, 'LNG terminal depth': 'lng' };
/** the numbers a text holds, as numbers */
const numbers = (t) => (t.match(/\d[\d,]*(?:\.\d+)?/g) ?? []).map((x) => Number(x.replace(/,/g, '')));
const enUS = (v) => v.toLocaleString('en-US', { maximumFractionDigits: 3 });

// ---------------------------------------------------------------- the key

test('the key is the sixteen bands of the publication, in order, with no gap but the rounding of feet to metres', () => {
  assert.equal(WPI_DEPTH_KEY.length, 16);
  assert.deepEqual(WPI_DEPTH_KEY.map((b) => b.code).join(''), 'abcdefghjklmnopq'.replace('i', ''));
  assert.equal(WPI_DEPTH_KEY[0].to, null, 'only the top band is open');
  for (const [i, b] of WPI_DEPTH_KEY.entries()) {
    if (i > 0) assert.ok(b.to != null && b.to > b.from, `${b.code}: the band is not empty`);
    const above = WPI_DEPTH_KEY[i - 1];
    if (above) {
      assert.ok(above.from > b.to, `${b.code}: the bands do not overlap`);
      const gap = above.from - b.to;
      assert.ok(gap > 0 && gap < 0.7, `${b.code}: ${gap} m between the top of this band and the floor of the one above`);
    }
    // steps of 5 feet, about 1.5 m: the floors are 1.4 to 1.7 m apart down to the lowest one the publication prints
    if (above && b.from > 0) assert.ok(above.from - b.from > 1.4 && above.from - b.from < 1.7, `${b.code}: the floors are one step of 5 feet apart`);
  }
  assert.equal(WPI_DEPTH_KEY.at(-1).from, 0);
});

test('a depth that is the floor of a band prints as the band, the top band as "or more"', () => {
  for (const b of WPI_DEPTH_KEY) {
    if (b.from === 0) continue;
    const want = b.to == null ? `${b.from.toFixed(1)} m or more` : `${b.from.toFixed(1)} to ${b.to.toFixed(1)} m`;
    assert.equal(depthText(b.from), want, b.code);
  }
  // the file writes a whole number without its ".0"
  const whole = WPI_DEPTH_KEY.find((b) => Number.isInteger(b.from));
  assert.ok(whole && depthText(whole.from).startsWith(`${whole.from}.0 `));
});

test('a depth off the floors prints as given, and a figure that is not stated prints nothing', () => {
  const top = WPI_DEPTH_KEY[0];
  assert.equal(depthText(16.1), '16.1 m');
  assert.equal(depthText(36.5), '36.5 m');
  assert.equal(depthText(970), '970 m');
  assert.equal(depthText(top.from + 0.1), `${(top.from + 0.1).toFixed(1)} m`, 'above the top floor but not on it');
  // the top of a band is not the floor of one: the publication's next band starts a step lower
  const g = WPI_DEPTH_KEY.find((b) => b.code === 'g');
  assert.equal(depthText(g.to), `${g.to} m`);
  for (const v of [0, -1, NaN, Infinity, undefined, null, '14']) assert.equal(depthText(v), null, String(v));
});

test('the maximum vessel prints the parts the publication states, in order', () => {
  assert.equal(vesselText(340, 60, 11.8), '340 m long, 60 m beam, 11.8 m draught');
  assert.equal(vesselText(340, undefined, undefined), '340 m long');
  assert.equal(vesselText(undefined, undefined, 11.8), '11.8 m draught');
  assert.equal(vesselText(1000, 0, undefined), '1,000 m long');
  assert.equal(vesselText(), null);
  assert.equal(vesselText(0, 0, 0), null);
});

test('a figure is never parted from its unit by a space that breaks', () => {
  const e = Object.values(file.ports).find((x) => x.loa && x.beam && x.draft && x.chan && x.tide);
  for (const r of wpiRowsNb(e)) assert.ok(!/\d m\b/.test(r.value), `${r.label}: ${JSON.stringify(r.value)}`);
  assert.ok(wpiRowsNb(e).some((r) => /\d\u00a0m/.test(r.value)));
});

test('the harbour is the class and the type, in sentence case', () => {
  assert.equal(harbourText('Medium', 'River (Natural)'), 'Medium, river (natural)');
  assert.equal(harbourText('Very Small', 'Open Roadstead'), 'Very small, open roadstead');
  assert.equal(harbourText(undefined, 'Coastal (Breakwater)'), 'Coastal (breakwater)');
  assert.equal(harbourText('Large', undefined), 'Large');
  assert.equal(harbourText(), null);
});

test('the rows of a fixture follow the fixed order and leave out what is not stated', () => {
  const floor = WPI_DEPTH_KEY[6].from;
  const rows = wpiRows({ n: 1, name: 'Testport', by: 'code', km: 0, chan: floor, pier: 16.1, loa: 300, pilot: 'No', tideRes: 'Yes', size: 'Small', type: 'Coastal (Natural)' });
  assert.deepEqual(
    rows.map((r) => r.label),
    ['Channel depth', 'Cargo pier depth', 'Maximum vessel', 'Harbour', 'Pilotage', 'Tide restricts entry'],
  );
  assert.deepEqual(rows.map((r) => r.value), [depthText(floor), '16.1 m', '300 m long', 'Small, coastal (natural)', 'Not compulsory', 'Yes']);
  assert.deepEqual(wpiRows({ n: 1, name: 'Testport', by: 'code', km: 0 }), []);
  // the LNG terminal depth is never a band, whether or not it sits on a floor of the key
  const lng = (v) => wpiRows({ n: 1, name: 'Testport', by: 'code', km: 0, lng: v })[0];
  assert.deepEqual(lng(floor), { label: 'LNG terminal depth', value: `${floor} m` });
  assert.equal(lng(12.8).value, '12.8 m');
  assert.equal(lng(WPI_DEPTH_KEY[0].from).value, `${WPI_DEPTH_KEY[0].from} m`);
  assert.equal(wpiRows({ n: 1, name: 'Testport', by: 'code', km: 0, pilot: 'Yes' })[0].value, 'Compulsory');
  assert.equal(wpiEntryText({ name: 'Testport', n: 42 }), 'Testport, no. 42');
});

// ---------------------------------------------------------------- the file

test('the file has entries to print', () => {
  assert.ok(entries.length > 100);
});

test('the labels are the fixed list, once each and in its order; each entry has at least one row', () => {
  for (const [id, e] of entries) {
    const labels = wpiRows(e).map((r) => r.label);
    assert.ok(labels.length > 0, id);
    assert.equal(new Set(labels).size, labels.length, id);
    assert.deepEqual(labels, LABELS.filter((l) => labels.includes(l)), `${id}: order`);
  }
});

test('a row stands for a figure the file gives, and no figure of the file is left out or invented', () => {
  for (const [id, e] of entries) {
    const rows = Object.fromEntries(wpiRows(e).map((r) => [r.label, r.value]));
    for (const [label, k] of Object.entries(DEPTH_FIELDS)) {
      assert.equal(label in rows, e[k] != null, `${id}: ${label}`);
      if (e[k] == null) continue;
      // the first number is the figure itself, whether it is the floor of a band or off the floors
      assert.equal(numbers(rows[label])[0], e[k], `${id}: ${label}`);
      assert.ok(label === 'LNG terminal depth' ? rows[label] === `${enUS(e[k])} m` : rows[label].endsWith(' m') || rows[label].endsWith(' m or more'), `${id}: ${label}`);
      assert.ok(!/(^|\D)0(\.0)? m/.test(rows[label]), `${id}: ${label} prints a zero`);
    }
    assert.equal('Maximum vessel' in rows, e.loa != null || e.beam != null || e.draft != null, `${id}: maximum vessel`);
    if (rows['Maximum vessel']) assert.deepEqual(numbers(rows['Maximum vessel']), [e.loa, e.beam, e.draft].filter((v) => v != null), id);
    assert.equal('Offshore maximum vessel' in rows, e.oloa != null || e.obeam != null || e.odraft != null, `${id}: offshore`);
    if (rows['Offshore maximum vessel']) assert.deepEqual(numbers(rows['Offshore maximum vessel']), [e.oloa, e.obeam, e.odraft].filter((v) => v != null), id);
    assert.equal('Tidal range' in rows, e.tide != null, `${id}: tide`);
    if (e.tide != null) assert.equal(rows['Tidal range'], `${enUS(e.tide)} m`);
    assert.equal('Harbour' in rows, e.size != null || e.type != null, `${id}: harbour`);
    assert.equal('Pilotage' in rows, e.pilot != null, `${id}: pilotage`);
    if (e.pilot) assert.equal(rows.Pilotage, e.pilot === 'Yes' ? 'Compulsory' : 'Not compulsory');
    assert.equal('Tide restricts entry' in rows, e.tideRes != null, `${id}: tide restricts`);
    if (e.tideRes) assert.equal(rows['Tide restricts entry'], e.tideRes);
  }
});

test('every number of every row is a figure of the entry or an edge of the key', () => {
  const edges = new Set(WPI_DEPTH_KEY.flatMap((b) => [b.from, b.to]).filter((v) => v != null));
  for (const [id, e] of entries) {
    const own = new Set(['chan', 'anch', 'pier', 'oil', 'lng', 'loa', 'beam', 'draft', 'oloa', 'obeam', 'odraft', 'tide'].map((k) => e[k]).filter((v) => v != null));
    for (const r of wpiRows(e)) {
      for (const v of numbers(r.value)) assert.ok(own.has(v) || (BAND_FIELDS[r.label] && edges.has(v)), `${id}: ${r.label} prints ${v}`);
    }
  }
});

test('a figure is a band exactly when it sits on a floor of the key, and only the four depths of the key are bands', () => {
  const floors = new Set(WPI_DEPTH_KEY.map((b) => b.from));
  for (const [id, e] of entries) {
    for (const r of wpiRows(e)) {
      const band = / to |or more/.test(r.value);
      if (!BAND_FIELDS[r.label]) assert.ok(!band, `${id}: ${r.label}`);
      else assert.equal(band, floors.has(e[BAND_FIELDS[r.label]]), `${id}: ${r.label}`);
    }
  }
});

test('most depths of the file sit on the floors of the key, which is the evidence that the key is the file\'s', () => {
  const floors = new Set(WPI_DEPTH_KEY.map((b) => b.from));
  const all = entries.flatMap(([, e]) => Object.values(BAND_FIELDS).map((k) => e[k]).filter((v) => v != null));
  const on = all.filter((v) => floors.has(v)).length;
  assert.ok(on / all.length > 0.7, `${on} of ${all.length}`);
  // the top band is what the file's heap at its largest value is
  assert.ok(entries.some(([, e]) => wpiRows(e).some((r) => r.value.endsWith(' m or more'))));
});

test('the ports whose maximum vessel the cache holds back have no row for it, and keep their depths', () => {
  assert.ok(meta.held_vessel.length > 0);
  for (const h of meta.held_vessel) {
    const e = file.ports[h.id];
    assert.ok(e, `${h.id} has an entry`);
    const labels = wpiRows(e).map((r) => r.label);
    assert.ok(!labels.includes(h.group === 'maximum' ? 'Maximum vessel' : 'Offshore maximum vessel'), `${h.id}: ${h.group}`);
    assert.ok(labels.some((l) => l.endsWith('depth')), `${h.id} keeps a depth`);
  }
});

test('the entry line names the entry and its number as the file gives them, and no more', () => {
  for (const [id, e] of entries) {
    const t = wpiEntryText(e);
    assert.equal(t, `${e.name}, no. ${e.n}`, id);
    assert.ok(!/code|name and position|review|\bkm\b/i.test(t.replace(e.name, '')), id);
  }
});

test('no printed text is an estimate, an instruction or a comparison', () => {
  for (const [id, e] of entries) {
    for (const r of wpiRows(e)) assert.ok(!/estimate|see |click|note that|differs|than the/i.test(`${r.label} ${r.value}`), `${id}: ${r.label}`);
  }
});

test('the LNG terminal depth is printed as the file gives it; the one that sits on a floor of the key is no band', () => {
  const floors = new Set(WPI_DEPTH_KEY.map((b) => b.from));
  const withLng = entries.filter(([, e]) => e.lng != null);
  assert.ok(withLng.length > 0);
  for (const [id, e] of withLng) {
    assert.equal(wpiRows(e).find((r) => r.label === 'LNG terminal depth').value, `${enUS(e.lng)} m`, id);
  }
  // Manzanillo's depth is the floor of a band of the key, and reads as the figure the file gives
  const manzanillo = file.ports['manzanillo-mexico'];
  assert.ok(floors.has(manzanillo.lng), 'the case this test is about');
  assert.equal(wpiRows(manzanillo).find((r) => r.label === 'LNG terminal depth').value, `${enUS(manzanillo.lng)} m`);
});

// ---------------------------------------------------------------- the source line

test('the day is written as the site writes a date', () => {
  const status = fs.readFileSync(path.join(here, '../src/lib/status.ts'), 'utf8');
  const mon = /const MON = \[([^\]]+)\]/.exec(status)[1].match(/'([A-Za-z]+)'/g).map((x) => x.slice(1, -1));
  for (const [i, m] of mon.entries()) assert.equal(dayText(`2026-${String(i + 1).padStart(2, '0')}-09`), `9 ${m} 2026`);
  assert.equal(dayText('2026-09-29'), '29 Sep 2026');
  assert.equal(dayText('2026-09'), '2026-09', 'what is not a day is returned as it is');
});

test('the source line names the archived copy when the file has a capture date, else the month it was read', () => {
  assert.equal(wpiWhen({ read: '2026-11', captured: '2026-09-29', edition: null }, 'November 2026'), 'Internet Archive copy of 29 Sep 2026');
  assert.equal(wpiWhen({ read: '2026-11', edition: null }, 'November 2026'), 'read November 2026');
  // a typed edition goes into the name of the source, so a file from the publisher has nothing to add; an archived copy is still said
  assert.equal(wpiWhen({ read: '2026-11', edition: 'Pub. 150, 27th edition' }, 'November 2026'), null);
  assert.equal(wpiWhen({ read: '2026-11', captured: '2026-09-29', edition: 'Pub. 150, 27th edition' }, 'November 2026'), 'Internet Archive copy of 29 Sep 2026');
});

test('the data file and the meta file give the same capture day, and the line carries it', () => {
  assert.equal(file.captured, meta.captured ?? undefined);
  assert.match(String(meta.captured_from ?? ''), meta.captured ? /^https:\/\/web\.archive\.org\/web\/\d{14}id_\/https:\/\/msi\.nga\.mil\// : /^$/);
  if (meta.captured) assert.ok(meta.captured_from.includes(meta.captured.replace(/-/g, '')), 'the address is the capture of that day');
  const line = wpiWhen(file, 'November 2026');
  if (file.captured) assert.equal(line, `Internet Archive copy of ${dayText(file.captured)}`);
  else assert.ok(file.edition || /^read /.test(line));
  assert.ok(!/read November/.test(line ?? ''), 'a file that has a capture date is not described by the month it was read');
});
