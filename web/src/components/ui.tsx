/** Small shared UI primitives: switches, ranked bars, KPI tiles, source lines. */
import type { ComponentChildren } from 'preact';
import type { Fig, Ranked } from '../types';
import { countryName, sources } from '../lib/data';
import { fmt, pct, fig as fmtFig } from '../lib/format';
import { select } from '../lib/store';

export function Switch(props: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <button
      class="toggle-row"
      role="switch"
      aria-checked={props.checked}
      onClick={() => props.onChange(!props.checked)}
      title={props.hint}
    >
      <span>{props.label}</span>
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

export function Kpi(props: { label: string; f?: Fig; value?: string }) {
  return (
    <div class="kpi" title={props.f ? `${props.f.s} · ${props.f.y}${props.f.n ? ' · ' + props.f.n : ''}` : undefined}>
      <div class="kpi-label">{props.label}</div>
      <div class="kpi-value">{props.value ?? fmtFig(props.f)}</div>
      {props.f && (
        <div class="kpi-src">
          {sources.value[props.f.s]?.publisher ?? props.f.s} · {props.f.y}
        </div>
      )}
    </div>
  );
}

/** Ranked horizontal bars for a country table. Rows are clickable (open the country). */
export function RankedBars(props: { data: Ranked; color?: string; limit?: number; unitLabel?: string }) {
  const { data } = props;
  const rows = data.rows.slice(0, props.limit ?? 10);
  const max = Math.max(...rows.map((r) => r.v), 1e-9);
  const world = data.world;
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
