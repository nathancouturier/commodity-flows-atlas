/**
 * Price explorer: a bottom drawer with a searchable series picker (up to 3 series; a second axis for two
 * units, an index beyond that), a zoomable time chart, a date lookup ("1986", "Q3 2008", "Mar 2008",
 * "14 Mar 2008"), key stats for the visible window and toggleable, clickable freight-event markers.
 * Every number carries its date and source.
 */
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { commodity, priceDrawer, priceSeries, priceView, select } from '../lib/store';
import { commodityMeta, sourceLabel } from '../lib/data';
import { FAMILY_COLOR, TOUCH } from '../lib/format';
import { downloadPrices, priceSources } from '../lib/pricesCsv';
import { CsvAction } from './CsvAction';
import { loadEvents } from '../lib/freight';
import { eventShownForAny, useAlertEvents } from '../lib/events';
import {
  DAY_S,
  FREQ_WORD,
  GROUP_LABEL,
  GROUP_ORDER,
  PRICE_COVERAGE_NOTE,
  annualRun,
  annualWord,
  closePrices,
  defaultSeriesIds,
  findMeta,
  fmtObsDate,
  fmtPct,
  firstAtOrAfter,
  groupOf,
  inEstimate,
  isAnnualSeries,
  isLate,
  monthlyFrom,
  periodStats,
  fmtPrice,
  fmtSeriesValue,
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
  spreadMetas,
  type LoadedSeries,
  type ParsedDate,
  type PriceGroup,
  type PriceMeta,
} from '../lib/prices';
import { TimeChart, parseDate, parseEnd, type TimeMarker, type TimeSeries } from './charts/TimeChart';
import { PriceBoard, PriceStatusLine } from './PriceBoard';
import { CloseIcon } from './ui';
import type { FreightEvent } from '../types';
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
const SPREAD_GROUP = 'Spreads and ratios';
/** A series listed in the picker: a few words of its basis, the rest is in the side column. */
const shortBasis = (b: string): string => (b.length > 110 ? b.slice(0, 107).replace(/[\s,;(]+\S*$/, '') + '…' : b);
/** A deviation from a trend or an average (two freight indicators) crosses zero: it has no base to index on. */
const isDeviation = (m: PriceMeta): boolean => /deviation/i.test(m.unit);

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
    const fam = groupOf(m);
    const pref = fam !== 'index' ? FAMILY_COLOR[fam] : undefined;
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

/** The lookup as an address writes it: 2008, 2008-Q3, 2008-03, 2008-03-14 (parseLookup reads all four). */
function lookupKey(p: ParsedDate): string {
  const d = new Date(p.t * 1000);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  if (p.precision === 'year') return String(y);
  if (p.precision === 'quarter') return `${y}-Q${d.getUTCMonth() / 3 + 1}`;
  if (p.precision === 'month') return `${y}-${m}`;
  return `${y}-${m}-${String(d.getUTCDate()).padStart(2, '0')}`;
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
  const byAlert = useAlertEvents();
  const [showEvents, setShowEvents] = useState(true);
  const [indexed, setIndexed] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [query, setQuery] = useState('');
  const [queryErr, setQueryErr] = useState(false);
  const [noSeries, setNoSeries] = useState<string | null>(null);
  const [openedFor, setOpenedFor] = useState<string | null>(null);
  const [h, setH] = useState(160);
  const [board, setBoard] = useState(false);
  const [real, setReal] = useState(false);
  const boardOpen = useRef(false);
  boardOpen.current = board;
  const chartBox = useRef<HTMLDivElement>(null);
  const resetView = useRef(true);
  const pendingDate = useRef<string | null>(null);
  const pendingRange = useRef<[number, number] | null>(null);
  const [rangeTick, setRangeTick] = useState(0);
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
      // the ids of an address are checked against the index: a series that does not exist is left out
      const wanted = req.series?.filter((id) => findMeta(id));
      if (wanted?.length) next = wanted.slice(0, MAX_SERIES);
      else if (k && !seriesForCommodity(k).length) {
        // no series for this commodity: say so, and never show another commodity's price, even an earlier selection
        setNoSeries(lowerName(commodityMeta(k)?.name ?? k));
        next = [];
      } else if (!cur.length) next = defaultSeriesIds(k);
      else if (k && !cur.some((id) => findMeta(id)?.k === k)) next = defaultSeriesIds(k);
      // the period and date of the page before are not those of this request: the address stops carrying them until it settles
      if (req.range || req.date) priceView.value = null;
      if (next.join() !== cur.join()) {
        priceSeries.value = next;
        resetView.current = true;
        setFocus(0);
        setLookup(null);
        setQuery('');
      }
      if (req.date) pendingDate.current = req.date;
      // what an address carries beyond the series: the period, index to 100, real prices
      pendingRange.current = req.range ?? null;
      setRangeTick((t) => t + 1);
      if (req.index != null) setIndexed(req.index);
      if (req.real != null) setReal(req.real);
    });
    return () => {
      alive = false;
    };
  }, [reqKey]);

  // Real prices: each selected series is replaced by its annual real counterpart (constant 2010 US dollars, deflated by
  // the MUV index). Possible only when every selected series has one.
  const realOk = ids.length > 0 && ids.every((id) => !!findMeta(id)?.real);
  const realOn = real && realOk;
  const loadIds = realOn ? ids.map((id) => findMeta(id)!.real!) : ids;

  // ---- load the selected series lazily
  useEffect(() => {
    if (!loadIds.length) {
      setData([]);
      return;
    }
    let alive = true;
    setLoading(true);
    Promise.all(loadIds.map(loadSeries))
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
  }, [loadIds.join()]);

  useEffect(() => {
    if (!open) setBoard(false);
  }, [open]);

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
  const allDeviation = data.length > 0 && data.every((d) => isDeviation(d.meta));
  if (allDeviation && indexed) setIndexed(false);
  const idxOn = (indexed || forcedIndex) && !allDeviation;
  // in an indexed chart a deviation keeps its own unit on the right axis; a second deviation unit has no axis left and is not drawn
  const devUnit = idxOn ? data.find((d) => isDeviation(d.meta))?.meta.unit : undefined;
  const roles = data.map((d) => (!idxOn ? 'own' : !isDeviation(d.meta) ? 'index' : d.meta.unit === devUnit ? 'own' : 'off'));
  const roleKey = roles.join();
  // "Index to 100": each series rebased at the first observation inside the visible range
  const baseKey = idxOn && win ? data.map((d) => firstAtOrAfter(d, win.min)).join() : '';
  const chartSeries: TimeSeries[] = useMemo(() => {
    if (!merged) return [];
    const u0 = data[0].meta.unit;
    const second = data.find((d) => d.meta.unit !== u0)?.meta.unit;
    const bases = baseKey ? baseKey.split(',').map((k, i) => (Number(k) >= 0 && roles[i] === 'index' ? data[i].v[Number(k)]! : null)) : null;
    return data.map((d, i) => ({
      label: bases && roles[i] === 'index' ? `${d.meta.name} (index)` : d.meta.name,
      values: !bases || roles[i] === 'own' ? merged.cols[i] : merged.cols[i].map((v) => (v == null || bases[i] == null ? null : (v / bases[i]!) * 100)),
      color: colors[i],
      scale: bases ? (roles[i] === 'own' ? 'y2' : 'y') : d.meta.unit === u0 || d.meta.unit !== second ? 'y' : 'y2',
      gaps: d.gaps,
      step: isAnnualSeries(d.meta),
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [merged, data, colors, baseKey, roleKey]);
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

  // the period of an address, after the date lookup (which zooms around its date) so that the period wins
  useEffect(() => {
    const r = pendingRange.current;
    // only once the chart holds the series the request names (the series of the page before it may still be there)
    if (!merged || !r || data.map((d) => d.meta.id).join() !== loadIds.join()) return;
    pendingRange.current = null;
    const w = { min: Math.max(xMin, Math.min(r[0], xMax)), max: Math.min(xMax, Math.max(r[1], xMin)) };
    if (w.max > w.min) {
      setView(w);
      setWin(w);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [merged, reqKey, rangeTick]);

  // what the drawer shows beyond its series goes to the address, once it has settled (a drag-zoom fires many times)
  useEffect(() => {
    if (!open) {
      priceView.value = null;
      return;
    }
    // not while a requested period is still to be applied, nor while the chart holds the series of the page before
    if (pendingRange.current || data.map((d) => d.meta.id).join() !== loadIds.join()) return;
    const id = setTimeout(() => {
      priceView.value = {
        range: win && merged ? [Math.floor(win.min), Math.floor(win.max)] : null,
        date: lookup ? lookupKey(lookup.parsed) : null,
        index: indexed,
        real: realOn,
      };
    }, 350);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, win, merged, lookup, indexed, realOn, data, rangeTick]);

  const lookupRows = useMemo(() => {
    if (!lookup || !ready) return null;
    const p = lookup.parsed;
    const rows = data.map((d, i) => withYoy(d, p.precision === 'day' || isAnnualSeries(d.meta) ? rowAt(d, colors[i], p.t) : periodRow(d, colors[i], p), p));
    const answered = new Set(data.filter((_, i) => !rows[i].pre).map((d) => d.meta.k));
    // a series without data for the date names the other series of its commodity that have some, unless one is already charted
    return rows.map((r, i) => {
      if (r.sparse) {
        // the monthly average of the same commodity covers the whole month: offer it
        const mon = data[i].meta.monthly ? findMeta(data[i].meta.monthly!) : undefined;
        const offer = mon && !ids.includes(mon.id) && !loadIds.includes(mon.id) ? [mon] : [];
        return offer.length ? { ...r, offer, offerLead: 'The monthly average of the same benchmark covers the whole period:' } : r;
      }
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
      // the rule of the timeline (lib/events.ts): an event that names a charted commodity, or names none (a general shipping
      // or market event), or belongs to an alert that covers one
      const charted = new Set(data.map((d) => d.meta.k));
      for (const e of events) {
        if (!eventShownForAny(e, charted, byAlert)) continue;
        const t = parseDate(e.date);
        const end = e.end ? parseEnd(e.end) : undefined;
        if ((end ?? t) < xMin || t > xMax) continue;
        m.push({ t, end, id: e.id, title: `${eventDate(e.date)}${e.end ? ' to ' + eventDate(e.end) : ''} · ${e.title}`, tag: e.kind, color: EVENT_COLOR[e.kind], subtle: true });
      }
    }
    // changes of basis (thin lines), runs of annual values (grey tint) and months the source marks as estimates (amber tint)
    data.forEach((d, i) => {
      for (const b of d.meta.breaks ?? []) {
        const t = parseDate(b.at);
        if (t < xMin || t > xMax) continue;
        m.push({ t, subtle: true, color: colors[i], tag: 'basis change', title: `${d.meta.name} · ${eventDate(b.at)}: ${b.now}${b.before ? ` (before: ${b.before})` : ''}` });
      }
      for (const [y0, y1] of d.meta.annual ?? []) {
        const t = Date.UTC(y0, 0, 1) / 1000;
        const end = Date.UTC(y1, 11, 31) / 1000;
        if (end < xMin || t > xMax) continue;
        m.push({ t, end, shade: true, color: '#98a4b2', tag: 'unchanged all year', title: `${d.meta.name} · ${y0 === y1 ? y0 : `${y0} to ${y1}`}: the twelve monthly values of each year are identical` });
      }
      for (const [a, b] of d.meta.est ?? []) {
        const t = parseDate(a);
        const end = parseEnd(b);
        if (end < xMin || t > xMax) continue;
        m.push({ t, end, shade: true, color: '#ffb547', tag: 'estimate', title: `${d.meta.name} · ${eventDate(a)}${b !== a ? ' to ' + eventDate(b) : ''}: estimated by the source` });
      }
    });
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
  }, [events, byAlert, showEvents, lookup, merged, xMin, xMax, data, colors]);

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
      if (e.key !== 'Escape' || (e.target as HTMLElement)?.closest?.('.pd-pop')) return;
      if (boardOpen.current) setBoard(false);
      else closePrices();
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
  // a lookup answers in the side column: bring the answer into view when the statistics above push it down,
  // but never by more than it takes to leave the chart's top edge in view (stacked on a short screen the
  // answer sits under the chart, and scrolling all the way to it used to push the chart out of sight)
  useEffect(() => {
    const box = readBox.current;
    if (!lookup || !box) return;
    let sc: HTMLElement | null = box.parentElement;
    while (sc && !(sc.scrollHeight > sc.clientHeight + 1 && /auto|scroll/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement;
    const chart = box.closest('.pd')?.querySelector('.pd-chart');
    if (!sc || !chart) {
      box.scrollIntoView?.({ block: 'nearest' });
      return;
    }
    const view = sc.getBoundingClientRect();
    const b = box.getBoundingClientRect();
    if (b.top < view.top) sc.scrollTop += b.top - view.top;
    else if (b.bottom > view.bottom) sc.scrollTop += Math.min(b.bottom - view.bottom, Math.max(0, chart.getBoundingClientRect().top - view.top));
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
      class={`pd glass${open ? ' open' : ''}${data.length >= 2 ? ' pd-tall' : ''}${board ? ' pd-board-open' : ''}`}
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
                      <small
                        class="num"
                        title={
                          roles[i] === 'off'
                            ? `Not drawn: in ${d.meta.unit}, it crosses zero and cannot be indexed, and the right axis holds another unit`
                            : roles[i] === 'index'
                              ? `Indexed to 100; published in ${d.meta.unit}`
                              : `${d.meta.unit}${chartSeries[i]?.scale === 'y2' ? ', plotted on the right axis' : ''}`
                        }
                      >
                        <span class="pd-chip-unit">{roles[i] === 'index' ? 'index' : roles[i] === 'off' ? 'not drawn' : d.meta.unit}</span>
                        {roles[i] !== 'off' && chartSeries[i]?.scale === 'y2' ? ' · R' : ''}
                      </small>
                    </button>
                    {data.length > 1 && (
                      <button class="pd-chip-x" aria-label={`Remove ${d.meta.name}`} onClick={() => setIds(ids.filter((_, j) => j !== i))}>
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
              <button class="pd-add pd-board-btn" onClick={() => setBoard(true)} title="Every series with its last value and its changes">
                Price board
              </button>
              <CsvAction
                class="pd-add pd-board-btn"
                sources={priceSources(data)}
                disabled={!merged || !win}
                onClick={() => merged && win && downloadPrices(data, win.min, win.max)}
                title="The series shown, over the period shown, with their source and licence, as a CSV file (values as published, not indexed)"
              />
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
                    placeholder="e.g. Mar 2008"
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
                disabled={forcedIndex || allDeviation}
                onClick={() => setIndexed(!indexed)}
                title={
                  allDeviation
                    ? `${data.length > 1 ? 'These series are deviations' : 'This series is a deviation'} from a trend or an average: ${data.length > 1 ? 'they cross' : 'it crosses'} zero and cannot be indexed to 100`
                    : forcedIndex
                      ? `${unitCount} different units cannot share two axes: the series are shown as an index`
                      : 'Rebase every series to 100 at the start of the visible range, to compare series in different units'
                }
              >
                <span class="switch" aria-hidden="true" />
                Index to 100
              </button>
              <button class="pd-toggle" role="switch" aria-checked={showEvents} onClick={() => setShowEvents(!showEvents)} title="Freight and market events from the Atlas timeline. An event that names commodities is shown when one of them is charted, or when an alert that covers one points to it; general events always">
                <span class="switch" aria-hidden="true" />
                Events
              </button>
              <button
                class="pd-toggle"
                role="switch"
                aria-checked={realOn}
                disabled={!realOk}
                onClick={() => setReal(!real)}
                title={
                  realOk
                    ? 'Annual averages in constant 2010 US dollars, deflated by the World Bank MUV index (monthly and daily prices stay in current dollars)'
                    : 'Real prices exist for the World Bank price series (and Brent, WTI and Henry Hub through them), not for the other series or for spreads'
                }
              >
                <span class="switch" aria-hidden="true" />
                Real prices
              </button>
            </div>

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
              {/* first, so that it stays in view when the source lines scroll */}
              {idxOn && (
                <div class={forcedIndex || roles.includes('off') ? 'pd-hint pd-warn' : 'pd-hint'}>
                  {forcedIndex ? `${unitCount} different units cannot share two axes, so the chart is indexed: ` : 'Index: '}
                  each series = 100 at the start of the visible range; readouts and statistics stay in native units.
                  {devHint(data.find((_, i) => roles[i] === 'own')?.meta, data.find((_, i) => roles[i] === 'off')?.meta)}
                </div>
              )}
              {data.map((d, i) => (
                <div key={d.meta.id} class="pd-src" style={{ '--c': colors[i] }}>
                  <i />
                  <span>
                    {d.meta.name}: {sourceLabel(d.meta.s)}
                    {d.meta.basis ? ` · ${shortBasis(d.meta.basis)}` : ''}
                    {d.meta.note ? ` · ${d.meta.note}` : ''} · {d.meta.unit} · {FREQ_WORD[d.meta.freq]} {d.meta.start.slice(0, 7)} to {d.meta.end.slice(0, 7)}
                    {d.gaps?.length ? ` · ${d.gaps.length} stretch${d.gaps.length === 1 ? '' : 'es'} of more than 7 days without a quote left blank` : ''}
                    {isLate(d.meta) ? ' · late: no new value yet' : ''}
                    {d.meta.closed ? ' · closed: no new values' : ''}
                  </span>
                </div>
              ))}
              {realOn && (
                <div class="pd-hint">
                  Real prices: annual averages in constant 2010 US dollars, deflated by the World Bank MUV index (workbook CMO-Historical-Data-Annual, sheet "Annual Prices (Real)").
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
                      <Tile label="Last" value={fmtSeriesValue(fs.meta, stats.last.v)} unit={fs.meta.unit} sub={stats.last.d} />
                      <Tile
                        label="Change"
                        value={stats.change == null ? '—' : fmtPct(stats.change)}
                        tone={stats.change == null ? undefined : stats.change >= 0 ? 'up' : 'down'}
                        sub={`since ${stats.first.d}`}
                      />
                      <Tile label="Low" value={fmtSeriesValue(fs.meta, stats.min.v)} unit={fs.meta.unit} sub={stats.min.d} />
                      <Tile label="High" value={fmtSeriesValue(fs.meta, stats.max.v)} unit={fs.meta.unit} sub={stats.max.d} />
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
                              <b class="num">{fmtSeriesValue(d.meta, st.last.v)}</b>
                              <small>{st.last.d}</small>
                            </span>
                            <span>
                              <b class={`num${st.change == null ? '' : st.change >= 0 ? ' up' : ' down'}`}>{st.change == null ? '—' : fmtPct(st.change)}</b>
                              <small>since {st.first.d}</small>
                            </span>
                            <span>
                              <b class="num">{fmtSeriesValue(d.meta, st.min.v)}</b>
                              <small>{st.min.d}</small>
                            </span>
                            <span>
                              <b class="num">{fmtSeriesValue(d.meta, st.max.v)}</b>
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
                          {r.change && <> · {r.change}</>}
                        </>
                      )}
                      {r.detail && <> · {r.detail}</>}
                      {r.value != null && <> · {r.source}</>}
                      {r.post && <em> · {r.post}</em>}
                      {r.offer && r.offer.length > 0 && lookup && (
                        <span class="pd-offers">
                          {r.offerLead ?? `Other ${lowerName(commodityMeta(r.k)?.name ?? r.k)} series with data for ${lookupLabel(lookup.parsed)}:`}
                          {r.offer.map((m) => (
                            <button
                              key={m.id}
                              class="pd-offer"
                              disabled={full}
                              title={full ? `${MAX_SERIES} series max: remove one to add this series` : 'Add this series to the chart'}
                              onClick={() => addSeries(m.id)}
                            >
                              {full ? '' : '+ '}
                              {m.name} · {FREQ_WORD[m.freq]}, {m.start.slice(0, 4)} to {m.end.slice(0, 4)}
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
            {ready && <BasisBlock data={data} colors={colors} />}
            <div class="pd-hint">
              <PriceStatusLine />
            </div>
          </aside>
        </div>
      )}
      {everOpen && board && (
        <PriceBoard
          onClose={() => setBoard(false)}
          onOpen={(id) => {
            priceSeries.value = [id];
            resetView.current = true;
            setNoSeries(null);
            setFocus(0);
            setLookup(null);
            setQuery('');
            setBoard(false);
          }}
        />
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
  /** words that introduce the offer, when it is not the default */
  offerLead?: string;
  /** a daily series with too few quotes in the period asked for it to stand for the period */
  sparse?: boolean;
  /** the figure as a number, and its change on the same period one year earlier ("+74% on Jul 2007") */
  num?: number;
  change?: string;
}

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;
/** "14 Mar 2008" for a daily quote; "Mar 2008 monthly average" for a monthly price ("monthly value" for an index). */
const obsLabel = (d: LoadedSeries, i: number) => {
  const f = d.meta.freq;
  const year = new Date(d.x[i] * 1000).getUTCFullYear();
  if (f === 'A') return `${year} ${annualWord(d.meta)}`;
  return fmtObsDate(d.x[i], f) + (f !== 'M' ? '' : ` ${monthlyWord(d.meta)}`);
};
/** An index or a deviation is a value of the month, not an average of daily prices. */
const monthlyWord = (m: PriceMeta) => (m.unit.startsWith('index') || isDeviation(m) ? 'monthly value' : 'monthly average');

/**
 * What an indexed chart does with the deviation series (two exist, in two units): the first keeps its unit on the right
 * axis, the other has no axis left and is not drawn.
 */
function devHint(own?: PriceMeta, off?: PriceMeta): string {
  let s = own ? ` ${own.name}: not indexed (it crosses zero), right axis in ${own.unit}.` : '';
  if (off) s += ` ${off.name}: not drawn (it crosses zero too, and no axis is left for its unit).`;
  return s;
}

/**
 * What a figure of a series with years of twelve identical monthly values is: said next to the value, as what is
 * observed. The source may publish one price a year there, or a price that did not move (gold reads 35.00 in 1960 to
 * 1967): only the iron ore row of the source says "annual contract prices", and that is its own annual series.
 */
function annualNote(m: PriceMeta, year: number): string | null {
  const run = annualRun(m, year);
  if (!run) return null;
  const mf = monthlyFrom(m);
  const lead = mf != null && run[0] === Number(m.start.slice(0, 4));
  return `unchanged all year: the twelve monthly values of ${year} are identical${lead ? `; the values differ from month to month from ${mf}` : ''}`;
}

/** Caveats of one observation: an annual value in a monthly series, a month the source estimates. */
function obsCaveats(d: LoadedSeries, i: number): string[] {
  const out: string[] = [];
  if (d.meta.freq === 'M') {
    const a = annualNote(d.meta, new Date(d.x[i] * 1000).getUTCFullYear());
    if (a) out.push(a);
  }
  if (d.meta.freq !== 'D' && inEstimate(d.meta, d.x[i])) out.push('estimated by the source');
  return out;
}

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
    return { ...row, pre: `${asked} is not published yet`, label: `latest: ${obsLabel(d, i)}`, value: fmtSeriesValue(d.meta, d.v[i]) };
  return { ...row, pre: `no data after ${fmtObsDate(d.x[i], f)}, the latest value of this series` };
}

/** The value at one day (lookup by day, or the chart cursor): see observationAt for the rules. */
function rowAt(d: LoadedSeries, color: string, t: number): Row {
  const row = blankRow(d, color);
  const f = d.meta.freq;
  const o = observationAt(d, f, t);
  if (o.kind === 'missing') return { ...row, pre: 'no value at this date' };
  if (o.kind === 'before' || o.kind === 'after') return outside(d, row, o.kind, o.i, fmtObsDate(t, f), t);
  const notes = obsCaveats(d, o.i);
  const out = { ...row, label: obsLabel(d, o.i), value: fmtSeriesValue(d.meta, d.v[o.i]), num: d.v[o.i] ?? undefined, post: notes.length ? notes.join(' · ') : null };
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
  // monthly series: months that are annual values or estimates of the source
  let annualMonths = 0;
  let estMonths = 0;
  let months = 0;
  if (f === 'M') {
    for (let t = Math.max(p.t, d.x[b.first]); t < Math.min(t1, dataEnd); ) {
      const dt = new Date(t * 1000);
      months++;
      if (annualRun(d.meta, dt.getUTCFullYear())) annualMonths++;
      if (inEstimate(d.meta, t)) estMonths++;
      t = Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth() + 1, 1) / 1000;
    }
  }
  const allAnnual = months > 0 && annualMonths === months;
  if (annualMonths && !allAnnual) caveats.push(`${plural(annualMonths, 'month')} of ${months} are in years whose twelve monthly values are identical`);
  // a daily series with far fewer quotes than the period has trading days does not stand for the period
  const expected = f === 'D' ? { month: 21, quarter: 63, year: 252 }[p.precision as 'month' | 'quarter' | 'year'] : undefined;
  const sparse = expected != null && st.n < expected * 0.7;
  if (estMonths) caveats.push(`${plural(estMonths, 'month')} estimated by the source`);
  const post = [
    allAnnual ? annualNote(d.meta, new Date(Math.max(p.t, d.x[b.first]) * 1000).getUTCFullYear()) : null,
    sparse ? `the source has a quote on only ${st.n} of about ${expected} trading days: this average does not stand for the period` : null,
    caveats.length ? `partial period: ${caveats.join('; ')}` : null,
  ]
    .filter(Boolean)
    .join(' · ') || null;
  if (f === 'M' && p.precision === 'month') return { ...row, label: obsLabel(d, st.min.i), value: fmtPrice(st.avg), num: st.avg, post };
  const on = (i: number) => fmtObsDate(d.x[i], f);
  return {
    ...row,
    // the source publishes the observations, not this average
    source: allAnnual ? row.source : `average computed by the atlas from ${row.source}`,
    label: allAnnual
      ? `${name} value, unchanged all year`
      : f === 'M'
        ? `${name} average of ${plural(st.n, monthlyWord(d.meta))}`
        : `${name} average`,
    value: fmtPrice(st.avg),
    num: st.avg,
    detail: allAnnual ? null : `low ${fmtPrice(st.min.v)} (${on(st.min.i)}) · high ${fmtPrice(st.max.v)} (${on(st.max.i)})${f === 'M' ? '' : ` · ${plural(st.n, 'daily price')}`}`,
    post,
    sparse,
  };
}

/** The same day, month, quarter or year one year earlier. */
function yearBefore(p: ParsedDate): ParsedDate {
  const d = new Date(p.t * 1000);
  return { ...p, t: Date.UTC(d.getUTCFullYear() - 1, d.getUTCMonth(), d.getUTCDate()) / 1000 };
}

/** Adds "+74% on Jul 2007": the figure against the same period a year earlier, from the same series (arithmetic on the published values). */
function withYoy(d: LoadedSeries, row: Row, p: ParsedDate): Row {
  if (row.num == null || row.pre) return row;
  const q = yearBefore(p);
  let prev: number | null = null;
  if (p.precision === 'day' || isAnnualSeries(d.meta)) {
    const o = observationAt(d, d.meta.freq, q.t);
    if (o.kind === 'exact' || o.kind === 'period' || (o.kind === 'previous' && d.x[o.i] > q.t - 7 * DAY_S)) prev = d.v[o.i];
  } else {
    const st = periodStats(d, q.t, lookupEnd(q) - 1);
    // a daily average over a handful of quotes is not a reference
    const enough = d.meta.freq !== 'D' || st == null || st.n >= { month: 15, quarter: 44, year: 176, day: 1 }[q.precision];
    prev = st && enough ? st.avg : null;
  }
  if (prev == null || !(prev > 0) || row.num < 0 || /deviation/i.test(d.meta.unit)) return row;
  // a monthly series answers a day with its month: the reference is the same month a year before
  const label = isAnnualSeries(d.meta) ? String(new Date(q.t * 1000).getUTCFullYear()) : p.precision === 'day' && d.meta.freq === 'M' ? fmtObsDate(q.t, 'M') : lookupLabel(q);
  return { ...row, change: `${fmtPct((row.num / prev - 1) * 100)} on ${label}` };
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
  // a deviation from a trend or an average has no change in percent (it crosses zero)
  const change = fs.v[first]! !== 0 && !/deviation/i.test(fs.meta.unit) ? (fs.v[last]! / fs.v[first]! - 1) * 100 : null;
  return {
    last: { v: fs.v[last]!, d: d(last) },
    first: { d: d(first) },
    change,
    min: { v: fs.v[mn]!, d: d(mn) },
    max: { v: fs.v[mx]!, d: d(mx) },
    n: last - first + 1,
  };
}

/** What each charted price measures and when that changed, read from the source's own description. */
function BasisBlock({ data, colors }: { data: LoadedSeries[]; colors: string[] }) {
  if (!data.some((d) => d.meta.basis || d.meta.breaks?.length || d.meta.annual?.length || d.meta.est?.length)) return null;
  return (
    <div class="pd-basis" aria-label="What each price measures">
      <div class="pd-read-head">
        <span>What the price measures</span>
      </div>
      <div class="pd-bs-key">Thin lines on the chart mark a change of basis, grey bands years whose twelve monthly values are identical, amber bands months the source estimates: hover them.</div>
      {data.map((d, i) => {
        const m = d.meta;
        const mf = monthlyFrom(m);
        const inner = (m.annual ?? []).filter((r) => !(mf != null && r[0] === Number(m.start.slice(0, 4))));
        const runs = (l: [number, number][]) => l.map((r) => (r[0] === r[1] ? r[0] : `${r[0]} to ${r[1]}`)).join(', ');
        return (
          <div class="pd-bs" key={m.id} style={{ '--c': colors[i] }}>
            <b>
              <i />
              {m.name}
            </b>
            {m.basis && <p>{m.basis}</p>}
            {!!m.breaks?.length && (
              <ul>
                {[...m.breaks].reverse().map((b) => (
                  <li key={b.at}>
                    <b class="num">{eventDate(b.at)}</b> {b.now}
                    {b.before && <em> (before: {b.before})</em>}
                  </li>
                ))}
              </ul>
            )}
            {mf != null && (
              <p>
                {m.start.slice(0, 4)} to {mf - 1}: the twelve monthly values of each year are identical (the source may publish one price a year, or the price did not move). They differ from month to month from {mf}.
              </p>
            )}
            {inner.length > 0 && <p>Twelve identical monthly values in each year of: {runs(inner)}.</p>}
            {!!m.est?.length && (
              <p>
                Estimated by the source:{' '}
                {m.est
                  .map((r) => {
                    const [a, b] = m.freq === 'A' ? [r[0].slice(0, 4), r[1].slice(0, 4)] : [eventDate(r[0]), eventDate(r[1])];
                    return a === b ? a : `${a} to ${b}`;
                  })
                  .join(', ')}
                .
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
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

  const spreads = useMemo(() => spreadMetas(props.meta), [props.meta]);
  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const match = (m: PriceMeta) => !needle || `${m.name} ${commodityMeta(m.k)?.name ?? ''} ${m.unit} ${m.id}`.toLowerCase().includes(needle);
    const out: { fam: PriceGroup | 'spread'; items: PriceMeta[] }[] = [];
    for (const fam of GROUP_ORDER) {
      const items = props.meta.filter((m) => !m.hidden && groupOf(m) === fam && match(m));
      if (items.length) out.push({ fam, items });
    }
    const sp = spreads.filter(match);
    if (sp.length) out.push({ fam: 'spread', items: sp });
    return out;
  }, [props.meta, spreads, q]);

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
          {m.basis && <em class="pd-opt-basis">{shortBasis(m.basis)}</em>}
        </span>
        <span class="pd-opt-meta num">
          {m.unit} · {FREQ_WORD[m.freq]} {m.start.slice(0, 4)}
          {m.closed ? ` to ${m.end.slice(0, 4)} · closed` : ''}
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
                {props.ids.map((id) => findMeta(id, props.meta)).map((m) => m && option(m))}
              </div>
            )}
            {groups.length === 0 && <div class="pd-empty">No series match.</div>}
            {groups.map((g) => (
              <div key={g.fam}>
                <div class="pd-fam" style={{ color: g.fam === 'index' || g.fam === 'spread' ? undefined : FAMILY_COLOR[g.fam] }}>
                  {g.fam === 'spread' ? SPREAD_GROUP : GROUP_LABEL[g.fam]}
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
