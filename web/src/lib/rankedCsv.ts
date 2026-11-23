/** CSV of a ranked country table (the `RankedBars` component): every row of the table, not only the rows on screen. */
import type { Ranked } from '../types';
import { commodityMeta, countryName } from './data';
import { atlasKind, sig2 } from './format';
import { ATLAS_LICENCE, downloadCsv, licenceOf, slug, sourceName, toCsv } from './csv';
import { selection } from './store';

const HEAD = ['commodity', 'table', 'rank', 'country_iso3', 'country', 'year', 'value', 'unit', 'share_of_world_pct', 'estimate', 'note', 'source', 'licence'];

/** The title of the section a table sits in ("Top exporters"), read from the page when the button is pressed: RankedBars is not given it. */
export function tableTitle(from: Element | null): string {
  // the section's own words: the title bar may also hold a year or a note on its right
  return from?.closest('.section')?.querySelector('.section-title > span')?.textContent?.trim() ?? '';
}

/** The commodity of the open page, "" when the page is not a commodity's. */
function pageCommodity(): string {
  const s = selection.peek();
  return s?.kind === 'commodity' ? (commodityMeta(s.id)?.name ?? s.id) : '';
}

export function rankedCsv(data: Ranked, title: string): { file: string; text: string } {
  const kind = atlasKind(data);
  const world = data.world;
  const commodity = pageCommodity();
  const share = (v: number) => (world ? ((v / world) * 100).toFixed(2) : '');
  const out: (string | number | null)[][] = [];
  const line = (rank: number | '', iso: string, name: string, v: number, est: boolean, note: string) => {
    const own = est || kind === 'est';
    // a row the atlas estimated inside another source's table: say so in both columns, and give the atlas licence too
    const rowEst = est && kind !== 'est';
    out.push([
      commodity, title, rank, iso, name, data.y, own ? sig2(v) : v, data.u, share(v), own ? 'Atlas estimate' : '', note,
      sourceName(data.s, rowEst ? 'row is an Atlas estimate' : undefined),
      rowEst ? `${licenceOf(data.s)}; the estimate: ${ATLAS_LICENCE}` : licenceOf(data.s),
    ]);
  };
  data.rows.forEach((r, i) => line(i + 1, r.c, r.name ?? countryName(r.c), r.v, !!r.est, r.n ?? ''));
  const other = data.other && data.other > 0 ? data.other : 0;
  if (other) line('', '', 'Other countries (as published)', other, false, "the source's own line");
  // what the world total holds beyond the rows and that line, when it is 0.05% of the world or more (as the table prints it)
  const gap = world ? world - data.rows.reduce((a, r) => a + r.v, 0) - other : 0;
  if (world && gap > world * 5e-4) line('', '', 'Not given by country', gap, false, 'the world total minus the countries listed');
  if (world) line('', 'WLD', 'World', world, false, 'sum the shares are of');
  const name = [commodity, title || 'table', data.y].filter((x) => x !== '').join(' ');
  return { file: `commodity-flows-atlas-${slug(name)}.csv`, text: toCsv(HEAD, out) };
}

export function downloadRanked(data: Ranked, from: Element | null) {
  const { file, text } = rankedCsv(data, tableTitle(from));
  downloadCsv(file, text);
}
