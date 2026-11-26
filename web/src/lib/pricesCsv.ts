/** CSV of the price series the drawer shows, over the period it shows: one row per observation. */
import { findMeta, inEstimate, type LoadedSeries } from './prices';
import { ATLAS_LICENCE, downloadCsv, licenceColumn, licenceTexts, slug, sourceName, termsNotConfirmed, toCsv } from './csv';
import { splitOffered } from './priceFile';

const FREQ = { D: 'daily', M: 'monthly', A: 'annual' } as const;

/** Date of an observation as the series gives it: a day, a month or a year. */
function obsDate(t: number, freq: 'D' | 'M' | 'A'): string {
  const iso = new Date(t * 1000).toISOString();
  return freq === 'D' ? iso.slice(0, 10) : freq === 'M' ? iso.slice(0, 7) : iso.slice(0, 4);
}

/** The registry sources of a series: its own, and for a spread or ratio the two it is computed from. */
function sourcesOf(m: LoadedSeries['meta']): string[] {
  if (!m.spread) return [m.s];
  return [...new Set([m.spread.a, m.spread.b].map((id) => findMeta(id)?.s ?? m.s))];
}

/** Every registry source the selection rests on: a CSV is offered only when each of them states a permission to reuse its data. */
export const priceSources = (data: LoadedSeries[]): string[] => [...new Set(data.flatMap((d) => sourcesOf(d.meta)))];

/** The series of the chart that may go into a file (`offered`) and those whose source states no permission to reuse its data (`withheld`: the daily EIA spot prices). */
export const offeredPrices = (data: LoadedSeries[]) => splitOffered(data, (d) => sourcesOf(d.meta), (id) => termsNotConfirmed([id]).length === 0);

/** Source and licence of a series: a spread or ratio is computed here from two published series, so it names both. */
function provenance(m: LoadedSeries['meta']): { source: string; licence: [string, string] } {
  if (!m.spread) return { source: sourceName(m.s), licence: licenceTexts([m.s]) };
  const srcs = sourcesOf(m);
  return {
    source: `${srcs.map((s) => sourceName(s)).join(' and ')}; ${m.spread.kind === 'diff' ? 'difference' : 'ratio'} computed by the Atlas`,
    licence: licenceTexts(srcs, `; the computation: ${ATLAS_LICENCE}`),
  };
}

export function pricesCsv(data: LoadedSeries[], from: number, to: number): string {
  const rows: (string | number | null)[][] = [];
  const lic = licenceColumn();
  // never a row of a series whose source states no permission, whatever the caller gives
  for (const d of offeredPrices(data).offered) {
    const { source, licence } = provenance(d.meta);
    for (let i = 0; i < d.x.length; i++) {
      const t = d.x[i];
      const v = d.v[i];
      if (v == null || t < from || t > to) continue;
      rows.push([d.meta.id, d.meta.name, obsDate(t, d.meta.freq), v, d.meta.unit, FREQ[d.meta.freq], inEstimate(d.meta, t) ? 'source estimate' : '', source, lic(...licence)]);
    }
  }
  return toCsv(['series_id', 'series', 'date', 'value', 'unit', 'frequency', 'estimate', 'source', 'licence'], rows);
}

/** Save the series over [from, to] (seconds). */
export function downloadPrices(data: LoadedSeries[], from: number, to: number) {
  const first = obsDate(from, 'D');
  const last = obsDate(to, 'D');
  const { offered } = offeredPrices(data);
  if (!offered.length) return;
  downloadCsv(`commodity-flows-atlas-prices-${slug(offered.map((d) => d.meta.id).join('-'))}-${first}-to-${last}.csv`, pricesCsv(offered, from, to));
}
