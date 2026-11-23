/** CSV of a ranked country table (the `RankedBars` component): every row of the table, not only the rows on screen. */
import type { Ranked } from '../types';
import { commodityMeta, countryName, sourceLabel } from './data';
import { atlasKind, sig2 } from './format';
import { ATLAS_LICENCE, downloadCsv, licenceColumn, licenceOf, licenceTexts, publisherOf, slug, sourceName, toCsv } from './csv';
import { licenceShort } from './licence';
import { selection } from './store';

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

/** The registry sources an Atlas estimate or conversion is computed from, named in the table's note ("CEPII BACI 2024", "USGS MCS 2026"). */
const INPUTS: [RegExp, string][] = [
  [/CEPII BACI|\bBACI\b/, 'baci'],
  [/World Bank Pink Sheet|\bPink Sheet\b/, 'wb-pink'],
  [/\bUSGS\b/, 'usgs-mcs'],
  [/\bUSDA\b/, 'usda-psd'],
  [/\bFAOSTAT\b/, 'faostat'],
];
const inputsOf = (note: string): string[] => INPUTS.filter(([re]) => re.test(note)).map(([, id]) => id);

/** The registry sources a CSV of this table rests on: the table's own, and for an Atlas estimate or conversion the sources it is computed from. */
export function rankedSources(data: Ranked): string[] {
  return [...new Set([data.s, ...(atlasKind(data) ? inputsOf(data.n ?? '') : [])])];
}

/** The note of an Atlas estimate or conversion, as the page prints it, without the caveat the page shows apart. */
function methodOf(data: Ranked): string {
  let n = data.n ?? '';
  if (data.caveat) n = n.replace(` · ${data.caveat}`, '').replace(data.caveat, '');
  return n.replace(/\s*·\s*$/, '').trim();
}

export function rankedCsv(data: Ranked, title: string): { file: string; text: string } {
  const kind = atlasKind(data);
  const eu = data.scope === 'EU';
  const world = data.world;
  const commodity = pageCommodity();
  // the table is shares of the world, or (the EU member states) of the total of the 27: the column and the total row say which
  const head = ['commodity', 'table', 'rank', 'country_code', 'country', 'year', 'value', 'unit', eu ? 'share_of_eu_total_pct' : 'share_of_world_pct', 'estimate', 'note', 'source', 'licence'];
  const share = (v: number) => (world ? ((v / world) * 100).toFixed(2) : '');
  const method = kind ? methodOf(data) : '';
  const inputs = kind ? inputsOf(data.n ?? '') : [];
  const lic = licenceColumn();
  // what the page says of the year: the forecast of a marketing year in progress, the estimate of the one before
  const year = data.yk ? `${data.y} ${data.yk}` : data.y;
  const out: (string | number | null)[][] = [];
  const line = (rank: number | '', iso: string, name: string, v: number, est: boolean, note: string, conv = false) => {
    const own = est || kind === 'est';
    // a row the atlas estimated inside another source's table: say so in both columns, and give the atlas licence too
    const rowEst = est && kind !== 'est';
    // a row the atlas converted inside another source's table (the United States in the EIA LPG table)
    const rowConv = conv && !est && !kind;
    // an Atlas estimate or conversion carries its method and inputs on every row, as the page carries them in the table note
    const text = [note, method].filter(Boolean).join(' | ');
    const [full, short] = kind
      ? [
          `${ATLAS_LICENCE}; computed from ${inputs.map((i) => `${publisherOf(i)} (${licenceShort(licenceOf(i))})`).join(' and ') || 'the sources named in the note'}`,
          ATLAS_LICENCE,
        ]
      : rowEst
        ? licenceTexts([data.s], `; the estimate: ${ATLAS_LICENCE}`)
        : rowConv
          ? licenceTexts([data.s], `; the conversion: ${ATLAS_LICENCE}`)
          : licenceTexts([data.s]);
    out.push([
      commodity, title, rank, iso, name, year, own ? sig2(v) : v, data.u, share(v), own ? 'Atlas estimate' : kind === 'conv' || rowConv ? 'Atlas conversion' : '', text,
      kind
        ? sourceName('atlas', `${kind === 'conv' ? 'converted' : 'computed'} from ${inputs.map(sourceLabel).join(' and ') || 'the sources named in the note'}`)
        : sourceName(data.s, rowEst ? 'row is an Atlas estimate' : rowConv ? 'row is an Atlas conversion' : undefined),
      lic(full, short),
    ]);
  };
  data.rows.forEach((r, i) => line(i + 1, r.c, r.name ?? countryName(r.c), r.v, !!r.est, r.n ?? '', !!r.conv));
  const other = data.other && data.other > 0 ? data.other : 0;
  if (other) line('', '', 'Other countries (as published)', other, false, "the source's own line");
  // what the world total holds beyond the rows and that line, when it is 0.05% of the world or more (as the table prints it)
  const gap = world ? world - data.rows.reduce((a, r) => a + r.v, 0) - other : 0;
  if (world && gap > world * 5e-4) line('', '', 'Not given by country', gap, false, eu ? 'the EU total minus the member states listed' : 'the world total minus the countries listed');
  if (world) line('', eu ? 'EU27' : 'WLD', eu ? 'EU total' : 'World', world, false, eu ? 'sum of the 27 member states, the base of the shares' : 'sum the shares are of', !!data.convWorld);
  // the title of a table often ends with its year ("Apparent consumption, 2024 (Atlas estimate)"): the file name does not say it twice
  const name = [commodity, title || 'table', title.includes(String(data.y)) ? '' : data.y].filter((x) => x !== '').join(' ');
  return { file: `commodity-flows-atlas-${slug(name)}.csv`, text: toCsv(head, out) };
}

export function downloadRanked(data: Ranked, from: Element | null) {
  const { file, text } = rankedCsv(data, tableTitle(from));
  downloadCsv(file, text);
}
