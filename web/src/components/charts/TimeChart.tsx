/**
 * Reusable uPlot time-series wrapper in the Abyssal style.
 * x = unix timestamps in seconds. Supports lines, stacked areas, bars, a crosshair
 * readout (instead of uPlot's legend), event markers, range buttons, drag-to-zoom
 * (double-click resets) and a "jump to date" month input.
 */
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import { fmt } from '../../lib/format';

export interface TimeSeries {
  label: string;
  values: (number | null)[];
  color: string;
}

export interface TimeMarker {
  /** seconds */
  t: number;
  /** optional end (seconds) draws a shaded band */
  end?: number;
  title: string;
  color?: string;
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
}

export const DAY = 86400;
export const YEAR = 365.25 * DAY;

const MONO = '10.5px "IBM Plex Mono", ui-monospace, monospace';
const MUTED = '#7d8a99';
const GRID = 'rgba(255,255,255,0.06)';
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

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
  const [mk, setMk] = useState<TimeMarker | null>(null);
  const initial = props.defaultRange ?? (ranges && ranges.length ? ranges[ranges.length - 1].label : undefined);
  const [active, setActive] = useState<string | null>(initial ?? null);
  const markersRef = useRef<TimeMarker[]>([]);
  markersRef.current = markers ?? [];

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
    const drawOrder = stacked ? [...series].reverse() : series;
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
        y: { range: (_u, mn, mx) => [stacked || bars || mn > 0 ? Math.min(0, mn) : mn, mx + (mx - Math.min(0, mn)) * 0.08 || 1] },
      },
      axes: [
        {
          stroke: MUTED,
          font: MONO,
          grid: { stroke: GRID, width: 1 },
          ticks: { show: false },
          size: 34,
          gap: 2,
          ...(xf === 'year' ? { values: (_u: uPlot, sp: number[]) => sp.map((v) => String(new Date(v * 1000).getUTCFullYear())) } : {}),
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
      ],
      series: [
        {},
        ...drawOrder.map((s) => ({
          label: s.label,
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
            const left = u.cursor.left;
            let hit: TimeMarker | null = null;
            if (left != null && left >= 0) {
              for (const m of markersRef.current) {
                const x1 = u.valToPos(m.t, 'x');
                const x2 = m.end != null ? u.valToPos(m.end, 'x') : x1;
                if (left >= Math.min(x1, x2) - 5 && left <= Math.max(x1, x2) + 5) {
                  hit = m;
                  break;
                }
              }
            }
            setMk(hit);
          },
        ],
        setScale: [
          (u, key) => {
            if (key !== 'x') return;
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
            for (const m of markersRef.current) {
              const c = m.color ?? '#ff5c7a';
              const x1 = u.valToPos(m.t, 'x', true);
              if (m.end != null) {
                const x2 = u.valToPos(m.end, 'x', true);
                ctx.fillStyle = c + '1f';
                ctx.fillRect(x1, top, Math.max(1, x2 - x1), h);
              }
              ctx.strokeStyle = c + 'cc';
              ctx.lineWidth = dpr;
              ctx.setLineDash([3 * dpr, 3 * dpr]);
              ctx.beginPath();
              ctx.moveTo(x1, top);
              ctx.lineTo(x1, top + h);
              ctx.stroke();
              ctx.setLineDash([]);
              ctx.fillStyle = c;
              ctx.beginPath();
              ctx.moveTo(x1 - 4 * dpr, top);
              ctx.lineTo(x1 + 4 * dpr, top);
              ctx.lineTo(x1, top + 7 * dpr);
              ctx.fill();
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
    u.over.addEventListener('mouseleave', () => {
      setIdx(null);
      setMk(null);
    });
    if (initial) {
      const r = ranges?.find((r) => r.label === initial);
      if (r) window_(u, r.seconds);
    }
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth;
      if (w > 0 && Math.abs(w - u.width) > 1) u.setSize({ width: w, height });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      u.destroy();
      uref.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, height, bars, stacked, zoom, xf]);

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
      <div class="tc-mk" style={{ visibility: mk ? 'visible' : 'hidden' }}>
        {mk ? (
          <>
            <i style={{ background: mk.color ?? '#ff5c7a' }} />
            {mk.title}
          </>
        ) : (
          ' '
        )}
      </div>
      <div ref={host} class="tc-plot" style={{ height: `${height}px` }} />
      {zoom && <div class="tc-foot">Drag to zoom · double-click to reset</div>}
    </div>
  );
}
