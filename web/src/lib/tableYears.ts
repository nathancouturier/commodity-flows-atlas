/**
 * The commodity tables in another year: the series by country and year (data/commodities/history, HistTable) turned
 * into the ranking of one year, the trend of a row and the largest changes from one year to the next.
 */
import type { HistTable, Ranked } from '../types';

/** How a year of the series is printed: the year, or the marketing year of USDA PSD ("2010/11"). */
export function yearLabel(h: HistTable, i: number): string {
  return h.labels?.[i] ?? String(h.years[i]);
}

/**
 * The table to show for the History year `yr`. With no year, or a year the series does not hold, the latest table (and,
 * for a year it does not hold, the words to put next to the heading); otherwise the ranking of that year with the shares
 * on that year's world total. `i` is the year of the series shown (for the dot on the trend lines).
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
  const rows = Object.entries(h.c)
    .filter(([, v]) => v[at] != null && (v[at] as number) > 0)
    .map(([c, v]) => {
      const est = !!h.est?.[c]?.includes(at);
      const src = !!h.srcEst?.[c]?.includes(at);
      return { c, v: v[at] as number, ...(est ? { est } : {}), ...(src ? { n: 'estimated by the source' } : {}) };
    })
    .sort((a, b) => b.v - a.v);
  const label = yearLabel(h, at);
  const n = [
    `ranking of ${label} from the series by year, same rules as the latest table (${base.y}); its notes are for ${base.y}`,
    h.yl?.[at] ? `${h.yl[at]} figures, as the source labels them` : null,
    h.worldEst?.includes(at) ? 'a tenth or more of the world tonnage is an Atlas estimate from the declared value' : null,
  ].filter(Boolean).join('; ');
  const other = h.other?.[at];
  const table: Ranked = {
    y: label,
    s: h.s,
    u: h.u,
    world: h.world[at],
    rows,
    n,
    ...(other ? { other } : {}),
    ...(h.pub && h.pub[at] !== h.world[at] ? { worldPublished: h.pub[at] } : {}),
    ...(base.basis ? { basis: base.basis } : {}),
    ...(base.norank ? { norank: base.norank } : {}),
  };
  return { table, i: at, note: null, past: true };
}

export interface Change {
  c: string;
  /** change in the unit of the table, this year minus the year before */
  d: number;
  /** relative change, null when the year before has no figure */
  p: number | null;
  /** an Atlas estimate on either side */
  est: boolean;
}

/**
 * The `n` largest increases and decreases between year `i - 1` and year `i` of a series. A country with no figure on
 * one side counts as 0 there (the source records no figure for it that year).
 */
export function largestChanges(h: HistTable, i: number, n = 5): { up: Change[]; down: Change[] } | null {
  if (i < 1 || i >= h.years.length) return null;
  const all: Change[] = [];
  for (const [c, v] of Object.entries(h.c)) {
    const a = v[i - 1];
    const b = v[i];
    if (a == null && b == null) continue;
    const d = (b ?? 0) - (a ?? 0);
    if (!d) continue;
    const est = !!h.est?.[c]?.some((k) => k === i || k === i - 1);
    all.push({ c, d, p: a ? d / a : null, est });
  }
  const up = all.filter((x) => x.d > 0).sort((x, y) => y.d - x.d).slice(0, n);
  const down = all.filter((x) => x.d < 0).sort((x, y) => x.d - y.d).slice(0, n);
  return { up, down };
}
