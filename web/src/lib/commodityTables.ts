/**
 * The tables of a commodity page by place, and the words that name them in the Notes section: a note that stands under many
 * tables is said once, for the tables it covers (`coverText`). Kept apart from the page so that a node test can read the data
 * files and call it (web/scripts/table-covers.test.mjs).
 */
import type { CommodityData, Ranked } from '../types';

/** What the main trade tables measure when it is not the finished commodity (used when the data file has no `basis`). */
export const TRADE_BASIS: Record<string, string> = {
  copper: 'ores and concentrates (gross weight)',
  nickel: 'ores (gross weight)',
  zinc: 'ores and concentrates (gross weight)',
  lead: 'ores and concentrates (gross weight)',
  bauxite: 'bauxite ore',
};

/** Section title: the wording set by the data file, else the default with what the table measures. */
export function sectionTitle(d: CommodityData, key: 'production' | 'reserves' | 'consumption' | 'exports' | 'imports' | 'flows', base: string, fallback?: string): string {
  const basis = (key === 'flows' ? undefined : d[key]?.basis) ?? fallback;
  return d.labels?.[key] ?? (basis ? `${base} — ${basis}` : base);
}

/** The core kinds of table, in the order of the page. */
export const KINDS = ['production', 'consumption', 'exports', 'imports', 'reserves'] as const;
export type Kind = (typeof KINDS)[number];
/** The word of a kind in the Notes section. */
export const KIND_WORD: Record<string, string> = { production: 'production', refinery: 'refinery output', consumption: 'consumption', exports: 'exporters', imports: 'importers', reserves: 'reserves' };

export type Table = { key: string; title: string; data: Ranked };

/** "Top consumers — motor gasoline, EIA 2025" names itself "motor gasoline, EIA 2025" in the line that holds the other tables of its kind. */
export const shortName = (title: string) => title.match(/^Top \w+ — (.+)$/)?.[1] ?? title;

/** "a, b and c". */
export const listText = (xs: string[]) => (xs.length > 1 ? `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}` : (xs[0] ?? ''));

/**
 * The tables of the page by place: each core kind (its main table first, then the extra tables whose key ends with the kind; refinery or
 * smelter output goes with production), the EU member states and the ending stocks (secondary blocks of the crops), and the rest.
 */
export function pageTables(d: CommodityData, id: string) {
  const kinds = {} as Record<Kind, Table[]>;
  for (const k of KINDS) {
    const main = d[k];
    const fallback = k === 'exports' || k === 'imports' ? TRADE_BASIS[id] : undefined;
    const base = { production: 'Top producers', consumption: 'Top consumers', exports: 'Top exporters', imports: 'Top importers', reserves: 'Reserves' }[k];
    kinds[k] = main ? [{ key: k, title: sectionTitle(d, k, base, fallback), data: main }] : [];
  }
  const eu: Table[] = [];
  const stocks: Table[] = [];
  const other: Table[] = [];
  for (const x of d.extra ?? []) {
    const t = { key: x.key, title: x.title, data: x.table };
    const k = KINDS.find((kk) => x.key === kk || x.key.endsWith(`-${kk}`));
    if (x.key.startsWith('eu-')) eu.push(t);
    else if (x.key === 'stocks') stocks.push(t);
    else if (k) kinds[k].push(t);
    else other.push(t);
  }
  if (d.refinery) kinds.production.push({ key: 'refinery', title: 'Refinery / smelter output', data: d.refinery });
  return { kinds, eu, stocks, other };
}

/** Every table of the page, in the order of the page: the order of the Notes section. */
export const allTables = (t: ReturnType<typeof pageTables>): Table[] => [...KINDS.flatMap((k) => t.kinds[k]), ...t.other, ...t.stocks, ...t.eu];

const kindOf = (t: { key: string }) => KINDS.find((k) => t.key === k || t.key.endsWith(`-${k}`));
const isMain = (t: { key: string }) => (KINDS as readonly string[]).includes(t.key);
const isEu = (t: { key: string }) => t.key.startsWith('eu-');
const isStocks = (t: { key: string }) => t.key === 'stocks';
/**
 * What a main table of trade counts when its title says it ("Top exporters — Mt of ferro-chromium, gross weight": ferro-chromium; "Top importers
 * — ores and concentrates": ores and concentrates). The title of a table of production, consumption or reserves says what is measured, not
 * a product, and is not read.
 */
const product = (t: Table) =>
  isMain(t) && (t.key === 'exports' || t.key === 'imports') ? /^[^—]+ — (?:(?:Mt|kt) of )?(.+?)(?:, (?:gross|product|net) weight)?$/.exec(t.title)?.[1] : undefined;

/**
 * How a table is named in a list of the Notes section, so that a reader can match it to its title on the page: a main table by its kind
 * ("exporters"), and, where the list holds a further table of the same kind, by what it counts ("exporters of ferro-chromium" beside "other
 * ferro-alloys exporters"); a further table by its title ("ferro-silicon exporters", "EU member states, exports (customs data)", "ending stocks").
 */
export function tableLabel(t: Table, among: Table[] = []): string {
  const what = product(t);
  if (what && among.some((o) => o !== t && kindOf(o) === kindOf(t))) return `${KIND_WORD[t.key]} of ${what}`;
  if (isMain(t)) return KIND_WORD[t.key];
  return (KIND_WORD[t.key] ?? t.title.replace(/^Top /, '')).replace(/^[A-Z](?![A-Z])/, (c) => c.toLowerCase());
}

/**
 * The tables that a shared note covers, in words: the titles of up to three; for more, the kinds of table (exporters, importers...) and
 * what else is among them, each named for what it is. The further tables of a kind (the tables of kinds of pulses, of the other
 * ferro-alloys, of the iron content of iron ore) are tables of that kind and are not said to be "kinds" or a split of the main one: that is
 * what this wording wrongly said before (GV6C.2). The EU member states and the ending stocks are named.
 */
export function coverText(ts: Table[], lead: string, collapsed: string): string {
  if (ts.length <= 3) return `${lead} ${listText(ts.map((t) => tableLabel(t, ts)))}`;
  const isProduct = (t: Table) => !isMain(t) && !isEu(t) && !isStocks(t) && !!kindOf(t);
  const words = [...new Set(ts.filter((t) => isMain(t) || isProduct(t)).map((t) => KIND_WORD[kindOf(t)!]))];
  const also = [
    ...(ts.some(isEu) ? ['the EU member states'] : []),
    ...(ts.some(isStocks) ? ['ending stocks'] : []),
    ...ts.filter((t) => !isMain(t) && !isProduct(t) && !isEu(t) && !isStocks(t)).map((t) => tableLabel(t, ts)),
  ];
  const head = words.length ? `${collapsed} ${listText(words)}` : `${collapsed} ${listText(also)}`;
  return words.length && also.length ? `${head}, and of ${listText(also)}` : head;
}
