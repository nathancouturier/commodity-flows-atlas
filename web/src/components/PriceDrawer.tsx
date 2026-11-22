/**
 * Price explorer: a bottom drawer with a searchable series picker (up to 3 series, second axis when
 * units differ), a zoomable time chart, a date lookup ("1986", "Mar 2008", "2008-03-14"), key stats for
 * the visible window and toggleable freight-event markers. Every number carries its date and source.
 */
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { commodity, priceDrawer, priceSeries } from '../lib/store';
import { commodityMeta, sourceLabel } from '../lib/data';
import { FAMILY_COLOR, FAMILY_LABEL } from '../lib/format';
import { loadEvents } from '../lib/freight';
import {
  DAY_S,
  closePrices,
  defaultSeriesIds,
  fmtObsDate,
  fmtPct,
  firstAtOrAfter,
  periodStats,
  fmtPrice,
  loadPriceIndex,
  loadSeries,
  lowerBound,
  mergeSeries,
  nearestIndex,
  parseLookup,
  priceIndex,
  seriesForCommodity,
  type LoadedSeries,
  type ParsedDate,
  type PriceMeta,
} from '../lib/prices';
import { TimeChart, parseDate, type TimeMarker, type TimeSeries } from './charts/TimeChart';
import { CloseIcon } from './ui';
import type { Family, FreightEvent } from '../types';
import '../styles/drawers.css';

const PALETTE = ['#3ee6ff', '#ffb547', '#c7a3ff', '#7ee0a1', '#9db7ff'];
const MAX_SERIES = 3;
const RANGES = [
  { label: '1M', seconds: 30 * DAY_S, dailyOnly: true },
  { label: '1Y', seconds: 365.25 * DAY_S },
  { label: '5Y', seconds: 5 * 365.25 * DAY_S },
  { label: '20Y', seconds: 20 * 365.25 * DAY_S },
  { label: 'All', seconds: null as number | null },
];
const FAMILY_ORDER: Family[] = ['energy', 'metals', 'softs', 'freight'];
/** Price series keyed 'freight' (freight cost proxies) have no catalogue commodity. */
const famOf = (k: string): Family | undefined => (k === 'freight' ? 'freight' : commodityMeta(k)?.family);

interface Lookup {
  query: string;
  parsed: ParsedDate;
}
interface Win {
  min: number;
  max: number;
}

function pickColors(list: PriceMeta[]): string[] {
  const used = new Set<string>();
  return list.map((m) => {
    const fam = famOf(m.k);
    const pref = fam ? FAMILY_COLOR[fam] : undefined;
    const c = pref && !used.has(pref) && PALETTE.includes(pref) ? pref : PALETTE.find((p) => !used.has(p)) ?? PALETTE[0];
    used.add(c);
    return c;
  });
}

function endOfPeriod(p: ParsedDate): number {
  const d = new Date(p.t * 1000);
  if (p.precision === 'year') return Date.UTC(d.getUTCFullYear() + 1, 0, 1) / 1000 - DAY_S;
  if (p.precision === 'month') return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) / 1000 - DAY_S;
  return p.t;
}

function lookupLabel(p: ParsedDate): string {
  const d = new Date(p.t * 1000);
  const M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getUTCMonth()];
  if (p.precision === 'year') return String(d.getUTCFullYear());
  if (p.precision === 'month') return `${M} ${d.getUTCFullYear()}`;
  return `${d.getUTCDate()} ${M} ${d.getUTCFullYear()}`;
}

export function PriceDrawer() {
  const req = priceDrawer.value;
  const open = req !== null;
  const ids = priceSeries.value;
  const [everOpen, setEverOpen] = useState(false);
  const [data, setData] = useState<LoadedSeries[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState(0);
  const [view, setView] = useState<Win | null>(null);
  const [win, setWin] = useState<Win | null>(null);
  const [events, setEvents] = useState<FreightEvent[]>([]);
  const [showEvents, setShowEvents] = useState(true);
  const [indexed, setIndexed] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [query, setQuery] = useState('');
  const [queryErr, setQueryErr] = useState(false);
  const [noSeries, setNoSeries] = useState<string | null>(null);
  const [h, setH] = useState(160);
  const chartBox = useRef<HTMLDivElement>(null);
  const resetView = useRef(true);
  const pendingDate = useRef<string | null>(null);
  const rootRef = useRef<HTMLElement>(null);
  const reqKey = req?.nonce ?? 0;

  if (open && !everOpen) setEverOpen(true);

  // ---- apply an open request (commodity / explicit series / date)
  useEffect(() => {
    if (!req) return;
    let alive = true;
    loadPriceIndex().then(() => {
      if (!alive) return;
      const cur = priceSeries.peek();
      const k = req.commodity ?? commodity.peek();
      let next = cur;
      setNoSeries(null);
      if (req.series?.length) next = req.series.slice(0, MAX_SERIES);
      else if (!cur.length) next = defaultSeriesIds(k);
      else if (k && !cur.some((id) => priceIndex.value.find((m) => m.id === id)?.k === k)) {
        if (seriesForCommodity(k).length) next = defaultSeriesIds(k);
        else if (req.commodity) setNoSeries(commodityMeta(k)?.name ?? k);
      }
      if (next.join() !== cur.join()) {
        priceSeries.value = next;
        resetView.current = true;
        setFocus(0);
        setLookup(null);
        setQuery('');
      }
      if (req.date) pendingDate.current = req.date;
    });
    return () => {
      alive = false;
    };
  }, [reqKey]);

  // ---- load the selected series lazily
  useEffect(() => {
    if (!ids.length) return;
    let alive = true;
    setLoading(true);
    Promise.all(ids.map(loadSeries))
      .then((r) => {
        if (!alive) return;
        setData(r);
        setError(null);
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setError(String(e.message ?? e));
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [ids.join()]);

  useEffect(() => {
    if (open && !events.length) loadEvents().then(setEvents).catch(() => undefined);
  }, [open]);

  // ---- derived chart data
  const ready = data.length > 0;
  const merged = useMemo(() => (ready ? mergeSeries(data) : null), [data, ready]);
  const colors = useMemo(() => pickColors(data.map((d) => d.meta)), [data]);
  // "Index to 100": each series rebased at the first observation inside the visible range
  const baseKey = indexed && win ? data.map((d) => firstAtOrAfter(d, win.min)).join() : '';
  const chartSeries: TimeSeries[] = useMemo(() => {
    if (!merged) return [];
    const u0 = data[0].meta.unit;
    const second = data.find((d) => d.meta.unit !== u0)?.meta.unit;
    const bases = baseKey ? baseKey.split(',').map((k, i) => (Number(k) >= 0 ? data[i].v[Number(k)]! : null)) : null;
    return data.map((d, i) => ({
      label: bases ? `${d.meta.name} (index)` : d.meta.name,
      values: bases ? merged.cols[i].map((v) => (v == null || bases[i] == null ? null : (v / bases[i]!) * 100)) : merged.cols[i],
      color: colors[i],
      scale: bases || d.meta.unit === u0 || d.meta.unit !== second ? 'y' : 'y2',
    }));
  }, [merged, data, colors, baseKey]);
  const xMin = merged ? merged.x[0] : 0;
  const xMax = merged ? merged.x[merged.x.length - 1] : 0;
  const hasDaily = data.some((d) => d.meta.freq === 'D');

  // default window once data is there
  useEffect(() => {
    if (!merged) return;
    if (resetView.current || !view) {
      resetView.current = false;
      const w = { min: Math.max(xMin, xMax - 20 * 365.25 * DAY_S), max: xMax };
      setView(w);
      setWin(w);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [merged]);

  // ---- lookup
  const windowAround = (p: ParsedDate): Win => {
    const yr = 365.25 * DAY_S;
    let centre = p.t;
    let half: number;
    if (p.precision === 'year') {
      centre = p.t + yr / 2;
      half = 0.75 * yr;
    } else if (p.precision === 'month') {
      centre = p.t + 15 * DAY_S;
      half = hasDaily ? 75 * DAY_S : 3 * yr;
    } else half = hasDaily ? 45 * DAY_S : 3 * yr;
    const span = Math.min(half * 2, xMax - xMin);
    let mn = centre - span / 2;
    let mx = centre + span / 2;
    if (mn < xMin) [mn, mx] = [xMin, xMin + span];
    if (mx > xMax) [mn, mx] = [xMax - span, xMax];
    return { min: mn, max: mx };
  };

  const runLookup = (text: string) => {
    const p = parseLookup(text);
    if (!p) {
      setQueryErr(true);
      return;
    }
    setQueryErr(false);
    setLookup({ query: text, parsed: p });
    if (merged) setView(windowAround(p));
  };

  useEffect(() => {
    if (merged && pendingDate.current) {
      const t = pendingDate.current;
      pendingDate.current = null;
      setQuery(t);
      runLookup(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [merged, reqKey]);

  const lookupRows = useMemo(() => {
    if (!lookup || !ready) return null;
    return data.map((d, i) => ({ ...rowAt(d, colors[i], lookup.parsed.t), period: periodAt(d, lookup.parsed) }));
  }, [lookup, data, colors, ready]);

  const hoverRows = useMemo(() => {
    if (hover == null || !merged) return null;
    const t = merged.x[hover];
    if (t == null) return null;
    return data.map((d, i) => rowAt(d, colors[i], t));
  }, [hover, merged, data, colors]);

  // ---- stats for the focused series over the visible window
  const fi = Math.min(focus, data.length - 1);
  const fs = ready ? data[fi] : null;
  const stats = useMemo(() => {
    if (!fs || !win) return null;
    const lo = lowerBound(fs.x, win.min - 1);
    let first = -1;
    let last = -1;
    let mn = -1;
    let mx = -1;
    for (let i = lo; i < fs.x.length && fs.x[i] <= win.max + 1; i++) {
      const v = fs.v[i];
      if (v == null) continue;
      if (first < 0) first = i;
      last = i;
      if (mn < 0 || v < fs.v[mn]!) mn = i;
      if (mx < 0 || v > fs.v[mx]!) mx = i;
    }
    if (first < 0) return null;
    const f = fs.meta.freq;
    const d = (i: number) => fmtObsDate(fs.x[i], f);
    const change = fs.v[first]! !== 0 ? (fs.v[last]! / fs.v[first]! - 1) * 100 : null;
    return {
      last: { v: fs.v[last]!, d: d(last) },
      first: { d: d(first) },
      change,
      min: { v: fs.v[mn]!, d: d(mn) },
      max: { v: fs.v[mx]!, d: d(mx) },
      n: last - first + 1,
    };
  }, [fs, win]);

  // ---- markers
  const markers: TimeMarker[] = useMemo(() => {
    const m: TimeMarker[] = [];
    if (showEvents && merged) {
      for (const e of events) {
        const t = parseDate(e.date);
        const end = e.end ? parseDate(e.end) : undefined;
        if ((end ?? t) < xMin || t > xMax) continue;
        m.push({ t, end, title: `${e.date}${e.end ? ' to ' + e.end : ''} · ${e.title}`, color: '#8d9fb3', subtle: true });
      }
    }
    if (lookup) {
      const e = endOfPeriod(lookup.parsed);
      m.push({
        t: lookup.parsed.t,
        end: e > lookup.parsed.t ? e : undefined,
        title: `Lookup · ${lookupLabel(lookup.parsed)}`,
        color: '#3ee6ff',
      });
    }
    return m;
  }, [events, showEvents, lookup, merged, xMin, xMax]);

  // ---- chart height follows its box
  useEffect(() => {
    const el = chartBox.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const next = Math.max(120, Math.round((el.clientHeight - 20) / 6) * 6);
      setH((p) => (Math.abs(p - next) >= 6 ? next : p));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [everOpen]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !(e.target as HTMLElement)?.closest?.('.pd-pop')) closePrices();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const setIds = (next: string[]) => {
    priceSeries.value = next;
    setFocus((f) => Math.min(f, next.length - 1));
  };
  const rangeActive = (r: (typeof RANGES)[number]) => {
    if (!win || !merged) return false;
    const tol = 4 * DAY_S;
    if (Math.abs(win.max - xMax) > tol) return false;
    const want = r.seconds == null ? xMin : Math.max(xMin, xMax - r.seconds);
    return Math.abs(win.min - want) < tol;
  };

  const meta = priceIndex.value;
  const shown = RANGES.filter((r) => !r.dailyOnly || hasDaily);
  const lookupBlock: Row[] | null = hoverRows ?? lookupRows;

  return (
    <section
      ref={rootRef}
      class={`pd glass${open ? ' open' : ''}`}
      aria-label="Price explorer"
      aria-hidden={!open}
    >
      {everOpen && (
        <div class="pd-grid">
          <div class="pd-main">
            <div class="pd-head">
              <div class="pd-chips" role="group" aria-label="Selected price series">
                {data.map((d, i) => (
                  <span class={`pd-chip${i === fi ? ' on' : ''}`} key={d.meta.id} style={{ '--c': colors[i] }}>
                    <button
                      class="pd-chip-main"
                      aria-pressed={i === fi}
                      title="Show statistics for this series"
                      onClick={() => setFocus(i)}
                    >
                      <i />
                      <span class="pd-chip-name" title={d.meta.name}>{d.meta.name}</span>
                      <small class="num" title={chartSeries[i]?.scale === 'y2' ? 'Plotted on the right axis' : undefined}>
                        {indexed ? 'index' : d.meta.unit}
                        {chartSeries[i]?.scale === 'y2' ? ' · R' : ''}
                      </small>
                    </button>
                    {data.length > 1 && (
                      <button class="pd-chip-x" aria-label={`Remove ${d.meta.name}`} onClick={() => setIds(ids.filter((x) => x !== d.meta.id))}>
                        <CloseIcon />
                      </button>
                    )}
                  </span>
                ))}
              </div>
              <button class="pd-close" aria-label="Close price explorer" onClick={closePrices}>
                <CloseIcon />
              </button>
            </div>

            <div class="pd-tools">
              <Picker meta={meta} ids={ids} onPick={(id) => setIds(ids.length >= MAX_SERIES ? ids.map((x, i) => (i === fi ? id : x)) : [...ids, id])} onRemove={(id) => setIds(ids.filter((x) => x !== id))} />
              <div class="tc-ranges" role="group" aria-label="Time range">
                {shown.map((r) => (
                  <button
                    key={r.label}
                    class="tc-btn"
                    aria-pressed={rangeActive(r)}
                    disabled={!merged}
                    onClick={() => merged && setView({ min: r.seconds == null ? xMin : Math.max(xMin, xMax - r.seconds), max: xMax })}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
              <form
                class={`pd-lookup${queryErr ? ' bad' : ''}`}
                onSubmit={(e) => {
                  e.preventDefault();
                  runLookup(query);
                }}
              >
                <label>
                  <span>Date</span>
                  <input
                    type="text"
                    inputMode="text"
                    value={query}
                    placeholder="1986 · Mar 2008 · 2008-03-14"
                    aria-label="Look up a date: year, month or day"
                    aria-invalid={queryErr}
                    autocomplete="off"
                    onInput={(e) => {
                      setQuery((e.target as HTMLInputElement).value);
                      setQueryErr(false);
                    }}
                  />
                </label>
                <button type="submit" class="tc-btn pd-go" disabled={!merged || !query.trim()}>
                  Go
                </button>
                {queryErr && <em role="alert">Try 1986, 2008-03 or 2008-03-14</em>}
              </form>
              <button class="pd-toggle" role="switch" aria-checked={indexed} onClick={() => setIndexed(!indexed)} title="Rebase every series to 100 at the start of the visible range, to compare series in different units">
                <span class="switch" aria-hidden="true" />
                Index to 100
              </button>
              <button class="pd-toggle" role="switch" aria-checked={showEvents} onClick={() => setShowEvents(!showEvents)} title="Freight and market events from the Atlas timeline">
                <span class="switch" aria-hidden="true" />
                Events
              </button>
            </div>

            <div class="pd-chart" ref={chartBox}>
              {error ? (
                <div class="pd-msg">Could not load the price series ({error}).</div>
              ) : merged ? (
                <TimeChart
                  x={merged.x}
                  series={chartSeries}
                  height={h}
                  zoom
                  yZero={false}
                  readout={false}
                  foot={false}
                  xFormat="date"
                  markers={markers}
                  view={view}
                  onCursor={setHover}
                  onRange={(min, max) => {
                    setWin((w) => (w && Math.abs(w.min - min) < 1 && Math.abs(w.max - max) < 1 ? w : { min, max }));
                    // keep the controlled view in step so that rebasing never snaps a drag-zoom back
                    if (indexed) setView((v) => (v && Math.abs(v.min - min) < 1 && Math.abs(v.max - max) < 1 ? v : { min, max }));
                  }}
                  ariaLabel={`Price chart: ${data.map((d) => d.meta.name).join(', ')}`}
                />
              ) : (
                <div class="pd-msg">{loading ? 'Loading prices…' : 'Pick a price series to begin.'}</div>
              )}
              {loading && merged && <span class="pd-loading">Loading…</span>}
            </div>

            <div class="pd-sources">
              {data.map((d, i) => (
                <div key={d.meta.id} class="pd-src" style={{ '--c': colors[i] }}>
                  <i />
                  <span>
                    {d.meta.name}: {sourceLabel(d.meta.s)}
                    {d.meta.basis ? ` · ${d.meta.basis}` : ''}
                    {d.meta.note ? ` · ${d.meta.note}` : ''} · {d.meta.unit} · {d.meta.freq === 'D' ? 'daily' : 'monthly'} {d.meta.start.slice(0, 7)} to {d.meta.end.slice(0, 7)}
                  </span>
                </div>
              ))}
              {indexed && <div class="pd-hint">Index: each series = 100 at the start of the visible range; readouts and statistics stay in native units.</div>}
              <div class="pd-hint">Drag to zoom · double-click resets · Esc closes</div>
            </div>
          </div>

          <aside class="pd-side">
            {noSeries && <div class="pd-note">No price series for {noSeries}; showing the previous selection.</div>}
            <div class="pd-stats" aria-label="Statistics for the visible range">
              <div class="pd-stats-head">
                {fs ? (
                  <>
                    <b>{fs.meta.name}</b>
                    <span>
                      {stats ? `${stats.first.d} to ${stats.last.d}` : 'no data in view'} · {sourceLabel(fs.meta.s)}
                    </span>
                  </>
                ) : (
                  <span>Visible range</span>
                )}
              </div>
              {stats && fs && (
                <div class="pd-tiles">
                  <Tile label="Last" value={fmtPrice(stats.last.v)} unit={fs.meta.unit} sub={stats.last.d} />
                  <Tile
                    label="Change"
                    value={stats.change == null ? '—' : fmtPct(stats.change)}
                    tone={stats.change == null ? undefined : stats.change >= 0 ? 'up' : 'down'}
                    sub={`since ${stats.first.d}`}
                  />
                  <Tile label="Low" value={fmtPrice(stats.min.v)} unit={fs.meta.unit} sub={stats.min.d} />
                  <Tile label="High" value={fmtPrice(stats.max.v)} unit={fs.meta.unit} sub={stats.max.d} />
                </div>
              )}
            </div>

            <div class="pd-read" aria-live="polite">
              <div class="pd-read-head">
                <span>{hoverRows ? 'At cursor' : lookup ? `Lookup · ${lookupLabel(lookup.parsed)}` : 'Readout'}</span>
                {lookup && !hoverRows && (
                  <button
                    class="pd-clear"
                    onClick={() => {
                      setLookup(null);
                      setQuery('');
                    }}
                  >
                    Clear
                  </button>
                )}
              </div>
              {lookupBlock ? (
                lookupBlock.map((r) => (
                  <div class="pd-row" key={r.name} style={{ '--c': r.color }}>
                    <i />
                    <span>
                      {r.period && (
                        <>
                          <b>{r.name}</b> · {r.period.label} {r.period.kind}{' '}
                          <b class="num pd-val">
                            {fmtPrice(r.period.avg)} {r.unit}
                          </b>{' '}
                          · low <b class="num">{fmtPrice(r.period.lo.v)}</b> ({r.period.lo.d}) · high <b class="num">{fmtPrice(r.period.hi.v)}</b> ({r.period.hi.d}) · {r.period.n}{' '}
                          {r.freq === 'M' ? 'monthly values' : 'observations'} · {r.source}
                          <br />
                          <span class="pd-near">Nearest single observation: </span>
                        </>
                      )}
                      {!r.period && (
                        <>
                          <b>{r.name}</b> ·{' '}
                        </>
                      )}
                      <span class="num">{r.date}</span> ·{' '}
                      <b class="num pd-val">
                        {r.value} {r.unit}
                      </b>
                      {r.freq === 'M' && ' (monthly average)'}
                      {!r.period && <> · {r.source}</>}
                      {r.gap && <em> · nearest observation, {r.gap} from the date asked</em>}
                    </span>
                  </div>
                ))
              ) : (
                <div class="pd-empty">Hover the chart, or type a year, month or day (for example 1986 or March 2008) to read the exact value.</div>
              )}
            </div>
          </aside>
        </div>
      )}
    </section>
  );
}

type Row = ReturnType<typeof rowAt> & { period?: ReturnType<typeof periodAt> };

function rowAt(d: LoadedSeries, color: string, t: number) {
  const i = nearestIndex(d, t);
  const f = d.meta.freq;
  if (i < 0) return { name: d.meta.name, color, freq: f, date: '—', value: '—', unit: d.meta.unit, source: sourceLabel(d.meta.s), gap: null as string | null };
  const gapDays = Math.abs(d.x[i] - t) / DAY_S;
  const limit = f === 'D' ? 7 : 45;
  return {
    name: d.meta.name,
    color,
    freq: f,
    date: fmtObsDate(d.x[i], f),
    value: fmtPrice(d.v[i]),
    unit: d.meta.unit,
    source: sourceLabel(d.meta.s),
    gap: gapDays > limit ? (gapDays > 400 ? `${(gapDays / 365.25).toFixed(1)} years` : `${Math.round(gapDays)} days`) : null,
  };
}

/** Average, low and high over the named year or month (year and month lookups only). */
function periodAt(d: LoadedSeries, p: ParsedDate) {
  if (p.precision === 'day') return null;
  const end = endOfPeriod(p) + DAY_S - 1;
  const st = periodStats(d, p.t, end);
  if (!st) return null;
  const f = d.meta.freq;
  return {
    label: lookupLabel(p),
    kind: f === 'M' ? 'average of monthly averages' : 'average',
    avg: st.avg,
    n: st.n,
    lo: { v: st.min.v, d: fmtObsDate(d.x[st.min.i], f) },
    hi: { v: st.max.v, d: fmtObsDate(d.x[st.max.i], f) },
  };
}

function Tile(props: { label: string; value: string; unit?: string; sub: string; tone?: 'up' | 'down' }) {
  return (
    <div class="pd-tile">
      <div class="pd-tile-l">{props.label}</div>
      <div class={`pd-tile-v num${props.tone ? ' ' + props.tone : ''}`}>
        {props.value}
        {props.unit && <small>{props.unit}</small>}
      </div>
      <div class="pd-tile-s num">{props.sub}</div>
    </div>
  );
}

function Picker(props: { meta: PriceMeta[]; ids: string[]; onPick: (id: string) => void; onRemove: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const wrap = useRef<HTMLSpanElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const full = props.ids.length >= MAX_SERIES;

  useEffect(() => {
    if (!open) return;
    setTimeout(() => input.current?.focus(), 0);
    const down = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setOpen(false);
        (wrap.current?.querySelector('.pd-add') as HTMLElement | null)?.focus();
      }
    };
    document.addEventListener('pointerdown', down);
    document.addEventListener('keydown', key, true);
    return () => {
      document.removeEventListener('pointerdown', down);
      document.removeEventListener('keydown', key, true);
    };
  }, [open]);

  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const out: { fam: Family; items: PriceMeta[] }[] = [];
    for (const fam of FAMILY_ORDER) {
      const items = props.meta.filter((m) => {
        const cm = commodityMeta(m.k);
        if ((famOf(m.k) ?? 'energy') !== fam) return false;
        if (!needle) return true;
        return `${m.name} ${cm?.name ?? ''} ${m.unit} ${m.id}`.toLowerCase().includes(needle);
      });
      if (items.length) out.push({ fam, items });
    }
    return out;
  }, [props.meta, q]);

  return (
    <span class="pd-pick" ref={wrap}>
      <button class="pd-add" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}>
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M6 1v10M1 6h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
        </svg>
        {full ? 'Series 3/3' : 'Add series'}
      </button>
      {open && (
        <div class="pd-pop" role="dialog" aria-label="Choose price series">
          <input
            ref={input}
            type="search"
            class="pd-search"
            placeholder="Search series, e.g. copper, TTF, USD/t"
            aria-label="Search price series"
            value={q}
            onInput={(e) => setQ((e.target as HTMLInputElement).value)}
          />
          <div class="pd-list" role="listbox" aria-multiselectable="true" aria-label="Price series">
            {groups.length === 0 && <div class="pd-empty">No series match.</div>}
            {groups.map((g) => (
              <div key={g.fam}>
                <div class="pd-fam" style={{ color: FAMILY_COLOR[g.fam] }}>
                  {FAMILY_LABEL[g.fam]}
                </div>
                {g.items.map((m) => {
                  const sel = props.ids.includes(m.id);
                  return (
                    <button
                      key={m.id}
                      role="option"
                      aria-selected={sel}
                      class="pd-opt"
                      title={[m.basis, full && !sel ? 'Replaces the series selected in the chips above' : ''].filter(Boolean).join(' · ') || undefined}
                      onClick={() => {
                        if (sel) {
                          if (props.ids.length > 1) props.onRemove(m.id);
                        } else props.onPick(m.id);
                        setOpen(false);
                      }}
                    >
                      <span class="pd-opt-name">
                        {m.name}
                        <small>{commodityMeta(m.k)?.name ?? m.k}</small>
                        {m.basis && <em class="pd-opt-basis">{m.basis}</em>}
                      </span>
                      <span class="pd-opt-meta num">
                        {m.unit} · {m.freq === 'D' ? 'daily' : 'monthly'} {m.start.slice(0, 4)}
                      </span>
                      {sel && <span class="pd-check" aria-hidden="true">✓</span>}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </span>
  );
}
