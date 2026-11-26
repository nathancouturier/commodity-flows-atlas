/**
 * What the Freight market now page holds besides the traffic lists: two indicators of the price files (not freight rates),
 * and the publishers it only links to. Pure functions and text, no import but types: scripts/market-now.test.mjs runs this
 * file as it is, against the price files and the registry of the folder.
 */

/**
 * The price series the page shows, and what each one speaks for. Both are in data/prices/index.json under the Freight family; the words of the second come from
 * the `basis` of its series ("the prices US-based deep-sea carriers receive for their freight services"), which scripts/market-now.test.mjs checks.
 */
export const INDICATORS: readonly { id: string; segment: string }[] = [
  { id: 'igrea-m', segment: 'Dry bulk' },
  { id: 'freight-ppi-m', segment: 'US deep-sea carriers' },
];

/** The label the series' own notes carry, said on the row. */
export const NOT_A_RATE = 'not a freight rate';

/**
 * The price board's own test for a deviation from a trend or an average: it crosses zero, so the board gives it no per-cent
 * change (its footer says so), and nor does this page.
 */
export const isDeviation = (unit: string): boolean => /deviation/i.test(unit);

/** The change over one year the price board gives for the series, or null: none for a deviation, none when the board has none. */
export function percentOnYear(m: { unit: string; stats?: { chg?: { y?: number | null } } }): number | null {
  if (isDeviation(m.unit)) return null;
  const y = m.stats?.chg?.y;
  return typeof y === 'number' && Number.isFinite(y) ? y : null;
}

/** "2026-10" -> "2025-10": the month of a monthly series a year before. */
export const yearEarlier = (ym: string): string => `${Number(ym.slice(0, 4)) - 1}${ym.slice(4, 7)}`;

/** The value of a monthly series (x in seconds, as `loadSeries` gives it) in the month "YYYY-MM", found by its date, or null when it has none. */
export function valueInMonth(x: readonly number[], v: readonly (number | null)[], ym: string): number | null {
  if (!/^\d{4}-\d{2}$/.test(ym)) return null;
  const at = Date.UTC(Number(ym.slice(0, 4)), Number(ym.slice(5, 7)) - 1, 1) / 1000;
  const i = x.indexOf(at);
  const val = i < 0 ? null : v[i];
  return typeof val === 'number' && Number.isFinite(val) ? val : null;
}

/** The parts of a price series' metadata that an indicator row reads (PriceMeta of the price index has them all). */
export interface IndicatorMeta {
  id: string;
  unit: string;
  stats?: { last: { t: string; v: number }; chg?: { y?: number | null } };
}

/** An indicator: a series of the price files, the segment it speaks for, and the value of the same month a year earlier (null when the series has none). */
export interface Indicator<M extends IndicatorMeta = IndicatorMeta> {
  meta: M;
  segment: string;
  ago: number | null;
}

/** The indicator of a loaded series (`x` in seconds, `v` its values, as `loadSeries` gives them), or null when the series has no last value. */
export function indicatorOf<M extends IndicatorMeta>(meta: M, x: readonly number[], v: readonly (number | null)[], segment: string): Indicator<M> | null {
  const last = meta.stats?.last;
  if (!last) return null;
  return { meta, segment, ago: valueInMonth(x, v, yearEarlier(last.t)) };
}

/** A piece of a line: text, or text the page sets in bold. */
export type Part = string | { b: string };
/** A line of an indicator row; `title` is shown on hover. */
export interface IndicatorLine {
  parts: Part[];
  title?: string;
}
/** How the page writes a price, a month and a per cent, and whether the series is late on the day `now` (the price board's own functions, given by the view). */
export interface Formats {
  price: (v: number | null | undefined) => string;
  date: (s: string) => string;
  pct: (p: number) => string;
  isLate: (now: number) => boolean;
}

/**
 * The lines an indicator row prints: what it is, the last value with its month (and the late mark when the series is late on `now`), and the
 * value of the same month a year earlier with the board's change on the year (none for a deviation).
 */
export function indicatorLines(ind: Indicator, f: Formats, now: number): IndicatorLine[] {
  const { meta: m, segment, ago } = ind;
  const last = m.stats!.last;
  const late = f.isLate(now);
  const pct = percentOnYear(m);
  const lines: IndicatorLine[] = [
    { parts: [`${segment} · ${NOT_A_RATE}`] },
    { parts: [`${f.price(last.v)} ${m.unit} in ${f.date(last.t)}${late ? ' · late' : ''}`], title: late ? `No value since ${f.date(last.t)}: this series is late` : undefined },
  ];
  if (ago != null) lines.push({ parts: [`A year earlier, ${f.date(yearEarlier(last.t))}: ${f.price(ago)}`, ...(pct != null ? [' · ', { b: f.pct(pct) }, ' on the year'] : [])] });
  else if (pct != null) lines.push({ parts: ['Change on one year: ', { b: f.pct(pct) }] });
  return lines;
}
/** A line as one string, as the page reads it. */
export const indicatorLineText = (l: IndicatorLine): string => l.parts.map((p) => (typeof p === 'string' ? p : p.b)).join('');

/**
 * What the Dallas Fed says on its page of the index (https://www.dallasfed.org/research/igrea, read 25 November 2026), word for word.
 * scripts/market-now.test.mjs finds each piece in the `basis` of the series, which the price build wrote from that page.
 */
export const DALLAS_WORDS = {
  citation: 'as proposed in Kilian (2009), with the correction discussed in Kilian (2019)',
  built: 'derived from a panel of dollar-denominated global bulk dry cargo shipping rates',
  proxy: 'may be viewed as a proxy for the volume of shipping in global industrial commodity markets',
} as const;

/**
 * The note of the Dallas Fed row: the Bank's credit (the registry's licence asks for it) unless the source line above it, which carries the registry's name of the
 * source, already starts with it; the citation the registry asks for, and what the Bank says the index is a proxy for.
 */
export const dallasNote = (credit: string): string =>
  `${credit ? credit + '; ' : ''}${DALLAS_WORDS.citation}; ${DALLAS_WORDS.built}, it “${DALLAS_WORDS.proxy}”, in the Bank’s words; ${NOT_A_RATE}`;

/**
 * Indices and rates other publishers give and the atlas does not show: the name, what it measures in a few words, the registry entry
 * of its publisher. No value is stored or shown, and none of these entries is a source of a figure of the page, so none is cited.
 * An address comes from the registry entry (`href` absent) or is the address of a page read on 25 November 2026 and named in the
 * registry entry's licence (scripts/market-now.test.mjs checks it).
 */
export interface LinkOnly {
  s: string;
  name: string;
  what: string;
  href?: string;
}
export const LINK_ONLY: readonly LinkOnly[] = [
  { s: 'baltic', name: 'Baltic Exchange indices', what: 'indices of the benchmark routes for dry cargo, tankers and gas' },
  { s: 'sse', name: 'China Import Dry Bulk Freight Index', what: 'freight into China, dry bulk', href: 'https://en.sse.net.cn/indices/cdfinew2.jsp' },
  { s: 'sse', name: 'China Import Crude Oil Tanker Freight Index', what: 'freight into China, crude oil tankers', href: 'https://en.sse.net.cn/indices/ctfinew2.jsp' },
  { s: 'usda-ams', name: 'Weekly port region grain ocean vessel activity (number of vessels)', what: 'grain vessels loaded during the week and expected to be loaded within the next ten days in the Gulf, the Pacific Northwest and Vancouver, B.C.' },
  { s: 'usda-ams', name: 'Grain ocean freight rates', what: 'the cost of shipping grain from the US Gulf and Pacific Northwest to Japan, credited there to O’Neil Commodity Consulting' },
];

/**
 * The note under an indicator row, which follows the source line (the registry's name of the source, as the line prints it): the publisher, unless that name
 * already starts with it (the Bank is not printed twice in a row), and what the series itself says it is; the Dallas Fed adds its citation and its own words.
 */
export const indicatorNote = (id: string, publisher: string, note?: string, sourceName = ''): string => {
  const credit = sourceName.startsWith(publisher) ? '' : publisher;
  return id === 'igrea-m' ? dallasNote(credit) : `${credit ? credit + '; ' : ''}${note ?? NOT_A_RATE}`;
};

/** The note of a series of the price index, from the registry's entry of its source (the publisher and the name its source line prints); the id when the registry lacks it. */
export const indicatorSourceNote = (m: { id: string; s: string; note?: string }, entry?: { name: string; publisher: string }): string =>
  indicatorNote(m.id, entry?.publisher ?? m.s, m.note, entry?.name ?? m.s);
