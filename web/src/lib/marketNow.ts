/**
 * The figures of the Freight market now page (data/freight/market-now.json): reading the digest, the way its numbers are written,
 * and the digest's own arithmetic on the weekly files of data/freight/portwatch, which scripts/market-now.test.mjs uses to prove
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

function rowOf(r: unknown): MarketNowRow | null {
  if (!r || typeof r !== 'object') return null;
  const o = r as Record<string, unknown>;
  const mt = o.mt as Record<string, unknown> | undefined;
  if (typeof o.id !== 'string' || !o.id || !isCount(o.now) || !isCount(o.ago) || !mt || !isCount(mt.now) || !isCount(mt.ago)) return null;
  return { id: o.id, now: o.now, ago: o.ago, mt: { now: mt.now, ago: mt.ago }, rankMt: isCount(o.rankMt) ? o.rankMt : 0 };
}

/**
 * The digest as the page reads it, or null when the file is not one: not an object, a date that is not a day, a list that is
 * missing, a row without a finite non-negative count. The page prints nothing from a file it cannot read as a whole.
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

/** (now - ago) / ago in per cent; null when there is nothing a year earlier to compare with (a zero or a missing figure). */
export function changePct(now: number | null | undefined, ago: number | null | undefined): number | null {
  if (now == null || ago == null || !Number.isFinite(now) || !Number.isFinite(ago) || ago <= 0) return null;
  return (100 * (now - ago)) / ago;
}

/**
 * The change as the page prints it: a true minus, one decimal ("+12.4%", "−13.7%"); "0%" for no change; "<0.1%" for a change
 * smaller than a tenth; "−100%" only when nothing is left (a fall that one decimal would round to 100% while ships remain
 * reads "−99.9%"). "—" when `ago` is zero or missing: there is no per cent of nothing.
 */
export function changeText(now: number | null | undefined, ago: number | null | undefined): string {
  const p = changePct(now, ago);
  if (p == null) return '—';
  if (p === 0) return '0%';
  const a = Math.abs(p);
  let body: string;
  if (a < 0.1) body = '<0.1%';
  else {
    body = a.toFixed(1);
    if (p < 0 && now! > 0 && Number(body) >= 100) body = '99.9';
    if (Number(body) === 100) body = '100';
    body += '%';
  }
  return `${p > 0 ? '+' : '−'}${body}`;
}

/**
 * The change in cargo. A volume under 0.05 Mt is the length of a rounding error: it is said as a bound ("down more than N%", from
 * the bound itself) and has no figure; when the year-earlier cargo is that small too there is nothing to compare.
 */
export function mtChangeText(now: number, ago: number): string {
  if (tinyMt(ago)) return '—';
  if (tinyMt(now)) return `down more than ${Math.floor((100 * (ago - TINY_MT)) / ago)}%`;
  return changeText(now, ago);
}

/** What a row prints: the two figures of each measure and the change between them, as text. */
export interface RowText {
  transits: { now: string; ago: string; change: string };
  cargo: { now: string; ago: string; change: string };
}
export function rowText(r: MarketNowRow): RowText {
  return {
    transits: { now: countText(r.now), ago: countText(r.ago), change: changeText(r.now, r.ago) },
    cargo: { now: mtText(r.mt.now), ago: mtText(r.mt.ago), change: mtChangeText(r.mt.now, r.mt.ago) },
  };
}

// ---------------------------------------------------------------- the digest's arithmetic on the weekly files

/** The parts of a weekly file the arithmetic reads. */
export type WeeklySeries = Pick<PortwatchSeries, 'id' | 'start' | 'y' | 'tanker' | 'dry'> & { vol: Pick<NonNullable<PortwatchSeries['vol']>, 'tanker' | 'dry'> };

/** A value as an integer count of 10^-decimals; refuses a value that has more decimals than the file says it has. */
function scaled(v: number, decimals: number, where: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) throw new Error(`${where}: ${String(v)} is not a finite number that is not negative`);
  const k = 10 ** decimals;
  const r = Math.round(v * k);
  if (Math.abs(v * k - r) > 1e-6) throw new Error(`${where}: ${v} has more than ${decimals} decimals`);
  return r;
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

/** Vessels over the window: the weekly means times 7, summed, whole vessels, a half rounded up. The weekly means hold one decimal. */
export function vesselsOver(s: WeeklySeries, type: MarketType, end: string, weeks: number): number {
  return Math.floor((weeklySum(s[type], s, end, weeks, 1, type) * WEEK_DAYS + 5) / 10);
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
  return sig3(weeklySum(s.vol[type], s, end, weeks, 4, `vol.${type}`) * WEEK_DAYS, 4);
}

/**
 * The digest of a set of weekly files, by the rules the weekly job's builder follows (METHODOLOGY.md): `to` is the earliest last
 * complete week of the files; the window is the `weeks` weeks that end on it, the comparison window ends 364 days before; the five
 * passages are those with the most cargo of the type over the `rankWeeks` weeks that end with the comparison window, ties by id.
 */
export function buildDigest(all: WeeklySeries[]): Pick<MarketNow, 'to' | 'yearAgoTo' | 'types'> {
  const to = all.map(lastWeekEnd).sort()[0];
  const agoTo = addDays(to, -WEEK_DAYS * YEAR_BACK);
  const types = { tanker: [] as MarketNowRow[], dry: [] as MarketNowRow[] };
  for (const t of ['tanker', 'dry'] as const) {
    const ranked = all
      .map((s) => ({ s, sum: weeklySum(s.vol[t], s, agoTo, RANK_WEEKS, 4, `vol.${t}`) }))
      .sort((a, b) => b.sum - a.sum || (a.s.id < b.s.id ? -1 : 1));
    types[t] = ranked.slice(0, PASSAGES).map(({ s, sum }) => ({
      id: s.id,
      now: vesselsOver(s, t, to, WINDOW_WEEKS),
      ago: vesselsOver(s, t, agoTo, WINDOW_WEEKS),
      mt: { now: cargoOver(s, t, to, WINDOW_WEEKS), ago: cargoOver(s, t, agoTo, WINDOW_WEEKS) },
      rankMt: sig3(sum * WEEK_DAYS, 4),
    }));
  }
  return { to, yearAgoTo: agoTo, types };
}
