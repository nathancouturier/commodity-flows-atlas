/** Small shared UI primitives: switches, ranked bars, KPI tiles, source lines. */
import type { ComponentChildren } from 'preact';
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import type { Alert, Company, Fig, InfraType, Ranked, StatusNote } from '../types';
import { commodityMeta, countryName, load, sourceLabel, sources } from '../lib/data';
import { fmt, pct, fig as fmtFig } from '../lib/format';
import { select } from '../lib/store';
import { statusClassOf, statusText } from '../lib/infra';
import '../styles/lane-table.css';

export function Switch(props: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string; desc?: string }) {
  return (
    <button
      class="toggle-row"
      role="switch"
      aria-checked={props.checked}
      onClick={() => props.onChange(!props.checked)}
      title={props.hint}
    >
      <span class="toggle-text">
        <span>{props.label}</span>
        {props.desc && <small class="toggle-desc">{props.desc}</small>}
      </span>
      <span class="switch" aria-hidden="true" />
    </button>
  );
}

export function Section(props: { title: ComponentChildren; children: ComponentChildren; aside?: ComponentChildren }) {
  return (
    <section class="section">
      <h3 class="section-title">
        <span>{props.title}</span>
        {props.aside}
      </h3>
      {props.children}
    </section>
  );
}

/** "Source: USGS Mineral Commodity Summaries · 2024" with a link to the source page. */
export function SourceLine(props: { s?: string; y?: number | string; n?: string }) {
  if (!props.s) return null;
  const src = sources.value[props.s];
  return (
    <div class="src-line">
      Source:{' '}
      {src ? (
        <a href={src.url} target="_blank" rel="noopener">
          {src.name}
        </a>
      ) : (
        props.s
      )}
      {props.y != null && <> · {props.y}</>}
      {props.n && <> · {props.n}</>}
    </div>
  );
}

/** Short publisher label for footnotes ("CEPII BACI", "USGS", "EIA"...). */
const SHORT_SOURCE: Record<string, string> = {
  baci: 'CEPII BACI',
  'usgs-mcs': 'USGS',
  'usda-psd': 'USDA',
  'eia-intl': 'EIA',
  'eia-spot': 'EIA',
  'eia-tie': 'EIA',
  'eia-chokepoints': 'EIA',
  'wb-pink': 'World Bank',
  faostat: 'FAOSTAT',
  wna: 'World Nuclear Association',
  portwatch: 'IMF PortWatch',
  atlas: 'Atlas estimate',
  'port-authorities': 'port authorities',
  'company-reports': 'company reports',
  'operator-reports': 'operator reports',
  'eia-refinery-capacity': 'EIA',
  'giignl-2026': 'GIIGNL',
  'trade-press': 'trade press',
  wikipedia: 'Wikipedia',
};
export function shortSource(id: string): string {
  return SHORT_SOURCE[id] ?? sources.value[id]?.publisher ?? id;
}

/** "Sources: CEPII BACI 2024 · USGS 2024, 2025 · EIA 2023": every distinct source and year of a block. */
export function SourcesLine(props: { items: { s: string; y?: number | string }[]; n?: string }) {
  const by = new Map<string, { s: string; ys: Set<string> }>();
  for (const it of props.items) {
    if (!it.s) continue;
    const key = shortSource(it.s);
    const e = by.get(key) ?? { s: it.s, ys: new Set<string>() };
    if (it.y != null) e.ys.add(String(it.y));
    by.set(key, e);
  }
  if (!by.size) return null;
  const list = [...by.entries()];
  return (
    <div class="src-line">
      {list.length > 1 ? 'Sources: ' : 'Source: '}
      {list.map(([label, e], i) => {
        const src = sources.value[e.s];
        const ys = [...e.ys].sort();
        return (
          <>
            {i > 0 && ' · '}
            {src ? (
              <a href={src.url} target="_blank" rel="noopener" title={src.name}>
                {label}
              </a>
            ) : (
              label
            )}
            {ys.length > 0 && <> {ys.join(', ')}</>}
          </>
        );
      })}
      {props.n && <> · {props.n}</>}
    </div>
  );
}

// ---------------------------------------------------------------- active disruptions

let alertsPromise: Promise<Alert[]> | null = null;
function useAlerts(): Alert[] {
  const [a, setA] = useState<Alert[]>([]);
  useEffect(() => {
    alertsPromise ??= load<Alert[]>('freight/alerts.json').catch(() => []);
    let live = true;
    alertsPromise.then((r) => live && setA(r));
    return () => {
      live = false;
    };
  }, []);
  return a;
}

const MON_S = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function sinceLabel(s: string): string {
  const [y, m] = s.split('-');
  return m ? `${MON_S[Number(m) - 1] ?? m} ${y}` : y;
}

/**
 * Dated disruption banners. Alerts are matched by commodity, country, or chokepoint ids;
 * `status` are lane/route-specific notes, de-duplicated against the alerts by event id.
 */
type AlertProps = { commodity?: string; country?: string; chokepoints?: string[]; status?: StatusNote[]; expanded?: boolean };

function CollapsedAlerts(props: AlertProps & { count: number; high: boolean; titles: string[] }) {
  const [open, setOpen] = useState(false);
  if (open) return <AlertBanners {...props} expanded />;
  return (
    <button class={`alert alert-${props.high ? 'high' : 'medium'} alert-collapsed`} onClick={() => setOpen(true)} aria-expanded="false">
      <b>Active disruptions ({props.count})</b>
      <span>{props.titles.join(' · ')}</span>
      <span class="alert-more">Show</span>
    </button>
  );
}

export function AlertBanners(props: AlertProps) {
  const all = useAlerts();
  const cps = props.chokepoints ?? [];
  const hit = all.filter(
    (a) =>
      (props.commodity != null && a.commodities.includes(props.commodity)) ||
      (props.country != null && a.countries.includes(props.country)) ||
      cps.some((c) => a.chokepoints.includes(c)),
  );
  const seen = new Set(hit.map((a) => a.event));
  const notes = (props.status ?? []).filter((n) => {
    const key = n.event ?? n.text;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  // high severity first
  hit.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'high' ? -1 : 1));
  if (!hit.length && !notes.length) return null;
  const total = hit.length + notes.length;
  if (total > 1 && !props.expanded) {
    // several disruptions: one compact row, expandable, so the tables stay above the fold
    return <CollapsedAlerts {...props} count={total} high={hit.some((a) => a.severity === 'high')} titles={hit.map((a) => a.title)} />;
  }
  return (
    <div class="alerts">
      {hit.map((a) => (
        <div class={`alert alert-${a.severity}`} role="note" key={a.id}>
          <div class="alert-head">
            <b>{a.title}</b>
            <span class="alert-since num">since {sinceLabel(a.since)}</span>
          </div>
          <p>{a.text}</p>
          <div class="alert-links">
            <button onClick={() => select({ kind: 'event', id: a.event })}>Details</button>
            <a href={a.src} target="_blank" rel="noopener">
              Source ↗
            </a>
          </div>
        </div>
      ))}
      {notes.map((n, i) => (
        <div class="alert alert-medium" role="note" key={'n' + i}>
          <p>{n.text}</p>
          {n.event && (
            <div class="alert-links">
              <button onClick={() => select({ kind: 'event', id: n.event! })}>Details</button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/** Smallest size a key figure shrinks to before it is allowed to wrap, px. */
const KPI_MIN_PX = 12;

/**
 * A key figure stays on one line: when it is wider than its card it shrinks to fit, and only below
 * KPI_MIN_PX does it wrap (a figure is never cut). Refits when the card changes width.
 */
function useFitOneLine(text: string) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    let lastW = -1;
    const fit = () => {
      lastW = el.clientWidth;
      el.style.fontSize = '';
      el.style.whiteSpace = 'nowrap';
      if (el.scrollWidth <= el.clientWidth) {
        el.style.whiteSpace = '';
        return;
      }
      const full = parseFloat(getComputedStyle(el).fontSize);
      const px = Math.floor(((full * el.clientWidth) / el.scrollWidth) * 10) / 10;
      el.style.fontSize = `${Math.max(px, KPI_MIN_PX)}px`;
      if (px >= KPI_MIN_PX) el.style.whiteSpace = '';
      else el.style.whiteSpace = 'normal';
    };
    fit();
    const ro = typeof ResizeObserver === 'function' ? new ResizeObserver(() => el.clientWidth !== lastW && fit()) : null;
    ro?.observe(el);
    document.fonts?.ready.then(fit);
    return () => ro?.disconnect();
  }, [text]);
  return ref;
}

export function Kpi(props: { label: string; f?: Fig; value?: string; sub?: string; note?: string; title?: string; span?: boolean }) {
  const f = props.f;
  const [open, setOpen] = useState(false);
  const valueText = props.value ?? fmtFig(f);
  const valueRef = useFitOneLine(valueText);
  const title = props.title ?? (f ? `${f.s} · ${f.y}${f.n ? ' · ' + f.n : ''}` : undefined);
  const note = props.note;
  const long = !!note && note.length > 90;
  return (
    <div class={`kpi${props.span ? ' kpi-span' : ''}`} title={title}>
      <div class="kpi-label">{props.label}</div>
      <div class="kpi-value" ref={valueRef}>{valueText}</div>
      {(f || props.sub) && (
        <div class="kpi-src">{props.sub ?? `${sources.value[f!.s]?.publisher ?? f!.s} · ${f!.y}`}</div>
      )}
      {note &&
        (long ? (
          <button class={`kpi-note kpi-note-btn${open ? ' open' : ''}`} aria-expanded={open} onClick={() => setOpen(!open)} title={open ? 'Show less' : 'Show the full note'}>
            {note}
          </button>
        ) : (
          <div class="kpi-note">{note}</div>
        ))}
    </div>
  );
}

/** Ranked horizontal bars for a country table. Rows are clickable (open the country). */
export function RankedBars(props: { data: Ranked; color?: string; limit?: number; unitLabel?: string }) {
  const { data } = props;
  const rows = data.rows.slice(0, props.limit ?? 10);
  const max = Math.max(...rows.map((r) => r.v), 1e-9);
  const world = data.world;
  const rest = data.other ? data.other + data.rows.slice(rows.length).reduce((a, r) => a + r.v, 0) : 0;
  return (
    <div>
      <div class="bars" style={{ '--bar-color': props.color }}>
        {rows.map((r, i) => (
          <button class="bar-row" key={r.c} onClick={() => select({ kind: 'country', id: r.c })} title={r.n}>
            <span class="bar-rank">{i + 1}</span>
            <span>
              <span class="bar-label">{countryName(r.c)}</span>
              <div class="bar-track">
                <div class="bar-fill" style={{ width: `${(r.v / max) * 100}%` }} />
              </div>
            </span>
            <span class="bar-value">
              {fmt(r.v)}
              {world ? <small>{pct(r.v / world)}</small> : null}
            </span>
          </button>
        ))}
        {rest > 0 && (
          <div class="bar-row bar-other">
            <span class="bar-rank" />
            <span class="bar-label">Other countries</span>
            <span class="bar-value">
              {fmt(rest)}
              {world ? <small>{pct(rest / world)}</small> : null}
            </span>
          </div>
        )}
      </div>
      <SourceLine s={data.s} y={data.y} n={`${props.unitLabel ?? data.u}${world ? ` · world ${fmt(world)} ${data.u}` : ''}${data.n ? ' · ' + data.n : ''}`} />
    </div>
  );
}

export function Placeholder(props: { children: ComponentChildren }) {
  return <div class="placeholder">{props.children}</div>;
}

export function Skeleton(props: { lines?: number }) {
  return (
    <div style={{ display: 'grid', gap: '8px' }}>
      {Array.from({ length: props.lines ?? 4 }, (_, i) => (
        <div class="skeleton" key={i} style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
    </svg>
  );
}

export function BrandMark() {
  return (
    <svg class="brand-mark" viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="22" fill="none" stroke="#2a3a4f" stroke-width="3" />
      <path d="M12 39 C 23 15, 42 15, 53 27" fill="none" stroke="#3ee6ff" stroke-width="4" stroke-linecap="round" />
      <circle cx="53" cy="27" r="5" fill="#ffb547" />
    </svg>
  );
}

// ---------------------------------------------------------------- infrastructure icons

export interface InfraTypeMeta {
  label: string;
  /** plural label used by the side-panel chips */
  plural: string;
  /** glyph strokes in a 24x24 box (stroke = currentColor) */
  glyph: string;
  /** extra decoration in the 28x28 icon box (LNG direction arrow) */
  extra?: string;
}

const SNOWFLAKE =
  '<path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9"/><path d="M9.5 4.8L12 7l2.5-2.2M9.5 19.2L12 17l2.5 2.2"/>';

export const INFRA_META: Record<InfraType, InfraTypeMeta> = {
  field: {
    label: 'Oil & gas field',
    plural: 'Fields',
    glyph:
      '<path d="M12 3.5C12 3.5 6 10 6 14.5a6 6 0 0 0 12 0C18 10 12 3.5 12 3.5z"/><path d="M9.3 15a3 3 0 0 0 2.3 2.8"/>',
  },
  refinery: {
    label: 'Refinery',
    plural: 'Refineries',
    glyph:
      '<path d="M3 21h18"/><path d="M6 21V10h5v11"/><path d="M8.5 10V5"/><path d="M6 14h5M6 17.5h5"/><path d="M16 21V11"/><path d="M16 11c-2.2-2-2.2-4 0-6.5 2.2 2.5 2.2 4.5 0 6.5z"/>',
  },
  'lng-export': {
    label: 'LNG export terminal',
    plural: 'LNG export',
    glyph: SNOWFLAKE,
    extra: '<path d="M19.5 9.5L25.5 3.5M20.8 3.2h4.9v4.9" />',
  },
  'lng-import': {
    label: 'LNG import terminal',
    plural: 'LNG import',
    glyph: SNOWFLAKE,
    extra: '<path d="M25.5 3.5L19.5 9.5M19.2 4.8v4.9h4.9" />',
  },
  pipeline: {
    label: 'Pipeline',
    plural: 'Pipelines',
    glyph: '<path d="M3 15h5.5l3-6h1l3 6H21"/><path d="M3 19h18"/>',
  },
  mine: {
    label: 'Mine',
    plural: 'Mines',
    glyph:
      '<path d="M4.5 19.5L16.5 7.5"/><path d="M9 4.5C14.5 3.5 19.5 6 20 13"/><path d="M19.5 19.5L8 8"/><path d="M4.5 10l5-5" stroke-width="3.4"/>',
  },
  smelter: {
    label: 'Smelter / refinery',
    plural: 'Smelters',
    glyph:
      '<path d="M5 10h14l-1.8 8.4a2 2 0 0 1-2 1.6H8.8a2 2 0 0 1-2-1.6z"/><path d="M7.4 13.6c1.5-1 3-1 4.6 0s3 1 4.6 0"/><path d="M9 7c-1-1.2 1-1.8 0-3.2M15 7c-1-1.2 1-1.8 0-3.2"/>',
  },
  port: {
    label: 'Port',
    plural: 'Ports',
    glyph:
      '<circle cx="12" cy="5.5" r="2"/><path d="M12 7.5V20M8.5 11h7"/><path d="M5 13.5c.3 3.8 3.3 6.5 7 6.5s6.7-2.7 7-6.5"/><path d="M3.8 12l1.2 2 2.2-1.2M20.2 12L19 14l-2.2-1.2"/>',
  },
};

/** Display order of the infrastructure types in filters. */
export const INFRA_ORDER: InfraType[] = ['field', 'refinery', 'lng-export', 'lng-import', 'pipeline', 'mine', 'smelter', 'port'];

/** SVG markup of an infrastructure badge icon (also rasterised for the map). */
export function infraSvg(type: InfraType, color: string, size = 28): string {
  const m = INFRA_META[type];
  const scale = type === 'lng-export' || type === 'lng-import' ? 0.56 : 0.6;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" width="${size}" height="${size}">` +
    `<circle cx="14" cy="14" r="10.5" fill="#0a1019" fill-opacity="0.94" stroke="${color}" stroke-width="1.8"/>` +
    `<g transform="translate(14 14) scale(${scale}) translate(-12 -12)" fill="none" stroke="${color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${m.glyph}</g>` +
    (m.extra ? `<g fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${m.extra}</g>` : '') +
    `</svg>`
  );
}

export function InfraIcon(props: { type: InfraType; color?: string; size?: number }) {
  return (
    <span
      class="infra-ic"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: infraSvg(props.type, props.color ?? '#b9c4d0', props.size ?? 20) }}
    />
  );
}

/**
 * Status pill of an infrastructure asset: green when operating, grey when the status is not stated, amber otherwise.
 * `asOf` ("2026-03") is when the status was true: "Damaged as of March 2026".
 */
export function StatusBadge(props: { status?: string; asOf?: string }) {
  if (!props.status) return null;
  const cls = props.status === 'not-stated' ? 'badge-plain' : statusClassOf(props.status) === 'ok' ? 'badge-ok' : 'badge-warn';
  return <span class={`badge ${cls}`}>{statusText(props.status, props.asOf)}</span>;
}

const MODE_LABEL: Record<string, string> = { sea: 'sea', land: 'land', mixed: 'sea + land', pipeline: 'pipeline' };
const MODE_TITLE: Record<string, string> = {
  sea: 'Seaborne',
  land: 'Overland',
  mixed: 'By sea and overland; the split is not known',
  pipeline: 'Pipeline',
};

/**
 * How a flow moves: SEA, LAND, SEA + LAND (both, split not known) or PIPELINE. `via` is the transit port of a
 * landlocked country's sea cargo ("sea via Dar es Salaam"): the badge stays SEA and its title names the port.
 */
export function ModeBadge(props: { mode?: string; via?: string }) {
  const m = props.mode;
  if (!m) return null;
  const title = m === 'sea' && props.via ? `Sea via ${props.via}` : (MODE_TITLE[m] ?? m);
  return (
    <span class={`badge badge-mode mode-${m}`} title={title}>
      {MODE_LABEL[m] ?? m}
    </span>
  );
}

/** A note that folds to three lines when it is long and opens on a tap: a hover title cannot be read on a touch screen. */
export function FoldNote(props: { text?: string | null; class?: string; style?: Record<string, string> }) {
  const [open, setOpen] = useState(false);
  const text = props.text;
  if (!text) return null;
  const cls = props.class ?? 'kpi-note';
  if (text.length <= 130) return <div class={cls} style={props.style}>{text}</div>;
  return (
    <button class={`${cls} kpi-note-btn${open ? ' open' : ''}`} style={props.style} aria-expanded={open} onClick={() => setOpen(!open)} title={open ? 'Show less' : 'Show the full note'}>
      {text}
    </button>
  );
}

/** Mark on a figure that the atlas computed itself (a tonnage estimated from the declared value). */
export function EstMark(props: { title?: string }) {
  return (
    <span class="est-mark" title={props.title ?? 'Tonnage computed by the atlas from the declared value, shown to two significant digits'}>
      Atlas estimate
    </span>
  );
}

/** Compact clickable row: leading node, title, optional sub line, right-aligned meta. */
export function RowBtn(props: {
  onClick?: () => void;
  lead?: ComponentChildren;
  title: ComponentChildren;
  sub?: ComponentChildren;
  meta?: ComponentChildren;
  tip?: string;
  href?: string;
}) {
  const body = (
    <>
      {props.lead}
      <span class="row-main">
        <span class="row-title">{props.title}</span>
        {props.sub != null && <span class="row-sub">{props.sub}</span>}
      </span>
      {props.meta != null && <span class="row-meta num">{props.meta}</span>}
    </>
  );
  if (props.href)
    return (
      <a class="row-btn" href={props.href} target="_blank" rel="noopener" title={props.tip}>
        {body}
      </a>
    );
  return (
    <button class="row-btn" onClick={props.onClick} title={props.tip} disabled={!props.onClick} style={!props.onClick ? { cursor: 'default' } : undefined}>
      {body}
    </button>
  );
}

export function CompanyRows(props: { title?: string; list: Company[]; showK?: boolean }) {
  const { list } = props;
  if (!list.length) return null;
  const yrs = list.map((c) => c.fig?.y ?? c.y).filter((y) => y != null);
  return (
    <div class="co-group">
      {props.title && <h4 class="route-sub">{props.title}</h4>}
      {list.map((c) => (
        <RowBtn
          key={c.name}
          href={c.url}
          tip={[c.s ? sourceLabel(c.s) : '', c.fig?.y ?? c.y].filter(Boolean).join(' · ')}
          title={<>{c.name}{c.url && <span class="ext"> ↗</span>}</>}
          sub={
            <>
              {[c.hq ? countryName(c.hq) : null, c.role, props.showK && c.k ? [c.k].flat().map((k) => commodityMeta(k)?.name ?? k).join(', ') : null].filter(Boolean).join(' · ')}
              {c.detail && <span class="row-detail">{c.detail}</span>}
            </>
          }
          meta={c.fig ? <>{fmt(c.fig.v)} {c.fig.u}<small>{c.fig.y}</small></> : undefined}
        />
      ))}
      <SourceLine s={list[0].fig?.s ?? list[0].s} y={yrs.length ? [...new Set(yrs)].slice(0, 3).join(', ') : undefined} />
    </div>
  );
}

