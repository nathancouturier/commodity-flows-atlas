/**
 * What the Freight market now page holds besides the traffic lists: two indicators of the price files (not freight rates),
 * and the publishers it only links to. Pure functions and text, no import but types: scripts/market-now.test.mjs runs this
 * file as it is, against the price files and the registry of the folder.
 */

/** The price series the page shows, and the segment each one speaks for. Both are in data/prices/index.json under the Freight family. */
export const INDICATORS: readonly { id: string; segment: string }[] = [
  { id: 'igrea-m', segment: 'Dry bulk' },
  { id: 'freight-ppi-m', segment: 'All ships' },
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

/**
 * What the Dallas Fed says on its page of the index (https://www.dallasfed.org/research/igrea, read 25 November 2026), word for word.
 * scripts/market-now.test.mjs finds each piece in the `basis` of the series, which the price build wrote from that page.
 */
export const DALLAS_WORDS = {
  citation: 'as proposed in Kilian (2009), with the correction discussed in Kilian (2019)',
  built: 'derived from a panel of dollar-denominated global bulk dry cargo shipping rates',
  proxy: 'may be viewed as a proxy for the volume of shipping in global industrial commodity markets',
} as const;

/** The note of the Dallas Fed row: the citation the registry asks for, and what the Bank says the index is a proxy for. */
export const dallasNote = (publisher: string): string =>
  `${publisher}; ${DALLAS_WORDS.citation}; ${DALLAS_WORDS.built}, it “${DALLAS_WORDS.proxy}”, in the Bank’s words; ${NOT_A_RATE}`;

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
  { s: 'usda-ams', name: 'Weekly grain vessel line-up', what: 'grain vessels loading at the US Gulf and Pacific Northwest ports' },
  { s: 'usda-ams', name: 'Grain ocean freight rates', what: 'the cost of shipping grain from the US Gulf and Pacific Northwest to Japan, credited there to O’Neil Commodity Consulting' },
];

/** The note under an indicator row: its publisher and what the series itself says it is; the Dallas Fed adds its citation and its own words. */
export const indicatorNote = (id: string, publisher: string, note?: string): string => (id === 'igrea-m' ? dallasNote(publisher) : `${publisher}; ${note ?? NOT_A_RATE}`);
