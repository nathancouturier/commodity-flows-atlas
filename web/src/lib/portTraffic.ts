/**
 * The computations of the "Weekly port traffic" block of a port page, from one file of data/freight/port-traffic: the weeks
 * and their dates, the sums of the last 52 weeks and of the 52 before, the measure the block opens on, the way a tonnage is
 * written, the stretches of the chart that have no data and the rows of the CSV file. Tonnes are PortWatch's estimates, in
 * thousand tonnes (`u` of the file); nothing here adds, compares or reconciles them with another figure of the atlas.
 *
 * Type import only: scripts/port-traffic.test.mjs runs this file as it is, against every file of the folder.
 */
import type { PortTraffic } from '../types';

export type Measure = 'calls' | 'exports' | 'imports';
export const MEASURES: readonly Measure[] = ['calls', 'exports', 'imports'];
export type ShipType = 'tanker' | 'dry' | 'container' | 'other';
/** The four ship types of the files, in the order of the chart, with the words the chokepoint chart uses. */
export const SHIP_TYPES: readonly (readonly [ShipType, string])[] = [
  ['tanker', 'Tanker'],
  ['dry', 'Dry bulk'],
  ['container', 'Container'],
  ['other', 'Other'],
];
/** The weeks of a year of the atlas's sums: the last 52 weeks and the 52 before. */
export const YEAR_WEEKS = 52;

const DAY_MS = 86_400_000;
const WEEK_S = 7 * 86_400;

/** The number of weeks of a file. */
export const weekCount = (doc: PortTraffic): number => doc.calls.tanker.length;

/** The ISO day of the Monday that starts week `i` (0 is `start`). */
export const weekStart = (doc: PortTraffic, i: number): string => new Date(Date.parse(`${doc.start}T00:00:00Z`) + 7 * i * DAY_MS).toISOString().slice(0, 10);

/** The ISO day of the Sunday that ends week `i`: the date the weeks of a sum run to. */
export const weekEnd = (doc: PortTraffic, i: number): string => new Date(Date.parse(`${doc.start}T00:00:00Z`) + (7 * i + 6) * DAY_MS).toISOString().slice(0, 10);

/** The x values of the chart (seconds, UTC): the Monday of each week. */
export function weekTimes(doc: PortTraffic): number[] {
  const t0 = Date.parse(`${doc.start}T00:00:00Z`) / 1000;
  return Array.from({ length: weekCount(doc) }, (_, i) => t0 + i * WEEK_S);
}

/** True when PortWatch did not give week `i` whole: the file holds null in it, for every ship type and every measure. */
export const isHole = (doc: PortTraffic, i: number): boolean => doc.calls.tanker[i] === null;

/** The sum of the four ship types of one measure over the weeks from `from` up to, not including, `to`; the weeks that have a value are counted. */
export interface WeekSum {
  value: number;
  weeks: number;
  span: number;
}
export function sumWeeks(doc: PortTraffic, measure: Measure, from: number, to: number): WeekSum {
  let value = 0;
  let weeks = 0;
  for (let i = from; i < to; i++) {
    let has = false;
    for (const [t] of SHIP_TYPES) {
      const v = doc[measure][t][i];
      if (v != null) {
        value += v;
        has = true;
      }
    }
    if (has) weeks++;
  }
  return { value, weeks, span: to - from };
}

/** A stretch of weeks: the Sunday it ends on and the three sums. */
export interface Stretch {
  end: string;
  calls: WeekSum;
  exports: WeekSum;
  imports: WeekSum;
}
const stretch = (doc: PortTraffic, from: number, to: number): Stretch => ({
  end: weekEnd(doc, to - 1),
  calls: sumWeeks(doc, 'calls', from, to),
  exports: sumWeeks(doc, 'exports', from, to),
  imports: sumWeeks(doc, 'imports', from, to),
});

/**
 * The last 52 weeks of the file (all of them when it has fewer) and the 52 before. The earlier stretch exists only when the file
 * holds a whole second year: a shorter earlier stretch would not be comparable.
 */
export function rolling52(doc: PortTraffic): { last: Stretch; before: Stretch | null } {
  const n = weekCount(doc);
  return {
    last: stretch(doc, Math.max(0, n - YEAR_WEEKS), n),
    before: n >= 2 * YEAR_WEEKS ? stretch(doc, n - 2 * YEAR_WEEKS, n - YEAR_WEEKS) : null,
  };
}

/** The measure the block opens on: the exports of the last 52 weeks when they are at least the imports, else the imports; the calls when both are nil. */
export function defaultMeasure(doc: PortTraffic): Measure {
  const { last } = rolling52(doc);
  if (last.exports.value === 0 && last.imports.value === 0) return 'calls';
  return last.exports.value >= last.imports.value ? 'exports' : 'imports';
}

const nf3 = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 3 });

/** A weekly sum of tonnes (thousand tonnes) to three significant digits: "512 Mt", "7.09 Mt", "310 kt", "4.1 kt". */
export function fmtTonnes(kt: number): string {
  const r = Number(kt.toPrecision(3));
  return r >= 1000 ? `${nf3.format(kt / 1000)} Mt` : `${nf3.format(r)} kt`;
}

/** A count of calls with thousands separators. */
export const fmtCalls = (n: number): string => n.toLocaleString('en-US');

/** The figure of a sum in the table: "—" when no week of the stretch has a value. */
export function sumText(measure: Measure, s: WeekSum): string {
  if (!s.weeks) return '—';
  return measure === 'calls' ? fmtCalls(s.value) : fmtTonnes(s.value);
}

/**
 * The stretches of the chart (seconds, [last point before, first point after]) that a week without data covers, so that the chart
 * leaves a gap there instead of drawing a zero. A hole at an end of the file is bounded by the week outside it.
 */
export function holeGaps(doc: PortTraffic): [number, number][] {
  const x = weekTimes(doc);
  const out: [number, number][] = [];
  for (let i = 0; i < x.length; i++) {
    if (!isHole(doc, i)) continue;
    let j = i;
    while (j + 1 < x.length && isHole(doc, j + 1)) j++;
    out.push([i > 0 ? x[i - 1] : x[i] - WEEK_S, j + 1 < x.length ? x[j + 1] : x[j] + WEEK_S]);
    i = j;
  }
  return out;
}

/** What each measure is called in the CSV file, and its unit. */
export function measureCsv(doc: PortTraffic, m: Measure): { what: string; unit: string } {
  return m === 'calls'
    ? { what: 'port calls', unit: 'calls/week' }
    : { what: m === 'exports' ? 'estimated export tonnes' : 'estimated import tonnes', unit: `${doc.u}/week` };
}

/**
 * The rows of the CSV file (week_start, ship_type, measure, value, unit): every measure, every week, the four ship types and their
 * total (the sum of the four, null for a week without data). The file's own values are never changed.
 */
export function csvRows(doc: PortTraffic): [string, string, string, number | null, string][] {
  const rows: [string, string, string, number | null, string][] = [];
  const n = weekCount(doc);
  const scale = 10 ** doc.dp;
  for (const m of MEASURES) {
    const { what, unit } = measureCsv(doc, m);
    for (let i = 0; i < n; i++) {
      const week = weekStart(doc, i);
      for (const [t, label] of SHIP_TYPES) rows.push([week, label, what, doc[m][t][i], unit]);
      const total = isHole(doc, i) ? null : Math.round(sumWeeks(doc, m, i, i + 1).value * scale) / scale;
      rows.push([week, 'Total', what, total, unit]);
    }
  }
  return rows;
}

/** True when two names are the same name: case and surrounding spaces do not tell them apart. */
export const sameName = (a: string, b: string): boolean => a.trim().toLowerCase() === b.trim().toLowerCase();
