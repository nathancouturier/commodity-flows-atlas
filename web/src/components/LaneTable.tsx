/**
 * Sortable table of the main lanes of a commodity (M-002): origin, destination, tonnes, share, vessel class,
 * distance and passages, then what is not on a lane (one row per exporter) and a CSV export built in the browser.
 */
import { useMemo, useState } from 'preact/hooks';
import type { Lane, LaneFile } from '../types';
import { countryName, sourceLabel } from '../lib/data';
import { fmt, fmtEst, pct, sig2 } from '../lib/format';
import { GROUP_LABEL, chokepointName, vesselName } from '../lib/freight';
import { select } from '../lib/store';
import { useFreightCatalogue } from './views/shared';
import { EstMark, ModeBadge } from './ui';
import '../styles/lane-table.css';

type SortKey = 'from' | 'to' | 'mt' | 'share' | 'class' | 'nm' | 'via';

const SORTS: { key: SortKey; label: string; title: string; text: boolean }[] = [
  { key: 'from', label: 'From', title: 'Sort by origin', text: true },
  { key: 'to', label: 'To', title: 'Sort by destination', text: true },
  { key: 'mt', label: 'Mt', title: 'Sort by tonnes', text: false },
  { key: 'share', label: 'Share', title: "Sort by share of the commodity's seaborne trade", text: false },
  { key: 'class', label: 'Class', title: 'Sort by typical vessel class', text: true },
  { key: 'nm', label: 'Distance', title: 'Sort by distance', text: false },
  { key: 'via', label: 'Passages', title: 'Sort by passages crossed', text: true },
];

/** Rows shown before "Show all N". */
const FIRST_ROWS = 12;

export interface LaneRow {
  id: string;
  group: string;
  /** product name, only for a commodity that has two customs groups */
  product: string | null;
  o: string;
  d: string;
  /** tonnes of the year shown (file unit), null = no figure that year */
  v: number | null;
  u: string;
  /** share of the group's seaborne tonnes, 0..1; null for a lane that is not all sea */
  share: number | null;
  est: boolean;
  kind: 'sea' | 'transit' | 'mixed';
  /** transit port name, for a landlocked end */
  transit: string | null;
  cls: string | null;
  nm: number;
  via: string[];
  /** passages that only some options may cross */
  maybe: string[];
  s: string;
  y: number;
}

export interface RestRow {
  group: string;
  product: string | null;
  o: string;
  v: number;
  u: string;
  n: number;
}

const flat = (l: Lane): string[] => [...new Set((l.viaAlt ?? []).flat())].filter((g) => !l.via.includes(g));

/**
 * The lanes to list. With no History year (or the latest year): the main set. In a past year: every lane that
 * has a figure that year, which is what the map draws. `rest` (what is not on a lane) is a latest-year figure.
 */
export function laneRows(files: LaneFile[], yr: number | null): { rows: LaneRow[]; rest: RestRow[]; past: boolean } {
  const rows: LaneRow[] = [];
  const rest: RestRow[] = [];
  let past = false;
  for (const f of files) {
    const at = yr != null && yr !== f.y ? f.years.indexOf(yr) : -1;
    const product = files.length > 1 ? (GROUP_LABEL[f.group] ?? f.label ?? f.group) : null;
    if (at >= 0) past = true;
    for (const l of f.lanes) {
      const mixed = l.mode === 'mixed';
      let v: number | null;
      let share: number | null;
      let est: boolean;
      if (at >= 0) {
        v = l.hist[at] ?? null;
        if (!v || v <= 0) continue;
        const tot = f.seaborne[at];
        share = mixed || !tot ? null : v / tot;
        est = l.histFlags?.[String(yr)] === 'est';
      } else {
        if (l.set === 'history') continue;
        v = l.flow.v;
        share = mixed ? null : l.share;
        est = !!l.flow.est;
      }
      rows.push({
        id: l.id,
        group: f.group,
        product,
        o: l.o,
        d: l.d,
        v,
        u: f.unit,
        share,
        est,
        kind: mixed ? 'mixed' : l.transit ? 'transit' : 'sea',
        transit: l.transit ? (f.ports[l.transit.port]?.name ?? null) : null,
        cls: l.vclass[0] ?? null,
        nm: l.distanceNm,
        via: l.via,
        maybe: flat(l),
        s: f.s,
        y: at >= 0 ? (yr as number) : f.y,
      });
    }
    if (at < 0) for (const r of f.rest ?? []) rest.push({ group: f.group, product, o: r.o, v: r.v, u: f.unit, n: r.n });
  }
  rest.sort((a, b) => b.v - a.v);
  return { rows, rest, past };
}

const names = (ids: string[]) => ids.map(chokepointName);

/** "Malacca, Singapore" and, for the passages only some options cross, "may use Taiwan Strait, Luzon". */
export function passagesText(via: string[], maybe: string[]): string {
  const parts: string[] = [];
  if (via.length) parts.push(names(via).join(', '));
  if (maybe.length) parts.push(`may use ${names(maybe).join(', ')}`);
  return parts.join(' · ');
}

const cmpNum = (a: number | null, b: number | null, dir: 1 | -1) => {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return (a - b) * dir;
};

function sortRows(rows: LaneRow[], key: SortKey, dir: 1 | -1): LaneRow[] {
  const txt = (r: LaneRow): string => {
    switch (key) {
      case 'from':
        return countryName(r.o);
      case 'to':
        return countryName(r.d);
      case 'class':
        return r.cls ? vesselName(r.cls) : '';
      default:
        return names([...r.via, ...r.maybe]).join(' ');
    }
  };
  const by = [...rows];
  by.sort((a, b) => {
    let c = 0;
    if (key === 'mt') c = cmpNum(a.v, b.v, dir);
    else if (key === 'share') c = cmpNum(a.share, b.share, dir);
    else if (key === 'nm') c = cmpNum(a.nm, b.nm, dir);
    else if (key === 'via') {
      // fewest certain passages first when ascending, then by name; a lane with none sorts as "no passage"
      c = (a.via.length - b.via.length) * dir || txt(a).localeCompare(txt(b)) * dir;
    } else c = txt(a).localeCompare(txt(b)) * dir;
    // ties: the larger lane first, so that the order is stable and readable
    return c || (b.v ?? 0) - (a.v ?? 0);
  });
  return by;
}

const csvCell = (x: string | number | null | undefined): string => {
  const s = x == null ? '' : String(x);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const MODE_TEXT = { sea: 'sea', transit: 'sea via a foreign port', mixed: 'sea and overland (split not known)' } as const;

/** One line per lane, then one per exporter for what is not on a lane. Values are not rounded, except an Atlas estimate (two significant digits). */
export function lanesCsv(rows: LaneRow[], rest: RestRow[]): string {
  const head = [
    'product', 'from_iso3', 'from', 'to_iso3', 'to', 'year', 'tonnes', 'unit', 'share_of_seaborne_pct',
    'mode', 'transit_port', 'vessel_class', 'distance_nm', 'passages', 'may_use_passages', 'atlas_estimate', 'source',
  ];
  const out = [head.join(',')];
  for (const r of rows) {
    out.push(
      [
        r.product ?? r.group, r.o, countryName(r.o), r.d, countryName(r.d), r.y,
        r.v == null ? '' : r.est ? sig2(r.v) : r.v, r.u,
        r.share == null ? '' : (r.share * 100).toFixed(2),
        MODE_TEXT[r.kind], r.transit ?? '', r.cls ? vesselName(r.cls) : '', r.nm || '',
        names(r.via).join('; '), names(r.maybe).join('; '), r.est ? 'yes' : '', sourceLabel(r.s),
      ].map(csvCell).join(','),
    );
  }
  for (const r of rest) {
    const y = rows[0]?.y ?? '';
    out.push(
      [
        r.product ?? r.group, r.o, countryName(r.o), '', `Other destinations (${r.n} countries)`, y, r.v, r.u,
        '', 'sea', '', '', '', '', '', '', sourceLabel(rows[0]?.s ?? 'baci'),
      ].map(csvCell).join(','),
    );
  }
  return out.join('\r\n') + '\r\n';
}

function download(name: string, text: string) {
  // a byte-order mark so that spreadsheet programs read the country names as UTF-8
  const url = URL.createObjectURL(new Blob(['﻿', text], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function LaneLine({ r }: { r: LaneRow }) {
  const passages = passagesText(r.via, r.maybe);
  return (
    <button class="lt-row" onClick={() => select({ kind: 'lane', id: r.id })} title="Open this lane">
      <span>
        <span class="lt-route">
          {countryName(r.o)} <span class="arrow">→</span> {countryName(r.d)}
        </span>
        <span class="lt-sub">
          {r.kind === 'mixed' && <ModeBadge mode="mixed" />}
          {r.kind === 'transit' && (
            <>
              <ModeBadge mode="sea" via={r.transit ?? undefined} />
              <span class="mode-via">via {r.transit ?? 'a foreign port'} </span>
            </>
          )}
          {[r.product, r.cls ? vesselName(r.cls) : null, r.nm ? `${r.nm.toLocaleString('en-US')} nm` : null, passages || null].filter(Boolean).join(' · ')}
          {r.est && <EstMark />}
        </span>
      </span>
      <span class="lt-fig num">
        {r.v == null ? '—' : `${fmtEst(r.v, r.est)} ${r.u}`}
        <small>{r.share == null ? (r.kind === 'mixed' ? 'all modes' : '—') : pct(r.share, true)}</small>
      </span>
    </button>
  );
}

export default function LaneTable(props: { files: LaneFile[]; yr: number | null; name: string }) {
  useFreightCatalogue();
  const [key, setKey] = useState<SortKey>('mt');
  const [dir, setDir] = useState<1 | -1>(-1);
  const [all, setAll] = useState(false);
  const { rows, rest, past } = useMemo(() => laneRows(props.files, props.yr), [props.files, props.yr]);
  const sorted = useMemo(() => sortRows(rows, key, dir), [rows, key, dir]);
  if (!rows.length) return null;
  const more = sorted.length > FIRST_ROWS;
  const open = all || !more;
  const shown = open ? sorted : sorted.slice(0, FIRST_ROWS);
  const first = props.files[0];
  const year = rows[0].y;
  const restV = rest.reduce((n, r) => n + r.v, 0);
  const restN = rest.reduce((n, r) => n + r.n, 0);
  const cover = props.files.length === 1 ? first.coverage : undefined;
  const sort = (k: SortKey, text: boolean) => {
    if (k === key) setDir((dir * -1) as 1 | -1);
    else {
      setKey(k);
      setDir(text ? 1 : -1);
    }
  };
  return (
    <div class="lt">
      <div class="lt-sort" role="group" aria-label="Sort the lanes">
        <span class="lt-sort-k">Sort</span>
        {SORTS.map((s) => (
          <button key={s.key} aria-pressed={key === s.key} title={s.title} onClick={() => sort(s.key, s.text)}>
            {s.label}
            {key === s.key ? (dir === 1 ? ' ↑' : ' ↓') : ''}
          </button>
        ))}
      </div>
      <div class="lt-list" role="list" aria-label={`Lanes, ${year}`}>
        {shown.map((r) => (
          <div role="listitem" key={r.id}>
            <LaneLine r={r} />
          </div>
        ))}
      </div>
      {open && rest.length > 0 && (
        <>
          <div class="lt-rest-title">Other destinations, {year}</div>
          <div class="lt-list lt-rest" role="list">
            {rest.map((r) => (
              <div role="listitem" key={r.group + r.o}>
                <div class="lt-row">
                  <span>
                    <span class="lt-route">{countryName(r.o)} <span class="arrow">→</span> other destinations</span>
                    <span class="lt-sub">{[r.product, `to ${r.n.toLocaleString('en-US')} countr${r.n === 1 ? 'y' : 'ies'}`].filter(Boolean).join(' · ')}</span>
                  </span>
                  <span class="lt-fig num">{fmt(r.v)} {r.u}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
      <div class="lt-foot">
        {more && (
          <button class="act-btn" aria-expanded={all} onClick={() => setAll(!all)}>
            {all ? 'Show fewer' : `Show all ${sorted.length} lanes`}
          </button>
        )}
        <button class="act-btn" onClick={() => download(`commodity-flows-atlas-${props.name}-lanes-${year}.csv`, lanesCsv(sorted, rest))} title="Download these lanes as a CSV file">
          Download CSV
        </button>
      </div>
      <div class="lt-note">
        {past
          ? `Lanes with a flow in ${year}; the tonnage that is not on a lane is listed for the latest year only.`
          : [
              cover ? `The lanes carry ${pct(cover.share)} of the ${fmt(first.seaborne[first.seaborne.length - 1])} ${first.unit} seaborne in ${year}.` : null,
              rest.length && !open ? `Not on a lane: ${fmt(restV)} ${first.unit} in ${restN.toLocaleString('en-US')} pairs, listed by exporter under "Show all".` : null,
            ]
              .filter(Boolean)
              .join(' ')}
      </div>
    </div>
  );
}
