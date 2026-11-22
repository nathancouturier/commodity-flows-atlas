/**
 * Price explorer: a bottom drawer with a searchable series picker (up to 3 series; a second axis for two
 * units, an index beyond that), a zoomable time chart, a date lookup ("1986", "Q3 2008", "Mar 2008",
 * "14 Mar 2008"), key stats for the visible window and toggleable, clickable freight-event markers.
 * Every number carries its date and source.
 */
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { commodity, priceDrawer, priceSeries, select } from '../lib/store';
import { commodityMeta, sourceLabel } from '../lib/data';
import { FAMILY_COLOR, FAMILY_LABEL, TOUCH } from '../lib/format';
import { loadEvents } from '../lib/freight';
import {
  DAY_S,
  PRICE_COVERAGE_NOTE,
  closePrices,
  defaultSeriesIds,
  fmtObsDate,
  fmtPct,
  firstAtOrAfter,
  periodStats,
  fmtPrice,
  loadPriceIndex,
  loadSeries,
  lookupEnd,
  lowerBound,
  lowerName,
  mergeSeries,
  obsEnd,
  observationAt,
  parseLookup,
  priceIndex,
  seriesBounds,
  seriesCovering,
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

/** Same colours as the event pages and the history timeline. */
const EVENT_COLOR: Record<FreightEvent['kind'], string> = {
  conflict: '#ff5c7a',
  canal: '#3ee6ff',
  weather: '#9db7ff',
  policy: '#c7a3ff',
  accident: '#ff7a59',
  market: '#ffb547',
  infrastructure: '#7ee0a1',
};
const EVENT_KINDS = Object.keys(EVENT_COLOR) as FreightEvent['kind'][];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAY = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

/** "2022-02-24" -> "24 Feb 2022", "2020-10" -> "Oct 2020". */
function eventDate(s: string): string {
  const [y, m, d] = s.split('-');
  return m ? `${d ? `${Number(d)} ` : ''}${MON[Number(m) - 1]} ${y}` : y;
}

/** Start of the last day of the period a lookup names. */
function endOfPeriod(p: ParsedDate): number {
  return lookupEnd(p) - DAY_S;
}

function lookupLabel(p: ParsedDate): string {
  const d = new Date(p.t * 1000);
  const M = MON[d.getUTCMonth()];
  if (p.precision === 'year') return String(d.getUTCFullYear());
  if (p.precision === 'quarter') return `Q${d.getUTCMonth() / 3 + 1} ${d.getUTCFullYear()}`;
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
  const [openedFor, setOpenedFor] = useState<string | null>(null);
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
      setOpenedFor(k ?? null);
      if (req.series?.length) next = req.series.slice(0, MAX_SERIES);
      else if (k && !seriesForCommodity(k).length) {
        // no series for this commodity: say so, and never fall back to another commodity's price
        setNoSeries(lowerName(commodityMeta(k)?.name ?? k));
      } else if (!cur.length) next = defaultSeriesIds(k);
      else if (k && !cur.some((id) => priceIndex.value.find((m) => m.id === id)?.k === k)) next = defaultSeriesIds(k);
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
    if (!ids.length) {
      setData([]);
      return;
    }
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
  // two axes carry two units; with a third, the series are indexed rather than sharing an axis with an unrelated unit
  const unitCount = new Set(data.map((d) => d.meta.unit)).size;
  const forcedIndex = unitCount > 2;
  const idxOn = indexed || forcedIndex;
  // "Index to 100": each series rebased at the first observation inside the visible range
  const baseKey = idxOn && win ? data.map((d) => firstAtOrAfter(d, win.min)).join() : '';
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
    } else if (p.precision === 'quarter') {
      centre = p.t + 45 * DAY_S;
      half = hasDaily ? 120 * DAY_S : 3 * yr;
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
      // an answer left on screen under the error would read as the answer to the new question
      setQueryErr(true);
      setLookup(null);
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
    const p = lookup.parsed;
    const rows = data.map((d, i) => (p.precision === 'day' ? rowAt(d, colors[i], p.t) : periodRow(d, colors[i], p)));
    const answered = new Set(data.filter((_, i) => !rows[i].pre).map((d) => d.meta.k));
    // a series without data for the date names the other series of its commodity that have some, unless one is already charted
    return rows.map((r, i) => {
      if (!r.pre || answered.has(data[i].meta.k)) return r;
      // the same benchmark at another frequency first ("Brent crude" for "Brent crude, daily spot")
      const head = data[i].meta.name.split(/[ ,]/)[0];
      const same = (m: PriceMeta) => (m.name.split(/[ ,]/)[0] === head ? 0 : 1);
      return { ...r, offer: seriesCovering(data[i].meta.k, p.t, lookupEnd(p), ids).sort((a, b) => same(a) - same(b)).slice(0, 3) };
    });
    // priceIndex feeds the offers; it is loaded before any series
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lookup, data, colors, ready]);

  const hoverRows = useMemo(() => {
    if (hover == null || !merged) return null;
    const t = merged.x[hover];
    if (t == null) return null;
    return data.map((d, i) => rowAt(d, colors[i], t));
  }, [hover, merged, data, colors]);

  // ---- stats for every series over the visible window
  const fi = Math.min(focus, data.length - 1);
  const fs = ready ? data[fi] : null;
  const allStats = useMemo(() => (win ? data.map((d) => windowStats(d, win)) : []), [data, win]);
  const stats = allStats[fi] ?? null;

  // ---- markers
  const markers: TimeMarker[] = useMemo(() => {
    const m: TimeMarker[] = [];
    if (showEvents && merged) {
      for (const e of events) {
        const t = parseDate(e.date);
        const end = e.end ? parseDate(e.end) : undefined;
        if ((end ?? t) < xMin || t > xMax) continue;
        m.push({ t, end, id: e.id, title: `${eventDate(e.date)}${e.end ? ' to ' + eventDate(e.end) : ''} · ${e.title}`, tag: e.kind, color: EVENT_COLOR[e.kind], subtle: true });
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
    setNoSeries(null);
    setFocus((f) => Math.max(0, Math.min(f, next.length - 1)));
  };
  const full = ids.length >= MAX_SERIES;
  const addSeries = (id: string) => {
    if (!full && !ids.includes(id)) setIds([...ids, id]);
  };
  const readBox = useRef<HTMLDivElement>(null);
  // a lookup answers in the side column: bring the answer into view when the statistics above push it down
  useEffect(() => {
    if (lookup) readBox.current?.scrollIntoView?.({ block: 'nearest' });
  }, [lookup]);
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
      class={`pd glass${open ? ' open' : ''}${data.length >= MAX_SERIES ? ' pd-tall' : ''}`}
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
                        {idxOn ? 'index' : d.meta.unit}
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
              <Picker meta={meta} ids={ids} onPick={addSeries} onRemove={(id) => setIds(ids.filter((x) => x !== id))} />
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
                    placeholder="Year, month or day: Mar 2008"
                    aria-label="Look up a date: year, quarter, month or day"
                    title="A year (2008), a quarter (Q3 2008), a month (Mar 2008 or 2008-03) or a day (14 Mar 2008, 2008-03-14 or 14/03/2008)"
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
                {queryErr && <em role="alert">Not a date. Try 2008, Q3 2008, Mar 2008 or 14 Mar 2008</em>}
              </form>
              <button
                class="pd-toggle"
                role="switch"
                aria-checked={idxOn}
                disabled={forcedIndex}
                onClick={() => setIndexed(!indexed)}
                title={forcedIndex ? `${unitCount} different units cannot share two axes: the series are shown as an index` : 'Rebase every series to 100 at the start of the visible range, to compare series in different units'}
              >
                <span class="switch" aria-hidden="true" />
                Index to 100
              </button>
              <button class="pd-toggle" role="switch" aria-checked={showEvents} onClick={() => setShowEvents(!showEvents)} title="Freight and market events from the Atlas timeline">
                <span class="switch" aria-hidden="true" />
                Events
              </button>
            </div>

            {noSeries && data.length > 0 && (
              <div class="pd-note" role="status">
                No free price series for {noSeries} yet. The chart shows your previous selection: {data.map((d) => d.meta.name).join(', ')}.
              </div>
            )}
            {!noSeries && openedFor && PRICE_COVERAGE_NOTE[openedFor] && data.some((d) => d.meta.k === openedFor) && (
              <div class="pd-note" role="status">{PRICE_COVERAGE_NOTE[openedFor]}</div>
            )}
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
                  onMarker={(m) => m.id && select({ kind: 'event', id: m.id })}
                  view={view}
                  onCursor={setHover}
                  onRange={(min, max) => {
                    setWin((w) => (w && Math.abs(w.min - min) < 1 && Math.abs(w.max - max) < 1 ? w : { min, max }));
                    // keep the controlled view in step so that rebasing never snaps a drag-zoom back
                    if (idxOn) setView((v) => (v && Math.abs(v.min - min) < 1 && Math.abs(v.max - max) < 1 ? v : { min, max }));
                  }}
                  ariaLabel={`Price chart: ${data.map((d) => d.meta.name).join(', ')}`}
                />
              ) : (
                <div class="pd-msg">
                  {loading ? (
                    'Loading prices…'
                  ) : noSeries ? (
                    <span>
                      <b>No free price series for {noSeries} yet.</b>
                      <br />
                      Use "Add series" to chart another commodity.
                    </span>
                  ) : (
                    'Pick a price series to begin.'
                  )}
                </div>
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
              {idxOn && (
                <div class={forcedIndex ? 'pd-hint pd-warn' : 'pd-hint'}>
                  {forcedIndex ? `${unitCount} different units cannot share two axes, so the chart is indexed: ` : 'Index: '}
                  each series = 100 at the start of the visible range; readouts and statistics stay in native units.
                </div>
              )}
              {showEvents && merged && events.length > 0 && (
                <div class="pd-hint pd-kinds">
                  <span>Events:</span>
                  {EVENT_KINDS.map((k) => (
                    <span key={k} style={{ '--c': EVENT_COLOR[k] }}>
                      <i />
                      {k}
                    </span>
                  ))}
                  <span>· click a marker to open the event</span>
                </div>
              )}
              <div class="pd-hint">{TOUCH ? 'Touch the chart to read values · the range buttons zoom' : 'Drag to zoom · double-click resets · Esc closes'}</div>
            </div>
          </div>

          <aside class="pd-side">
            <div class="pd-stats" aria-label="Statistics for the visible range">
              {data.length <= 1 ? (
                <>
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
                </>
              ) : (
                <>
                  <div class="pd-st-g pd-st-cols">
                    <span>Last</span>
                    <span>Change</span>
                    <span>Low</span>
                    <span>High</span>
                  </div>
                  {data.map((d, i) => {
                    const st = allStats[i];
                    return (
                      <div class={`pd-st${i === fi ? ' on' : ''}`} key={d.meta.id} style={{ '--c': colors[i] }} title={sourceLabel(d.meta.s)}>
                        <div class="pd-st-h">
                          <i />
                          <b>{d.meta.name}</b>
                          <small class="num" title={d.meta.unit}>{d.meta.unit}</small>
                        </div>
                        {st ? (
                          <div class="pd-st-g">
                            <span>
                              <b class="num">{fmtPrice(st.last.v)}</b>
                              <small>{st.last.d}</small>
                            </span>
                            <span>
                              <b class={`num${st.change == null ? '' : st.change >= 0 ? ' up' : ' down'}`}>{st.change == null ? '—' : fmtPct(st.change)}</b>
                              <small>since {st.first.d}</small>
                            </span>
                            <span>
                              <b class="num">{fmtPrice(st.min.v)}</b>
                              <small>{st.min.d}</small>
                            </span>
                            <span>
                              <b class="num">{fmtPrice(st.max.v)}</b>
                              <small>{st.max.d}</small>
                            </span>
                          </div>
                        ) : (
                          <div class="pd-st-none">no data in view</div>
                        )}
                      </div>
                    );
                  })}
                </>
              )}
            </div>

            <div class="pd-read" aria-live="polite" ref={readBox}>
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
                  <div class="pd-row" key={r.id} style={{ '--c': r.color }}>
                    <i />
                    <span>
                      <b>{r.name}</b>
                      {r.pre && <em> · {r.pre}</em>}
                      {r.value != null && (
                        <>
                          {' · '}
                          {r.label}{' '}
                          <b class="num pd-val">
                            {r.value} {r.unit}
                          </b>
                        </>
                      )}
                      {r.detail && <> · {r.detail}</>}
                      {r.value != null && <> · {r.source}</>}
                      {r.post && <em> · {r.post}</em>}
                      {r.offer && r.offer.length > 0 && lookup && (
                        <span class="pd-offers">
                          Other {lowerName(commodityMeta(r.k)?.name ?? r.k)} series with data for {lookupLabel(lookup.parsed)}:
                          {r.offer.map((m) => (
                            <button
                              key={m.id}
                              class="pd-offer"
                              disabled={full}
                              title={full ? `${MAX_SERIES} series max: remove one to add this series` : 'Add this series to the chart'}
                              onClick={() => addSeries(m.id)}
                            >
                              {full ? '' : '+ '}
                              {m.name} · {m.freq === 'D' ? 'daily' : 'monthly'}, {m.start.slice(0, 4)} to {m.end.slice(0, 4)}
                            </button>
                          ))}
                        </span>
                      )}
                    </span>
                  </div>
                ))
              ) : (
                <div class="pd-empty">Hover the chart, or type a year, a quarter, a month or a day (for example 2008, Q3 2008 or 14 Mar 2008) to read the exact value.</div>
              )}
            </div>
          </aside>
        </div>
      )}
    </section>
  );
}

interface Row {
  id: string;
  /** commodity (or 'freight') of the series */
  k: string;
  name: string;
  color: string;
  unit: string;
  source: string;
  /** what the value is: "14 Mar 2008", "Mar 2008 monthly average", "2008 average" */
  label: string | null;
  value: string | null;
  /** low, high and count of a period */
  detail: string | null;
  /** caveat stated before the value (no data, not published yet) and after it (previous trading day, partial period) */
  pre: string | null;
  post: string | null;
  /** series of the same commodity that cover the date asked */
  offer?: PriceMeta[];
}

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;
/** "14 Mar 2008" for a daily quote; "Mar 2008 monthly average" for a monthly price ("monthly value" for an index). */
const obsLabel = (d: LoadedSeries, i: number) =>
  fmtObsDate(d.x[i], d.meta.freq) + (d.meta.freq !== 'M' ? '' : d.meta.unit.startsWith('index') ? ' monthly value' : ' monthly average');

function blankRow(d: LoadedSeries, color: string): Row {
  return { id: d.meta.id, k: d.meta.k, name: d.meta.name, color, unit: d.meta.unit, source: sourceLabel(d.meta.s), label: null, value: null, detail: null, pre: null, post: null };
}

/** Wording for a date outside the series. `asked` names the date or period ("Nov 2026", "21 Nov 2026"). */
function outside(d: LoadedSeries, row: Row, kind: 'before' | 'after', i: number, asked: string, askedStart: number): Row {
  const f = d.meta.freq;
  if (kind === 'before') return { ...row, pre: `no data before ${fmtObsDate(d.x[i], f)}, the start of this series` };
  // a past date just after the last value is a publication lag, not the end of the series: show the latest value, named as such
  const lag = askedStart - obsEnd(d.x[i], f);
  if (askedStart * 1000 <= Date.now() && lag <= (f === 'D' ? 14 : 92) * DAY_S)
    return { ...row, pre: `${asked} is not published yet`, label: `latest: ${obsLabel(d, i)}`, value: fmtPrice(d.v[i]) };
  return { ...row, pre: `no data after ${fmtObsDate(d.x[i], f)}, the latest value of this series` };
}

/** The value at one day (lookup by day, or the chart cursor): see observationAt for the rules. */
function rowAt(d: LoadedSeries, color: string, t: number): Row {
  const row = blankRow(d, color);
  const f = d.meta.freq;
  const o = observationAt(d, f, t);
  if (o.kind === 'missing') return { ...row, pre: 'no value at this date' };
  if (o.kind === 'before' || o.kind === 'after') return outside(d, row, o.kind, o.i, fmtObsDate(t, f), t);
  const out = { ...row, label: obsLabel(d, o.i), value: fmtPrice(d.v[o.i]) };
  if (o.kind !== 'previous') return out;
  const gap = Math.round((t - d.x[o.i]) / DAY_S);
  const day = `${WEEKDAY[new Date(t * 1000).getUTCDay()]} ${fmtObsDate(t, 'D')}`;
  return { ...out, post: gap <= 5 ? `previous trading day: no quote on ${day}` : `last quote before ${day}, ${gap} days earlier (gap in the series)` };
}

/** Average, low and high over the named year, quarter or month. */
function periodRow(d: LoadedSeries, color: string, p: ParsedDate): Row {
  const row = blankRow(d, color);
  const f = d.meta.freq;
  const b = seriesBounds(d);
  if (!b) return { ...row, pre: 'no value at this date' };
  const name = lookupLabel(p);
  const t1 = lookupEnd(p);
  const dataEnd = obsEnd(d.x[b.last], f);
  if (t1 <= d.x[b.first]) return outside(d, row, 'before', b.first, name, p.t);
  if (p.t >= dataEnd) return outside(d, row, 'after', b.last, name, p.t);
  const st = periodStats(d, p.t, t1 - 1);
  if (!st) return { ...row, pre: `no observations in ${name}` };
  // what is missing from the period: a late start, an early end (often a period still running), or gaps
  const caveats: string[] = [];
  // daily series: a year that opens or closes on a holiday or a weekend is not a partial year
  const slack = f === 'D' ? 5 * DAY_S : 0;
  if (d.x[b.first] > p.t + slack) caveats.push(`the series starts ${fmtObsDate(d.x[b.first], f)}`);
  if (dataEnd < t1 - slack) caveats.push(`data to ${fmtObsDate(d.x[b.last], f)}${t1 * 1000 > Date.now() ? ', period not finished' : ''}`);
  if (f === 'M') {
    const from = new Date(Math.max(p.t, d.x[b.first]) * 1000);
    const to = new Date(Math.min(t1, dataEnd) * 1000);
    const months = (to.getUTCFullYear() - from.getUTCFullYear()) * 12 + to.getUTCMonth() - from.getUTCMonth();
    if (st.n < months) caveats.push(`${st.n} of ${months} months have a value`);
  }
  const post = caveats.length ? `partial period: ${caveats.join('; ')}` : null;
  if (f === 'M' && p.precision === 'month') return { ...row, label: obsLabel(d, st.min.i), value: fmtPrice(st.avg), post };
  const on = (i: number) => fmtObsDate(d.x[i], f);
  return {
    ...row,
    label: f === 'M' ? `${name} average of ${plural(st.n, d.meta.unit.startsWith('index') ? 'monthly value' : 'monthly average')}` : `${name} average`,
    value: fmtPrice(st.avg),
    detail: `low ${fmtPrice(st.min.v)} (${on(st.min.i)}) · high ${fmtPrice(st.max.v)} (${on(st.max.i)})${f === 'M' ? '' : ` · ${plural(st.n, 'daily price')}`}`,
    post,
  };
}

/** Last, change, low and high of one series over the visible window. */
function windowStats(fs: LoadedSeries, win: Win) {
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
}

function Tile(props: { label: string; value: string; unit?: string; sub: string; tone?: 'up' | 'down' }) {
  return (
    <div class="pd-tile">
      <div class="pd-tile-l">{props.label}</div>
      <div class={`pd-tile-v num${props.tone ? ' ' + props.tone : ''}`}>
        {props.value}
        {props.unit && <small title={props.unit}>{props.unit}</small>}
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

  const option = (m: PriceMeta) => {
    const sel = props.ids.includes(m.id);
    // at the limit nothing is replaced silently: the other series are disabled until one is removed
    const blocked = full && !sel;
    return (
      <button
        key={m.id}
        role="option"
        aria-selected={sel}
        class="pd-opt"
        disabled={blocked}
        title={[m.basis, blocked ? `${MAX_SERIES} series max: remove one first` : sel ? 'Click to remove from the chart' : ''].filter(Boolean).join(' · ') || undefined}
        onClick={() => {
          if (sel) {
            // removing at the limit keeps the list open, to pick the replacement
            if (props.ids.length > 1) props.onRemove(m.id);
            if (!full) setOpen(false);
          } else {
            props.onPick(m.id);
            setOpen(false);
          }
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
  };

  return (
    <span class="pd-pick" ref={wrap}>
      <button
        class="pd-add"
        aria-haspopup="listbox"
        aria-expanded={open}
        title={full ? `${MAX_SERIES} series max: remove one to add another` : undefined}
        onClick={() => {
          // a search left from the last visit would hide the series shown and the note about the limit
          if (!open) setQ('');
          setOpen(!open);
        }}
      >
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M6 1v10M1 6h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
        </svg>
        {full ? `Series ${MAX_SERIES}/${MAX_SERIES}` : 'Add series'}
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
          {full && (
            <div class="pd-max" role="status">
              {MAX_SERIES} series max. Remove one of the series shown to add another.
            </div>
          )}
          <div class="pd-list" role="listbox" aria-multiselectable="true" aria-label="Price series">
            {full && !q.trim() && (
              <div>
                <div class="pd-fam">Shown now · click to remove</div>
                {props.ids.map((id) => props.meta.find((m) => m.id === id)).map((m) => m && option(m))}
              </div>
            )}
            {groups.length === 0 && <div class="pd-empty">No series match.</div>}
            {groups.map((g) => (
              <div key={g.fam}>
                <div class="pd-fam" style={{ color: FAMILY_COLOR[g.fam] }}>
                  {FAMILY_LABEL[g.fam]}
                </div>
                {g.items.map(option)}
              </div>
            ))}
          </div>
        </div>
      )}
    </span>
  );
}
