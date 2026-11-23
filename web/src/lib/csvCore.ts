/**
 * The pure part of the CSV helper (no import: scripts/csv.test.mjs runs this file as it is): how a cell is written, and the
 * rule for a long cell that repeats on every row.
 */

/** A number as a data file holds it: no floating-point noise ("153.81379999997444" is 153.8138), twelve significant digits at most. */
export const numberText = (x: number): string => (Number.isFinite(x) && !Number.isInteger(x) ? String(Number(x.toPrecision(12))) : String(x));

export const csvCell = (x: string | number | boolean | null | undefined): string => {
  const t = x == null ? '' : typeof x === 'number' ? numberText(x) : String(x);
  return /[",\r\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
};

/** Header and rows as CSV text. */
export function toCsv(head: string[], rows: (string | number | boolean | null | undefined)[][]): string {
  return [head, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n') + '\r\n';
}


/**
 * A long cell that repeats on every row of a file is written in full on the first row that uses it, and on the others by
 * its short form with a pointer to that row: a weekly series of four thousand rows does not carry the IMF's licence text
 * four thousand times. Make one per file and per column; a cell of up to `limit` characters is always written in full.
 * The rule for the `source` and the `licence` column of every CSV of the site.
 */
export function onceColumn(limit: number, what: string): (full: string, short?: string) => string {
  const seen = new Set<string>();
  return (full, short = full) => {
    if (full.length <= limit || short === full) return full;
    if (!seen.has(full)) {
      seen.add(full);
      return full;
    }
    return `${short} (${what} on the first row of this source)`;
  };
}
export const LONG_LICENCE = 100;
export const LONG_SOURCE = 80;
