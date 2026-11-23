/** CSV of the price series the drawer shows, over the period it shows: one row per observation. */
import { findMeta, inEstimate, type LoadedSeries } from './prices';
import { ATLAS_LICENCE, downloadCsv, licenceOf, slug, sourceName, toCsv } from './csv';

const FREQ = { D: 'daily', M: 'monthly', A: 'annual' } as const;

/** Date of an observation as the series gives it: a day, a month or a year. */
function obsDate(t: number, freq: 'D' | 'M' | 'A'): string {
  const iso = new Date(t * 1000).toISOString();
  return freq === 'D' ? iso.slice(0, 10) : freq === 'M' ? iso.slice(0, 7) : iso.slice(0, 4);
}

/** Source and licence of a series: a spread or ratio is computed here from two published series, so it names both. */
function provenance(m: LoadedSeries['meta']): { source: string; licence: string } {
  if (!m.spread) return { source: sourceName(m.s), licence: licenceOf(m.s) };
  const legs = [m.spread.a, m.spread.b].map((id) => findMeta(id));
  const srcs = [...new Set(legs.map((l) => l?.s ?? m.s))];
  return {
    source: `${srcs.map((s) => sourceName(s)).join(' and ')}; ${m.spread.kind === 'diff' ? 'difference' : 'ratio'} computed by the Atlas`,
    licence: `${srcs.map((s) => licenceOf(s)).join('; ')}; the computation: ${ATLAS_LICENCE}`,
  };
}

export function pricesCsv(data: LoadedSeries[], from: number, to: number): string {
  const rows: (string | number | null)[][] = [];
  for (const d of data) {
    const { source, licence } = provenance(d.meta);
    for (let i = 0; i < d.x.length; i++) {
      const t = d.x[i];
      const v = d.v[i];
      if (v == null || t < from || t > to) continue;
      rows.push([d.meta.id, d.meta.name, obsDate(t, d.meta.freq), v, d.meta.unit, FREQ[d.meta.freq], inEstimate(d.meta, t) ? 'source estimate' : '', source, licence]);
    }
  }
  return toCsv(['series_id', 'series', 'date', 'value', 'unit', 'frequency', 'estimate', 'source', 'licence'], rows);
}

/** Save the series over [from, to] (seconds). */
export function downloadPrices(data: LoadedSeries[], from: number, to: number) {
  const first = obsDate(from, 'D');
  const last = obsDate(to, 'D');
  downloadCsv(`commodity-flows-atlas-prices-${slug(data.map((d) => d.meta.id).join('-'))}-${first}-to-${last}.csv`, pricesCsv(data, from, to));
}
