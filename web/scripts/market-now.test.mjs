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
import { DALLAS_WORDS, INDICATORS, LINK_ONLY, NOT_A_RATE, dallasNote, indicatorLineText, indicatorLines, indicatorNote, indicatorOf, indicatorSourceNote, isDeviation, percentOnYear, valueInMonth, yearEarlier } from '../src/lib/freightIndicators.ts';
import { basisSuffix, withoutCredit } from '../src/lib/credit.ts';
import { CLASSES_NOTE, NO_CHANGE_TITLE, TINY_AGO_TITLE, TINY_MT, addDays, buildDigest, canRank, cargoOver, changeBetween, changeText, countText, isIsoDay, lastWeekEnd, classesNote, leadText, lineText, mtChangeText, mtText, readMarketNow, refusal, rowLines, rowText, sig3, vesselsOver, weekIndex } from '../src/lib/marketNow.ts';

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

test('the page prints the change the builder stored: a true minus, one decimal, nothing worked out', () => {
  assert.equal(changeText(25), '+25.0%');
  assert.equal(changeText(-25), '−25.0%');
  assert.equal(changeText(-99.8), '−99.8%', 'a collapse is a fall: the figure says how far');
  assert.equal(changeText(-99.9), '−99.9%', 'the builder stores −99.9 for a fall that one decimal would round to 100 while something is left');
  assert.equal(changeText(-100), '−100%', '"−100%" only when nothing is left');
  assert.equal(changeText(0), '0.0%', 'one decimal also for no change');
  assert.equal(changeText(2900), '+2900.0%');
  assert.equal(changeText(100), '+100.0%');
  assert.equal(changeText(-0.1), '−0.1%');
  assert.ok(!changeText(-25).includes('-'), 'no hyphen-minus');
  // nothing stored: a dash. The page has no other way to a change: a figure it is not given it does not work out
  for (const none of [null, undefined, Number.NaN, Infinity]) assert.equal(changeText(none), '—');
  assert.equal(changeText.length, 1, 'a change is read from one value');
});

test('the cargo follows the status board: under 0.05 Mt is said as a bound; a year earlier that small has no change; the rest is the stored change', () => {
  // the same constant as the board, which this page must agree with
  assert.match(src('components/views/BoardView.tsx'), new RegExp(`const TINY_MT = ${TINY_MT};`));
  assert.equal(mtText(TINY_MT / 2), `under ${TINY_MT} Mt`);
  assert.equal(mtText(0), '0 Mt');
  assert.equal(mtText(null), '—');
  assert.equal(mtText(87.2), '87.2 Mt');
  assert.equal(mtText(1280), '1,280 Mt');
  assert.equal(mtText(0.253), '0.253 Mt');
  assert.equal(mtText(0.0512), '0.0512 Mt');
  assert.equal(mtChangeText(TINY_MT / 2, 40, -99.9), `down more than ${Math.floor((100 * (40 - TINY_MT)) / 40)}%`, 'a cargo now under the bound: the change is a bound too');
  assert.equal(mtChangeText(TINY_MT / 2, TINY_MT / 4, 100), '—', 'nothing to compare when the year earlier is that small');
  assert.equal(mtChangeText(10, TINY_MT / 2, 19900), '—', 'a year earlier under the bound has no change, whatever was stored');
  assert.equal(mtChangeText(0, 40, -100), '−100%', 'nothing carried now is not "under the bound": it is a fall of everything');
  assert.equal(mtChangeText(90, 120, -25), '−25.0%', 'otherwise the stored change');
  assert.equal(mtChangeText(5, 0, null), '—', 'nothing a year earlier: nothing stored');
  assert.equal(mtChangeText(TINY_MT / 2, 0, null), '—', 'a small cargo now and none a year earlier is a dash, not a bound of nothing');
  assert.equal(countText(2373), '2,373');
  assert.equal(countText(0), '0');
  assert.equal(countText(null), '—');
});

test('the builder\'s rule of the change, in the library: one decimal, a half away from zero, null on a zero, −99.9 while something is left', () => {
  assert.equal(changeBetween(1125, 1000), 12.5);
  assert.equal(changeBetween(875, 1000), -12.5);
  assert.equal(changeBetween(1000, 1000), 0);
  assert.ok(Object.is(changeBetween(1000, 1000), 0), 'never −0');
  assert.ok(Object.is(changeBetween(99996, 100000), 0), 'a fall of 0.004% reads 0.0, not −0');
  assert.equal(changeBetween(100050, 100000), 0.1, 'a half goes up');
  assert.equal(changeBetween(99950, 100000), -0.1, 'and away from zero for a fall');
  assert.equal(changeBetween(100049, 100000), 0);
  assert.equal(changeBetween(5, 0), null);
  assert.equal(changeBetween(0, 0), null);
  assert.equal(changeBetween(0, 7), -100);
  assert.equal(changeBetween(1, 10000), -99.9, 'a fall that one decimal would round to −100.0 while something is left');
  assert.equal(changeBetween(2, 1000), -99.8);
  assert.equal(changeBetween(3000, 100), 2900);
});

test('a row is written as the figures, the two years and the change of each measure', () => {
  const row = { id: 'x', now: 2373, ago: 2750, pct: -13.7, mt: { now: 134, ago: 158, pct: -15.2 }, rankMt: 1 };
  const t = rowText(row);
  assert.deepEqual(t.transits, { now: '2,373', ago: '2,750', change: '−13.7%' });
  assert.deepEqual(t.cargo, { now: '134 Mt', ago: '158 Mt', change: '−15.2%' });
  const zero = rowText({ id: 'x', now: 4, ago: 0, pct: null, mt: { now: 1, ago: 0, pct: null }, rankMt: 0 });
  assert.equal(zero.transits.change, '—');
  assert.equal(zero.cargo.change, '—');
});

test('the lines of a row: the year earlier is the second figure, each line carries its own change, a dash says why', () => {
  const row = { id: 'x', now: 2373, ago: 2750, pct: -13.7, mt: { now: 134, ago: 158, pct: -15.2 }, rankMt: 1 };
  const l = rowLines(row);
  assert.equal(lineText(l.transits), 'Transits 2,373 vs 2,750 a year earlier: −13.7%');
  assert.equal(lineText(l.cargo), 'Cargo 134 Mt vs 158 Mt a year earlier: −15.2%');
  assert.equal(l.transits.title, undefined);
  const none = rowLines({ id: 'x', now: 4, ago: 0, pct: null, mt: { now: 1, ago: 0, pct: null }, rankMt: 0 });
  assert.equal(lineText(none.transits), 'Transits 4 vs 0 a year earlier: —');
  assert.equal(none.transits.title, NO_CHANGE_TITLE);
  assert.equal(none.cargo.title, NO_CHANGE_TITLE);
  // the two lines are not interchangeable: figures and changes that differ show on their own line
  const odd = rowLines({ id: 'x', now: 10, ago: 20, pct: -50, mt: { now: 3, ago: 6, pct: 5 }, rankMt: 1 });
  assert.equal(lineText(odd.transits), 'Transits 10 vs 20 a year earlier: −50.0%');
  assert.equal(lineText(odd.cargo), 'Cargo 3 Mt vs 6 Mt a year earlier: +5.0%');
  // a dash for a year-earlier cargo under the bound says that, not "nothing a year earlier"; the transits of the same row keep the other reason
  const tinyAgo = rowLines({ id: 'x', now: 10, ago: 0, pct: null, mt: { now: 0.3, ago: 0.02, pct: 1400 }, rankMt: 1 });
  assert.equal(lineText(tinyAgo.cargo), `Cargo 0.3 Mt vs under ${TINY_MT} Mt a year earlier: —`);
  assert.equal(tinyAgo.cargo.title, TINY_AGO_TITLE);
  assert.equal(tinyAgo.transits.title, NO_CHANGE_TITLE);
  assert.notEqual(TINY_AGO_TITLE, NO_CHANGE_TITLE);
  const small = rowLines({ id: 'x', now: 10, ago: 20, pct: -50, mt: { now: 0.02, ago: 6, pct: -99.9 }, rankMt: 1 });
  assert.equal(lineText(small.cargo), `Cargo under ${TINY_MT} Mt vs 6 Mt a year earlier: down more than ${Math.floor((100 * (6 - TINY_MT)) / 6)}%`);
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
    ['a row without its change of the transits', (() => { const c = clone(); delete c.types.dry[1].pct; return c; })()],
    ['a change of the transits as text', (() => { const c = clone(); c.types.dry[1].pct = '-9.9'; return c; })()],
    ['a row without its change of the cargo', (() => { const c = clone(); delete c.types.tanker[2].mt.pct; return c; })()],
    ['an infinite change of the cargo', (() => { const c = clone(); c.types.tanker[2].mt.pct = Infinity; return c; })()],
  ];
  for (const [what, doc] of bad) assert.equal(readMarketNow(doc), null, what);
  // an empty list is a digest with nothing to show for that type: the page says so for it alone
  const empty = clone();
  empty.types.tanker = [];
  assert.deepEqual(readMarketNow(empty).types.tanker, []);
  assert.ok(readMarketNow(empty).types.dry.length > 0);
  // a change that is null is a change that was not given (nothing a year earlier): the row is read, and prints a dash
  const nothing = clone();
  nothing.types.dry[0].pct = null;
  nothing.types.dry[0].mt.pct = null;
  assert.equal(readMarketNow(nothing).types.dry[0].pct, null);
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

test('passages are ranked on the sum before rounding: the same printed figure keeps the order of the unrounded sums, and only an exact tie goes by id', () => {
  const weeks = 120;
  const flat = (id, v) => series(id, weeks, { vt: () => v });
  // 52 weeks x 7 days x the weekly mean: 512.9124 and 512.6576 both print 513, and the id of the larger one sorts last
  const all = [flat('a', 1.4084), flat('z', 1.4091), flat('b', 2), flat('c', 1.9), flat('d', 1.8), flat('e', 0.1), flat('f', 0.1)];
  const rows = buildDigest(all).types.tanker;
  assert.deepEqual(rows.map((r) => r.id), ['b', 'c', 'd', 'z', 'a']);
  assert.equal(rows[3].rankMt, 513);
  assert.equal(rows[4].rankMt, 513, 'the same figure for both');
  // an exact tie of the sums goes by id (and a tie on the rounded figure alone does not)
  const tied = [flat('m', 1.4084), flat('k', 1.4084), flat('b', 2), flat('c', 1.9), flat('d', 1.8), flat('e', 0.1)];
  assert.deepEqual(buildDigest(tied).types.tanker.map((r) => r.id), ['b', 'c', 'd', 'k', 'm']);
});

test('a file that starts after the first of the ranking weeks is left out of the ranking; fewer than five that can be ranked is a refusal; a malformed file is one wherever it ranks', () => {
  const weeks = 120;
  const all = ['a', 'b', 'c', 'd', 'e'].map((id, i) => series(id, weeks, { vt: () => 0.5 - i / 100 }));
  const young = series('young', 60, { start: addDays('2024-01-01', 7 * 60), vt: () => 9 }); // starts 60 weeks late, ends on the same Sunday
  assert.equal(lastWeekEnd(young), lastWeekEnd(all[0]));
  const d = buildDigest([...all, young]);
  assert.deepEqual(d.types.tanker.map((r) => r.id), ['a', 'b', 'c', 'd', 'e'], 'the new passage, however large, is not ranked');
  assert.equal(canRank(young, d.yearAgoTo), false);
  assert.ok(all.every((s) => canRank(s, d.yearAgoTo)));
  assert.deepEqual(buildDigest([...all, young]).types, buildDigest(all).types, 'the digest is that of the others');
  // the first file that can rank: it starts on the first Monday of the 52 weeks
  const edge = series('edge', 120, { start: addDays(d.yearAgoTo, -(7 * 52 - 1)), vt: () => 9 });
  assert.equal(canRank(edge, d.yearAgoTo), true);
  assert.equal(canRank({ ...edge, start: addDays(edge.start, 7) }, d.yearAgoTo), false);
  assert.throws(() => buildDigest([...all.slice(0, 4), young]), /1 of 5 weekly series|4 of 5 weekly series/);
  // a malformed file stops the digest, even one that would not rank
  const broken = series('broken', 60, { start: addDays('2024-01-01', 7 * 60) });
  broken.tanker.pop();
  assert.throws(() => buildDigest([...all, broken]), /weeks from/);
});

test('the digest can be rebuilt as it stood on an earlier week, from files that have since advanced', () => {
  const all = ['a', 'b', 'c', 'd', 'e'].map((id, i) => series(id, 130, { vt: (k) => Math.round((0.3 + i / 50 + k / 10000) * 1e4) / 1e4 }));
  const earlier = addDays('2024-01-01', 7 * 120 - 1);
  const asThen = buildDigest(all, earlier);
  assert.equal(asThen.to, earlier);
  assert.equal(asThen.yearAgoTo, addDays(earlier, -364));
  const direct = buildDigest(all.map((s) => ({ ...s, y: earlier, tanker: s.tanker.slice(0, 120), dry: s.dry.slice(0, 120), vol: { tanker: s.vol.tanker.slice(0, 120), dry: s.vol.dry.slice(0, 120) } })));
  assert.deepEqual(asThen, direct, 'the same figures as files that stop on that week');
  assert.throws(() => buildDigest(all, addDays(lastWeekEnd(all[0]), 7)), /no week ends on/, 'a date after the files cannot be rebuilt');
});

test('the window ends on the earliest last complete week of the files', () => {
  const all = ['a', 'b', 'c', 'd', 'e'].map((id, i) => series(id, 110 - (i === 2 ? 1 : 0)));
  assert.equal(buildDigest(all).to, addDays('2024-01-01', 7 * 109 - 1));
});

// ---------------------------------------------------------------- the published file, rebuilt from the weekly files

/**
 * The digest rebuilt from the weekly files at the digest's own date, to compare with it. A weekly job may write new weekly files and keep
 * the old digest (its step refused: the job ends green by design): the files are then newer than the digest, and the digest is
 * compared with what they say of its own week. What the files no longer allow is a skip with the reason, not a failure: a file the
 * builder would refuse, or one that no longer reaches back to the digest's window. A digest that ends after the files do is a failure.
 */
/**
 * The reason to skip the comparison when the digest's own step failed at its last run: the script records the failure in
 * data/_status/updates.json and keeps the previous digest, and the weekly files written before it in the same job may have been revised
 * under that digest. The failure is recorded and alerted; the republication of the site does not wait for it. Null when the step succeeded
 * at its last run or has never run.
 */
function stepFailedLast(updates) {
  const e = updates?.sources?.['build-market-now'];
  return e && e.consecutive_failures > 0
    ? `the digest step failed at its last run (${e.last_error}): the previous digest is kept, the failure is recorded and alerted, and the digest is compared with the weekly files again after a run that succeeds`
    : null;
}
const statusNow = () => { try { return json('data/_status/updates.json'); } catch { return null; } };

function rebuiltAtDigestDate(all, file) {
  const refused = all.map((s) => [s.id, refusal(s)]).filter(([, why]) => why);
  const sound = all.filter((s) => !refusal(s));
  const behind = sound.filter((s) => lastWeekEnd(s) < file.to);
  if (behind.length) assert.fail(`the digest ends on ${file.to}, after the weekly files of ${behind.map((s) => s.id).join(', ')} (${behind.map(lastWeekEnd).join(', ')})`);
  if (refused.length) return { skip: `the builder would refuse ${refused.map(([id, why]) => `${id}.json (${why})`).join('; ')}: the digest of ${file.to} is kept and is compared again when the files hold together` };
  const lost = [...file.types.tanker, ...file.types.dry].filter((r) => !canRank(all.find((s) => s.id === r.id) ?? { start: '' }, file.yearAgoTo));
  if (lost.length) return { skip: `${[...new Set(lost.map((r) => r.id))].join(', ')} no longer reach back ${file.rankWeeks} weeks before ${file.yearAgoTo}: the digest of ${file.to} cannot be rebuilt from them` };
  return { built: buildDigest(all, file.to) };
}

test('every row of the digest is rebuilt from the weekly files, by date, at the digest\'s own date', (t) => {
  const all = weekly();
  assert.ok(all.length >= 5);
  const file = json('data/freight/market-now.json');
  const r = rebuiltAtDigestDate(all, file);   // a digest dated after the files fails here, whatever the status says
  if (r.skip) return t.skip(r.skip);
  const failed = stepFailedLast(statusNow());
  if (failed) return t.skip(failed);
  const built = r.built;
  assert.equal(built.to, file.to, 'the window ends where the digest says');
  assert.equal(built.yearAgoTo, file.yearAgoTo);
  for (const ty of ['tanker', 'dry']) {
    assert.equal(file.types[ty].length, built.types[ty].length);
    file.types[ty].forEach((row, i) => assert.deepEqual(row, built.types[ty][i], `${ty} row ${i + 1} (${row.id})`));
  }
  // a passage that is not shown, and that can be ranked, carries no more cargo of the type a year back than the fifth one
  for (const ty of ['tanker', 'dry']) {
    const shown = new Set(file.types[ty].map((x) => x.id));
    const floor = file.types[ty].at(-1).rankMt;
    for (const s of all) if (!shown.has(s.id) && canRank(s, file.yearAgoTo)) assert.ok(cargoOver(s, ty, file.yearAgoTo, file.rankWeeks) <= floor, `${ty}: ${s.id}`);
  }
  // the ranking is not increasing; passages are named once in a list
  for (const ty of ['tanker', 'dry']) {
    const x = file.types[ty].map((row) => row.rankMt);
    assert.deepEqual([...x].sort((a, b) => b - a), x);
    assert.equal(new Set(file.types[ty].map((row) => row.id)).size, file.types[ty].length);
  }
});

test('a digest whose own step failed at its last run is not compared with the files; another step\'s failure, or none, changes nothing', () => {
  assert.equal(stepFailedLast(null), null);
  assert.equal(stepFailedLast({ sources: {} }), null);
  assert.equal(stepFailedLast({ sources: { 'build-market-now': { consecutive_failures: 0, last_error: null } } }), null);
  assert.equal(stepFailedLast({ sources: { portwatch: { consecutive_failures: 3, last_error: 'x' } } }), null);
  const why = stepFailedLast({ sources: { 'build-market-now': { consecutive_failures: 1, last_error: 'TimeoutError: stopped' } } });
  assert.match(why, /TimeoutError: stopped/);
  assert.match(why, /the previous digest is kept/);
  // the published state: skipped only if its own record says the step failed
  const e = statusNow()?.sources?.['build-market-now'];
  assert.equal(stepFailedLast(statusNow()) !== null, !!(e && e.consecutive_failures > 0));
});

test('the rebuild at the digest\'s date: files that have advanced since are compared with their own past; what the files no longer allow is skipped, a digest later than them fails', () => {
  const ids = ['a', 'b', 'c', 'd', 'e', 'f'];
  const r4 = (x) => Math.round(x * 1e4) / 1e4; // the weekly files hold four decimals of cargo
  const mk = (weeks, extra = {}) => ids.map((id, i) => series(id, weeks, { vt: (k) => r4(0.3 + i / 50 + k / 10000), vd: (k) => r4(0.2 + i / 70 + k / 9000), ...extra }));
  const advanced = mk(133);
  const digestOf = (weeks) => ({ s: 'portwatch', weeks: 4, rankWeeks: 52, ...buildDigest(mk(weeks)) });
  // the job wrote three newer weeks and kept the digest of three weeks before: rebuilt at its own date, the rows equal the digest
  const old = digestOf(130);
  const same = rebuiltAtDigestDate(advanced, old);
  assert.equal(same.skip, undefined);
  assert.deepEqual(same.built.types, old.types);
  assert.equal(same.built.to, old.to);
  // without a date the same files give the newer week: a test that compared with it would fail on a digest that was only kept
  assert.notEqual(buildDigest(advanced).to, old.to);
  // a weekly file the builder would refuse (a week lost): skipped with its name and the reason
  const lost = mk(133);
  for (const k of ['tanker', 'dry']) lost[2][k].pop();
  lost[2].vol.tanker.pop();
  lost[2].vol.dry.pop();
  const skipped = rebuiltAtDigestDate(lost, old);
  assert.match(skipped.skip, /the builder would refuse c\.json \(c\.json: .* weeks from/);
  // a value that is not a number, or negative: refused by the builder, skipped here
  const bad = mk(133);
  bad[1].dry[5] = null;
  assert.match(rebuiltAtDigestDate(bad, old).skip, /b\.json dry\[5\]: null/);
  const neg = mk(133);
  neg[0].vol.tanker[7] = -0.1;
  assert.match(rebuiltAtDigestDate(neg, old).skip, /a\.json vol\.tanker\[7\]/);
  // a file that no longer reaches back to the digest's window (it starts too late) and sits among the rows: skipped
  const short = mk(133);
  short[4] = series('e', 60, { start: addDays('2024-01-01', 7 * 73), vt: () => 9 });
  assert.equal(lastWeekEnd(short[4]), lastWeekEnd(short[0]));
  assert.match(rebuiltAtDigestDate(short, old).skip, /e no longer reach back 52 weeks/);
  // a digest that ends after the files do is still a failure, whatever else is wrong with them
  const newer = digestOf(140);
  assert.throws(() => rebuiltAtDigestDate(advanced, newer), /the digest ends on .* after the weekly files of a, b, c, d, e, f/);
  assert.throws(() => rebuiltAtDigestDate(lost, newer), /after the weekly files of a, b, d, e, f/);
  // a row that differs from the files is a failure, not a skip: compare as the real test does
  const wrong = structuredClone(old);
  wrong.types.tanker[0].mt.now += 1;
  const r = rebuiltAtDigestDate(advanced, wrong);
  assert.throws(() => assert.deepEqual(wrong.types.tanker[0], r.built.types.tanker[0]));
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

/**
 * What METHODOLOGY ("What the page prints") says a row prints, written again here from the STORED values alone, case by case and with no
 * knowledge of the library: the digest holds whatever the builder can write (a passage with no transit, nothing a year earlier, a cargo of
 * a few thousand tonnes), so no test may guess which case a real row is. The cases are the document's, in its order.
 */
const printedCount = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const printedMt = (v) => {
  if (v === 0) return '0 Mt';
  if (v < 0.05) return 'under 0.05 Mt';
  const [whole, decimals] = String(v).split('.');
  return `${printedCount(whole)}${decimals ? `.${decimals}` : ''} Mt`;
};
/** A stored change: a dash for null, "−100%" for exactly −100, otherwise the sign, one decimal and a true minus. */
const printedChange = (p) => {
  if (p === null) return '—';
  if (p === -100) return '−100%';
  return `${p < 0 ? '−' : p > 0 ? '+' : ''}${Math.abs(p).toFixed(1)}%`;
};
const printedCargoChange = (mt) => {
  if (mt.pct === null) return '—'; // nothing a year earlier
  if (mt.ago > 0 && mt.ago < 0.05) return '—'; // a year-earlier cargo that small has nothing to compare with, whatever was stored
  if (mt.now > 0 && mt.now < 0.05) return `down more than ${Math.floor((100 * (mt.ago - 0.05)) / mt.ago)}%`; // and only then, a bound
  return printedChange(mt.pct);
};
const printedLines = (r) => ({
  transits: { text: `Transits ${printedCount(r.now)} vs ${printedCount(r.ago)} a year earlier`, change: printedChange(r.pct) },
  cargo: { text: `Cargo ${printedMt(r.mt.now)} vs ${printedMt(r.mt.ago)} a year earlier`, change: printedCargoChange(r.mt) },
});
const expectLines = (r, what) => {
  const want = printedLines(r);
  const got = rowLines(r);
  assert.equal(got.transits.text, want.transits.text, `${what}: the transits line`);
  assert.equal(got.transits.change, want.transits.change, `${what}: the change of the transits`);
  assert.equal(got.cargo.text, want.cargo.text, `${what}: the cargo line`);
  assert.equal(got.cargo.change, want.cargo.change, `${what}: the change of the cargo`);
  assert.equal(lineText(got.transits), `${want.transits.text}: ${want.transits.change}`, what);
  assert.equal(lineText(got.cargo), `${want.cargo.text}: ${want.cargo.change}`, what);
  // a dash says why, in the hover text; a change that is printed has none
  assert.equal(got.transits.title, want.transits.change === '—' ? NO_CHANGE_TITLE : undefined, `${what}: the hover text of the transits`);
  assert.equal(got.cargo.title, want.cargo.change !== '—' ? undefined : r.mt.ago > 0 && r.mt.ago < 0.05 ? TINY_AGO_TITLE : NO_CHANGE_TITLE, `${what}: the hover text of the cargo`);
};

/**
 * Whether a stored change can be the change of figures that were rounded: whole vessels (a half rounded up, so the sum is within a half of
 * the figure) and three significant figures (within a half per cent of the figure). One decimal of rounding, and the 0.1 that the −99.9 rule
 * of the builder can move a fall by, are allowed for. Holds for every digest the builder can write.
 */
function agreesWithFigures(pct, now, ago, halfNow, halfAgo, relative) {
  if (pct === null) return true; // nothing a year earlier: the sum was zero, the figure may be a rounded zero or not
  const [nowLo, nowHi] = relative ? [now * (1 - 0.005), now * (1 + 0.005)] : [Math.max(now - halfNow, 0), now + halfNow];
  const [agoLo, agoHi] = relative ? [ago * (1 - 0.005), ago * (1 + 0.005)] : [Math.max(ago - halfAgo, 0), ago + halfAgo];
  if (agoLo <= 0) return true; // the year-earlier sum may be as small as the rounding: any change is possible
  const lo = (100 * (nowLo - agoHi)) / agoHi;
  const hi = (100 * (nowHi - agoLo)) / agoLo;
  return pct >= lo - 0.2 && pct <= hi + 0.1;
}

test('every row of the real digest prints what METHODOLOGY says of its stored values, case by case: the library against an independent writing', () => {
  const file = json('data/freight/market-now.json');
  const d = readMarketNow(file);
  assert.ok(d);
  for (const t of ['tanker', 'dry']) {
    d.types[t].forEach((r, i) => {
      const stored = file.types[t][i];
      // the page reads the stored values as they are
      assert.deepEqual(r, stored, `${t} ${r.id}: read as stored`);
      expectLines(stored, `${t} ${r.id}`);
      assert.ok(agreesWithFigures(stored.pct, stored.now, stored.ago, 0.5, 0.5, false), `${t} ${r.id}: ${stored.pct} is not the change of ${stored.now} and ${stored.ago}, rounded to whole vessels`);
      assert.ok(agreesWithFigures(stored.mt.pct, stored.mt.now, stored.mt.ago, 0, 0, true), `${t} ${r.id} cargo: ${stored.mt.pct} is not the change of ${stored.mt.now} and ${stored.mt.ago}, to three figures`);
    });
  }
});

test('the cases of "What the page prints", on rows the test makes: a stopped passage, nothing a year earlier, a tiny cargo, a change that rounds to zero, a rise past 100%, a collapse', () => {
  const row = (now, ago, pct, mtNow, mtAgo, mtPct) => ({ id: 'x', now, ago, pct, mt: { now: mtNow, ago: mtAgo, pct: mtPct }, rankMt: 1 });
  const cases = [
    // a passage with no transit and no cargo in the window: the builder stores −100.0 and prints nothing smaller
    ['no transit, no cargo', row(0, 1211, -100, 0, 87.2, -100), { transits: '−100%', cargo: '−100%' }],
    ['no cargo only', row(22, 1211, -98.2, 0, 87.2, -100), { transits: '−98.2%', cargo: '−100%' }],
    // nothing a year earlier: null for the transits, for the cargo, for both
    ['nothing a year earlier, transits', row(10, 0, null, 3.5, 4, -12.5), { transits: '—', cargo: '−12.5%' }],
    ['nothing a year earlier, cargo', row(10, 20, -50, 3.5, 0, null), { transits: '−50.0%', cargo: '—' }],
    ['nothing a year earlier, both', row(10, 0, null, 3.5, 0, null), { transits: '—', cargo: '—' }],
    // a cargo under the bound, now, a year earlier, both
    ['a tiny cargo now', row(10, 20, -50, 0.0123, 40, -99.9), { transits: '−50.0%', cargo: `down more than ${Math.floor((100 * (40 - 0.05)) / 40)}%` }],
    ['a tiny cargo a year earlier', row(10, 20, -50, 40, 0.0123, 325000), { transits: '−50.0%', cargo: '—' }],
    ['a tiny cargo both', row(10, 20, -50, 0.0021, 0.0056, -62.5), { transits: '−50.0%', cargo: '—' }],
    ['the bound itself is not tiny', row(10, 20, -50, 0.05, 0.05, 0), { transits: '−50.0%', cargo: '0.0%' }],
    // a change that rounds to 0.0, a rise above 100%, a collapse that is not a stop
    ['a change that rounds to 0.0', row(10, 10, 0, 5, 5, 0), { transits: '0.0%', cargo: '0.0%' }],
    ['a rise above 100%', row(2900, 100, 2800, 1280, 12.5, 10140), { transits: '+2800.0%', cargo: '+10140.0%' }],
    ['a collapse that leaves something', row(1, 10000, -99.9, 0.0512, 4000, -99.9), { transits: '−99.9%', cargo: '−99.9%' }],
  ];
  for (const [what, r, want] of cases) {
    expectLines(r, what);
    const got = rowLines(r);
    assert.equal(got.transits.change, want.transits, `${what}: transits`);
    assert.equal(got.cargo.change, want.cargo, `${what}: cargo`);
  }
  // the stored changes of those rows are readable as a digest row
  for (const [what, r] of cases) assert.ok(readMarketNow({ s: 'portwatch', to: '2026-11-22', yearAgoTo: '2025-11-23', unit: 'u', mtUnit: 'm', types: { tanker: [r], dry: [r] } }), what);
  // the bound and the dash that share a row: the year-earlier cargo under the bound wins, as METHODOLOGY says
  assert.equal(mtChangeText(0.0021, 0.0056, -62.5), '—');
  assert.equal(mtChangeText(0.0021, 0.06, -96.5), `down more than ${Math.floor((100 * (0.06 - 0.05)) / 0.06)}%`);
  // the consistency rule holds for every one of them, a collapse and a stop included
  for (const [what, r] of cases) assert.ok(agreesWithFigures(r.pct, r.now, r.ago, 0.5, 0.5, false) && agreesWithFigures(r.mt.pct, r.mt.now, r.mt.ago, 0, 0, true), what);
  assert.ok(agreesWithFigures(-99.9, 0, 2000, 0.5, 0.5, false), 'a stop after a long year: the sum was a few hundredths of a vessel, the builder stores −99.9, the figure is 0');
  assert.ok(!agreesWithFigures(-20, 90, 100, 0.5, 0.5, false), 'a change that the figures do not allow is caught');
});

// ---------------------------------------------------------------- the view, the entry and what they must not do

test('the page carries the words of the decisions: what it is and is not, how the five are chosen, the classes, the data adapted', () => {
  const view = src('components/views/FreightNowView.tsx');
  assert.match(view, /<h2 class="detail-title">Freight market now<\/h2>/);
  // the lead and the classes sentence are the library's (their words are tested on its output, below); the view only calls them
  assert.match(view, /\{leadText\(indicators\?\.length \?\? 0\)\}/);
  assert.match(view, /classesNote\(type, rows\)/);
  assert.doesNotMatch(view, /defines none|two indicators|PortWatch lists five/);
  assert.match(view, /No traffic figures are available\./);
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

test('the lead names the indicators only on a page that has them; the classes sentence says what was read and shows with tanker rows only', () => {
  const two = leadText(2);
  assert.match(two, /^This page shows traffic at the main passages and two indicators, none of them a freight rate: the atlas shows no spot rate for tankers or gas carriers and no Baltic Exchange index value, since the sources it knows for them are proprietary or cannot be republished\.$/);
  assert.match(leadText(1), /^This page shows traffic at the main passages and one indicator, which is not a freight rate: the atlas shows no spot rate/);
  // the price files cannot be read: no indicator is named, no count is claimed, the sentence on rates stays
  const none = leadText(0);
  assert.doesNotMatch(none, /indicator|\btwo\b/);
  assert.match(none, /^This page shows traffic at the main passages and no freight rate: the atlas shows no spot rate for tankers or gas carriers/);
  assert.notEqual(none, two);
  // the page has as many indicators as the code lists: the lead of a full page names that number
  assert.match(leadText(INDICATORS.length), new RegExp(`and ${['no', 'one', 'two'][INDICATORS.length]} indicators`));
  // the classes: what the atlas read, not what PortWatch does; no "defines none"
  assert.match(CLASSES_NOTE, /^The description of PortWatch's passage data that the atlas read lists five ship classes \(container, dry bulk, general cargo, ro-ro and tanker\) and does not say what each holds, so the atlas cannot say whether gas carriers are in its tanker class: the tanker figures may include them or not\. The atlas shows no separate gas carrier figure\.$/);
  assert.doesNotMatch(CLASSES_NOTE, /defines none|\babove\b/);
  const rows = [{ id: 'x' }];
  assert.equal(classesNote('tanker', rows), CLASSES_NOTE);
  assert.equal(classesNote('tanker', []), null, 'no tanker figure, nothing to qualify');
  assert.equal(classesNote('dry', rows), null, 'the sentence belongs to the tanker list');
  assert.equal(classesNote('dry', []), null);
  // on the real digest both lists have rows: the tanker list carries it
  const digest = readMarketNow(json('data/freight/market-now.json'));
  assert.equal(classesNote('tanker', digest.types.tanker), CLASSES_NOTE);
  assert.equal(classesNote('dry', digest.types.dry), null);
});

test('the view only calls the library for what a row and an indicator print', () => {
  const view = src('components/views/FreightNowView.tsx');
  // a row: two lines, each its own, from rowLines; nothing of the digest is formatted or compared in the view
  assert.match(view, /const lines = rowLines\(row\);/);
  assert.match(view, /\{\[lines\.transits, lines\.cargo\]\.map\(\(l\) => \(\s*<span key=\{l\.text\}>\s*\{l\.text\}: <b title=\{l\.title\}>\{l\.change\}<\/b>\s*<\/span>\s*\)\)\}/);
  assert.doesNotMatch(view, /rowText|changeText|mtChangeText|mtText|countText|\.mt\.(now|ago|pct)|row\.(now|ago|pct)/, 'the view formats nothing of a row');
  // an indicator: the lines of the library, one span each; the year earlier is read by indicatorOf
  assert.match(view, /return indicatorOf\(s\.meta, s\.x, s\.v, segment\);/);
  assert.match(view, /\{lines\.map\(\(l, i\) => \(\s*<span key=\{i\} title=\{l\.title\}>\s*\{l\.parts\.map\(part\)\}\s*<\/span>\s*\)\)\}/);
  assert.doesNotMatch(view, /valueInMonth|yearEarlier|\.ago\b/, 'the view looks nothing up');
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
  assert.deepEqual(INDICATORS.map((i) => i.segment), ['Dry bulk', 'US deep-sea carriers']);
  // the BLS row is labelled for what its series measures, in the words of the series' own basis, and not as the whole fleet
  assert.match(metaOf('freight-ppi-m').basis, /the prices US-based deep-sea carriers receive for their freight services/);
  assert.ok(!INDICATORS.some((i) => /all ships/i.test(i.segment)));
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
  // the page prints a per cent only through that rule, in the lines of the library: the view reads no change itself
  const view = src('components/views/FreightNowView.tsx');
  assert.match(view, /indicatorLines\(ind, \{ price: fmtPrice, date: fmtDate, pct: fmtPct, isLate: \(now\) => isLate\(m, now\) \}, Date\.now\(\)\)/);
  assert.doesNotMatch(view, /chg\??\.|stats\??\.chg|percentOnYear|fmtPct\(/, 'the view does not read the change itself');
  const lib = src('lib/freightIndicators.ts');
  assert.equal((lib.match(/percentOnYear\(m\)/g) ?? []).length, 1);
  assert.equal((lib.match(/\bf\.pct\(/g) ?? []).length, 2, 'both prints of a change are the board\'s figure');
});

// formats of the test, unlike the page's: what the lines say is what they are given
const fmt = { price: (v) => (v == null ? '—' : v.toFixed(2)), date: (s) => `<${s}>`, pct: (p) => `${p}%` };
const lines = (ind, late = false, now = 0) => indicatorLines(ind, { ...fmt, isLate: () => late }, now).map(indicatorLineText);

test('the lines of an indicator, from the price files: the value and its month, the same month a year earlier, the board\'s change on the year', () => {
  for (const { id, segment } of INDICATORS) {
    const m = metaOf(id);
    const { raw, x } = unpacked(id);
    const ind = indicatorOf(m, x, raw.v, segment);
    assert.equal(ind.segment, segment);
    // the year earlier is read in the file at the month a year before the last one, by an independent walk of the file
    const want = raw.v[x.findIndex((s) => ym(s) === yearEarlier(m.stats.last.t))];
    assert.equal(ind.ago, want, id);
    assert.notEqual(ind.ago, m.stats.last.v, `${id}: the year earlier is not the last value`);
    const l = lines(ind);
    assert.equal(l[0], `${segment} · ${NOT_A_RATE}`);
    assert.equal(l[1], `${m.stats.last.v.toFixed(2)} ${m.unit} in <${m.stats.last.t}>`);
    const pct = percentOnYear(m);
    assert.equal(l[2], `A year earlier, <${yearEarlier(m.stats.last.t)}>: ${want.toFixed(2)}` + (pct != null ? ` · ${pct}% on the year` : ''));
    assert.equal(l.length, 3);
  }
});

test('the lines of an indicator, on series the test makes: a missing year earlier, no change, a late series on a given day', () => {
  const x = [Date.UTC(2025, 9, 1) / 1000, Date.UTC(2025, 10, 1) / 1000, Date.UTC(2026, 9, 1) / 1000];
  const meta = (extra = {}) => ({ id: 's', unit: 'index', stats: { last: { t: '2026-10', v: 150 }, chg: { y: 50 } }, ...extra });
  const full = indicatorOf(meta(), x, [100, 120, 150], 'Seg');
  assert.equal(full.ago, 100, 'October 2025, not the neighbour');
  assert.deepEqual(lines(full), ['Seg · not a freight rate', '150.00 index in <2026-10>', 'A year earlier, <2025-10>: 100.00 · 50% on the year']);
  // the same month a year earlier is what is printed, never the last value or the month before it
  assert.equal(indicatorOf(meta(), x, [100, 120, 150], 'Seg').ago, 100);
  assert.equal(indicatorOf(meta(), [x[1], x[2]], [120, 150], 'Seg').ago, null, 'a month the series lacks has no value');
  // no value a year earlier but a change on the year: the change alone
  assert.deepEqual(lines(indicatorOf(meta(), [x[1], x[2]], [120, 150], 'Seg')).slice(2), ['Change on one year: 50%']);
  // no change (a deviation): the year earlier alone
  const dev = indicatorOf(meta({ unit: '% deviation from trend' }), x, [100, 120, 150], 'Seg');
  assert.deepEqual(lines(dev).slice(2), ['A year earlier, <2025-10>: 100.00']);
  // neither: two lines
  assert.equal(lines(indicatorOf(meta({ unit: '% deviation from trend' }), [x[1], x[2]], [120, 150], 'Seg')).length, 2);
  // a series with no last value has no row
  assert.equal(indicatorOf({ id: 's', unit: 'index' }, x, [1, 2, 3], 'Seg'), null);
});

test('a late series is marked as the price board marks it, on the day the page is given', () => {
  const x = [Date.UTC(2025, 9, 1) / 1000, Date.UTC(2026, 9, 1) / 1000];
  const ind = indicatorOf({ id: 's', unit: 'index', stats: { last: { t: '2026-10', v: 150 } } }, x, [100, 150], 'Seg');
  // the board's rule for a monthly series, as a stand-in: late from the 15th of the second month after the last one (checked against the board's source below)
  const monthly = (now) => now > Date.UTC(2026, 10 - 1 + 2, 15);
  const at = (day) => indicatorLines(ind, { ...fmt, isLate: monthly }, day);
  const early = at(Date.UTC(2026, 11, 14));
  const late = at(Date.UTC(2026, 11, 16));
  assert.equal(indicatorLineText(early[1]), '150.00 index in <2026-10>');
  assert.equal(early[1].title, undefined);
  assert.equal(indicatorLineText(late[1]), '150.00 index in <2026-10> · late');
  assert.equal(late[1].title, 'No value since <2026-10>: this series is late');
  assert.equal(late.length, early.length);
  // the date given is the one the rule gets
  let got;
  indicatorLines(ind, { ...fmt, isLate: (n) => ((got = n), false) }, 12345);
  assert.equal(got, 12345);
  // the view gives the board's own rule and today's date; the board words the mark the same way, and states the rule
  const view = src('components/views/FreightNowView.tsx');
  assert.match(view, /import \{[^}]*\bisLate\b[^}]*\} from '\.\.\/\.\.\/lib\/prices'/);
  assert.match(view, /isLate: \(now\) => isLate\(m, now\)\ \}, Date\.now\(\)\)/);
  const board = src('components/PriceBoard.tsx');
  assert.match(board, /\{late \? ' · late' : ''\}/);
  assert.match(board, /No value since \$\{fmtDate\(st\.last\.t\)\}: this series is late/);
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
  const dallasEntry = json('data/sources.json').find((s) => s.id === 'dallasfed');
  // the Bank's terms ask that it be credited: the registry's name of the source starts with the Bank, which is what the source line and "Copy citation" print
  assert.ok(dallasEntry.name.startsWith(dallasEntry.publisher), 'the registry name of the source starts with the Bank');
  assert.equal(dallasEntry.name, 'Federal Reserve Bank of Dallas, index of global real economic activity (Kilian index)');
  // with no credit in the name, the note gives it
  const note = dallasNote(dallasEntry.publisher);
  assert.match(note, /^Federal Reserve Bank of Dallas; /);
  assert.match(note, /Kilian \(2009\).*Kilian \(2019\)/);
  assert.ok(note.includes(`“${DALLAS_WORDS.proxy}”`));
  assert.ok(note.endsWith(NOT_A_RATE));
  // the page's source line reads "Source: <name> · <month> · <note>": the name already holds the Bank, so the note does not print it again
  const line = indicatorNote('igrea-m', dallasEntry.publisher, metaOf('igrea-m').note, dallasEntry.name);
  assert.doesNotMatch(line, /Federal Reserve Bank of Dallas/);
  assert.match(line, /^as proposed in Kilian \(2009\)/);
  assert.equal(`${dallasEntry.name} · 2026-10 · ${line}`.match(/Federal Reserve Bank of Dallas/g).length, 1);
  assert.ok(line.endsWith(NOT_A_RATE));
  // a name that does not start with the publisher keeps it
  assert.equal(indicatorNote('igrea-m', 'The Bank', undefined, 'Some index'), dallasNote('The Bank'));
  // the BLS row says what its series says it is, whatever the series' note holds
  const bls = metaOf('freight-ppi-m');
  assert.equal(indicatorNote('freight-ppi-m', 'U.S. Bureau of Labor Statistics', bls.note, json('data/sources.json').find((s) => s.id === 'bls').name), `U.S. Bureau of Labor Statistics; ${bls.note}`);
  assert.equal(indicatorNote('freight-ppi-m', 'U.S. Bureau of Labor Statistics', bls.note), `U.S. Bureau of Labor Statistics; ${bls.note}`, 'a registry name that does not start with the publisher keeps the credit');
  assert.match(bls.note, /not a freight rate/);
  assert.match(metaOf('igrea-m').note, /not a freight rate/);
});

test('the price drawer does not name the Bank twice in a row: the basis is printed from what follows the credit its source name already holds', () => {
  const reg = json('data/sources.json');
  const dallas = reg.find((s) => s.id === 'dallasfed');
  const basis = metaOf('igrea-m').basis;
  assert.ok(basis.startsWith('Federal Reserve Bank of Dallas: “Updated index'), 'the basis credits the Bank first');
  const shown = withoutCredit(basis, dallas);
  assert.ok(shown.startsWith('“Updated index of global real economic activity'));
  assert.equal(`${dallas.name} · ${shown}`.match(/Federal Reserve Bank of Dallas/g).length, 1);
  // a source whose name does not start with its publisher keeps the whole basis, and so does a basis that does not start with the credit
  const bls = reg.find((s) => s.id === 'bls');
  assert.equal(withoutCredit(metaOf('freight-ppi-m').basis, bls), metaOf('freight-ppi-m').basis);
  assert.equal(withoutCredit('A basis of its own', dallas), 'A basis of its own');
  assert.equal(withoutCredit(basis, undefined), basis);
  assert.equal(withoutCredit(basis, { name: 'Federal Reserve Bank of Dallas, index' }), basis, 'no publisher, nothing to drop');
  // the drawer uses it for the line under the chart
  assert.match(src('components/PriceDrawer.tsx'), /shortBasis\(withoutCredit\(d\.meta\.basis, sources\.value\[d\.meta\.s\]\)\)/);
});

test('the hover titles name the Bank once: the tail of the title built for the real registry entry and the real series basis', () => {
  const reg = json('data/sources.json');
  for (const { id } of INDICATORS) {
    const m = metaOf(id);
    const entry = reg.find((s) => s.id === m.s);
    // the three titles (the row of the page, the name button of the price board, the figure of a commodity) end with the registry's name of the source and the basis
    const tail = `${entry.name}${basisSuffix(m.basis, entry)}`;
    assert.ok(tail.startsWith(entry.name));
    assert.ok(tail.split(entry.publisher).length - 1 <= 1, `${id}: the publisher is named at most once in "${tail}"`);
    assert.equal(tail, `${entry.name} · ${withoutCredit(m.basis, entry)}`);
  }
  const bank = reg.find((s) => s.id === 'dallasfed');
  const bankTail = `${bank.name}${basisSuffix(metaOf('igrea-m').basis, bank)}`;
  assert.equal(bankTail.split(bank.publisher).length - 1, 1, `the Bank is named once in "${bankTail}"`);
  assert.equal(`${bank.name}${' · ' + metaOf('igrea-m').basis}`.split(bank.publisher).length - 1, 2, 'and twice without the rule');
  // the Dallas Fed series: the basis credits the Bank, and so does the name of its source; the title keeps the quotation and drops the repeat
  const dallas = reg.find((s) => s.id === 'dallasfed');
  assert.ok(metaOf('igrea-m').basis.startsWith(`${dallas.publisher}: `));
  assert.ok(basisSuffix(metaOf('igrea-m').basis, dallas).startsWith(' · “Updated index'));
  // a source whose name does not start with its publisher, a series with no basis, and a registry without the source
  assert.equal(basisSuffix(metaOf('freight-ppi-m').basis, reg.find((s) => s.id === 'bls')), ` · ${metaOf('freight-ppi-m').basis}`);
  assert.equal(basisSuffix(undefined, dallas), '');
  assert.equal(basisSuffix('', dallas), '');
  assert.equal(basisSuffix('A basis', undefined), ' · A basis');
  // the three components build their titles with it, and none joins the basis itself any more
  for (const f of ['components/views/FreightNowView.tsx', 'components/PriceBoard.tsx', 'components/PriceFigure.tsx']) {
    assert.match(src(f), /\$\{basisSuffix\(m\.basis, sources\.value\[m\.s\]\)\}/, f);
    assert.doesNotMatch(src(f), /m\.basis \? ' · ' \+ m\.basis/, f);
  }
});

test('the note under an indicator row is built from the registry\'s real entry, so that the Bank is printed once by the source line and the note together', () => {
  const reg = json('data/sources.json');
  for (const { id } of INDICATORS) {
    const m = metaOf(id);
    const entry = reg.find((s) => s.id === m.s);
    const note = indicatorSourceNote(m, entry);
    const line = `${entry.name} · ${m.stats.last.t} · ${note}`;
    assert.equal(line.split(entry.publisher).length - 1, 1, `${id}: the publisher is named once in "${line}"`);
    assert.equal(note, indicatorNote(m.id, entry.publisher, m.note, entry.name));
    assert.equal(line.split(entry.publisher).length - 1, 1);
  }
  // without the name of the source (the call the view used to make wrongly) the Bank would be named twice in a row
  const dallas = reg.find((s) => s.id === 'dallasfed');
  assert.equal(`${dallas.name} · ${indicatorNote('igrea-m', dallas.publisher, metaOf('igrea-m').note)}`.split(dallas.publisher).length - 1, 2);
  // a registry that lacks the source: the id stands for the publisher and the name
  assert.equal(indicatorSourceNote({ id: 'x', s: 'zz', note: 'a note' }, undefined), 'a note');
  // the view gives the registry's entry, and calls nothing else for the note
  const view = src('components/views/FreightNowView.tsx');
  assert.match(view, /n=\{indicatorSourceNote\(m, sources\.value\[m\.s\]\)\}/);
  assert.doesNotMatch(view, /indicatorNote\(/);
});

// ---------------------------------------------------------------- what the atlas links to and shows no value of

test('the link-only list names each publisher of the registry, has no figure, and its addresses are the registry\'s or pages read and named there', () => {
  const reg = json('data/sources.json');
  const entry = (id) => reg.find((s) => s.id === id);
  assert.deepEqual([...new Set(LINK_ONLY.map((l) => l.s))], ['baltic', 'sse', 'usda-ams']);
  assert.equal(LINK_ONLY.length, 5, 'Baltic, the two Shanghai indices, the weekly count of grain vessels and the grain ocean rates');
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
  // the line for the USDA's vessel count has the table's own name and says what the table counts, the Vancouver port region included
  const ams = LINK_ONLY.filter((l) => l.s === 'usda-ams');
  const quoted = json('pipeline/tests/fixtures/link_only_sources_quotations.json').quotations;
  assert.equal(ams[0].name, quoted.find((q) => q.key === 'ams-datasets-vessel-activity-table').quotation);
  assert.match(ams[0].what, /loaded during the week and expected to be loaded within the next ten days in the Gulf, the Pacific Northwest and Vancouver, B\.C\./);
  assert.match(entry('usda-ams').use, /Vancouver, B\.C\./);
  assert.doesNotMatch(ams[0].what, /loading at the US Gulf/);
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
  assert.match(names[1], /^Federal Reserve Bank of Dallas, index of global real economic activity \(Kilian index\)$/, 'the citation names the Bank');
  assert.match(names[2], /BLS/);
  for (const l of LINK_ONLY) assert.ok(!cited.includes(l.s), `${l.s} is not cited`);
  // the dates: the two windows of the digest, and the month of each indicator
  assert.match(view, /data-src=\{src\} data-y=\{y\}/);
  assert.match(view, /<div class="fn-ind" data-src=\{m\.s\} data-y=\{last\.t\}>/);
  // the Dallas Fed's licence asks that the Bank be credited: the row's note names it, from the registry's publisher
  assert.equal(reg.find((r) => r.id === 'dallasfed').publisher, 'Federal Reserve Bank of Dallas');
  assert.match(view, /indicatorSourceNote\(m, sources\.value\[m\.s\]\)/, 'the note is built from the registry entry of the series\' source');
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
