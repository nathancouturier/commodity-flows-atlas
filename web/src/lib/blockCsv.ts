/**
 * CSV of the commodity-page blocks that `RankedBars` does not draw: main flows, two years of USGS figures, value and unit value,
 * the balance of a USDA crop and the monthly EIA series. The conventions of rankedCsv.ts: one row per value, its year, source and
 * licence on every row; an Atlas estimate is written to two significant digits, says so, carries its method and adds the atlas licence.
 */
import type { CropBalance, Flow, HistTable, ImportRow, MonthlyRow } from '../types';
import { countryName, sourceLabel } from './data';
import { sig2 } from './format';
import { ATLAS_LICENCE, downloadCsv, licenceColumn, licenceOf, licenceTexts, publisherOf, slug, sourceColumn, sourceName, toCsv } from './csv';
import { licenceShort } from './licence';
import { mixedModeText } from './flowMode';

type Cell = string | number | null | undefined;

const file = (parts: (string | number | undefined)[]) => `commodity-flows-atlas-${slug(parts.filter((x) => x !== undefined && x !== '').join(' '))}.csv`;

/** The sources an Atlas estimate rests on, named in its note: the flows' estimates are computed from BACI's declared values, or (the United States' LPG
 * to Mexico) from a volume of the US Census Bureau and EIA. */
const inputsOf = (note?: string) => [
  ...(/\bBACI\b/.test(note ?? '') ? ['baci'] : []),
  ...(/Census Bureau/.test(note ?? '') ? ['census-exports'] : []),
  ...(/\bEIA\b/.test(note ?? '') ? ['eia-exports-destination'] : []),
];

/** The registry ids the rows of a flows table rest on: their own, and the inputs of an Atlas estimate. */
export const flowSources = (flows: Flow[]) => [...new Set(flows.flatMap((f) => [f.s, ...(f.s === 'atlas' ? inputsOf(f.n) : [])]))];

/** Every flow of the commodity's "Main flows", largest first. */
export function downloadFlows(commodity: string, title: string, flows: Flow[]) {
  const src = sourceColumn();
  const lic = licenceColumn();
  const rows: Cell[][] = [...flows]
    .sort((a, b) => b.v - a.v)
    .map((f, i) => {
      const own = f.s === 'atlas';
      const inputs = own ? inputsOf(f.n) : [];
      const from = inputs.map(sourceLabel).join(' and ') || 'the sources named in the note';
      const source = own ? src(sourceName('atlas', `computed from ${from}`), sourceName('atlas')) : src(sourceName(f.s), publisherOf(f.s));
      const licence = own
        ? lic(`${ATLAS_LICENCE}; computed from ${inputs.map((x) => `${publisherOf(x)}: ${licenceShort(licenceOf(x))}`).join('; ') || 'the sources named in the note'}`)
        : lic(...licenceTexts([f.s]));
      const mode = f.mode === 'mixed' ? mixedModeText(f) : (f.mode ?? 'not modelled');
      return [
        commodity, title, i + 1, f.o, countryName(f.o), f.d, countryName(f.d), f.y, f.est ? sig2(f.v) : f.v, f.u,
        f.transit ? `${mode}, via a port of ${countryName(f.transit.c)}` : mode, f.est ? 'Atlas estimate' : own ? 'Atlas conversion' : '', f.n ?? '', source, licence,
      ];
    });
  const head = ['commodity', 'table', 'rank', 'origin_code', 'origin', 'destination_code', 'destination', 'year', 'value', 'unit', 'mode', 'estimate', 'note', 'source', 'licence'];
  downloadCsv(file([commodity, title, flows[0]?.y]), toCsv(head, rows));
}

/** A table of two USGS years (MetalFigures): each country and year, the source's "Other countries" line and the sum of the lines. */
export function downloadYears(commodity: string, title: string, h: HistTable) {
  const src = sourceColumn();
  const lic = licenceColumn();
  const rows: Cell[][] = [];
  const line = (code: string, name: string, vals: (number | null)[], est: (i: number) => boolean, note: string) =>
    h.years.forEach((y, i) => {
      if (vals[i] == null) return;
      rows.push([commodity, title, code, name, y, vals[i], h.u, est(i) ? 'USGS estimate' : '', [h.yl?.[i], note].filter(Boolean).join(' | '), src(sourceName(h.s), publisherOf(h.s)), lic(...licenceTexts([h.s]))]);
    });
  const order = Object.entries(h.c).sort((a, b) => (b[1][1] ?? b[1][0] ?? 0) - (a[1][1] ?? a[1][0] ?? 0));
  for (const [c, v] of order) line(c, countryName(c), v, (i) => !!h.srcEst?.[c]?.includes(i), '');
  if (h.other) line('', 'Other countries', h.other, (i) => !!h.otherEst?.includes(i), "the source's own line");
  line('WLD', 'World (sum of lines)', h.world, () => false, 'sum of the lines above');
  const head = ['commodity', 'table', 'country_code', 'country', 'year', 'value', 'unit', 'estimate', 'note', 'source', 'licence'];
  downloadCsv(file([commodity, title, h.years.join(' and ')]), toCsv(head, rows));
}

/** One tab of "Value and unit value": tonnes, declared value and unit value of each row, and the world line. */
export function downloadTradeValue(
  commodity: string,
  tab: { title: string; u: string; usd?: number; uv?: number; rows: { c?: string; name: string; v: number; usd: number; uv?: number; est?: boolean }[] },
  y: number | string | undefined,
) {
  const src = sourceColumn();
  const lic = licenceColumn();
  const rows: Cell[][] = tab.rows.map((r) => [
    commodity, tab.title, r.c ?? '', r.name, y, r.est ? sig2(r.v) : r.v, tab.u, r.usd, r.uv ?? '', r.est ? 'Atlas estimate' : '',
    r.est ? 'the tonnage is an Atlas estimate computed from the declared value: no unit value' : '',
    src(sourceName('baci', r.est ? 'tonnage is an Atlas estimate' : undefined), publisherOf('baci')),
    lic(...licenceTexts(['baci'], r.est ? `; the estimate: ${ATLAS_LICENCE}` : '')),
  ]);
  if (tab.usd != null)
    rows.push([commodity, tab.title, 'WLD', 'World, all countries', y, '', tab.u, tab.usd, tab.uv ?? '', '', 'declared value of all countries', src(sourceName('baci'), publisherOf('baci')), lic(...licenceTexts(['baci']))]);
  const head = ['commodity', 'table', 'country_code', 'row', 'year', 'quantity', 'unit', 'value_usd', 'unit_value_usd_per_t', 'estimate', 'note', 'source', 'licence'];
  downloadCsv(file([commodity, 'value and unit value', tab.title, y]), toCsv(head, rows));
}

/** The balance of a USDA crop, both marketing years; a line the atlas computed from two USDA figures says so. */
export function downloadBalance(commodity: string, bal: CropBalance) {
  const src = sourceColumn();
  const lic = licenceColumn();
  const rows: Cell[][] = bal.rows.flatMap((r) =>
    bal.years.map((y, i) => {
      const calc = r.s === 'atlas';
      return [
        commodity, r.label, y.y, y.yk ?? '', y.rel, r.v[i], r.u, calc ? 'arithmetic on two USDA figures of the same year' : '', r.n ?? '',
        src(sourceName(bal.s, calc ? 'computed by the atlas from two of its figures' : undefined), publisherOf(bal.s)),
        lic(...licenceTexts([bal.s], calc ? `; the arithmetic: ${ATLAS_LICENCE}` : '')),
      ];
    }),
  );
  const head = ['commodity', 'line', 'marketing_year', 'year_kind', 'usda_report', 'value', 'unit', 'computed', 'note', 'source', 'licence'];
  downloadCsv(file([commodity, 'balance', bal.years.map((y) => y.y).join(' and ')]), toCsv(head, rows));
}

/** "2024-11" plus `n` months. */
function month(from: string, n: number): string {
  const t = Number(from.slice(0, 4)) * 12 + Number(from.slice(5)) - 1 + n;
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`;
}

/** A monthly EIA series of the page: one row per row of the block and month; a month EIA gives no figure for is left empty and says so. */
export function downloadMonthly(
  commodity: string,
  title: string,
  s: string,
  parts: { group?: string; u: string; from: string; to: string; rows: (MonthlyRow | ImportRow)[]; names?: Record<string, string> }[],
) {
  const src = sourceColumn();
  const lic = licenceColumn();
  const out: Cell[][] = [];
  for (const p of parts)
    for (const r of p.rows) {
      const code = r.c ?? r.o ?? '';
      const name = r.name ?? p.names?.[r.o ?? ''] ?? (r.c ? countryName(r.c) : (r.o ?? ''));
      r.v.forEach((v, i) =>
        out.push([commodity, title, p.group ?? '', code, name, month(p.from, i), v, p.u, v == null ? 'no figure in the EIA file' : '', src(sourceName(s), publisherOf(s)), lic(...licenceTexts([s]))]),
      );
    }
  const head = ['commodity', 'table', 'importer', 'code', 'name', 'month', 'value', 'unit', 'note', 'source', 'licence'];
  const last = parts.map((p) => p.to).sort().pop();
  downloadCsv(file([commodity, title, last]), toCsv(head, out));
}

