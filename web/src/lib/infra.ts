/**
 * What an infrastructure asset says, read from the schema of pipeline/infrastructure/README.md: its figures
 * (capacity and output, each with its own year), its status, and what the History year changes.
 */
import type { InfraFigure, InfraOutput, InfraProps, Route } from '../types';
import { loadOptional } from './data';

/**
 * A row of the port index of the lanes (pipeline/freight/build_port_index.py): a port of the trade engine by its code,
 * the largest lanes that use it, the asset that is this place, and the names the routes and the engine give it.
 */
export interface PortIndexRow { id: string; name: string; c: string; g: string[]; lane: string | null; lanes?: string[]; asset?: string; aka?: string[] }
let portIndex: Promise<PortIndexRow[]> | null = null;
export const loadPortIndex = () => (portIndex ??= loadOptional<{ ports: PortIndexRow[] }>('freight/ports.json').then((d) => d?.ports ?? []));

/** The row of the port index that a route's port is: same name, in the country of that end of the route when two share it. */
export function portRowOf(rows: PortIndexRow[], name: string, c?: string | null): PortIndexRow | undefined {
  const same = rows.filter((p) => p.name === name);
  return same.find((p) => p.c === c) ?? (same.length === 1 ? same[0] : undefined);
}

/** The customs groups of a commodity that are not its own id (pipeline/freight/build_freight.py, GROUPS_OF). */
const GROUPS_OF: Record<string, string[]> = {
  'thermal-coal': ['coal'],
  'met-coal': ['coal'],
  copper: ['copper-ore'],
  nickel: ['nickel-ore'],
  phosphate: ['phosphate-rock', 'dap'],
  lithium: ['spodumene'],
};

/** The customs groups a route carries: those its corridor names, else those of its cargoes. A lane id starts with its group. */
export function routeGroups(r: Pick<Route, 'corridor' | 'cargoes'>): string[] {
  const out = new Set<string>();
  for (const c of r.corridor ?? []) {
    if (c.g) out.add(c.g);
    for (const g of c.gs ?? []) out.add(g);
  }
  if (!out.size) for (const k of r.cargoes) for (const g of GROUPS_OF[k] ?? [k]) out.add(g);
  return [...out];
}

/** The largest lane through a port of a commodity the route carries (the index lists a port's largest lanes first), or null. */
export function laneOfGroups(row: PortIndexRow | undefined, groups: string[]): string | null {
  const lanes = row ? (row.lanes ?? (row.lane ? [row.lane] : [])) : [];
  return lanes.find((l) => groups.includes(l.slice(0, l.indexOf(':')))) ?? null;
}

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

/**
 * The year printed beside a figure: its own; where the page states none, the year the page was read, said as such
 * ("read 2026"), never as the year of the figure; "year not stated" only for a feature that has neither.
 */
export const yearText = (f: { y?: number | null }, read?: string): string => {
  if (f.y != null) return String(f.y);
  const r = read ? yearOfDate(read) : null;
  return r != null ? `read ${r}` : 'year not stated';
};

/** "2016 · Wikipedia", or "Wikipedia · read 2026" where the figure has no year of its own. */
export function yearSource(f: { y?: number | null }, source: string, read?: string): string {
  return f.y != null || !read || yearOfDate(read) == null ? `${yearText(f, read)} · ${source}` : `${source} · ${yearText(f, read)}`;
}

/**
 * The source as a reader sees it. An id that stands for many publishers ("Trade press (see the page linked on each
 * asset)") is shown with the site of the page read: "Trade press · mining.com".
 */
export function sourceText(label: string, url?: string): string {
  const m = /^(.*?)\s*\(see the (?:page|article)[^)]*\)\s*$/.exec(label);
  if (!m) return label;
  let host = '';
  try {
    host = new URL(url ?? '').hostname.replace(/^www\./, '');
  } catch {
    /* no page: the bare name */
  }
  return host ? `${m[1]} · ${host}` : m[1];
}

export const OUTPUT_LABEL: Record<InfraOutput['what'], string> = { production: 'Production', exports: 'Exports', throughput: 'Throughput' };

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
  /** a planned or target capacity, not one the asset has reached */
  planned?: boolean;
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
  planned: f.planned || undefined,
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
