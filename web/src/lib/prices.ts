/**
 * Price series access: lazy loading with a cache, packed -> uPlot arrays (x in seconds),
 * merging of several series on a common time axis, nearest-observation lookup and
 * free-text date parsing for the price explorer.
 */
import { signal } from '@preact/signals';
import type { PriceSeries, PriceSeriesMeta } from '../types';
import { load } from './data';
import { historyOpen, priceDrawer, commodity } from './store';

export type PriceMeta = PriceSeriesMeta & { note?: string };

export interface LoadedSeries {
  meta: PriceMeta;
  /** seconds since epoch (UTC), ascending */
  x: number[];
  v: (number | null)[];
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

const seriesCache = new Map<string, Promise<LoadedSeries>>();

export function loadSeries(id: string): Promise<LoadedSeries> {
  let p = seriesCache.get(id);
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
  } else {
    const [sy, sm] = (raw.start ?? meta.start).split('-').map(Number);
    for (let i = 0; i < n; i++) x[i] = Date.UTC(sy, sm - 1 + i, 1) / 1000;
  }
  return { meta, x, v: raw.v };
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

/** Index of the non-null observation closest to time t, or -1. */
export function nearestIndex(s: { x: number[]; v: (number | null)[] }, t: number): number {
  const { x, v } = s;
  if (!x.length) return -1;
  let lo = 0;
  let hi = x.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (x[mid] < t) lo = mid + 1;
    else hi = mid;
  }
  let best = -1;
  let bd = Infinity;
  for (let k = lo - 1; k >= 0 && k >= lo - 40; k--) {
    if (v[k] != null) {
      best = k;
      bd = Math.abs(x[k] - t);
      break;
    }
  }
  for (let k = lo; k < x.length && k <= lo + 40; k++) {
    if (v[k] != null) {
      if (Math.abs(x[k] - t) < bd) best = k;
      break;
    }
  }
  return best;
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

export type Precision = 'year' | 'month' | 'day';
export interface ParsedDate {
  /** seconds, start of the named period */
  t: number;
  precision: Precision;
}

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];

/** Accepts "1986", "2008-03", "2008/03", "2008-03-14", "Mar 2008", "March 2008", "14 Mar 2008". */
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
  if ((m = s.match(/^(\d{4})[-/.](\d{1,2})$/))) {
    const t = valid(+m[1], +m[2], 1);
    return t == null ? null : { t, precision: 'month' };
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

export function fmtObsDate(t: number, freq: 'D' | 'M'): string {
  const d = new Date(t * 1000);
  const y = d.getUTCFullYear();
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

export function fmtPct(p: number): string {
  return `${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p).toFixed(Math.abs(p) >= 100 ? 0 : 1)}%`;
}

// ---------------------------------------------------------------- defaults & opening

export const DEFAULT_SERIES = 'brent-m';

/** Default series ids for a commodity: monthly Pink Sheet series first (longest history). */
export function seriesForCommodity(k: string | null | undefined, idx = priceIndex.value): PriceMeta[] {
  if (!k) return [];
  return idx.filter((m) => m.k === k).sort((a, b) => (a.freq === b.freq ? 0 : a.freq === 'M' ? -1 : 1));
}

export function defaultSeriesIds(k: string | null | undefined): string[] {
  const l = seriesForCommodity(k);
  return l.length ? [l[0].id] : [DEFAULT_SERIES];
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
