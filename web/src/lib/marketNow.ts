/**
 * The figures of the Freight market now page (data/freight/market-now.json): reading the digest, the way its numbers and the lines of a
 * row are written (the page prints the changes in per cent that the builder stores and computes none), and the digest's own arithmetic on the weekly files of data/freight/portwatch, which scripts/market-now.test.mjs uses to prove
 * the published file week by week. Weeks are taken by date, never by position: a series says where it starts (a Monday) and its
 * last day, and a file whose length does not match its dates is refused.
 *
 * Type import only: scripts/market-now.test.mjs runs this file as it is, against the files of the folder.
 */
import type { MarketNow, MarketNowRow, PortwatchSeries } from '../types';

export type MarketType = 'tanker' | 'dry';
/** The two lists of the page, in the order it shows them, with the ship type's own words. */
export const MARKET_TYPES: readonly { type: MarketType; title: string; noun: string }[] = [
  { type: 'dry', title: 'Dry bulk carriers at the five passages with the most cargo', noun: 'dry bulk carriers' },
  { type: 'tanker', title: 'Tankers at the five passages with the most cargo', noun: 'tankers' },
];

/**
 * The lead of the page. It says "two indicators" only on a page that shows them: `indicators` is the number of rows the page has (none when the
 * price files cannot be read), and the sentence on rates is the atlas's, not the world's.
 */
export function leadText(indicators: number): string {
  const reason = 'the atlas shows no spot rate for tankers or gas carriers and no Baltic Exchange index value, since the sources it knows for them are proprietary or cannot be republished.';
  const WORDS = ['no', 'one', 'two', 'three', 'four', 'five'];
  const what = indicators <= 0 ? 'and no freight rate' : indicators === 1 ? 'and one indicator, which is not a freight rate' : `and ${WORDS[indicators] ?? indicators} indicators, none of them a freight rate`;
  return `This page shows traffic at the main passages ${what}: ${reason}`;
}

/**
 * What the atlas read of PortWatch's ship classes, and what it cannot say of gas carriers. Shown under the tanker list only, and only when that list
 * has rows: with no tanker figure on the page there is nothing for the sentence to qualify. The description is the one of the ArcGIS item of the
 * chokepoint table (METHODOLOGY.md quotes it; pipeline/tests/test_market_now_texts.py compares the quotation with the saved page).
 */
export const CLASSES_NOTE =
  "The description of PortWatch's passage data that the atlas read lists five ship classes (container, dry bulk, general cargo, ro-ro and tanker) and does not say what each holds, so the atlas cannot say whether gas carriers are in its tanker class: the tanker figures may include them or not. The atlas shows no separate gas carrier figure.";
export const classesNote = (type: MarketType, rows: readonly unknown[]): string | null => (type === 'tanker' && rows.length > 0 ? CLASSES_NOTE : null);

/** Same rule as the passage board: a volume under this is a rounding error's length, so it is said as a bound and has no per-cent change. */
export const TINY_MT = 0.05;

const DAY_MS = 86_400_000;
const WEEK_DAYS = 7;
/** The rules of the digest: four weeks, the same four weeks 52 weeks (364 days) earlier, 52 ranking weeks, five passages a list. */
const WINDOW_WEEKS = 4;
const YEAR_BACK = 52;
const RANK_WEEKS = 52;
const PASSAGES = 5;

// ---------------------------------------------------------------- dates

const ISO = /^\d{4}-\d{2}-\d{2}$/;
/** A real calendar day, as "YYYY-MM-DD". */
export const isIsoDay = (s: unknown): s is string => typeof s === 'string' && ISO.test(s) && !Number.isNaN(Date.parse(`${s}T00:00:00Z`)) && new Date(`${s}T00:00:00Z`).toISOString().slice(0, 10) === s;
const dayMs = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
export const addDays = (iso: string, n: number): string => new Date(dayMs(iso) + n * DAY_MS).toISOString().slice(0, 10);
const daysBetween = (a: string, b: string) => Math.round((dayMs(b) - dayMs(a)) / DAY_MS);

// ---------------------------------------------------------------- reading the digest

const isCount = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0;

/** A change in per cent as the builder stores it: a finite number, or null when there was nothing a year earlier. */
const isChange = (v: unknown): v is number | null => v === null || (typeof v === 'number' && Number.isFinite(v));

function rowOf(r: unknown): MarketNowRow | null {
  if (!r || typeof r !== 'object') return null;
  const o = r as Record<string, unknown>;
  const mt = o.mt as Record<string, unknown> | undefined;
  if (typeof o.id !== 'string' || !o.id || !isCount(o.now) || !isCount(o.ago) || !isChange(o.pct) || !mt || !isCount(mt.now) || !isCount(mt.ago) || !isChange(mt.pct)) return null;
  return { id: o.id, now: o.now, ago: o.ago, pct: o.pct, mt: { now: mt.now, ago: mt.ago, pct: mt.pct }, rankMt: isCount(o.rankMt) ? o.rankMt : 0 };
}

/**
 * The digest as the page reads it, or null when the file is not one: not an object, a date that is not a day, a list that is
 * missing, a row without a finite non-negative count or without its two changes (a number or null). The page prints nothing from a file it cannot read as a whole.
 */
export function readMarketNow(doc: unknown): MarketNow | null {
  if (!doc || typeof doc !== 'object') return null;
  const o = doc as Record<string, unknown>;
  const types = o.types as Record<string, unknown> | undefined;
  if (typeof o.s !== 'string' || !isIsoDay(o.to) || !isIsoDay(o.yearAgoTo) || typeof o.unit !== 'string' || typeof o.mtUnit !== 'string' || !types) return null;
  const lists: Partial<Record<MarketType, MarketNowRow[]>> = {};
  for (const t of ['tanker', 'dry'] as const) {
    const raw = types[t];
    if (!Array.isArray(raw)) return null;
    const rows = raw.map(rowOf);
    if (rows.some((r) => !r)) return null;
    lists[t] = rows as MarketNowRow[];
  }
  const n = (v: unknown, dflt: number) => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : dflt);
  return {
    s: o.s,
    to: o.to,
    yearAgoTo: o.yearAgoTo,
    weeks: n(o.weeks, 4),
    days: n(o.days, 28),
    rankWeeks: n(o.rankWeeks, 52),
    unit: o.unit,
    mtUnit: o.mtUnit,
    types: { tanker: lists.tanker!, dry: lists.dry! },
  };
}

// ---------------------------------------------------------------- how the figures are written

const INT = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
// the cargo is stored to three significant figures: up to four decimals are real digits (0.0512), more are never there
const MT = new Intl.NumberFormat('en-US', { maximumFractionDigits: 4 });

/** Whole vessels, with thousands separators. */
export const countText = (n: number | null | undefined): string => (n == null || !Number.isFinite(n) ? '—' : INT.format(n));

const tinyMt = (v: number | null | undefined): v is number => v != null && v > 0 && v < TINY_MT;

/** The cargo in Mt as the digest holds it (three significant figures), or "under 0.05 Mt". */
export const mtText = (v: number | null | undefined): string => (v == null || !Number.isFinite(v) ? '—' : tinyMt(v) ? `under ${TINY_MT} Mt` : `${MT.format(v)} Mt`);

/**
 * The change as the builder stored it (per cent, one decimal), as the page prints it: a true minus and one decimal ("+12.4%", "−13.7%", "0.0%");
 * "−100%" only when nothing is left (the builder stores −99.9 for a fall that one decimal would round to 100 while something is left);
 * "—" when there is none (nothing a year earlier: the builder stores null). The page works out nothing.
 */
export function changeText(pct: number | null | undefined): string {
  if (pct == null || !Number.isFinite(pct)) return '—';
  if (pct === -100) return '−100%';
  return `${pct > 0 ? '+' : pct < 0 ? '−' : ''}${Math.abs(pct).toFixed(1)}%`;
}

/**
 * The change in cargo, from the change the builder stored. A year-earlier cargo under 0.05 Mt is the length of a rounding error, so there is
 * nothing to compare (a dash); a cargo now under it is shown as a bound, and its change is said as one ("down more than N%", from the bound
 * itself and the year-earlier figure the row prints); otherwise the stored change.
 */
export function mtChangeText(now: number, ago: number, pct: number | null | undefined): string {
  if (pct == null || tinyMt(ago)) return '—';
  if (tinyMt(now)) return `down more than ${Math.floor((100 * (ago - TINY_MT)) / ago)}%`;
  return changeText(pct);
}

/** What a row prints: the two figures of each measure and the change between them, as text. */
export interface RowText {
  transits: { now: string; ago: string; change: string };
  cargo: { now: string; ago: string; change: string };
}
export function rowText(r: MarketNowRow): RowText {
  return {
    transits: { now: countText(r.now), ago: countText(r.ago), change: changeText(r.pct) },
    cargo: { now: mtText(r.mt.now), ago: mtText(r.mt.ago), change: mtChangeText(r.mt.now, r.mt.ago, r.mt.pct) },
  };
}

/** One of the two lines of a row: the words and figures, then the change (which the page sets in bold), and the title of a change that is a dash. */
export interface RowLine {
  text: string;
  change: string;
  title?: string;
}
export interface RowLines {
  transits: RowLine;
  cargo: RowLine;
}
/** The hover text of a dash: nothing a year earlier, or a year-earlier cargo too small to compare with. */
export const NO_CHANGE_TITLE = 'No per cent to print: nothing a year earlier';
export const TINY_AGO_TITLE = `No per cent to print: under ${TINY_MT} Mt a year earlier`;
/** The two lines a row prints under the passage's name: "Transits 2,158 vs 2,395 a year earlier: −9.9%" and "Cargo 87.2 Mt vs 113 Mt a year earlier: −23.0%". */
export function rowLines(r: MarketNowRow): RowLines {
  const t = rowText(r);
  const line = (label: string, f: { now: string; ago: string; change: string }, why = NO_CHANGE_TITLE): RowLine => ({
    text: `${label} ${f.now} vs ${f.ago} a year earlier`,
    change: f.change,
    title: f.change === '—' ? why : undefined,
  });
  return { transits: line('Transits', t.transits), cargo: line('Cargo', t.cargo, tinyMt(r.mt.ago) ? TINY_AGO_TITLE : NO_CHANGE_TITLE) };
}
/** A line as one string, as the page reads it. */
export const lineText = (l: RowLine): string => `${l.text}: ${l.change}`;

// ---------------------------------------------------------------- the digest's arithmetic on the weekly files

/** The parts of a weekly file the arithmetic reads. */
export type WeeklySeries = Pick<PortwatchSeries, 'id' | 'start' | 'y' | 'tanker' | 'dry'> & { vol: Pick<NonNullable<PortwatchSeries['vol']>, 'tanker' | 'dry'> };

/** The decimals of a number as it is written (its shortest form, "1.5e-7" has eight): the builder counts them the same way. */
function decimalsOf(v: number): number {
  const [mantissa, exp = '0'] = String(v).split('e');
  return Math.max(0, (mantissa.split('.')[1] ?? '').length - Number(exp));
}

/** The decimals of the weekly files: the vessel counts have one, the cargo in Mt a day four (pipeline/freight/build_portwatch.py), and the builder refuses more. */
const COUNT_DECIMALS = 1;
const CARGO_DECIMALS = 4;

/** A value as an integer count of 10^-decimals; refuses a value that has more decimals than the weekly files carry. */
function scaled(v: number, decimals: number, where: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) throw new Error(`${where}: ${String(v)} is not a finite number that is not negative`);
  if (decimalsOf(v) > decimals) throw new Error(`${where}: ${v} has more than ${decimals} decimals`);
  return Math.round(v * 10 ** decimals);
}

/** The Sunday that ends the last complete week of a file; refuses a file whose length does not match its dates. */
export function lastWeekEnd(s: WeeklySeries): string {
  const at = `${s.id}.json`;
  if (!isIsoDay(s.start) || !isIsoDay(s.y)) throw new Error(`${at}: start and y must be dates`);
  if (new Date(`${s.start}T00:00:00Z`).getUTCDay() !== 1) throw new Error(`${at}: the first week starts on ${s.start}, which is not a Monday`);
  const days = daysBetween(s.start, s.y) + 1;
  if (days < WEEK_DAYS) throw new Error(`${at}: y ${s.y} is before the end of the first week`);
  const complete = Math.floor(days / WEEK_DAYS);
  const expect = complete + (days % WEEK_DAYS ? 1 : 0);
  const lens = [s.tanker, s.dry, s.vol.tanker, s.vol.dry].map((a) => a.length);
  if (lens.some((n) => n !== expect)) throw new Error(`${at}: ${lens.join('/')} weeks from ${s.start}, but the dates (to ${s.y}) make ${expect}`);
  return addDays(s.start, WEEK_DAYS * complete - 1);
}

/** Why the builder would refuse the file (the checks it makes of a weekly file: dates and lengths, values that are numbers, not negative and with the decimals the files carry), or null when it would not. */
export function refusal(s: WeeklySeries): string | null {
  try {
    lastWeekEnd(s);
    for (const [what, list, decimals] of [['tanker', s.tanker, COUNT_DECIMALS], ['dry', s.dry, COUNT_DECIMALS], ['vol.tanker', s.vol.tanker, CARGO_DECIMALS], ['vol.dry', s.vol.dry, CARGO_DECIMALS]] as const) {
      list.forEach((v, i) => scaled(v, decimals, `${s.id}.json ${what}[${i}]`));
    }
    return null;
  } catch (e) {
    return (e as Error).message;
  }
}

/** Position of the week that ends on `end` (a Sunday inside the complete weeks of the file). */
export function weekIndex(s: WeeklySeries, end: string): number {
  const d = daysBetween(s.start, end) - (WEEK_DAYS - 1);
  const last = daysBetween(s.start, lastWeekEnd(s)) - (WEEK_DAYS - 1);
  if (d < 0 || d % WEEK_DAYS || d > last) throw new Error(`${s.id}.json: no week ends on ${end}`);
  return d / WEEK_DAYS;
}

/** Sum of `weeks` weekly means (a day) that end with `end`, as integers of 10^-decimals. */
function weeklySum(values: number[], s: WeeklySeries, end: string, weeks: number, decimals: number, what: string): number {
  let sum = 0;
  for (let k = 0; k < weeks; k++) sum += scaled(values[weekIndex(s, addDays(end, -WEEK_DAYS * k))], decimals, `${s.id}.json ${what}`);
  return sum;
}

/** Vessels over the window before any rounding, in tenths of a vessel: the weekly means (one decimal) times 7, summed. */
function vesselSum(s: WeeklySeries, type: MarketType, end: string, weeks: number): number {
  return weeklySum(s[type], s, end, weeks, COUNT_DECIMALS, type) * WEEK_DAYS;
}

/** Vessels over the window: the weekly means times 7, summed, whole vessels, a half rounded up. The weekly means hold one decimal. */
export function vesselsOver(s: WeeklySeries, type: MarketType, end: string, weeks: number): number {
  return Math.floor((vesselSum(s, type, end, weeks) + 5) / 10);
}

/** Estimated cargo over the window before any rounding, in 10^-4 Mt: the weekly means (four decimals) times 7, summed. */
function cargoSum(s: WeeklySeries, type: MarketType, end: string, weeks: number): number {
  return weeklySum(s.vol[type], s, end, weeks, CARGO_DECIMALS, `vol.${type}`) * WEEK_DAYS;
}

/**
 * The change between two sums of the same unit (integers, not rounded) in per cent, one decimal, a half rounded away from zero; null when
 * `ago` is zero; −99.9 for a fall that one decimal would round to −100.0 while `now` is not zero. The rule of the builder's `pct`.
 */
export function changeBetween(now: number, ago: number): number | null {
  if (ago === 0) return null;
  const num = (now - ago) * 1000; // tenths of a per cent, times `ago`
  const x = 2 * Math.abs(num) + ago;
  const d = 2 * ago;
  let r = (x - (x % d)) / d; // floor((2|num| + ago) / (2 ago)): a half goes up, whatever the sign. All integers, so exact
  if (num < 0) r = -r;
  if (r === -1000 && now !== 0) r = -999;
  return r === 0 ? 0 : r / 10;
}

/** Three significant figures, a half rounded up, of `n` x 10^-scale, as the nearest number. */
export function sig3(n: number, scale: number): number {
  const digits = String(n).length;
  if (n === 0) return 0;
  if (digits <= 3) return Number(`${n}e-${scale}`);
  const d = digits - 3;
  return Number(`${Math.floor((n + 5 * 10 ** (d - 1)) / 10 ** d)}e${d - scale}`);
}

/** Estimated cargo (Mt) over the window: the weekly means times 7, summed, three significant figures. The weekly means hold four decimals. */
export function cargoOver(s: WeeklySeries, type: MarketType, end: string, weeks: number): number {
  return sig3(cargoSum(s, type, end, weeks), 4);
}

/** Whether the file holds the `RANK_WEEKS` weeks that end on `agoTo`: a file that starts later is left out of the ranking. */
export function canRank(s: WeeklySeries, agoTo: string): boolean {
  return !!isIsoDay(s.start) && daysBetween(s.start, agoTo) >= WEEK_DAYS * RANK_WEEKS - 1;
}

/**
 * The digest of a set of weekly files, by the rules the weekly job's builder follows (METHODOLOGY.md): `to` is the earliest last
 * complete week of the files (or the date given: the digest as it stood on that week); the window is the `weeks` weeks that end on it, the
 * comparison window ends 364 days before; the five passages are those with the most cargo of the type over the `rankWeeks` weeks that end
 * with the comparison window, ranked on the sum before rounding (`rankMt` is that sum to three significant figures, so two passages can
 * show the same figure; only an exact tie of the sums goes by id); a file that starts after the first of those weeks is left out of the
 * ranking. The changes in per cent are worked out on the sums before rounding.
 */
export function buildDigest(all: WeeklySeries[], at?: string): Pick<MarketNow, 'to' | 'yearAgoTo' | 'types'> {
  const ends = all.map(lastWeekEnd).sort();
  const to = at ?? ends[0];
  const agoTo = addDays(to, -WEEK_DAYS * YEAR_BACK);
  const ranking = all.filter((s) => canRank(s, agoTo));
  if (ranking.length < PASSAGES) throw new Error(`${ranking.length} of ${all.length} weekly series reach back ${RANK_WEEKS} weeks before ${agoTo}, at least ${PASSAGES} are needed to name ${PASSAGES} passages`);
  const types = { tanker: [] as MarketNowRow[], dry: [] as MarketNowRow[] };
  for (const t of ['tanker', 'dry'] as const) {
    const ranked = ranking
      .map((s) => ({ s, sum: weeklySum(s.vol[t], s, agoTo, RANK_WEEKS, CARGO_DECIMALS, `vol.${t}`) }))
      .sort((a, b) => b.sum - a.sum || (a.s.id < b.s.id ? -1 : 1));
    types[t] = ranked.slice(0, PASSAGES).map(({ s, sum }) => {
      const [vNow, vAgo] = [vesselSum(s, t, to, WINDOW_WEEKS), vesselSum(s, t, agoTo, WINDOW_WEEKS)];
      const [cNow, cAgo] = [cargoSum(s, t, to, WINDOW_WEEKS), cargoSum(s, t, agoTo, WINDOW_WEEKS)];
      return {
        id: s.id,
        now: Math.floor((vNow + 5) / 10),
        ago: Math.floor((vAgo + 5) / 10),
        pct: changeBetween(vNow, vAgo),
        mt: { now: sig3(cNow, 4), ago: sig3(cAgo, 4), pct: changeBetween(cNow, cAgo) },
        rankMt: sig3(sum * WEEK_DAYS, 4),
      };
    });
  }
  return { to, yearAgoTo: agoTo, types };
}
