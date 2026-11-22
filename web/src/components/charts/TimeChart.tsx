/**
 * Reusable uPlot time-series wrapper in the Abyssal style.
 * x = unix timestamps in seconds. Supports lines, stacked areas, bars, a crosshair
 * readout (instead of uPlot's legend), event markers (hover lists every event under the
 * cursor, a click opens one), range buttons, drag-to-zoom (double-click resets) and a
 * "jump to date" month input.
 */
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import type uPlot from 'uplot';
import { fmt, TOUCH } from '../../lib/format';
import '../../styles/timechart.css';

export interface TimeSeries {
  label: string;
  values: (number | null)[];
  color: string;
  /** y scale: 'y2' draws against a second axis on the right (default 'y') */
  scale?: 'y' | 'y2';
}

export interface TimeMarker {
  /** seconds */
  t: number;
  /** optional end (seconds) draws a shaded band */
  end?: number;
  title: string;
  color?: string;
  /**
   * dense event sets: a thin line with a small top mark instead of the flag, and a period drawn as a
   * ribbon along the bottom of the plot instead of a full-height shade, so that it hides nothing
   */
  subtle?: boolean;
  /** opaque key handed back to onMarker; a marker without one is not clickable */
  id?: string;
  /** short qualifier shown after the title in the hover list (e.g. the kind of event) */
  tag?: string;
}

export interface TimeRange {
  label: string;
  /** window length in seconds, ending at the last point; null = all data */
  seconds: number | null;
}

export type XFormat = 'year' | 'month' | 'date';

export interface TimeChartProps {
  x: number[];
  series: TimeSeries[];
  unit?: string;
  height?: number;
  stacked?: boolean;
  bars?: boolean;
  markers?: TimeMarker[];
  ranges?: TimeRange[];
  /** label of the range applied initially (default: last of `ranges`, or all) */
  defaultRange?: string;
  zoom?: boolean;
  jump?: boolean;
  xFormat?: XFormat;
  /** show a total in the readout (stacked mode default true) */
  showTotal?: boolean;
  /** decimals hint for the readout; default smart formatting */
  ariaLabel?: string;
  /** y axis includes zero for positive data (default true); false fits the visible window (prices) */
  yZero?: boolean;
  /** built-in crosshair readout (default true) */
  readout?: boolean;
  /** "Drag to zoom" footer hint (default true when zoom is on) */
  foot?: boolean;
  /** controlled x window (seconds); applied on mount, on data change and whenever it changes */
  view?: { min: number; max: number } | null;
  /** called whenever the visible x window changes (zoom, ranges, view) */
  onRange?: (min: number, max: number) => void;
  /** called with the cursor index into `x` (null = cursor left the plot) */
  onCursor?: (i: number | null) => void;
  /** called when a marker that has an `id` is clicked */
  onMarker?: (m: TimeMarker) => void;
}

export const DAY = 86400;
export const YEAR = 365.25 * DAY;

const MONO = '11px "IBM Plex Mono", ui-monospace, monospace';
const MUTED = '#7d8a99';
const GRID = 'rgba(255,255,255,0.06)';
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** x-axis labels, day first like every other date of the site (uPlot's default writes 3/14). */
const DATE_AXIS = [
  [365 * DAY, '{YYYY}', null, null, null, null, null, null, 1],
  [28 * DAY, '{MMM}', '\n{YYYY}', null, null, null, null, null, 1],
  [DAY, '{D} {MMM}', '\n{YYYY}', null, null, null, null, null, 1],
  [3600, '{HH}:{mm}', '\n{D} {MMM} {YYYY}', null, '\n{D} {MMM}', null, null, null, 1],
];

/** Pointer tolerance around a point marker, CSS px. */
const HIT = 5;
/** Period ribbons along the bottom of the plot: height, gap and number of rows, CSS px. */
const RIBBON = { h: 3, gap: 2, rows: 4 };
/** Rows of the hover list before "+ n more". */
const MK_ROWS = 5;

interface Band {
  m: TimeMarker;
  x1: number;
  x2: number;
  row: number;
}

/** Ribbon rows for subtle periods: each takes the lowest row free at its start (CSS px along x). */
function layoutBands(u: uPlot, markers: TimeMarker[]): Band[] {
  const ends: number[] = [];
  const out: Band[] = [];
  const list = markers.filter((m) => m.subtle && m.end != null).sort((a, b) => a.t - b.t);
  for (const m of list) {
    const x1 = u.valToPos(m.t, 'x');
    const x2 = Math.max(x1 + 2, u.valToPos(m.end!, 'x'));
    let row = ends.findIndex((e) => e <= x1 - 2);
    if (row < 0) row = ends.length < RIBBON.rows ? ends.length : ends.indexOf(Math.min(...ends));
    ends[row] = x2;
    out.push({ m, x1, x2, row });
  }
  return out;
}
/** Top of a ribbon row, CSS px from the top of the plot area. */
const ribbonTop = (plotH: number, row: number) => plotH - (row + 1) * (RIBBON.h + RIBBON.gap);

/**
 * Markers under the pointer: point events first (nearest first), then the periods that contain it
 * (most recent first). A long period therefore never hides the events inside it.
 */
function markersAt(u: uPlot, markers: TimeMarker[], left: number): TimeMarker[] {
  const pts: { m: TimeMarker; d: number }[] = [];
  const spans: TimeMarker[] = [];
  for (const m of markers) {
    const x1 = u.valToPos(m.t, 'x');
    if (m.end == null) {
      if (Math.abs(left - x1) <= HIT) pts.push({ m, d: Math.abs(left - x1) });
    } else {
      const x2 = u.valToPos(m.end, 'x');
      if (left >= Math.min(x1, x2) - 2 && left <= Math.max(x1, x2) + 2) spans.push(m);
    }
  }
  pts.sort((a, b) => a.d - b.d);
  spans.sort((a, b) => b.t - a.t);
  return [...pts.map((p) => p.m), ...spans];
}

/** The marker a click at (left, top) opens: the nearest point event, else the period whose ribbon is under the pointer. */
function clickTarget(u: uPlot, markers: TimeMarker[], left: number, top: number): TimeMarker | null {
  const pt = markersAt(u, markers, left).find((m) => m.end == null && m.id);
  if (pt) return pt;
  const plotH = u.over.clientHeight;
  for (const b of layoutBands(u, markers)) {
    const y = ribbonTop(plotH, b.row);
    if (b.m.id && left >= b.x1 - 2 && left <= b.x2 + 2 && top >= y - 3 && top <= y + RIBBON.h + 3) return b.m;
  }
  return null;
}

export function fmtTime(t: number, f: XFormat): string {
  const d = new Date(t * 1000);
  const y = d.getUTCFullYear();
  if (f === 'year') return String(y);
  if (f === 'month') return `${MON[d.getUTCMonth()]} ${y}`;
  return `${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${y}`;
}

/** "2026-02" / "2026-02-14" / "2026" -> seconds (UTC). */
export function parseDate(s: string): number {
  const [y, m = '1', d = '1'] = s.split('-');
  return Date.UTC(Number(y), Number(m) - 1, Number(d)) / 1000;
}

function axisNum(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e9) return `${+(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${+(v / 1e6).toFixed(1)}M`;
  if (a >= 1e4) return `${+(v / 1e3).toFixed(0)}k`;
  return String(+v.toFixed(a < 1 ? 2 : a < 10 ? 1 : 0));
}

export function TimeChart(props: TimeChartProps) {
  const { x, series, stacked, bars, markers, ranges, zoom = !bars, jump } = props;
  const xf: XFormat = props.xFormat ?? 'date';
  const height = props.height ?? 170;
  const host = useRef<HTMLDivElement>(null);
  const uref = useRef<uPlot | null>(null);
  const expected = useRef<[number, number] | null>(null);
  const [idx, setIdx] = useState<number | null>(null);
  const [mk, setMk] = useState<TimeMarker[]>([]);
  const [mkHot, setMkHot] = useState<TimeMarker | null>(null);
  const initial = props.defaultRange ?? (ranges && ranges.length ? ranges[ranges.length - 1].label : undefined);
  const [active, setActive] = useState<string | null>(initial ?? null);
  const markersRef = useRef<TimeMarker[]>([]);
  markersRef.current = markers ?? [];
  const cbRef = useRef({ onRange: props.onRange, onCursor: props.onCursor, onMarker: props.onMarker, view: props.view });
  cbRef.current = { onRange: props.onRange, onCursor: props.onCursor, onMarker: props.onMarker, view: props.view };
  const yZero = props.yZero !== false;
  const hasY2 = series.some((s) => s.scale === 'y2');

  const xMin = x[0];
  const xMax = x[x.length - 1];

  const data = useMemo(() => {
    const cols: (number | null)[][] = [];
    if (stacked) {
      const acc = x.map(() => 0);
      const cum = series.map((s) => s.values.map((v, i) => (acc[i] += v ?? 0)));
      // draw the tallest (total) first so lower layers paint over it
      for (let i = cum.length - 1; i >= 0; i--) cols.push(cum[i]);
    } else for (const s of series) cols.push(s.values);
    return [x, ...cols] as uPlot.AlignedData;
  }, [x, series, stacked]);

  const window_ = (u: uPlot, seconds: number | null) => {
    const mn = seconds == null ? xMin : Math.max(xMin, xMax - seconds);
    expected.current = [mn, xMax];
    u.setScale('x', { min: mn, max: xMax });
  };

  const applyRange = (label: string | null) => {
    const u = uref.current;
    if (!u) return;
    const r = ranges?.find((r) => r.label === label);
    window_(u, r ? r.seconds : null);
  };

  useEffect(() => {
    const el = host.current;
    if (!el || !x.length) return;
    let cancelled = false;
    let cleanup: (() => void) | null = null;
    // uPlot is loaded on demand so it stays out of the initial bundle
    Promise.all([import('uplot'), import('uplot/dist/uPlot.min.css')]).then(([mod]) => {
      if (cancelled) return;
      const uPlot = mod.default;
      const drawOrder = stacked ? [...series].reverse() : series;
      const yRange = (mn: number, mx: number): [number, number] => {
        if (!yZero && !stacked && !bars) {
          const pad = (mx - mn) * 0.08 || Math.abs(mx) * 0.05 || 1;
          return [mn - pad, mx + pad];
        }
        return [stacked || bars || mn > 0 ? Math.min(0, mn) : mn, mx + (mx - Math.min(0, mn)) * 0.08 || 1];
      };
      const stepGuess = x.length > 1 ? (xMax - xMin) / (x.length - 1) : YEAR;
      const opts: uPlot.Options = {
        width: Math.max(220, el.clientWidth),
        height,
        padding: [8, 6, 0, 0],
        legend: { show: false },
        cursor: {
          drag: { x: zoom, y: false, setScale: zoom },
          points: { size: 6, width: 1.5, fill: '#0a0f17' },
          bind: { dblclick: () => null },
        },
        select: { show: zoom, left: 0, top: 0, width: 0, height: 0 },
        scales: {
          x: {
            time: true,
            range: bars ? (_u, mn, mx) => [mn - stepGuess / 2, mx + stepGuess / 2] : undefined,
          },
          y: { range: (_u, mn, mx) => yRange(mn, mx) },
          ...(hasY2 ? { y2: { range: (_u: uPlot, mn: number, mx: number) => yRange(mn, mx) } } : {}),
        },
        axes: [
          {
            stroke: MUTED,
            font: MONO,
            grid: { stroke: GRID, width: 1 },
            ticks: { show: false },
            size: 40,
            gap: 2,
            ...(xf === 'year' ? { values: (_u: uPlot, sp: number[]) => sp.map((v) => String(new Date(v * 1000).getUTCFullYear())) } : { values: DATE_AXIS }),
          },
          {
            stroke: MUTED,
            font: MONO,
            grid: { stroke: GRID, width: 1 },
            ticks: { show: false },
            size: 40,
            gap: 4,
            values: (_u: uPlot, sp: number[]) => sp.map(axisNum),
          },
          ...(hasY2
            ? [
                {
                  scale: 'y2',
                  side: 1,
                  stroke: MUTED,
                  font: MONO,
                  grid: { show: false },
                  ticks: { show: false },
                  size: 44,
                  gap: 4,
                  values: (_u: uPlot, sp: number[]) => sp.map(axisNum),
                } as uPlot.Axis,
              ]
            : []),
        ],
        series: [
          {},
          ...drawOrder.map((s) => ({
            label: s.label,
            scale: s.scale ?? 'y',
            stroke: s.color,
            width: bars ? 0 : 1.5,
            fill: bars ? s.color + 'cc' : stacked ? s.color + '55' : undefined,
            points: { show: false },
            spanGaps: true,
            paths: bars ? uPlot.paths.bars!({ size: [0.72, 60], radius: 0.15 }) : undefined,
          })),
        ],
        hooks: {
          setCursor: [
            (u) => {
              const i = u.cursor.idx;
              setIdx(i == null ? null : i);
              cbRef.current.onCursor?.(i == null ? null : i);
              const left = u.cursor.left;
              const top = u.cursor.top;
              const hits = left != null && left >= 0 ? markersAt(u, markersRef.current, left) : [];
              setMk((prev) => (prev.length === hits.length && prev.every((m, k) => m === hits[k]) ? prev : hits));
              const hot = cbRef.current.onMarker && left != null && left >= 0 && top != null ? clickTarget(u, markersRef.current, left, top) : null;
              setMkHot(hot);
              u.over.style.cursor = hot ? 'pointer' : '';
            },
          ],
          setScale: [
            (u, key) => {
              if (key !== 'x') return;
              cbRef.current.onRange?.(u.scales.x.min ?? xMin, u.scales.x.max ?? xMax);
              const e = expected.current;
              if (e && Math.abs((u.scales.x.min ?? 0) - e[0]) < 1 && Math.abs((u.scales.x.max ?? 0) - e[1]) < 1) return;
              setActive(null);
            },
          ],
          draw: [
            (u) => {
              const ctx = u.ctx;
              const { left, top, width, height: h } = u.bbox;
              const dpr = devicePixelRatio || 1;
              ctx.save();
              ctx.beginPath();
              ctx.rect(left, top, width, h);
              ctx.clip();
              // subtle periods: ribbons along the bottom, so that a long one covers no point marker
              for (const b of layoutBands(u, markersRef.current)) {
                ctx.fillStyle = (b.m.color ?? '#ff5c7a') + 'd9';
                ctx.fillRect(left + b.x1 * dpr, top + ribbonTop(h / dpr, b.row) * dpr, Math.max(2 * dpr, (b.x2 - b.x1) * dpr), RIBBON.h * dpr);
              }
              for (const m of markersRef.current) {
                if (m.subtle && m.end != null) continue;
                const c = m.color ?? '#ff5c7a';
                const x1 = u.valToPos(m.t, 'x', true);
                if (m.end != null) {
                  const x2 = u.valToPos(m.end, 'x', true);
                  ctx.fillStyle = c + '1f';
                  ctx.fillRect(x1, top, Math.max(1, x2 - x1), h);
                }
                ctx.strokeStyle = c + (m.subtle ? '8c' : 'cc');
                ctx.lineWidth = dpr;
                ctx.setLineDash([3 * dpr, 3 * dpr]);
                ctx.beginPath();
                ctx.moveTo(x1, top);
                ctx.lineTo(x1, top + h);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.fillStyle = c;
                if (m.subtle) ctx.fillRect(x1 - 2 * dpr, top, 4 * dpr, 4 * dpr);
                else {
                  ctx.beginPath();
                  ctx.moveTo(x1 - 4 * dpr, top);
                  ctx.lineTo(x1 + 4 * dpr, top);
                  ctx.lineTo(x1, top + 7 * dpr);
                  ctx.fill();
                }
              }
              ctx.restore();
            },
          ],
        },
      };
      const u = new uPlot(opts, data, el);
      uref.current = u;
      u.over.addEventListener('dblclick', () => {
        setActive(initial ?? null);
        window_(u, ranges?.find((r) => r.label === initial)?.seconds ?? null);
      });
      // touch: a tap or a drag on the chart moves the cursor and shows the readout
      const touchRead = (ev: TouchEvent) => {
        const t = ev.touches[0];
        if (!t) return;
        const r = u.over.getBoundingClientRect();
        u.setCursor({ left: Math.max(0, Math.min(r.width, t.clientX - r.left)), top: Math.max(0, Math.min(r.height, t.clientY - r.top)) });
      };
      u.over.addEventListener('touchstart', touchRead, { passive: true });
      u.over.addEventListener('touchmove', touchRead, { passive: true });
      u.over.addEventListener('mouseleave', () => {
        cbRef.current.onCursor?.(null);
        setIdx(null);
        setMk([]);
        setMkHot(null);
      });
      // a click (not the end of a drag-zoom) on a marker opens it
      let downX = 0;
      u.over.addEventListener('mousedown', (ev) => {
        downX = ev.clientX;
      });
      u.over.addEventListener('click', (ev) => {
        const cb = cbRef.current.onMarker;
        if (!cb || Math.abs(ev.clientX - downX) > 3) return;
        const r = u.over.getBoundingClientRect();
        const hit = clickTarget(u, markersRef.current, ev.clientX - r.left, ev.clientY - r.top);
        if (hit) cb(hit);
      });
      const v0 = cbRef.current.view;
      if (v0) {
        expected.current = [v0.min, v0.max];
        u.setScale('x', { min: v0.min, max: v0.max });
      } else if (initial) {
        const r = ranges?.find((r) => r.label === initial);
        if (r) window_(u, r.seconds);
      }
      const ro = new ResizeObserver(() => {
        const w = el.clientWidth;
        if (w > 0 && Math.abs(w - u.width) > 1) u.setSize({ width: w, height });
      });
      ro.observe(el);
      cleanup = () => {
        ro.disconnect();
        u.destroy();
        if (uref.current === u) uref.current = null;
      };
    });
    return () => {
      cancelled = true;
      cleanup?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, height, bars, stacked, zoom, xf, yZero, hasY2]);

  // controlled window
  const vmin = props.view?.min;
  const vmax = props.view?.max;
  useEffect(() => {
    const u = uref.current;
    if (!u || vmin == null || vmax == null) return;
    if (Math.abs((u.scales.x.min ?? 0) - vmin) < 1 && Math.abs((u.scales.x.max ?? 0) - vmax) < 1) return;
    expected.current = [vmin, vmax];
    u.setScale('x', { min: vmin, max: vmax });
    setActive(null);
  }, [vmin, vmax]);

  // redraw when markers change (e.g. loaded after the chart)
  useEffect(() => {
    uref.current?.redraw(false);
  }, [markers]);

  const jumpTo = (v: string) => {
    const u = uref.current;
    if (!u || !v) return;
    const c = parseDate(v) + 15 * DAY;
    const cur = (u.scales.x.max ?? xMax) - (u.scales.x.min ?? xMin);
    const extent = xMax - xMin;
    const w = cur >= extent * 0.8 ? Math.max(extent * 0.15, 90 * DAY) : cur;
    let mn = c - w / 2;
    let mx = c + w / 2;
    if (mn < xMin) [mn, mx] = [xMin, xMin + w];
    if (mx > xMax) [mn, mx] = [xMax - w, xMax];
    mn = Math.max(xMin, mn);
    mx = Math.min(xMax, mx);
    expected.current = [mn, mx];
    u.setScale('x', { min: mn, max: mx });
    setActive(null);
  };

  const i = idx ?? (x.length ? x.length - 1 : null);
  const live = idx != null;
  const unit = props.unit ? ` ${props.unit}` : '';
  const total = stacked && props.showTotal !== false && i != null ? series.reduce((a, s) => a + (s.values[i] ?? 0), 0) : null;
  const jumpMin = x.length ? new Date(xMin * 1000).toISOString().slice(0, 7) : undefined;
  const jumpMax = x.length ? new Date(xMax * 1000).toISOString().slice(0, 7) : undefined;
  const hasTools = (ranges && ranges.length > 0) || jump;

  return (
    <div class="tc" role="img" aria-label={props.ariaLabel ?? 'Time series chart'}>
      {hasTools && (
        <div class="tc-tools">
          {ranges && ranges.length > 0 && (
            <div class="tc-ranges" role="group" aria-label="Time range">
              {ranges.map((r) => (
                <button
                  key={r.label}
                  class="tc-btn"
                  aria-pressed={active === r.label}
                  onClick={() => {
                    setActive(r.label);
                    applyRange(r.label);
                  }}
                >
                  {r.label}
                </button>
              ))}
            </div>
          )}
          {jump && (
            <label class="tc-jump" title="Jump to a month">
              <span>Go to</span>
              <input type="month" min={jumpMin} max={jumpMax} onChange={(e) => jumpTo((e.target as HTMLInputElement).value)} />
            </label>
          )}
        </div>
      )}
      {props.readout !== false && (
      <div class="tc-readout" aria-live="off">
        {i != null && x[i] != null ? (
          <>
            <span class="tc-date num">{fmtTime(x[i], xf)}</span>
            {series.map((s) => (
              <span class="tc-item" key={s.label}>
                <i style={{ background: s.color }} />
                <span class="tc-lab">{s.label}</span>
                <b class="num">{s.values[i] == null ? '—' : fmt(s.values[i])}</b>
              </span>
            ))}
            {total != null && (
              <span class="tc-item tc-total">
                <span class="tc-lab">Total</span>
                <b class="num">{fmt(total)}</b>
              </span>
            )}
            {unit && <span class="tc-unit">{props.unit}</span>}
            {!live && series.length > 0 && <span class="tc-hint">latest</span>}
          </>
        ) : null}
      </div>
      )}
      <div class="tc-mk" style={{ visibility: mk.length ? 'visible' : 'hidden' }}>
        {mk.length ? (
          <div class="tc-mk-list">
            {mk.slice(0, MK_ROWS).map((m, k) => (
              <div class="tc-mk-row" key={k}>
                <i style={{ background: m.color ?? '#ff5c7a' }} />
                <span>
                  {m.title}
                  {m.tag && <small> · {m.tag}</small>}
                  {m === mkHot && <small> · click to open</small>}
                </span>
              </div>
            ))}
            {mk.length > MK_ROWS && <div class="tc-mk-row tc-mk-more">+ {mk.length - MK_ROWS} more: zoom in to separate them</div>}
          </div>
        ) : (
          ' '
        )}
      </div>
      <div ref={host} class="tc-plot" style={{ height: `${height}px` }} />
      {zoom && props.foot !== false && (
        <div class="tc-foot">{TOUCH ? 'Touch the chart to read values · the range buttons zoom' : 'Drag to zoom · double-click to reset'}</div>
      )}
    </div>
  );
}
