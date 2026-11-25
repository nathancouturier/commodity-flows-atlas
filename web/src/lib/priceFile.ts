/**
 * Which of the price series on the chart may go into a CSV file: those whose every source states a permission to reuse its data
 * (src/lib/licence.ts). The others stay on the chart with their credit and are left out of the file. Pure: no import, so that
 * scripts/price-file.test.mjs runs it as it is; the caller gives the rule.
 */
export function splitOffered<T>(series: T[], sourcesOf: (s: T) => string[], allowed: (id: string) => boolean): { offered: T[]; withheld: T[] } {
  const offered: T[] = [];
  const withheld: T[] = [];
  for (const s of series) (sourcesOf(s).every(allowed) ? offered : withheld).push(s);
  return { offered, withheld };
}
