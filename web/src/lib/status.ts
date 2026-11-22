/**
 * Data freshness: a cleaned view of data/_status/updates.json, the file the scheduled jobs write
 * (pipeline/common/status.py). Only dates and a health flag leave this module: the raw error
 * messages of the status file are never copied.
 */
import { load, loadOptional } from './data';

// The file is machine-written, but nothing here may break on a value of the wrong type: each field is
// checked where it is read.
interface RawEntry {
  last_success?: unknown;
  data_to?: unknown;
  consecutive_failures?: unknown;
  alert_after?: unknown;
  state?: unknown;
}
interface RawStatus {
  updated?: unknown;
  sources?: unknown;
}

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const count = (v: unknown, d: number): number => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : d);
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {});

/**
 * ok, stale, failing: from the dates and the failure count. manual: the source is fetched by hand on purpose,
 * so a failed scheduled check is not a fault. unconfigured: an optional series that needs a key nobody set.
 */
export type Health = 'ok' | 'stale' | 'failing' | 'manual' | 'unconfigured';

export interface Freshness {
  /** key in updates.json */
  key: string;
  /** ids in sources.json this job feeds (the first one names the row) */
  sources: string[];
  /** end of the data, ready to display; null when the status file does not date it (annual sources) */
  dataTo: string | null;
  /** release of the source in use ("2026 edition", "Version 202601"), when the status file gives one */
  release: string | null;
  /** date of the last successful check (ISO), null when there never was one */
  checked: string | null;
  health: Health;
  /** why the row is stale or failing, in plain words */
  why?: string;
  /** the last scheduled check did not complete, below the alert threshold */
  retrying: boolean;
}


export interface StatusView {
  /** last write of the status file (ISO) */
  updated: string | null;
  rows: Freshness[];
  /** last rebuild of the commodity pages and country profiles (ISO) */
  rebuilt: string | null;
  /** BACI release in use, e.g. "202601" */
  baciVersion: string | null;
  /** date of the last successful FAOSTAT / WNA check (ISO) */
  faoChecked: string | null;
}

/** How the job dates its source: an end of data (day, month) or a release (the annual sources). */
type Kind = 'day' | 'month' | 'edition' | 'publisher-update' | 'marketing-year' | 'year' | 'none';

interface Tracked {
  key: string;
  sources: string[];
  kind: Kind;
  /** days without a successful check before the row is late: two scheduled runs missed, plus a margin */
  maxAge: number;
  /** fetched by hand: CEPII refuses the cloud runners, so the scheduled check is expected to fail */
  manual?: boolean;
  /** only fetched when a key is set: nothing is recorded without one */
  optional?: boolean;
}

// The price job runs every Tuesday and the PortWatch job every Wednesday; the annual job runs on the 15th of
// each month, and checks FAOSTAT and WNA only when their last check is 80 days old (.github/workflows).
const WEEKLY = 16;
const MONTHLY = 64;
const TRACKED: Tracked[] = [
  { key: 'eia-spot', sources: ['eia-spot'], kind: 'day', maxAge: WEEKLY },
  { key: 'wb-pink', sources: ['wb-pink'], kind: 'month', maxAge: WEEKLY },
  { key: 'fred', sources: ['fred'], kind: 'month', maxAge: WEEKLY, optional: true },
  { key: 'portwatch', sources: ['portwatch'], kind: 'day', maxAge: WEEKLY },
  { key: 'baci', sources: ['baci'], kind: 'year', maxAge: MONTHLY, manual: true },
  { key: 'usgs-mcs', sources: ['usgs-mcs'], kind: 'edition', maxAge: MONTHLY },
  { key: 'usda-psd', sources: ['usda-psd'], kind: 'marketing-year', maxAge: MONTHLY },
  { key: 'eia-intl', sources: ['eia-intl'], kind: 'publisher-update', maxAge: MONTHLY },
  { key: 'faostat-wna', sources: ['faostat', 'wna'], kind: 'none', maxAge: 80 + MONTHLY },
];

/** Daily series are fetched weekly: more than three weeks behind means the publisher or the job is late. */
const DAY_LAG = 21;
const DAY_MS = 86400000;

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-11-17" or "2026-11-17T13:57:11Z" -> "17 Nov 2026"; "2026-10" -> "Oct 2026"; anything else unchanged. */
export function fmtDate(s: string | null | undefined): string {
  if (!s) return '';
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(s);
  if (!m) return s;
  const mon = MON[Number(m[2]) - 1] ?? m[2];
  return m[3] ? `${Number(m[3])} ${mon} ${m[1]}` : `${mon} ${m[1]}`;
}

function ageDays(iso: string, now: number): number {
  const t = Date.parse(iso);
  return Number.isFinite(t) ? (now - t) / DAY_MS : Infinity;
}

/** A monthly series ending in month M is late once month M+1 should have been published: mid-month M+2. */
function monthLate(ym: string, now: number): boolean {
  const m = /^(\d{4})-(\d{2})$/.exec(ym);
  if (!m) return false;
  return now > Date.UTC(Number(m[1]), Number(m[2]) - 1 + 2, 15);
}

/** End of the data, for the series the status file dates itself (daily and monthly series). */
function dataToText(t: Tracked, e: RawEntry): string | null {
  const d = str(e.data_to);
  return d && (t.kind === 'day' || t.kind === 'month') ? fmtDate(d) : null;
}

/** Which release of an annual source is in use, in plain words. */
function releaseText(t: Tracked, e: RawEntry): string | null {
  const d = str(e.data_to);
  const st = obj(e.state);
  switch (t.kind) {
    case 'edition': {
      if (!d) return null;
      const to = typeof st.values_to === 'string' || typeof st.values_to === 'number' ? `, figures to ${st.values_to}` : '';
      return `${d} edition${to}`;
    }
    case 'publisher-update':
      // the bulk file carries the date the publisher last revised a series, not an end of period
      return d ? `Publisher revision of ${fmtDate(d)}` : null;
    case 'marketing-year':
      return d ? `File includes projections to marketing year ${d}` : null;
    case 'year':
      return typeof st.version === 'string' ? `Version ${st.version.replace(/^V/, '')}` : null;
    default:
      return null;
  }
}

function clean(raw: RawStatus, now: number): StatusView {
  const src = obj(raw.sources);
  const rows: Freshness[] = [];
  for (const t of TRACKED) {
    const e = obj(src[t.key]) as RawEntry;
    if (!src[t.key] || typeof src[t.key] !== 'object') continue;
    const checked = str(e.last_success);
    const dataTo = str(e.data_to);
    const fails = count(e.consecutive_failures, 0);
    const limit = count(e.alert_after, 3);
    let health: Health = 'ok';
    let why: string | undefined;
    if (t.manual) {
      health = 'manual';
      why = 'New versions are fetched by hand, because the publisher can refuse automated downloads. The site keeps the last good data.';
    } else if (fails >= limit) {
      health = 'failing';
      why = `The last ${fails} scheduled checks did not complete. The site keeps the last good data.`;
    } else if (!checked || ageDays(checked, now) > t.maxAge) {
      if (t.optional && fails === 0) {
        health = 'unconfigured';
        why = 'This optional series is fetched only when a free FRED API key is set. The site keeps the last values fetched.';
      } else {
        health = 'stale';
        why = checked ? `No successful check for more than ${t.maxAge} days.` : 'No successful check recorded.';
      }
    } else if (dataTo && t.kind === 'day' && ageDays(dataTo, now) > DAY_LAG) {
      health = 'stale';
      why = `The latest data are more than ${DAY_LAG} days old.`;
    } else if (dataTo && t.kind === 'month' && monthLate(dataTo, now)) {
      health = 'stale';
      why = 'A newer month should have been published by now.';
    }
    rows.push({
      key: t.key,
      sources: t.sources,
      dataTo: dataToText(t, e),
      release: releaseText(t, e),
      checked,
      health,
      why,
      retrying: !t.manual && fails > 0 && fails < limit,
    });
  }
  const rebuilt = [obj(src['build-commodities']).last_success, obj(src['build-profiles']).last_success]
    .map(str)
    .filter((x): x is string => !!x)
    .sort()[0];
  const ver = obj(obj(src.baci).state).version;
  return {
    updated: str(raw.updated),
    rows,
    rebuilt: rebuilt ?? null,
    baciVersion: typeof ver === 'string' ? ver.replace(/^V/, '') : null,
    faoChecked: str(obj(src['faostat-wna']).last_success),
  };
}

/** Load the status file and reduce it to what the site shows. Throws when the file cannot be read. */
export async function loadStatus(now = Date.now()): Promise<StatusView> {
  const raw = await load<unknown>('_status/updates.json');
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('status file is not an object');
  return clean(raw as RawStatus, now);
}

// ---------------------------------------------------------------- vintages

// One small commodity file per annual source is enough to read the year its figures carry on the site.
const SAMPLES = ['crude-oil', 'copper', 'wheat', 'cocoa', 'uranium'];

/**
 * The latest year (or marketing year, "2025/26") the published figures of each source refer to, read
 * from the figures themselves in a few commodity files: source id -> year. Price series give the last
 * period they reach instead ("2026-10", "2026-11-17").
 */
export async function loadVintages(): Promise<Record<string, string>> {
  const out: Record<string, string> = {};
  const walk = (o: unknown) => {
    if (Array.isArray(o)) return o.forEach(walk);
    if (!o || typeof o !== 'object') return;
    const r = o as Record<string, unknown>;
    if (typeof r.s === 'string' && (typeof r.y === 'number' || typeof r.y === 'string')) {
      const y = String(r.y);
      // other period labels ("1H25", "FY2025") do not compare: they are left to the figure itself
      if (/^\d{4}(\/\d{2})?$/.test(y) && (!out[r.s] || y > out[r.s])) out[r.s] = y;
    }
    Object.values(r).forEach(walk);
  };
  const [files, prices] = await Promise.all([
    Promise.all(SAMPLES.map((id) => loadOptional<unknown>(`commodities/${id}.json`))),
    loadOptional<{ s?: string; end?: string }[]>('prices/index.json'),
  ]);
  files.forEach(walk);
  for (const p of prices ?? []) {
    if (!p.s || !p.end) continue;
    const cur = out[p.s];
    if (!cur || !/^\d{4}-\d{2}/.test(cur) || p.end > cur) out[p.s] = p.end;
  }
  return out;
}

// ---------------------------------------------------------------- build

declare const __BUILD_COMMIT__: string | undefined;
declare const __BUILD_DATE__: string | undefined;

/** Commit and date of the site build (set by vite.config.ts; empty when unknown). */
export const BUILD = {
  commit: typeof __BUILD_COMMIT__ === 'string' ? __BUILD_COMMIT__ : '',
  date: typeof __BUILD_DATE__ === 'string' ? __BUILD_DATE__ : '',
};
