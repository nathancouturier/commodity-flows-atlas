/**
 * What an infrastructure asset says, read from the schema of pipeline/infrastructure/README.md: its figures
 * (capacity and output, each with its own year), its status, and what the History year changes.
 *
 * The files not yet migrated to that schema still carry a feature-level `y` and free-text units: those are
 * read by lib/capacity.ts, which turns them into the same figures.
 */
import type { InfraFigure, InfraOutput, InfraProps } from '../types';

export const STATUS_LABEL: Record<string, string> = {
  operating: 'Operating',
  damaged: 'Damaged',
  suspended: 'Suspended',
  idle: 'Idle',
  construction: 'Under construction',
  planned: 'Planned',
  closed: 'Closed',
  'not-stated': 'Status not stated',
};

export type StatusClass = 'ok' | 'damaged' | 'idle' | 'construction' | 'planned' | 'closed';

/** Visual class of a status. `not-stated` and an empty status are drawn like `operating`. */
export function statusClassOf(status?: string): StatusClass {
  if (!status || status === 'not-stated' || /operat|active|producing/i.test(status)) return 'ok';
  if (status === 'closed' || /\b(closed|decommission|abandon)/i.test(status)) return 'closed';
  if (status === 'damaged' || /damag|destroy|attack|struck|\bhit\b/i.test(status)) return 'damaged';
  if (status === 'construction' || /construct|commission|build|develop/i.test(status)) return 'construction';
  if (status === 'planned' || /planned|propos/i.test(status)) return 'planned';
  return 'idle';
}

export const isOperating = (status?: string): boolean => statusClassOf(status) === 'ok';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** "2026-03" -> "March 2026"; "2026" -> "2026"; anything else is returned as it is. */
export function monthYear(s: string): string {
  const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(s);
  return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1]}` : s;
}

/** First four digits of "YYYY" or "YYYY-MM", or null. */
export function yearOfDate(s?: string): number | null {
  const m = s ? /^(\d{4})(-\d{2})?$/.exec(s) : null;
  return m ? Number(m[1]) : null;
}

/** "Operating as of March 2026", "Status not stated". */
export function statusText(status?: string, asOf?: string): string {
  const label = STATUS_LABEL[status ?? 'not-stated'] ?? status ?? STATUS_LABEL['not-stated'];
  return asOf && status && status !== 'not-stated' ? `${label} as of ${monthYear(asOf)}` : label;
}

/** The year printed beside a figure: its own, or "year not stated". Never the date the page was read. */
export const yearText = (f: { y?: number | null }): string => (f.y != null ? String(f.y) : 'year not stated');

export const OUTPUT_LABEL: Record<InfraOutput['what'], string> = { production: 'Production', exports: 'Exports', throughput: 'Throughput' };

/** The files not yet migrated carry a feature-level year; the new shape has none. */
export const isLegacy = (p: InfraProps): boolean => p.y !== undefined;

export type FigureKind = 'capacity' | InfraOutput['what'];

export interface Figure {
  kind: FigureKind;
  v: number;
  u: string;
  /** year of the figure; null = year not stated */
  y: number | null;
  /** what the figure counts */
  n?: string;
  /** the source's own figure, when v was converted */
  orig?: string;
}

/** "1,950 kt/y". The unit is printed whole. */
export const figureText = (f: { v: number; u: string }, fmt: (v: number) => string): string => `${fmt(f.v)} ${f.u}`;

export const figureOf = (kind: FigureKind, f: InfraFigure): Figure => ({
  kind,
  v: f.v,
  u: f.u,
  y: typeof f.y === 'number' && Number.isFinite(f.y) ? f.y : null,
  n: f.n,
  orig: f.orig,
});

/**
 * What an asset is when the History timeline stands at `year` (null = no timeline): an asset that opens later is
 * not open yet, and a status dated after that year is not applied (the asset was running, as far as the page says).
 */
export interface StateAt {
  status: string | undefined;
  /** not open yet at that year */
  notOpen: boolean;
  /** year the asset opens, when it is later than the selected year */
  opensIn: number | null;
  /** the status given by the file does not apply yet at that year */
  statusLater: boolean;
}

export function stateAt(p: InfraProps, year: number | null): StateAt {
  if (year == null) return { status: p.status, notOpen: false, opensIn: null, statusLater: false };
  const opened = typeof p.opened === 'number' ? p.opened : null;
  if (opened != null && opened > year) {
    // not open yet: a damage or a closure cannot have happened; planned and under-construction keep their style
    const unbuilt = p.status === 'planned' || p.status === 'construction';
    return { status: unbuilt ? p.status : 'operating', notOpen: true, opensIn: opened, statusLater: false };
  }
  const at = yearOfDate(p.statusAsOf);
  if (at != null && at > year) {
    // a planned or unbuilt asset with no opening year cannot have been running before its status date
    const unbuilt = opened == null && (p.status === 'planned' || p.status === 'construction');
    return { status: unbuilt ? p.status : 'operating', notOpen: unbuilt, opensIn: null, statusLater: true };
  }
  return { status: p.status, notOpen: false, opensIn: null, statusLater: false };
}
