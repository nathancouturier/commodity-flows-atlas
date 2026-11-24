/**
 * Price series access: lazy loading with a cache, packed -> uPlot arrays (x in seconds),
 * merging of several series on a common time axis, lookup of the observation that covers a
 * date and free-text date parsing for the price explorer.
 */
import { signal } from '@preact/signals';
import type { Family, PriceSeries, PriceSeriesMeta } from '../types';
import { commodityMeta, load } from './data';
import { FAMILY_LABEL } from './format';
import { historyOpen, priceDrawer, commodity } from './store';

/** A spread or ratio is built in the browser from two series of the same frequency: `spread` names the legs. */
export interface SpreadLegs {
  a: string;
  b: string;
  kind: 'diff' | 'ratio';
}
export type PriceMeta = PriceSeriesMeta & { note?: string; spread?: SpreadLegs };

export interface LoadedSeries {
  meta: PriceMeta;
  /** seconds since epoch (UTC), ascending */
  x: number[];
  v: (number | null)[];
  /** daily series: [last day before, first day after] of every stretch longer than GAP_DAYS without an observation */
  gaps?: [number, number][];
}

/** Where a series is listed: the family of its commodity, or the price indices (series with no page in the atlas name their own). */
export type PriceGroup = Family | 'index';
export const GROUP_ORDER: PriceGroup[] = ['energy', 'metals', 'softs', 'freight', 'index'];
export const GROUP_LABEL: Record<PriceGroup, string> = { ...FAMILY_LABEL, index: 'Price indices' };
export function groupOf(m: { k: string; fam?: string }): PriceGroup {
  if (m.k === 'freight') return 'freight';
  return commodityMeta(m.k)?.family ?? ((m.fam as PriceGroup | undefined) ?? 'energy');
}

/** A daily series is drawn as broken over a stretch of more than a week without an observation. */
export const GAP_DAYS = 7;
export const FREQ_WORD = { D: 'daily', M: 'monthly', A: 'annual' } as const;

/**
 * An annual series gives one value for a calendar year (USGS annual averages, the annual contract prices of iron ore,
 * the real prices). It is never read as a current price, nor as "the price one month later": a page that looks for the
 * price at a date or after it uses a daily or monthly series, and says "annual average <year>" for an annual one.
 */
export const isAnnualSeries = (m: { freq: string }): boolean => m.freq === 'A';

/**
 * What an annual value of a series is called. Only the iron ore row of the World Bank Description sheet says that its
 * early prices are "annual contract prices"; the others are the annual averages their sources publish.
 */
export function annualWord(m: { id: string }): string {
  return m.id === 'iron-ore-contract-a' ? 'annual contract price' : 'annual average';
}

export const DAY_S = 86400;
export const priceIndex = signal<PriceMeta[]>([]);
export const priceIndexError = signal<string | null>(null);

let indexPromise: Promise<PriceMeta[]> | null = null;
export function loadPriceIndex(): Promise<PriceMeta[]> {
  if (!indexPromise) {
    indexPromise = load<PriceMeta[]>('prices/index.json').then(
      (r) => {
        priceIndex.value = r;
        return r;
      },
      (e) => {
        indexPromise = null;
        priceIndexError.value = String(e.message ?? e);
        throw e;
      },
    );
  }
  return indexPromise;
}

/**
 * The key figure of a commodity page needs only the first series of the commodity: prices/figures.json holds it, with its
 * board figures, for every commodity (the page does not load the whole index).
 */
export const priceFigures = signal<Record<string, PriceMeta> | null>(null);
let figuresPromise: Promise<Record<string, PriceMeta>> | null = null;
export function loadPriceFigures(): Promise<Record<string, PriceMeta>> {
  if (!figuresPromise) {
    figuresPromise = load<Record<string, PriceMeta>>('prices/figures.json').then(
      (r) => {
        priceFigures.value = r;
        return r;
      },
      (e) => {
        figuresPromise = null;
        throw e;
      },
    );
  }
  return figuresPromise;
}

const seriesCache = new Map<string, Promise<LoadedSeries>>();

export function loadSeries(id: string): Promise<LoadedSeries> {
  let p = seriesCache.get(id);
  if (!p && id.startsWith(SPREAD_PREFIX)) {
    p = loadSpread(id);
    p.catch(() => seriesCache.delete(id));
    seriesCache.set(id, p);
  }
  if (!p) {
    p = Promise.all([loadPriceIndex(), load<PriceSeries>(`prices/${id}.json`)]).then(([idx, raw]) => {
      const meta = idx.find((m) => m.id === id);
      if (!meta) throw new Error(`unknown price series ${id}`);
      return unpack(meta, raw);
    });
    p.catch(() => seriesCache.delete(id));
    seriesCache.set(id, p);
  }
  return p;
}

export function unpack(meta: PriceMeta, raw: PriceSeries): LoadedSeries {
  const n = raw.v.length;
  const x = new Array<number>(n);
  if (raw.freq === 'D' && raw.d) {
    for (let i = 0; i < n; i++) x[i] = raw.d[i] * DAY_S;
  } else if (raw.freq === 'A') {
    const sy = Number((raw.start ?? meta.start).slice(0, 4));
    for (let i = 0; i < n; i++) x[i] = Date.UTC(sy + i, 0, 1) / 1000;
  } else {
    const [sy, sm] = (raw.start ?? meta.start).split('-').map(Number);
    for (let i = 0; i < n; i++) x[i] = Date.UTC(sy, sm - 1 + i, 1) / 1000;
  }
  return { meta, x, v: raw.v, gaps: raw.freq === 'D' ? gapsOf(x, raw.v) : undefined };
}

/** Stretches of a daily series longer than GAP_DAYS between two observations (nothing is interpolated over them). */
export function gapsOf(x: number[], v: (number | null)[]): [number, number][] {
  const out: [number, number][] = [];
  let prev = -1;
  for (let i = 0; i < x.length; i++) {
    if (v[i] == null) continue;
    if (prev >= 0 && x[i] - x[prev] > GAP_DAYS * DAY_S) out.push([x[prev], x[i]]);
    prev = i;
  }
  return out;
}

/** Merge series onto the union of their timestamps (gaps are null; the chart joins them). */
export function mergeSeries(list: LoadedSeries[]): { x: number[]; cols: (number | null)[][] } {
  if (list.length === 1) return { x: list[0].x, cols: [list[0].v] };
  const set = new Set<number>();
  for (const s of list) for (const t of s.x) set.add(t);
  const x = Array.from(set).sort((a, b) => a - b);
  const pos = new Map<number, number>();
  x.forEach((t, i) => pos.set(t, i));
  const cols = list.map((s) => {
    const col = new Array<number | null>(x.length).fill(null);
    for (let i = 0; i < s.x.length; i++) col[pos.get(s.x[i])!] = s.v[i];
    return col;
  });
  return { x, cols };
}

/**
 * End (exclusive, seconds) of the period an observation stamped t stands for: one day for a daily
 * series, the whole calendar month for a monthly one (stamped on the 1st), the calendar year otherwise.
 */
export function obsEnd(t: number, freq: string): number {
  if (freq === 'D') return t + DAY_S;
  const d = new Date(t * 1000);
  return (freq === 'M' ? Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) : Date.UTC(d.getUTCFullYear() + 1, 0, 1)) / 1000;
}

/**
 * How a series answers "the price at time t":
 * - exact: a daily quote for that very day;
 * - period: the monthly (or annual) value whose calendar period contains t;
 * - previous: no quote that day (weekend, holiday, gap): the last quote before it;
 * - before / after: t is outside the series; i is the first / last observation, to name the limit;
 * - missing: nothing to show (i = -1).
 */
export type ObsKind = 'exact' | 'period' | 'previous' | 'before' | 'after' | 'missing';
export interface ObsAt {
  kind: ObsKind;
  i: number;
}

/** First and last non-null observations, or null for an empty series. */
export function seriesBounds(s: { x: number[]; v: (number | null)[] }): { first: number; last: number } | null {
  let first = 0;
  while (first < s.x.length && s.v[first] == null) first++;
  let last = s.x.length - 1;
  while (last >= 0 && s.v[last] == null) last--;
  return last < 0 ? null : { first, last };
}

/**
 * The observation that covers time t. A date never resolves to a later observation: a monthly value
 * stands for its whole month (so the 25th belongs to that month, not to the next stamp), and a day
 * without a quote takes the last price on or before it.
 */
export function observationAt(s: { x: number[]; v: (number | null)[] }, freq: string, t: number): ObsAt {
  const b = seriesBounds(s);
  if (!b) return { kind: 'missing', i: -1 };
  if (t < s.x[b.first]) return { kind: 'before', i: b.first };
  if (t >= obsEnd(s.x[b.last], freq)) return { kind: 'after', i: b.last };
  let i = lowerBound(s.x, t + 1) - 1;
  if (freq !== 'D') return s.v[i] != null && t < obsEnd(s.x[i], freq) ? { kind: 'period', i } : { kind: 'missing', i: -1 };
  if (s.v[i] != null && t < s.x[i] + DAY_S) return { kind: 'exact', i };
  while (i >= 0 && s.v[i] == null) i--;
  return i < 0 ? { kind: 'missing', i: -1 } : { kind: 'previous', i };
}

export interface PeriodStats {
  n: number;
  avg: number;
  min: { v: number; i: number };
  max: { v: number; i: number };
}

/** Average, low and high of the observations with t0 <= x <= t1; null when there are none. */
export function periodStats(s: { x: number[]; v: (number | null)[] }, t0: number, t1: number): PeriodStats | null {
  let n = 0;
  let sum = 0;
  let mn = -1;
  let mx = -1;
  for (let i = lowerBound(s.x, t0); i < s.x.length && s.x[i] <= t1; i++) {
    const v = s.v[i];
    if (v == null) continue;
    n++;
    sum += v;
    if (mn < 0 || v < s.v[mn]!) mn = i;
    if (mx < 0 || v > s.v[mx]!) mx = i;
  }
  return n ? { n, avg: sum / n, min: { v: s.v[mn]!, i: mn }, max: { v: s.v[mx]!, i: mx } } : null;
}

/** Index of the first non-null observation with x >= t (-1 when none). */
export function firstAtOrAfter(s: { x: number[]; v: (number | null)[] }, t: number): number {
  for (let i = lowerBound(s.x, t); i < s.x.length; i++) if (s.v[i] != null && s.v[i] !== 0) return i;
  return -1;
}

/** First index with x >= t. */
export function lowerBound(x: number[], t: number): number {
  let lo = 0;
  let hi = x.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (x[mid] < t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

// ---------------------------------------------------------------- date lookup

export type Precision = 'year' | 'quarter' | 'month' | 'day';
export interface ParsedDate {
  /** seconds, start of the named period */
  t: number;
  precision: Precision;
}

/** End (exclusive, seconds) of the period a lookup names. */
export function lookupEnd(p: ParsedDate): number {
  const d = new Date(p.t * 1000);
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth();
  if (p.precision === 'year') return Date.UTC(y + 1, 0, 1) / 1000;
  if (p.precision === 'quarter') return Date.UTC(y, m + 3, 1) / 1000;
  if (p.precision === 'month') return Date.UTC(y, m + 1, 1) / 1000;
  return p.t + DAY_S;
}

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];

/**
 * Accepts "1986", "Q3 2008", "2008 Q3", "2008-03", "03/2008", "2008-03-14", "Mar 2008", "March 2008",
 * "14 Mar 2008" and "14/03/2008". An all-digit day/month/year is read day first, as the site writes its
 * dates ("14 Mar 2008"); it is read month first only when the second number cannot be a month.
 */
export function parseLookup(input: string): ParsedDate | null {
  const s = input.trim().toLowerCase().replace(/,/g, ' ').replace(/\s+/g, ' ');
  let m: RegExpMatchArray | null;
  const valid = (y: number, mo: number, d: number) => {
    if (y < 1900 || y > 2100 || mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    const dt = new Date(Date.UTC(y, mo - 1, d));
    if (dt.getUTCMonth() !== mo - 1) return null;
    return dt.getTime() / 1000;
  };
  if ((m = s.match(/^(\d{4})$/))) {
    const t = valid(+m[1], 1, 1);
    return t == null ? null : { t, precision: 'year' };
  }
  if ((m = s.match(/^(\d{4})[- ]?q([1-4])$/)) || (m = s.match(/^q([1-4])[- ]?(\d{4})$/))) {
    const [y, q] = m[1].length === 4 ? [+m[1], +m[2]] : [+m[2], +m[1]];
    const t = valid(y, q * 3 - 2, 1);
    return t == null ? null : { t, precision: 'quarter' };
  }
  if ((m = s.match(/^(\d{4})[-/.](\d{1,2})$/))) {
    const t = valid(+m[1], +m[2], 1);
    return t == null ? null : { t, precision: 'month' };
  }
  if ((m = s.match(/^(\d{1,2})[-/.](\d{4})$/))) {
    const t = valid(+m[2], +m[1], 1);
    return t == null ? null : { t, precision: 'month' };
  }
  if ((m = s.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/))) {
    const t = +m[2] > 12 ? valid(+m[3], +m[1], +m[2]) : valid(+m[3], +m[2], +m[1]);
    return t == null ? null : { t, precision: 'day' };
  }
  if ((m = s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/))) {
    const t = valid(+m[1], +m[2], +m[3]);
    return t == null ? null : { t, precision: 'day' };
  }
  const mon = (w: string) => MONTHS.indexOf(w.slice(0, 3)) + 1;
  if ((m = s.match(/^([a-z]{3,9}) (\d{4})$/)) && mon(m[1]) > 0) {
    const t = valid(+m[2], mon(m[1]), 1);
    return t == null ? null : { t, precision: 'month' };
  }
  if ((m = s.match(/^(\d{1,2}) ([a-z]{3,9}) (\d{4})$/)) && mon(m[2]) > 0) {
    const t = valid(+m[3], mon(m[2]), +m[1]);
    return t == null ? null : { t, precision: 'day' };
  }
  if ((m = s.match(/^([a-z]{3,9}) (\d{1,2}) (\d{4})$/)) && mon(m[1]) > 0) {
    const t = valid(+m[3], mon(m[1]), +m[2]);
    return t == null ? null : { t, precision: 'day' };
  }
  return null;
}

// ---------------------------------------------------------------- formatting

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function fmtObsDate(t: number, freq: 'D' | 'M' | 'A'): string {
  const d = new Date(t * 1000);
  const y = d.getUTCFullYear();
  if (freq === 'A') return String(y);
  return freq === 'M' ? `${MON[d.getUTCMonth()]} ${y}` : `${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${y}`;
}

const nf2 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const nf3 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 });

/** Price formatting: 2 decimals (3 below 1), no decimals from 10,000. */
export function fmtPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  const a = Math.abs(v);
  if (a >= 10000) return nf0.format(v);
  if (a < 1) return nf3.format(v);
  return nf2.format(v);
}

/**
 * A value as its series gives it. An annual series is shown with the decimals of the published number (USGS gives 9,000,
 * not 9,000.00, and 4.5, not 4.50); the other series use the usual price format.
 */
export function fmtSeriesValue(m: { freq: string }, v: number | null | undefined): string {
  if (v == null || Number.isNaN(v) || !isAnnualSeries(m)) return fmtPrice(v);
  const dec = Math.min(6, (String(v).split('.')[1] ?? '').length);
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(v);
}

export function fmtPct(p: number): string {
  return `${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p).toFixed(Math.abs(p) >= 100 ? 0 : 1)}%`;
}

// ---------------------------------------------------------------- defaults & opening

export const DEFAULT_SERIES = 'brent-d';

/** Series of a commodity, daily first (the monthly series stays available as an optional second series). */
export function seriesForCommodity(k: string | null | undefined, idx = priceIndex.value): PriceMeta[] {
  if (!k) return [];
  const rank = { D: 0, M: 1, A: 2 };
  return idx.filter((m) => m.k === k && !m.hidden).sort((a, b) => rank[a.freq] - rank[b.freq]);
}

/** A commodity opens on its own series, or on nothing when it has none: never on another commodity's price. */
export function defaultSeriesIds(k: string | null | undefined): string[] {
  if (!k) return [DEFAULT_SERIES];
  const l = seriesForCommodity(k);
  if (!l.length) return [];
  // a series its publisher closed (barley, sorghum) opens with the live series of the same unit that goes on after it, never alone:
  // a closed price must not read as the current one
  const next = l[0].closed ? l.find((m) => !m.closed && m.unit === l[0].unit) : undefined;
  return next ? [l[0].id, next.id] : [l[0].id];
}

/** Commodities whose price series cover only part of what the page describes. */
export const PRICE_COVERAGE_NOTE: Record<string, string> = {
  pgm: 'Platinum monthly (World Bank). Palladium and rhodium: annual average prices only (USGS).',
  // the metals pages of the third commodity package (review GNC3.5): USGS annual averages, each one product of a page that holds more
  chromium: 'Annual average price of chromite ore (USGS, United States salient statistics). No monthly series.',
  'ferro-alloys': 'Annual average prices (USGS, United States salient statistics): ferro-chromium, per pound of chromium content, and 75% ferrosilicon, in US cents per pound of silicon. No free series for the other alloys.',
  'ferrous-scrap': 'Annual average price of No. 1 heavy melting scrap only, one grade of the scrap the tables count (USGS, United States). No monthly series.',
  molybdenum: 'Annual average price of molybdic oxide (57% molybdenum content), in dollars per kilogram: USGS does not say whether the kilogram is of the oxide or of the molybdenum in it (United States). The oxide is a product made from the concentrates the tables count. No price series for the concentrates.',
  graphite: 'Annual average import unit values of three kinds of natural graphite (USGS, United States): flake, lump and chip, and amorphous. No monthly series.',
  // the fertiliser pages hold more products than the Pink Sheet prices (M-022): the note says which ones have a free series
  phosphate: 'Monthly prices (World Bank): phosphate rock, DAP and TSP (triple superphosphate only; the superphosphate tables hold single and triple together, HS 310310). No free series for MAP or phosphoric acid.',
  urea: 'Monthly price (World Bank): urea. Annual average price of ammonia, free on board Gulf Coast, in US dollars per short ton (USGS, United States). No free series for ammonium nitrate, UAN or ammonium sulphate.',
  sulphur: 'Annual average price of elemental sulphur, free on board mine or plant (USGS, United States). No monthly series.',
  potash: 'Monthly price (World Bank): potassium chloride only. No free series for potassium sulphate.',
  // the oilseed pages hold the seed, the oil and the meal (M-023): the price is the oil's
  rapeseed: 'Monthly price (World Bank): rapeseed oil only, the price of the oil and not of the seed. No free series for rapeseed seed or meal.',
  sunflower: 'Monthly price (World Bank): sunflower oil only, the price of the oil and not of the seed. No free series for sunflower seed or meal.',
};

/** "uranium", "rare earths": a catalogue name inside a sentence (acronyms such as LNG keep their capitals). */
export function lowerName(name: string): string {
  return /^[A-Z][a-z]/.test(name) ? name[0].toLowerCase() + name.slice(1) : name;
}

const stamp = (s: string): number => {
  const [y, m = '1', d = '1'] = s.split('-');
  return Date.UTC(Number(y), Number(m) - 1, Number(d)) / 1000;
};

/** Other series of the same commodity whose published range overlaps t0 <= t < t1. */
export function seriesCovering(k: string, t0: number, t1: number, exclude: string[], idx = priceIndex.value): PriceMeta[] {
  return idx.filter((m) => m.k === k && !m.hidden && !exclude.includes(m.id) && stamp(m.start) < t1 && obsEnd(stamp(m.end), m.freq) > t0);
}

/**
 * Does a freight or market event belong on a price chart? An event that names commodities is shown when one of them is
 * charted; an event that names none (a general shipping or market event) is always shown.
 */
export function eventOnChart(e: { commodities?: string[] }, charted: ReadonlySet<string>): boolean {
  return !e.commodities?.length || e.commodities.some((c) => charted.has(c));
}

// ---------------------------------------------------------------- annual values, estimates, late series

/** The run of calendar years [first, last] of twelve identical monthly values that contains `year`, or null (what is observed: the source may publish one price a year there). */
export function annualRun(m: PriceSeriesMeta, year: number): [number, number] | null {
  return m.annual?.find((r) => year >= r[0] && year <= r[1]) ?? null;
}

/** First year whose monthly values differ from month to month when the series opens with years of twelve identical values, else null. */
export function monthlyFrom(m: PriceSeriesMeta): number | null {
  const r = m.annual?.[0];
  return r && String(r[0]) === m.start.slice(0, 4) ? r[1] + 1 : null;
}

/** Is the month containing t one the source itself marks as an estimate? */
export function inEstimate(m: PriceSeriesMeta, t: number): boolean {
  if (!m.est) return false;
  const d = new Date(t * 1000);
  const ym = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
  return m.est.some((r) => ym >= r[0] && ym <= r[1]);
}

/**
 * Late: a daily series more than three weeks behind (the jobs are weekly), a monthly one once the following month is
 * overdue (mid-month, two months on). Same rule as pipeline/prices/build_prices.py check_freshness, which records it.
 */
export function isLate(m: PriceSeriesMeta, now = Date.now()): boolean {
  if (m.closed || m.hidden || m.freq === 'A') return false;
  const [y, mo = '1', d = '1'] = m.end.split('-');
  if (m.freq === 'D') return now - Date.UTC(Number(y), Number(mo) - 1, Number(d)) > 21 * DAY_S * 1000;
  return now > Date.UTC(Number(y), Number(mo) - 1 + 2, 15);
}

// ---------------------------------------------------------------- spreads and ratios

export const SPREAD_PREFIX = 'spread:';

interface SpreadDef {
  id: string;
  name: string;
  k: string;
  kind: 'diff' | 'ratio';
  a: string;
  b: string;
}

/**
 * Differences and ratios of two published series of the same frequency AND unit, so that no conversion factor is
 * needed (crack spreads, which set USD/gal against USD/bbl, and the soybean crush margin, which needs yield factors,
 * are left out). The browser computes them where both legs have a value; a leg's basis changes carry over.
 */
const SPREADS: SpreadDef[] = [
  { id: 'brent-wti-d', name: 'Brent minus WTI, daily spot', k: 'crude-oil', kind: 'diff', a: 'brent-d', b: 'wti-d' },
  { id: 'brent-wti-m', name: 'Brent minus WTI, monthly average', k: 'crude-oil', kind: 'diff', a: 'brent-m', b: 'wti-m' },
  { id: 'brent-dubai-m', name: 'Brent minus Dubai, monthly average', k: 'crude-oil', kind: 'diff', a: 'brent-m', b: 'dubai-m' },
  { id: 'ttf-hh-m', name: 'European gas minus Henry Hub', k: 'natural-gas', kind: 'diff', a: 'ttf-m', b: 'hh-m' },
  { id: 'lng-ttf-m', name: 'Japan LNG minus European gas', k: 'lng', kind: 'diff', a: 'lng-japan-m', b: 'ttf-m' },
  { id: 'coal-aus-zaf-m', name: 'Newcastle minus Richards Bay coal', k: 'thermal-coal', kind: 'diff', a: 'coal-aus-m', b: 'coal-zaf-m' },
  { id: 'gold-silver-m', name: 'Gold to silver ratio', k: 'gold', kind: 'ratio', a: 'gold-m', b: 'silver-m' },
  { id: 'platinum-gold-m', name: 'Platinum to gold ratio', k: 'pgm', kind: 'ratio', a: 'platinum-m', b: 'gold-m' },
  { id: 'hrw-srw-m', name: 'Wheat, HRW minus SRW', k: 'wheat', kind: 'diff', a: 'wheat-hrw-m', b: 'wheat-srw-m' },
  { id: 'wheat-maize-m', name: 'Wheat (HRW) minus maize', k: 'wheat', kind: 'diff', a: 'wheat-hrw-m', b: 'maize-m' },
  { id: 'arabica-robusta-m', name: 'Arabica minus Robusta', k: 'coffee', kind: 'diff', a: 'arabica-m', b: 'robusta-m' },
  { id: 'palm-soyoil-m', name: 'Palm oil minus soybean oil', k: 'palm-oil', kind: 'diff', a: 'palm-oil-m', b: 'soyoil-m' },
  { id: 'urea-maize-m', name: 'Urea to maize ratio', k: 'urea', kind: 'ratio', a: 'urea-m', b: 'maize-m' },
  { id: 'dap-wheat-m', name: 'DAP to wheat (HRW) ratio', k: 'phosphate', kind: 'ratio', a: 'dap-m', b: 'wheat-hrw-m' },
];

function mergeRuns(a: [number, number][] = [], b: [number, number][] = []): [number, number][] | undefined {
  const years = new Set<number>();
  for (const [x, y] of [...a, ...b]) for (let i = x; i <= y; i++) years.add(i);
  const list = [...years].sort((p, q) => p - q);
  const out: [number, number][] = [];
  for (const y of list) {
    if (out.length && out[out.length - 1][1] === y - 1) out[out.length - 1][1] = y;
    else out.push([y, y]);
  }
  return out.length ? out : undefined;
}

/** The spreads whose two legs are in the index with the same frequency and unit. */
export function spreadMetas(idx = priceIndex.value): PriceMeta[] {
  const by = new Map(idx.map((m) => [m.id, m]));
  const out: PriceMeta[] = [];
  for (const d of SPREADS) {
    const a = by.get(d.a);
    const b = by.get(d.b);
    if (!a || !b || a.freq !== b.freq || a.unit !== b.unit) continue;
    const brk = [
      ...(a.breaks ?? []).map((x) => ({ ...x, now: `${a.name}: ${x.now}` })),
      ...(b.breaks ?? []).map((x) => ({ ...x, now: `${b.name}: ${x.now}` })),
    ].sort((p, q) => (p.at < q.at ? -1 : 1));
    out.push({
      id: SPREAD_PREFIX + d.id,
      k: d.k,
      name: d.name,
      unit: d.kind === 'diff' ? a.unit : 'ratio',
      freq: a.freq,
      s: a.s === b.s ? a.s : 'atlas',
      start: a.start > b.start ? a.start : b.start,
      end: a.end < b.end ? a.end : b.end,
      basis: `Arithmetic on two published series, computed here wherever both have a value: ${a.name} ${d.kind === 'diff' ? 'minus' : 'divided by'} ${b.name}. ${a.name}: ${a.basis ?? 'see the series'} ${b.name}: ${b.basis ?? 'see the series'}`,
      breaks: brk.length ? brk : undefined,
      annual: mergeRuns(a.annual, b.annual),
      spread: { a: a.id, b: b.id, kind: d.kind },
    });
  }
  return out;
}

/** The index entry of a series, including the spreads (which exist only in the browser). */
export function findMeta(id: string, idx = priceIndex.value): PriceMeta | undefined {
  return id.startsWith(SPREAD_PREFIX) ? spreadMetas(idx).find((m) => m.id === id) : idx.find((m) => m.id === id);
}

async function loadSpread(id: string): Promise<LoadedSeries> {
  const idx = await loadPriceIndex();
  const meta = spreadMetas(idx).find((m) => m.id === id);
  if (!meta?.spread) throw new Error(`unknown spread ${id}`);
  const [a, b] = await Promise.all([loadSeries(meta.spread.a), loadSeries(meta.spread.b)]);
  const bv = new Map<number, number>();
  for (let i = 0; i < b.x.length; i++) if (b.v[i] != null) bv.set(b.x[i], b.v[i]!);
  const x: number[] = [];
  const v: number[] = [];
  for (let i = 0; i < a.x.length; i++) {
    const av = a.v[i];
    const bb = bv.get(a.x[i]);
    if (av == null || bb == null) continue;
    if (meta.spread.kind === 'ratio' && bb === 0) continue;
    x.push(a.x[i]);
    v.push(meta.spread.kind === 'diff' ? av - bb : av / bb);
  }
  return { meta, x, v, gaps: meta.freq === 'D' ? gapsOf(x, v) : undefined };
}

let nonce = 0;
/** Open the price drawer. Other components call e.g. openPrices({ commodity: 'copper' }). */
export function openPrices(opts: { commodity?: string | null; series?: string[]; date?: string } = {}) {
  historyOpen.value = false;
  priceDrawer.value = { ...opts, nonce: ++nonce };
}
export function closePrices() {
  priceDrawer.value = null;
}
export function togglePrices() {
  if (priceDrawer.value) closePrices();
  else openPrices({ commodity: commodity.value });
}
export function toggleHistory() {
  const next = !historyOpen.value;
  if (next) priceDrawer.value = null;
  historyOpen.value = next;
}
