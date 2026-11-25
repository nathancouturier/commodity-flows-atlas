/**
 * The commodity tables in another year: the series by country and year (data/commodities/history, HistTable) turned
 * into the ranking of one year, the trend of a row and the largest changes from one year to the next.
 */
import type { HistTable, Ranked } from '../types';
import { countryName } from './data';
import { atlasKind, fmt } from './format';

/** How a year of the series is printed: the year, or the marketing year of USDA PSD ("2010/11"). */
export function yearLabel(h: HistTable, i: number): string {
  return h.labels?.[i] ?? String(h.years[i]);
}

/** The name of a row in year `i`: the source's entity of that year when it is not the usual one ("EU-25"). */
export function rowName(h: HistTable | undefined, c: string, i: number | null): string {
  return (h && i != null ? h.cl?.[c]?.[i] : null) ?? countryName(c);
}

/** The values a trend line draws for a row (`c`) or for the world (no `c`): a value out of line is not drawn, and the line breaks where the row's entity changes. */
export function trendOf(h: HistTable, c?: string): { vals: (number | null)[]; breaks: number[] } {
  const raw = c ? h.c[c] : h.world;
  const out = c ? h.out?.[c] : h.worldOut;
  return { vals: (raw ?? []).map((v, i) => (out?.includes(i) ? null : v)), breaks: c ? (h.brk?.[c] ?? []) : [] };
}

/** The countries whose figure of year `i` is out of line with the years around it (not ranked that year). */
function outAt(h: HistTable, i: number): string[] {
  return Object.entries(h.out ?? {}).filter(([, ix]) => ix.includes(i)).map(([c]) => c);
}

/** "43.1 Mt in 2020; none in 2022": the figures of the years around an out-of-line one. */
function around(h: HistTable, c: string, i: number): string {
  return [i - 1, i + 1]
    .filter((j) => j >= 0 && j < h.years.length)
    .map((j) => (h.c[c][j] == null ? `no figure in ${yearLabel(h, j)}` : `${fmt(h.c[c][j])} ${h.u} in ${yearLabel(h, j)}`))
    .join(', ');
}

/**
 * The table to show for the History year `yr`. With no year, or a year the series does not hold, the latest table (and,
 * for a year it does not hold, the words to put next to the heading); otherwise the ranking of that year with the shares
 * on that year's world total. `i` is the year of the series shown (for the dot on the trend lines). The past table keeps
 * the caveat of the table (a scope caveat holds for every year), but one written for some years only (`caveatYears`)
 * gives way to `caveatPast` or `caveatShort` in the others.
 */
export function tableAt(base: Ranked, h: HistTable | undefined, yr: number | null): { table: Ranked; i: number | null; note: string | null; past: boolean } {
  const last = h ? h.years.length - 1 : null;
  if (yr == null) return { table: base, i: last, note: null, past: false };
  const at = h ? h.years.indexOf(yr) : -1;
  if (!h || at < 0) {
    const same = String(base.y) === String(yr) || String(base.y).startsWith(`${yr}/`);
    return { table: base, i: last, note: same ? null : `${base.y}: no series for ${yr}`, past: false };
  }
  if (at === last) return { table: base, i: at, note: null, past: false };
  // a value out of line with the years around it is kept in the file, not ranked: the shares are of the world without it
  const odd = outAt(h, at);
  const rows = Object.entries(h.c)
    .filter(([c, v]) => v[at] != null && (v[at] as number) > 0 && !odd.includes(c))
    .map(([c, v]) => {
      const est = !!h.est?.[c]?.includes(at);
      const src = !!h.srcEst?.[c]?.includes(at);
      const conv = !!h.conv?.[c]?.includes(at);
      const name = h.cl?.[c]?.[at];
      return { c, v: v[at] as number, ...(est ? { est } : {}), ...(conv ? { conv } : {}), ...(src ? { n: 'estimated by the source' } : {}), ...(name ? { name } : {}) };
    })
    .sort((a, b) => b.v - a.v);
  const label = yearLabel(h, at);
  const oddV = odd.reduce((a, c) => a + (h.c[c][at] as number), 0);
  const world = oddV ? h.world[at] - oddV : h.world[at];
  // an Atlas-estimate table keeps its method, as written for the latest table
  const estTable = atlasKind(base) === 'est';
  const n = [
    ...odd.map(
      (c) =>
        `the source's figure for ${countryName(c)} in ${label}, ${fmt(h.c[c][at])} ${h.u}, is far out of line with the years around it (${around(h, c, at)}): ` +
        `it is not ranked, and the shares are of the ${base.shareOf ? 'total' : 'world total'} without it, ${fmt(world)} ${h.u} (the source's total, ${fmt(h.world[at])} ${h.u}, includes it)`,
    ),
    `ranking of ${label} from the series by year, with the rules of the latest table (${base.y})`,
    estTable && base.n ? `the method of the estimate, as written for ${base.y}: ${base.n}` : null,
    h.yl?.[at] ? `${label} figures ${h.yl[at]}` : null,
    h.worldEst?.includes(at) ? 'a tenth or more of the world tonnage is an Atlas estimate from the declared value' : null,
  ].filter(Boolean).join('; ');
  const other = h.other?.[at];
  const holds = !base.caveatYears || base.caveatYears.includes(h.years[at]);
  const caveat = base.caveat ? (holds ? base.caveat : (base.caveatPast ?? base.caveatShort)) : undefined;
  const table: Ranked = {
    y: label,
    ...(h.kinds?.[at] ? { yk: h.kinds[at] as 'forecast' | 'estimate' } : {}),
    s: h.s,
    u: h.u,
    world,
    rows,
    n,
    ...(other ? { other } : {}),
    ...(h.pub && h.pub[at] !== h.world[at] ? { worldPublished: h.pub[at] } : {}),
    ...(base.basis ? { basis: base.basis } : {}),
    ...(base.norank ? { norank: base.norank } : {}),
    ...(caveat ? { caveat } : {}),
    ...(estTable ? { est: true } : {}),
    ...(rows.some((r) => r.conv) && base.conv ? { conv: base.conv } : {}),
    ...(h.convWorld?.includes(at) ? { convWorld: true } : {}),
  };
  return { table, i: at, note: null, past: true };
}

export interface Change {
  c: string;
  /** change in the unit of the table, this year minus the year before */
  d: number;
  /** relative change; null when one side has no figure or the year before is under SMALL_BASE of the world */
  p: number | null;
  /** why there is no relative change: no figure in the year before or in the year, or a very small figure the year before */
  why: 'none-before' | 'none-after' | 'small' | null;
  /** an Atlas estimate on either side */
  est: boolean;
}

/** A figure under this share of the world total is too small for a percentage change to mean anything. */
export const SMALL_BASE = 0.001;

/**
 * The `n` largest increases and decreases between year `i - 1` and year `i` of a series. A country with no figure on
 * one side counts as 0 there (the source gives none for it that year, or it is under the source's threshold or rounds to
 * 0), with no percentage. A figure out of line with the years around it, or a break of the row (a country that split,
 * a change of membership), gives no change.
 */
export function largestChanges(h: HistTable, i: number, n = 5): { up: Change[]; down: Change[] } | null {
  if (i < 1 || i >= h.years.length) return null;
  const all: Change[] = [];
  for (const [c, v] of Object.entries(h.c)) {
    const a = v[i - 1];
    const b = v[i];
    if (a == null && b == null) continue;
    if (h.out?.[c]?.some((k) => k === i || k === i - 1) || h.brk?.[c]?.includes(i)) continue;
    const d = (b ?? 0) - (a ?? 0);
    if (!d) continue;
    const est = !!h.est?.[c]?.some((k) => k === i || k === i - 1);
    const why = a == null ? 'none-before' : b == null ? 'none-after' : a < SMALL_BASE * h.world[i - 1] ? 'small' : null;
    all.push({ c, d, p: why ? null : d / (a as number), why, est });
  }
  const up = all.filter((x) => x.d > 0).sort((x, y) => y.d - x.d).slice(0, n);
  const down = all.filter((x) => x.d < 0).sort((x, y) => x.d - y.d).slice(0, n);
  return { up, down };
}
