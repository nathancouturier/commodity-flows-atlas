/**
 * The share of a lane file's seaborne tonnes that is an Atlas estimate, and the part of it made from a volume in the United States' own export
 * statistics (the rest is from the declared value). No import: scripts/estimate-parts.test.mjs runs this file as it is, against the lane files.
 */

/** The fields of a lane file that carry the estimated shares (types.ts: LaneFile). */
export interface EstimateFile {
  years: number[];
  y: number;
  est?: number;
  estY?: (number | null)[];
  estVol?: number;
  estVolY?: (number | null)[];
}

/**
 * The share of a file's seaborne tonnes that is an Atlas estimate in the year shown (the latest year, or the History year when the file has it),
 * when it is 1% or more. The year's list `estY` holds three decimals, `est` of the latest year four: the latest year is read from `est`, so that
 * its two parts (`estimatedVolume` and the rest) are taken from figures of the same precision.
 */
export function estimatedShare(f: EstimateFile, yr: number | null): { share: number; year: number } | null {
  const i = yr != null && f.years.includes(yr) ? f.years.indexOf(yr) : f.years.indexOf(f.y);
  const latest = f.years[i] === f.y;
  const listed = f.estY?.[i] ?? (latest ? f.est : undefined);
  if (listed == null || listed < 0.01) return null; // the line of the year is written on the published (three-decimal) share
  return { share: latest && f.est != null ? f.est : listed, year: f.years[i] };
}

/** The part of the estimated share (`estimatedShare`) that is made from a volume in the United States' own export statistics, 0 when none is. */
export function estimatedVolume(f: EstimateFile, year: number): number {
  const i = f.years.indexOf(year);
  if (year === f.y && f.estVol != null) return f.estVol;
  return f.estVolY?.[i] ?? 0;
}

/** The two bases of an estimated share, from shares that add up: the part made from a volume and the part made from the declared value. */
export function estimateParts(share: number, volume: number): { volume: number; value: number } {
  const r = (x: number) => Math.round(x * 1e4) / 1e4;
  return { volume: r(volume), value: r(share - volume) };
}
