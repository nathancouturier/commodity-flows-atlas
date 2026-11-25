/**
 * The Freight market now page: the figures of src/lib/marketNow.ts against the weekly files of data/freight/portwatch (every row of
 * data/freight/market-now.json is rebuilt from them by date, not read from the digest), the way a rise, a fall and a collapse are
 * worded, the cases where the digest is missing or malformed, and the words and attributes of the view: `node web/scripts/market-now.test.mjs`.
 *
 * The test holds no figure of the data: the cases that need numbers use series the test makes, and the real files are read when it runs.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { DALLAS_WORDS, INDICATORS, LINK_ONLY, NOT_A_RATE, dallasNote, indicatorNote, isDeviation, percentOnYear, valueInMonth, yearEarlier } from '../src/lib/freightIndicators.ts';
import { TINY_MT, addDays, buildDigest, cargoOver, changePct, changeText, countText, isIsoDay, lastWeekEnd, mtChangeText, mtText, readMarketNow, rowText, sig3, vesselsOver, weekIndex } from '../src/lib/marketNow.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const src = (rel) => fs.readFileSync(path.join(here, '../src', rel), 'utf8');
const json = (rel) => JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
const weekly = () =>
  fs
    .readdirSync(path.join(root, 'data/freight/portwatch'))
    .filter((f) => f.endsWith('.json'))
    .sort()
    .map((f) => json(`data/freight/portwatch/${f}`));

/** A weekly file the test makes: `weeks` weeks from a Monday, the last day a Sunday unless `extra` days follow it. */
const series = (id, weeks, { start = '2024-01-01', extra = 0, tanker = () => 1, dry = () => 1, vt = () => 0.1, vd = () => 0.1 } = {}) => {
  const n = weeks + (extra ? 1 : 0);
  const idx = [...Array(n).keys()];
  return { id, start, y: addDays(start, 7 * weeks - 1 + extra), tanker: idx.map(tanker), dry: idx.map(dry), vol: { tanker: idx.map(vt), dry: idx.map(vd) } };
};

// ---------------------------------------------------------------- the words of a change

test('a rise, a fall and a collapse to near zero are worded with a true minus and one decimal', () => {
  assert.equal(changeText(125, 100), '+25.0%');
  assert.equal(changeText(75, 100), '−25.0%');
  assert.equal(changeText(2, 1000), '−99.8%', 'a collapse is a fall: the figure says how far');
  assert.equal(changeText(100, 100), '0%');
  assert.equal(changeText(0, 100), '−100%', '"−100%" only when nothing is left');
  assert.equal(changeText(1, 10000), '−99.9%', 'a fall that one decimal would round to 100% while ships remain');
  assert.equal(changeText(100.01, 100), '+<0.1%');
  assert.equal(changeText(99.99, 100), '−<0.1%');
  assert.equal(changeText(3000, 100), '+2900.0%');
  assert.ok(!changeText(75, 100).includes('-'), 'no hyphen-minus');
});

test('a year earlier of zero or nothing has no per cent: the page prints a dash', () => {
  assert.equal(changePct(5, 0), null);
  assert.equal(changeText(5, 0), '—');
  assert.equal(changeText(0, 0), '—');
  assert.equal(changeText(null, 10), '—');
  assert.equal(changeText(10, undefined), '—');
  assert.equal(changeText(Number.NaN, 10), '—');
});

test('the cargo follows the status board: under 0.05 Mt is said as a bound and has no per cent', () => {
  // the same constant as the board, which this page must agree with
  assert.match(src('components/views/BoardView.tsx'), new RegExp(`const TINY_MT = ${TINY_MT};`));
  assert.equal(mtText(TINY_MT / 2), `under ${TINY_MT} Mt`);
  assert.equal(mtText(0), '0 Mt');
  assert.equal(mtText(null), '—');
  assert.equal(mtText(87.2), '87.2 Mt');
  assert.equal(mtText(1280), '1,280 Mt');
  assert.equal(mtText(0.253), '0.253 Mt');
  assert.equal(mtText(0.0512), '0.0512 Mt');
  assert.equal(mtChangeText(TINY_MT / 2, 40), `down more than ${Math.floor((100 * (40 - TINY_MT)) / 40)}%`);
  assert.equal(mtChangeText(TINY_MT / 2, TINY_MT / 4), '—', 'nothing to compare when both are that small');
  assert.equal(mtChangeText(10, TINY_MT / 2), '—');
  assert.equal(mtChangeText(0, 40), '−100%');
  assert.equal(mtChangeText(90, 120), changeText(90, 120));
  assert.equal(countText(2373), '2,373');
  assert.equal(countText(0), '0');
  assert.equal(countText(null), '—');
});

test('a row is written as the figures, the two years and the change of each measure', () => {
  const t = rowText({ id: 'x', now: 2373, ago: 2750, mt: { now: 134, ago: 158 }, rankMt: 1 });
  assert.deepEqual(t.transits, { now: '2,373', ago: '2,750', change: changeText(2373, 2750) });
  assert.deepEqual(t.cargo, { now: '134 Mt', ago: '158 Mt', change: changeText(134, 158) });
  const zero = rowText({ id: 'x', now: 4, ago: 0, mt: { now: 1, ago: 0 }, rankMt: 0 });
  assert.equal(zero.transits.change, '—');
  assert.equal(zero.cargo.change, '—');
});

// ---------------------------------------------------------------- the digest as the page reads it

test('the published digest is read; a file that is not a digest is not', () => {
  const real = json('data/freight/market-now.json');
  const d = readMarketNow(real);
  assert.ok(d, 'the published file is a digest');
  assert.equal(d.types.dry.length, real.types.dry.length);
  assert.deepEqual(d.types.tanker[0], real.types.tanker[0]);
  const clone = () => structuredClone(real);
  const bad = [
    ['not an object', null],
    ['a string', 'x'],
    ['no types', { ...clone(), types: undefined }],
    ['no tanker list', (() => { const c = clone(); delete c.types.tanker; return c; })()],
    ['a list that is not a list', (() => { const c = clone(); c.types.dry = {}; return c; })()],
    ['a date that is not a day', { ...clone(), to: '2026-13-40' }],
    ['a date in another form', { ...clone(), yearAgoTo: '25 November 2025' }],
    ['no unit', { ...clone(), unit: undefined }],
    ['no source', { ...clone(), s: undefined }],
    ['a count as text', (() => { const c = clone(); c.types.dry[0].now = '12'; return c; })()],
    ['a null count', (() => { const c = clone(); c.types.dry[0].ago = null; return c; })()],
    ['a negative count', (() => { const c = clone(); c.types.tanker[1].now = -1; return c; })()],
    ['an infinite cargo', (() => { const c = clone(); c.types.tanker[1].mt.now = Infinity; return c; })()],
    ['a row without its cargo', (() => { const c = clone(); delete c.types.tanker[0].mt; return c; })()],
    ['a row without an id', (() => { const c = clone(); c.types.dry[2].id = ''; return c; })()],
  ];
  for (const [what, doc] of bad) assert.equal(readMarketNow(doc), null, what);
  // an empty list is a digest with nothing to show for that type: the page says so for it alone
  const empty = clone();
  empty.types.tanker = [];
  assert.deepEqual(readMarketNow(empty).types.tanker, []);
  assert.ok(readMarketNow(empty).types.dry.length > 0);
});

test('the dates of the digest are real days, 364 days apart, and the unit words name the window', () => {
  const d = json('data/freight/market-now.json');
  assert.ok(isIsoDay(d.to) && isIsoDay(d.yearAgoTo));
  assert.equal(addDays(d.to, -364), d.yearAgoTo);
  assert.equal(new Date(`${d.to}T00:00:00Z`).getUTCDay(), 0, 'the window ends on a Sunday');
  assert.equal(d.days, 7 * d.weeks);
  assert.ok(d.unit.includes(`${d.days} days`) && d.mtUnit.includes(`${d.days} days`));
  assert.equal(isIsoDay('2026-02-30'), false);
});

// ---------------------------------------------------------------- the arithmetic, by date

test('weeks are taken by date: a file whose length does not match its dates is refused', () => {
  const ok = series('a', 60);
  assert.equal(lastWeekEnd(ok), ok.y);
  assert.equal(weekIndex(ok, ok.y), 59);
  assert.equal(weekIndex(ok, '2024-01-07'), 0);
  const missing = series('a', 60);
  for (const k of ['tanker', 'dry']) missing[k].pop();
  missing.vol.tanker.pop();
  missing.vol.dry.pop();
  assert.throws(() => lastWeekEnd(missing), /weeks from 2024-01-01/);
  const tuesday = series('a', 60, { start: '2024-01-02' });
  assert.throws(() => lastWeekEnd(tuesday), /not a Monday/);
  const lists = series('a', 60);
  lists.vol.dry.pop();
  assert.throws(() => lastWeekEnd(lists), /weeks from/);
  assert.throws(() => weekIndex(ok, '2024-01-08'), /no week ends on/, 'a Monday ends no week');
  assert.throws(() => weekIndex(ok, '2023-12-31'), /no week ends on/, 'before the first week');
  assert.throws(() => weekIndex(ok, addDays(ok.y, 7)), /no week ends on/, 'after the last');
});

test('the last week of a file whose last day is not a Sunday is not complete and is left out', () => {
  const s = series('a', 60, { extra: 3, tanker: (i) => (i === 60 ? 999 : 1) });
  assert.equal(s.tanker.length, 61);
  assert.equal(lastWeekEnd(s), addDays(s.start, 7 * 60 - 1));
  assert.equal(vesselsOver(s, 'tanker', lastWeekEnd(s), 4), 28, 'four weeks of one vessel a day: the partial week of 999 is not in it');
  assert.throws(() => weekIndex(s, addDays(lastWeekEnd(s), 7)), /no week ends on/);
});

test('vessels are the weekly means times 7, whole vessels, a half rounded up; cargo has three significant figures', () => {
  const s = series('a', 60, { tanker: () => 0.1, vt: () => 0.0123 });
  assert.equal(vesselsOver(s, 'tanker', s.y, 4), 3, '0.1 x 28 = 2.8, three whole vessels');
  const half = series('a', 60, { tanker: () => 0.1 });
  half.tanker[59] = 0.2; // 0.1 + 0.1 + 0.1 + 0.2 = 0.5 a day-week sum, x 7 = 3.5
  assert.equal(vesselsOver(half, 'tanker', half.y, 4), 4, 'a half rounds up, with no binary rounding to decide it');
  assert.equal(cargoOver(s, 'tanker', s.y, 4), 0.344, '0.0123 x 28 = 0.3444');
  assert.equal(sig3(12345, 2), 123, 'three figures of 123.45');
  assert.equal(sig3(1235, 1), 124, 'a half rounds up: 123.5');
  assert.equal(sig3(99950, 3), 100, 'rounding carries into a new digit');
  assert.equal(sig3(0, 4), 0);
  assert.equal(sig3(12, 4), 0.0012, 'fewer than three digits are exact');
  assert.throws(() => vesselsOver(series('a', 60, { tanker: () => 0.123 }), 'tanker', '2025-02-23', 4), /more than 1 decimals/);
  assert.throws(() => vesselsOver(series('a', 60, { tanker: () => 'x' }), 'tanker', '2025-02-23', 4), /not a finite number/);
  assert.throws(() => vesselsOver(series('a', 60, { tanker: () => -1 }), 'tanker', '2025-02-23', 4), /not a finite number/);
});

test('the five passages are those with the most cargo a year back; ties go by id', () => {
  const all = [];
  // seven passages over 120 weeks: a, b, c tie for first on the ranking weeks, so their ids decide; the passage that collapsed this year stays ranked
  const weeks = 120;
  const make = (id, back, now) => series(id, weeks, { dry: () => 1, vd: (i) => (i >= weeks - 4 ? now : back) });
  for (const [id, back, now] of [['c', 0.5, 0.5], ['a', 0.5, 0.5], ['b', 0.5, 0.5], ['d', 0.4, 0.4], ['e', 0.3, 0.3], ['f', 0.2, 0.2], ['collapsed', 0.45, 0]]) all.push(make(id, back, now));
  const d = buildDigest(all);
  assert.deepEqual(d.types.dry.map((r) => r.id), ['a', 'b', 'c', 'collapsed', 'd']);
  assert.equal(d.types.dry[3].mt.now, 0, 'nothing carried now');
  assert.ok(d.types.dry[3].mt.ago > 0);
  assert.equal(d.to, addDays('2024-01-01', 7 * weeks - 1));
  assert.equal(d.yearAgoTo, addDays(d.to, -364));
  assert.equal(d.types.dry[0].rankMt, sig3(Math.round(0.5 * 1e4) * 52 * 7, 4));
});

test('the window ends on the earliest last complete week of the files', () => {
  const all = ['a', 'b', 'c', 'd', 'e'].map((id, i) => series(id, 110 - (i === 2 ? 1 : 0)));
  assert.equal(buildDigest(all).to, addDays('2024-01-01', 7 * 109 - 1));
});

// ---------------------------------------------------------------- the published file, rebuilt from the weekly files

test('every row of the digest is rebuilt from the weekly files, by date', () => {
  const all = weekly();
  assert.ok(all.length >= 5);
  const file = json('data/freight/market-now.json');
  const built = buildDigest(all);
  assert.equal(built.to, file.to, 'the window ends where the files say');
  assert.equal(built.yearAgoTo, file.yearAgoTo);
  for (const t of ['tanker', 'dry']) {
    assert.equal(file.types[t].length, built.types[t].length);
    file.types[t].forEach((row, i) => assert.deepEqual(row, built.types[t][i], `${t} row ${i + 1} (${row.id})`));
  }
  // every file holds together (weeks by date) and none ends before the window
  for (const s of all) assert.ok(lastWeekEnd(s) >= file.to, s.id);
  // a passage that is not shown carries no more cargo of the type a year back than the fifth one
  for (const t of ['tanker', 'dry']) {
    const shown = new Set(file.types[t].map((r) => r.id));
    const floor = file.types[t].at(-1).rankMt;
    for (const s of all) if (!shown.has(s.id)) assert.ok(cargoOver(s, t, file.yearAgoTo, file.rankWeeks) <= floor, `${t}: ${s.id}`);
  }
  // the ranking is not increasing; passages are named once in a list
  for (const t of ['tanker', 'dry']) {
    const r = file.types[t].map((x) => x.rankMt);
    assert.deepEqual([...r].sort((a, b) => b - a), r);
    assert.equal(new Set(file.types[t].map((x) => x.id)).size, file.types[t].length);
  }
});

test('the figures of the digest are those of the status board and the banners within the rounding of the weekly means', () => {
  // `compare` of a weekly file is the 28-day total of all ships; the digest's ship types are parts of it
  const file = json('data/freight/market-now.json');
  const by = Object.fromEntries(weekly().map((s) => [s.id, s]));
  for (const t of ['tanker', 'dry']) {
    for (const r of file.types[t]) {
      const c = by[r.id].compare;
      if (!c || c.to !== file.to) continue;
      assert.ok(r.now <= c.transits.now + 1.5, `${r.id}: ${t} transits are part of all ships`);
      assert.ok(r.ago <= c.transits.yearAgo + 1.5, `${r.id}: ${t} transits a year earlier`);
    }
  }
});

test('every row of the real digest prints the way the page prints it', () => {
  const file = json('data/freight/market-now.json');
  const d = readMarketNow(file);
  let collapsed = 0;
  for (const t of ['tanker', 'dry']) {
    for (const r of d.types[t]) {
      const text = rowText(r);
      assert.equal(text.transits.now, r.now.toLocaleString('en-US'));
      if (r.ago > 0) {
        const p = (100 * (r.now - r.ago)) / r.ago;
        assert.ok(Math.abs(Number(text.transits.change.replace('−', '-').replace('%', '')) - p) <= 0.051, `${r.id}: ${text.transits.change}`);
        if (r.now / r.ago < 0.1) {
          collapsed++;
          assert.match(text.transits.change, /^−9\d(\.\d)?%$/, 'a collapse reads as a fall of more than 90%');
        }
      }
    }
  }
  if (!collapsed) console.log('no passage of the file has fallen below a tenth of a year earlier: the collapse wording is tested on the series above');
});

// ---------------------------------------------------------------- the view, the entry and what they must not do

test('the page carries the words of the decisions: what it is and is not, how the five are chosen, the classes, the data adapted', () => {
  const view = src('components/views/FreightNowView.tsx');
  assert.match(view, /<h2 class="detail-title">Freight market now<\/h2>/);
  assert.match(view, /This page shows traffic at the main passages and two indicators, none of them a freight rate:/);
  assert.match(view, /the atlas shows no spot rate for tankers or gas carriers and no Baltic Exchange index value, since the sources it knows for them are proprietary or cannot be republished/);
  assert.match(view, /No traffic figures are available\./);
  assert.match(view, /PortWatch lists five ship classes \(container, dry bulk, general cargo, ro-ro and tanker\) and defines none, so the atlas cannot say whether gas carriers are in its tanker class: the tanker figures above may include them or not\. The atlas shows no separate gas carrier figure\./);
  assert.match(view, /a rule of the atlas, not of PortWatch/);
  assert.match(view, /over the \{digest\.rankWeeks\} weeks to \{digest\.yearAgoTo\}/);
  assert.match(view, /data adapted/);
  assert.match(view, /the cargo is PortWatch's estimate of what the vessels carry, not a customs statistic/);
  const lib = src('lib/marketNow.ts');
  assert.match(lib, /title: 'Dry bulk carriers at the five passages with the most cargo'/);
  assert.match(lib, /title: 'Tankers at the five passages with the most cargo'/);
  // no universal negative, no licence claim, no value of a source the atlas links only
  for (const text of [view, lib, src('lib/freightIndicators.ts')]) {
    assert.doesNotMatch(text, /no free (source|series)|public domain|free to reuse|open licen[cs]e/i);
    assert.doesNotMatch(text, /\b(USDA|Shanghai|Baltic Dry|CDFI|CTFI)\b.*\d/);
  }
  // tankers and gas carriers are not two counts: the sentence says the tanker class may hold the gas carriers
  assert.doesNotMatch(view, /tanker and gas carrier counts|gas carriers? (count|figure) of/i);
  // the page names the atlas's passages from the catalogue and degrades to the id
  assert.match(view, /loadChokepoints\(\)\.catch\(\(\) => \[\] as Chokepoint\[\]\)/);
  assert.match(view, /name \?\? row\.id/);
});

test('every figure container carries its source and its dates, and the view says its source with the site\'s source line', () => {
  const view = src('components/views/FreightNowView.tsx');
  // the row is a button when the passage has a page and text when it has none: both carry what the citation reads
  assert.equal((view.match(/data-src=\{src\} data-y=\{y\}/g) ?? []).length, 2);
  assert.match(view, /<SourceLine\s+s=\{digest\.s\}\s+y=\{dates\}/);
  assert.match(view, /\$\{digest\.weeks\} weeks to \$\{digest\.to\}, against \$\{digest\.weeks\} weeks to \$\{digest\.yearAgoTo\}/);
  // the source is a registry id and the dates are the two ends of the windows
  const reg = json('data/sources.json');
  assert.ok(reg.some((s) => s.id === json('data/freight/market-now.json').s));
});

test('nothing is stored in the browser, no hint is shown, and the page opens only when asked', () => {
  for (const rel of ['components/views/FreightNowView.tsx', 'lib/marketNow.ts', 'lib/freightIndicators.ts']) {
    assert.doesNotMatch(src(rel), /localStorage|sessionStorage|indexedDB|document\.cookie/, rel);
  }
  const panel = src('components/SidePanel.tsx');
  const entry = panel.slice(panel.indexOf('function FreightNowEntry'), panel.indexOf('/** "VLOC (Valemax/Guaibamax)"'));
  assert.match(entry, /if \(family\.value !== 'freight' && !open\) return null;/, 'on the Freight view or while the page is open');
  assert.match(entry, /aria-pressed=\{open\}/);
  assert.match(entry, /select\(open \? null : \{ kind: 'board', id: 'freight-now' \}\)/, 'a second click closes it');
  assert.match(entry, />\s*Freight market now\s*<\/button>/);
  assert.doesNotMatch(entry, /title=|hint|cc-hint/, 'no hint text, no value');
  // immediately under Routes by vessel class
  assert.match(panel, /<FreightSection \/>\s*<FreightNowEntry \/>\s*<div class="panel-block">\s*<Dropdown name="Route finder"/);
  // nothing opens it on load: no selection is written outside the click
  assert.equal((panel.match(/id: 'freight-now'/g) ?? []).length, 1);
});

test('the page is a lazy view of the detail panel; the other board ids still go to the status board', () => {
  const detail = src('components/DetailPanel.tsx');
  assert.match(detail, /const FreightNowView = lazy\(\(\) => import\('\.\/views\/FreightNowView'\)\);/);
  assert.match(detail, /s\.kind === 'board' && s\.id === 'freight-now' \? \(\s*<FreightNowView \/>\s*\) : s\.kind === 'board' \? \(\s*<BoardView id=\{s\.id\} \/>/);
  assert.doesNotMatch(src('components/SidePanel.tsx'), /import .*FreightNowView/);
  // the status board is untouched: it still answers for `chokepoints` and for no other id
  assert.match(src('components/views/BoardView.tsx'), /if \(id !== 'chokepoints'\) return null;/);
});

// ---------------------------------------------------------------- the indicators of the price files

const priceIndex = () => json('data/prices/index.json');
const metaOf = (id) => priceIndex().find((m) => m.id === id);
/** The series file, unpacked by its own start (independent of the page's lookup by date). */
const unpacked = (id) => {
  const raw = json(`data/prices/${id}.json`);
  const [sy, sm] = raw.start.split('-').map(Number);
  const x = raw.v.map((_, i) => Date.UTC(sy, sm - 1 + i, 1) / 1000);
  return { raw, x };
};
const ym = (t) => new Date(t * 1000).toISOString().slice(0, 7);

test('the two indicators are series of the Freight family in the price index, each with its last value and month', () => {
  assert.deepEqual(INDICATORS.map((i) => i.segment), ['Dry bulk', 'All ships']);
  for (const { id } of INDICATORS) {
    const m = metaOf(id);
    assert.ok(m, `${id} is in data/prices/index.json`);
    assert.equal(m.k, 'freight');
    assert.equal(m.freq, 'M', 'a monthly series: its year earlier is the same month');
    assert.ok(m.stats?.last && Number.isFinite(m.stats.last.v), `${id} has a last value`);
    const { raw, x } = unpacked(id);
    const n = raw.v.length - 1;
    // the board's figure is the file's last value, and the month the file's last month
    assert.equal(m.stats.last.v, raw.v[n]);
    assert.equal(m.stats.last.t, ym(x[n]));
    assert.equal(m.stats.last.t, m.end);
    // the sources of the two rows are the Dallas Fed and the BLS, both in the registry
    assert.ok(json('data/sources.json').some((s) => s.id === m.s), `${m.s} is a registry id`);
  }
  assert.deepEqual(INDICATORS.map((i) => metaOf(i.id).s), ['dallasfed', 'bls']);
  // the New York Fed's supply-chain index is not a freight measure of any segment: it has no row
  assert.ok(!INDICATORS.some((i) => i.id === 'gscpi-m'));
});

test('the value of the same month a year earlier is found by its date and equals the file\'s', () => {
  for (const { id } of INDICATORS) {
    const m = metaOf(id);
    const { raw, x } = unpacked(id);
    const want = yearEarlier(m.stats.last.t);
    const i = x.findIndex((t) => ym(t) === want);
    assert.ok(i >= 0, `${id}: the file holds ${want}`);
    assert.equal(valueInMonth(x, raw.v, want), raw.v[i]);
    assert.equal(valueInMonth(x, raw.v, want), valueInMonth(x, raw.v, yearEarlier(m.stats.last.t)));
  }
  // by date, never by position: a missing month is not read from its neighbour
  const x = [Date.UTC(2025, 0, 1) / 1000, Date.UTC(2025, 2, 1) / 1000];
  assert.equal(valueInMonth(x, [1, 3], '2025-01'), 1);
  assert.equal(valueInMonth(x, [1, 3], '2025-02'), null, 'a month the series lacks has no value');
  assert.equal(valueInMonth(x, [1, null], '2025-03'), null, 'a null month has none');
  assert.equal(valueInMonth(x, [1, 3], 'Jan 2025'), null);
  assert.equal(yearEarlier('2026-10'), '2025-10');
  assert.equal(yearEarlier('2024-02'), '2023-02');
});

test('the change on the year is the price board\'s figure; a deviation from a trend or an average has none', () => {
  // the Dallas Fed series is a deviation and the board gives it no change; the BLS index is not and has one
  const dallas = metaOf('igrea-m');
  const bls = metaOf('freight-ppi-m');
  assert.ok(isDeviation(dallas.unit));
  assert.ok(!isDeviation(bls.unit));
  assert.equal(dallas.stats.chg, undefined, 'the price build gives the deviation no change');
  assert.equal(percentOnYear(dallas), null);
  assert.equal(percentOnYear(bls), bls.stats.chg.y);
  // the board's figure is the arithmetic of the two published values
  const { raw, x } = unpacked('freight-ppi-m');
  const ago = valueInMonth(x, raw.v, yearEarlier(bls.stats.last.t));
  assert.ok(Math.abs(100 * (bls.stats.last.v / ago - 1) - bls.stats.chg.y) < 0.05);
  // the rule, on series the test makes: a deviation has none even when a change is given, a measure without one has none
  for (const unit of ['% deviation from trend', 'standard deviations from average', 'percent deviation from an average']) {
    assert.equal(percentOnYear({ unit, stats: { chg: { y: 12.5 } } }), null, unit);
  }
  assert.equal(percentOnYear({ unit: 'index (Jun 1988 = 100)', stats: { chg: { y: 12.5 } } }), 12.5);
  assert.equal(percentOnYear({ unit: 'index' }), null);
  assert.equal(percentOnYear({ unit: 'index', stats: { chg: { y: null } } }), null);
  assert.equal(percentOnYear({ unit: 'index', stats: { chg: { y: Number.NaN } } }), null);
  // the board's footer states the same rule, with the same test of the unit
  assert.match(src('components/PriceBoard.tsx'), /\/deviation\/i\.test\(m\.unit\)/);
  // the page prints a per cent only through that rule
  const view = src('components/views/FreightNowView.tsx');
  assert.match(view, /const pct = percentOnYear\(m\);/);
  assert.equal((view.match(/fmtPct\(/g) ?? []).length, 2, 'both prints of a change are the board\'s figure');
  assert.doesNotMatch(view, /chg\??\.|stats\??\.chg/, 'the view does not read the change itself');
});

test('a late series is marked as the price board marks it', () => {
  const view = src('components/views/FreightNowView.tsx');
  assert.match(view, /import \{[^}]*\bisLate\b[^}]*\} from '\.\.\/\.\.\/lib\/prices'/);
  assert.match(view, /const late = isLate\(m\);/);
  assert.match(view, /\{late \? ' · late' : ''\}/);
  assert.match(view, /No value since \$\{fmtDate\(last\.t\)\}: this series is late/);
  // the board's own wording of the same mark
  const board = src('components/PriceBoard.tsx');
  assert.match(board, /\{late \? ' · late' : ''\}/);
  assert.match(board, /No value since \$\{fmtDate\(st\.last\.t\)\}: this series is late/);
  // the rule itself, for a monthly series: late from the 15th of the second month after the last one
  assert.match(src('lib/prices.ts'), /return now > Date\.UTC\(Number\(y\), Number\(mo\) - 1 \+ 2, 15\);/);
});

test('the Dallas Fed row carries the citation the registry asks for and the Bank\'s own words, found word for word in the series\' basis', () => {
  const dallas = metaOf('igrea-m');
  for (const piece of Object.values(DALLAS_WORDS)) assert.ok(dallas.basis.includes(piece), `the basis holds: ${piece}`);
  // the saved copy of the Dallas Fed page, when this machine has it
  const saved = '/tmp/claude-0/audit/work/6B/FNOW/critic/dl/dallasfed-igrea.html';
  if (fs.existsSync(saved)) {
    const page = fs.readFileSync(saved, 'utf8').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
    for (const piece of Object.values(DALLAS_WORDS)) assert.ok(page.includes(piece), `the page holds: ${piece}`);
  }
  // the registry asks for Kilian (2009) and Kilian (2019)
  const lic = json('data/sources.json').find((s) => s.id === 'dallasfed').licence;
  assert.match(lic, /Kilian \(2009\)/);
  assert.match(lic, /Kilian \(2019\)/);
  const note = dallasNote('Federal Reserve Bank of Dallas');
  assert.match(note, /^Federal Reserve Bank of Dallas; /, 'the Bank is credited on the page');
  assert.match(note, /Kilian \(2009\).*Kilian \(2019\)/);
  assert.ok(note.includes(`“${DALLAS_WORDS.proxy}”`));
  assert.ok(note.endsWith(NOT_A_RATE));
  // the BLS row says what its series says it is, whatever the series' note holds
  const bls = metaOf('freight-ppi-m');
  assert.equal(indicatorNote('freight-ppi-m', 'U.S. Bureau of Labor Statistics', bls.note), `U.S. Bureau of Labor Statistics; ${bls.note}`);
  assert.match(bls.note, /not a freight rate/);
  assert.match(metaOf('igrea-m').note, /not a freight rate/);
});

// ---------------------------------------------------------------- what the atlas links to and shows no value of

test('the link-only list names each publisher of the registry, has no figure, and its addresses are the registry\'s or pages read and named there', () => {
  const reg = json('data/sources.json');
  const entry = (id) => reg.find((s) => s.id === id);
  assert.deepEqual([...new Set(LINK_ONLY.map((l) => l.s))], ['baltic', 'sse', 'usda-ams']);
  assert.equal(LINK_ONLY.length, 5, 'Baltic, the two Shanghai indices, the grain vessel line-up and the grain ocean rates');
  for (const l of LINK_ONLY) {
    const e = entry(l.s);
    assert.ok(e, `${l.s} is in the registry`);
    assert.ok(!/\d/.test(`${l.name} ${l.what}`), `no figure: ${l.name}`);
    assert.doesNotMatch(`${l.name} ${l.what}`, /\b(free|open|public domain|download|rate of|index of \d)\b/i, `no claim of terms: ${l.name}`);
    if (l.href) {
      assert.match(l.href, /^https:\/\//);
      assert.ok(e.licence.includes(l.href), `${l.href} is an address the registry entry names (a page read on 25 November 2026)`);
    } else {
      assert.match(e.url, /^https:\/\//);
    }
    // the registry says it does not offer these for download and shows no value
    assert.match(e.licence + e.use, /no value|shows no value|offers no download/i);
  }
  // the names of the two Shanghai indices are the saved pages' own
  const names = LINK_ONLY.filter((l) => l.s === 'sse').map((l) => l.name);
  assert.deepEqual(names, ['China Import Dry Bulk Freight Index', 'China Import Crude Oil Tanker Freight Index']);
  assert.match(entry('sse').name, /China Import Dry Bulk Freight Index/);
  assert.match(entry('sse').name, /China Import Crude Oil Tanker Freight Index/);
  // none of them is a source of a figure of the page
  const view = src('components/views/FreightNowView.tsx');
  assert.doesNotMatch(view, /\bs=\{?['"](baltic|sse|usda-ams)/);
  assert.doesNotMatch(view, /data-src=\{?['"](baltic|sse|usda-ams)/);
  const links = view.slice(view.indexOf('function LinkRow'), view.indexOf('export default function FreightNowView'));
  assert.doesNotMatch(links, /data-src|data-y|SourceLine|src-line/, 'a link row is not cited');
  assert.match(links, /target="_blank"/);
  assert.match(links, /rel="noopener"/);
  // no digit follows the name of a publisher or index anywhere in the page's own text
  for (const text of [view, src('lib/freightIndicators.ts')]) {
    for (const line of text.split('\n')) {
      if (/\b(Baltic|Shanghai|USDA|SSE|CDFI|CTFI)\b/.test(line)) assert.doesNotMatch(line.replace(/\/\/.*$/, '').replace(/https?:\/\/\S+/g, ''), /\d/, line.trim());
    }
  }
});

// ---------------------------------------------------------------- the citation

test('"Copy citation" is fed by the figures of the page: PortWatch, the Dallas Fed and the BLS, with their dates, and by no link-only publisher', () => {
  const view = src('components/views/FreightNowView.tsx');
  // what the citation reads is every [data-src] of the panel (lib/cite.ts): list the places the view writes one
  const writers = view.match(/data-src=\{[^}]+\}/g) ?? [];
  assert.deepEqual([...new Set(writers)].sort(), ['data-src={m.s}', 'data-src={src}']);
  assert.equal((view.match(/<SourceLine\s+s=\{[^}]+\}/g) ?? []).length, 2, 'one source line under each traffic list and one under each indicator: two writers');
  assert.match(view, /<SourceLine s=\{m\.s\} y=\{last\.t\}/);
  // the sources those writers hold, as the citation prints them (the registry's name), and their dates
  const reg = json('data/sources.json');
  const cited = [json('data/freight/market-now.json').s, ...INDICATORS.map((i) => metaOf(i.id).s)];
  assert.deepEqual(cited, ['portwatch', 'dallasfed', 'bls']);
  const names = cited.map((s) => reg.find((r) => r.id === s).name);
  assert.match(names[0], /IMF PortWatch/);
  assert.match(names[1], /Index of global real economic activity/);
  assert.match(names[2], /BLS/);
  for (const l of LINK_ONLY) assert.ok(!cited.includes(l.s), `${l.s} is not cited`);
  // the dates: the two windows of the digest, and the month of each indicator
  assert.match(view, /data-src=\{src\} data-y=\{y\}/);
  assert.match(view, /<div class="fn-ind" data-src=\{m\.s\} data-y=\{last\.t\}>/);
  // the Dallas Fed's licence asks that the Bank be credited: the row's note names it, from the registry's publisher
  assert.equal(reg.find((r) => r.id === 'dallasfed').publisher, 'Federal Reserve Bank of Dallas');
  assert.match(view, /sources\.value\[m\.s\]\?\.publisher/);
});

test('the indicators section and the link list stay when the digest is missing, and say so when no indicator loads', () => {
  const view = src('components/views/FreightNowView.tsx');
  assert.match(view, /No indicator figures are available\./);
  // both sections are outside the branch that needs the digest
  const afterDigest = view.slice(view.indexOf('<Section title="Indicators that are not freight rates">'));
  assert.ok(afterDigest.includes('<Section title="Indices and rates published elsewhere">'));
  const digestBranch = view.slice(view.indexOf('!digest ? ('), view.indexOf('<Section title="Indicators that are not freight rates">'));
  assert.doesNotMatch(digestBranch, /IndicatorRow|LinkRow/);
  // a series that fails to load has no row, the others keep theirs
  assert.match(view, /\} catch \{\s*return null;/);
});
