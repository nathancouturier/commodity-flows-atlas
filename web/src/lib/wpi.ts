/**
 * The rows of the "World Port Index" block of a port page, from one entry of data/infrastructure/wpi.json. The figures are
 * the publication's own and are printed as it gives them; the only change is the one its key asks for: the depth of the
 * channel, the anchorage, the cargo pier and the oil terminal is a band (below). A figure the publication does not state is
 * absent from the entry and has no row.
 *
 * Type import only: scripts/wpi.test.mjs runs this file as it is.
 */
import type { WpiEntry } from '../types';

/**
 * The key to the depths of the World Port Index: a depth is given in steps of 5 feet and means a least depth "of this
 * or greater, but not as great as the next step". Typed from the "CODE KEY" at the head of every data page of the
 * twenty-sixth edition (2017) of Publication 150, band by band (code, from, to; "23.2-over" has no upper edge, "0-1.5"
 * has no lower one that is printed), and from item 11 of its "Explanation of Data Columns" ("Depths refer to chart
 * datum"). Archived copy of the PDF, read on 25 November 2026:
 * https://web.archive.org/web/20170829062601if_/http://msi.nga.mil/MSISiteContent/StaticFiles/NAV_PUBS/WPI/Pub150bk.pdf
 *
 * The edition of the file the atlas reads is not stated. That most of its depths sit on the floors of this key
 * (scripts/wpi.test.mjs counts them) is evidence that it is the same key, not proof; a value off these floors is a
 * newer, finer figure and is printed as it is. The key covers the four depths its item 11 explains; that edition has no LNG
 * terminal column, and the LNG depths of the file are not on its floors (scripts/wpi.test.mjs counts them), so that depth
 * is printed as the file gives it, never as a band.
 */
export const WPI_DEPTH_KEY: readonly { code: string; from: number; to: number | null }[] = [
  { code: 'a', from: 23.2, to: null },
  { code: 'b', from: 21.6, to: 22.9 },
  { code: 'c', from: 20.1, to: 21.3 },
  { code: 'd', from: 18.6, to: 19.8 },
  { code: 'e', from: 17.1, to: 18.2 },
  { code: 'f', from: 15.5, to: 16.8 },
  { code: 'g', from: 14.0, to: 15.2 },
  { code: 'h', from: 12.5, to: 13.7 },
  { code: 'j', from: 11.0, to: 12.2 },
  { code: 'k', from: 9.4, to: 10.7 },
  { code: 'l', from: 7.9, to: 9.1 },
  { code: 'm', from: 6.4, to: 7.6 },
  { code: 'n', from: 4.9, to: 6.1 },
  { code: 'o', from: 3.4, to: 4.6 },
  { code: 'p', from: 1.8, to: 3.0 },
  { code: 'q', from: 0, to: 1.5 },
];

const num = (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 3 });
const one = (v: number) => v.toFixed(1);
/** a figure and its unit stay on one line: a narrow panel breaks the row between its parts, not inside a figure */
const NB = '\u00a0';
const isFigure = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v > 0;

/**
 * "14.0 to 15.2 m" for a value that is the floor of a band of the key, "23.2 m or more" for the top band, the value as it
 * is ("16.1 m", "970 m") for one off the floors; null for a figure that is not stated (0 means that in the file, and is
 * never printed).
 */
export function depthText(v: number | undefined): string | null {
  if (!isFigure(v)) return null;
  const band = WPI_DEPTH_KEY.find((b) => b.from === v);
  if (!band) return `${num(v)}${NB}m`;
  return band.to == null ? `${one(band.from)}${NB}m or more` : `${one(band.from)} to ${one(band.to)}${NB}m`;
}

/** "340 m long, 60 m beam, 11.8 m draught": the parts the publication states, in that order; null when it states none. */
export function vesselText(loa?: number, beam?: number, draft?: number): string | null {
  const parts = [
    isFigure(loa) ? `${num(loa)}${NB}m long` : '',
    isFigure(beam) ? `${num(beam)}${NB}m beam` : '',
    isFigure(draft) ? `${num(draft)}${NB}m draught` : '',
  ].filter(Boolean);
  return parts.length ? parts.join(', ') : null;
}

/** "Medium, river (natural)": the publication's class of harbour and its type, in sentence case. */
export function harbourText(size?: string, type?: string): string | null {
  const t = [size, type].filter(Boolean).join(', ').toLowerCase();
  return t ? t[0].toUpperCase() + t.slice(1) : null;
}

/** The depths of the key, in the order of the block: the label, and the field of the entry. */
const DEPTHS = [
  ['Channel depth', 'chan'],
  ['Anchorage depth', 'anch'],
  ['Cargo pier depth', 'pier'],
  ['Oil terminal depth', 'oil'],
] as const;

export interface WpiRow {
  label: string;
  value: string;
}

/** Every row the entry has a figure for, in the order of the block; none for what the publication does not state. */
export function wpiRows(e: WpiEntry): WpiRow[] {
  const rows: (WpiRow | null)[] = [];
  const add = (label: string, value: string | null) => rows.push(value ? { label, value } : null);
  for (const [label, k] of DEPTHS) add(label, depthText(e[k]));
  add('LNG terminal depth', isFigure(e.lng) ? `${num(e.lng)}${NB}m` : null);
  add('Maximum vessel', vesselText(e.loa, e.beam, e.draft));
  add('Offshore maximum vessel', vesselText(e.oloa, e.obeam, e.odraft));
  add('Tidal range', isFigure(e.tide) ? `${num(e.tide)}${NB}m` : null);
  add('Harbour', harbourText(e.size, e.type));
  add('Pilotage', e.pilot === 'Yes' ? 'Compulsory' : e.pilot === 'No' ? 'Not compulsory' : null);
  add('Tide restricts entry', e.tideRes === 'Yes' || e.tideRes === 'No' ? e.tideRes : null);
  return rows.filter((r): r is WpiRow => r !== null);
}

/** The entry as the publication lists it: "Port Hedland, no. 54620". */
export const wpiEntryText = (e: Pick<WpiEntry, 'name' | 'n'>): string => `${e.name}, no. ${e.n}`;

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "29 Sep 2026" for "2026-09-29": the short form the site gives a date (`fmtDate` of lib/status.ts, which this file does not import). */
export function dayText(date: string): string {
  const m = /^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.exec(date);
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : date;
}

/**
 * Where the figures were read, after "Source: <publication> ·": "Internet Archive copy of 29 Sep 2026" when the file is the
 * archive's copy of the publisher's address (`captured` of the data file), else "read November 2026" (`monthYear` of the
 * month the atlas read the file, passed in). Null when the publication's edition is typed and the file is the publisher's
 * own: the edition is then part of the name. The month the file was read is never printed as the date of the figures.
 */
export function wpiWhen(file: { read: string; captured?: string; edition: string | null }, readText: string): string | null {
  if (file.captured) return `Internet Archive copy of ${dayText(file.captured)}`;
  return file.edition ? null : `read ${readText}`;
}
