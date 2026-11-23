/**
 * History timeline: a year slider (years from the lane files) that drives `year`, which the lanes layer
 * uses to scale flow widths. Play animates one year per 1.2 s; freight events appear as clickable ticks.
 * The event axis runs to the present: past the last year of flow data it carries events only.
 */
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { choroInfo, commodity, historyOpen, metric, select, selection, sheetSnap, year, type SheetSnap } from '../lib/store';
import { commodityMeta, sourceLabel } from '../lib/data';
import { LANE_GROUPS, loadEvents, loadLaneFile } from '../lib/freight';
import { eventShownFor, loadAlertEvents, type AlertEvents } from '../lib/events';
import { lowerName, toggleHistory } from '../lib/prices';
import { fmt, TOUCH } from '../lib/format';
import { isSheetLayout } from '../map/controller';
import { parseDate } from './charts/TimeChart';
import { CloseIcon } from './ui';
import type { FreightEvent, LaneFile } from '../types';
import '../styles/drawers.css';

const STEP_MS = 1200;
const KIND_COLOR: Record<FreightEvent['kind'], string> = {
  conflict: '#ff5c7a',
  canal: '#3ee6ff',
  weather: '#9db7ff',
  policy: '#c7a3ff',
  accident: '#ff7a59',
  market: '#ffb547',
  infrastructure: '#7ee0a1',
};

// a shared link with #y=2016 opens the timeline
if (year.value != null) historyOpen.value = true;

const pretty = (g: string) => g.replace(/-/g, ' ');

/** Event date as a decimal year (2021.22 for 23 March 2021). */
function yearFraction(date: string): number {
  const t = parseDate(date);
  const y = new Date(t * 1000).getUTCFullYear();
  return y + (t - Date.UTC(y, 0, 1) / 1000) / (365.25 * 86400);
}

/** How far from a tick, in px, a click or tap still opens its event: a finger is less exact than a mouse. */
const TAP_REACH = 24;
const CLICK_REACH = 5;

export function Timeline() {
  const open = historyOpen.value;
  const y = year.value;
  const k = commodity.value;
  const [years, setYears] = useState<number[]>([]);
  const [events, setEvents] = useState<FreightEvent[]>([]);
  const [byAlert, setByAlert] = useState<AlertEvents>(new Map());
  const [playing, setPlaying] = useState(false);
  const [files, setFiles] = useState<LaneFile[]>([]);
  const barRef = useRef<HTMLElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [trackW, setTrackW] = useState(0);
  const downX = useRef<number | null>(null);
  const snapBefore = useRef<SheetSnap | null>(null);

  // year range from any lane file
  useEffect(() => {
    if (!open || years.length) return;
    loadLaneFile('iron-ore')
      .then((f) => setYears(f.years))
      .catch(() => undefined);
    loadEvents().then(setEvents).catch(() => undefined);
    loadAlertEvents().then(setByAlert);
  }, [open]);

  const first = years[0];
  const last = years[years.length - 1];

  // entering sets a year, leaving resets it
  useEffect(() => {
    if (open && last != null && (year.peek() == null || year.peek()! < first || year.peek()! > last)) {
      year.value = last;
    }
    if (!open) {
      setPlaying(false);
      year.value = null;
    }
  }, [open, last]);

  // a year pasted or edited into the hash while the timeline is open is held to the years that have data
  useEffect(() => {
    if (!open || first == null || y == null) return;
    if (y < first) year.value = first;
    else if (y > last) year.value = last;
  }, [open, first, last, y]);

  // phones and tablets: the bar takes the bottom edge, so the sheets sit above it (see --tl-h in drawers.css)
  // and the controls sheet folds to its handle while History is open
  useEffect(() => {
    const el = barRef.current;
    const root = document.documentElement;
    if (!open || !el) {
      root.style.setProperty('--tl-h', '0px');
      return;
    }
    const ro = new ResizeObserver(() => {
      root.style.setProperty('--tl-h', `${Math.ceil(el.getBoundingClientRect().height)}px`);
      setTrackW(trackRef.current?.clientWidth ?? 0);
    });
    ro.observe(el);
    if (isSheetLayout() && sheetSnap.peek() !== 'peek') {
      snapBefore.current = sheetSnap.peek();
      sheetSnap.value = 'peek';
    }
    return () => {
      ro.disconnect();
      root.style.setProperty('--tl-h', '0px');
      // back to the height it had, unless the user resized the sheet in the meantime
      if (snapBefore.current && sheetSnap.peek() === 'peek') sheetSnap.value = snapBefore.current;
      snapBefore.current = null;
    };
  }, [open]);

  // play loop
  useEffect(() => {
    if (!playing || first == null) return;
    const id = setInterval(() => {
      const cur = year.peek() ?? first;
      if (cur >= last) {
        setPlaying(false);
        return;
      }
      year.value = cur + 1;
    }, STEP_MS);
    return () => clearInterval(id);
  }, [playing, first, last]);

  // seaborne totals of the selected commodity
  useEffect(() => {
    const groups = k ? LANE_GROUPS[k] ?? [] : [];
    if (!open || !groups.length) {
      setFiles([]);
      return;
    }
    let alive = true;
    // a group whose lane file is not built yet is left out
    Promise.all(groups.map((g) => loadLaneFile(g).catch(() => null)))
      .then((f) => alive && setFiles(f.filter((x): x is LaneFile => !!x)))
      .catch(() => alive && setFiles([]));
    return () => {
      alive = false;
    };
  }, [k, open]);

  // The axis ends with the current year (or the latest event), not with the last year of flow data:
  // the slider stops at `last`, the stretch after it shows events only.
  const end = useMemo(() => {
    if (first == null) return null;
    const lastEvent = Math.max(...events.map((e) => Math.floor(yearFraction(e.date))), last);
    return Math.max(last, new Date().getUTCFullYear(), lastEvent) + 1;
  }, [events, first, last]);
  const span = end != null ? end - first : 1;
  const dataFrac = end != null ? (last - first) / span : 1;

  // with a commodity chosen, the events that name it, name no commodity at all or belong to an alert that covers it are marked (lib/events.ts)
  const ticks = useMemo(() => {
    if (first == null || end == null) return [];
    return events
      .filter((e) => !k || eventShownFor(e, k, byAlert))
      .map((e) => {
        const frac = yearFraction(e.date);
        return { e, frac, pos: (frac - first) / (end - first) };
      })
      .filter((x) => x.pos >= 0 && x.pos <= 1)
      .sort((a, b) => a.frac - b.frac);
  }, [events, first, end, k, byAlert]);

  const cur = y ?? last;
  const pctPos = first == null || last === first ? 0 : ((cur - first) / (last - first)) * 100;
  const labelYears = years.filter((v) => v === first || v === last || v % 5 === 0);
  // calendar years after the last year of flow data
  const noData = end != null && end - 1 > last ? (end - 1 === last + 1 ? String(end - 1) : `${last + 1}–${end - 1}`) : null;
  // the "no flow data yet" label goes under its stretch when it fits there, else in the caption
  const noDataOnTrack = (trackW - 18) * (1 - dataFrac) >= 120;
  // the slider thumb is 18 px wide: its centre travels between 9 px from each end of the input
  const alongTrack = (f: number) => `calc(9px + (100% - 18px) * ${f.toFixed(5)})`;

  const openEvent = (e: FreightEvent) => {
    // the event opens and the map jumps to its year (clamped to the years with flow data)
    const ey = Number(e.date.slice(0, 4));
    if (first != null && last != null && Number.isFinite(ey)) year.value = Math.min(Math.max(ey, first), last);
    select({ kind: 'event', id: e.id });
  };
  // one handler for the whole strip: a click opens the event nearest to it, and clicking again on a spot where
  // ticks overlap goes on to the next one. A tap is aimed with a finger, and browsers move its click onto
  // the topmost overlapping tick, so both use where the pointer went down. Enter and Space open the focused tick.
  const onTicksClick = (ev: MouseEvent) => {
    if (ev.detail === 0) {
      const btn = (ev.target as HTMLElement).closest<HTMLElement>('.tl-tick');
      const own = ticks.find((t) => t.e.id === btn?.dataset.id);
      if (own) openEvent(own.e);
      return;
    }
    const r = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    if (!ticks.length || r.width <= 0) return;
    const x = (downX.current ?? ev.clientX) - r.left;
    downX.current = null;
    const reach = TOUCH ? TAP_REACH : CLICK_REACH;
    const near = ticks.filter((t) => Math.abs(t.pos * r.width - x) <= reach);
    if (!near.length) return;
    const cur = selection.peek();
    const at = cur?.kind === 'event' ? near.findIndex((t) => t.e.id === cur.id) : -1;
    const pick =
      at >= 0
        ? near[(at + 1) % near.length]
        : near.reduce((a, b) => (Math.abs(b.pos * r.width - x) < Math.abs(a.pos * r.width - x) ? b : a));
    openEvent(pick.e);
  };

  // previous / next event: from the open event, or else from the selected year
  const sel = selection.value;
  const selIdx = sel?.kind === 'event' ? ticks.findIndex((t) => t.e.id === sel.id) : -1;
  const after = ticks.findIndex((t) => t.frac >= cur);
  const nextIdx = selIdx >= 0 ? selIdx + 1 : after;
  const prevIdx = selIdx >= 0 ? selIdx - 1 : (after < 0 ? ticks.length : after) - 1;
  const selTick = selIdx >= 0 ? ticks[selIdx] : null;

  const move = (v: number) => {
    year.value = v;
  };
  const togglePlay = () => {
    if (!playing && cur >= last) year.value = first;
    setPlaying(!playing);
  };

  const sea = files
    .map((f) => {
      const i = f.years.indexOf(cur);
      if (i < 0 || f.seaborne[i] == null) return null;
      // acronyms keep their capitals: "LNG", "DAP"
      const label = lowerName(files.length === 1 && f.group === k ? (commodityMeta(k)?.name ?? pretty(f.group)) : pretty(f.label ?? f.group));
      return { label, v: f.seaborne[i], u: f.unit, s: f.s };
    })
    .filter(Boolean) as { label: string; v: number; u: string; s: string }[];

  return (
    <section ref={barRef} class={`tl glass${open ? ' open' : ''}`} aria-label="History timeline" aria-hidden={!open}>
      <button class="tl-play" onClick={togglePlay} aria-label={playing ? 'Pause animation' : 'Play animation'} title={playing ? 'Pause' : 'Play through the years'}>
        {playing ? (
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M3.5 2h2.5v10H3.5zM8 2h2.5v10H8z" fill="currentColor" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M4 2l8 5-8 5z" fill="currentColor" />
          </svg>
        )}
      </button>
      <div class="tl-track" ref={trackRef}>
        <div class="tl-ticks" onPointerDown={(e) => (downX.current = e.clientX)} onClick={onTicksClick}>
          {ticks.map(({ e, pos }) => (
            <button
              key={e.id}
              data-id={e.id}
              class={`tl-tick${selTick?.e.id === e.id ? ' on' : ''}`}
              style={{ left: `${pos * 100}%`, '--tc': KIND_COLOR[e.kind] ?? '#8d9fb3' }}
              title={`${e.date}${e.end ? ' to ' + e.end : ''} · ${e.title}`}
              aria-label={`Event ${e.date}: ${e.title}`}
            />
          ))}
        </div>
        {noData && (
          <div
            class="tl-after"
            style={{ left: alongTrack(dataFrac) }}
            title={`No flow data yet for ${noData}: this stretch shows events only`}
          />
        )}
        {first != null && (
          <input
            class="tl-range"
            type="range"
            min={first}
            max={last}
            step={1}
            value={cur}
            style={{ '--p': `${pctPos}%`, width: `calc(18px + (100% - 18px) * ${dataFrac.toFixed(5)})` }}
            aria-label="Year"
            aria-valuetext={String(cur)}
            onInput={(e) => {
              setPlaying(false);
              move(Number((e.target as HTMLInputElement).value));
            }}
          />
        )}
        <div class="tl-years" aria-hidden="true">
          {labelYears.map((v) => (
            <span key={v} class={v === cur ? 'on' : ''} style={{ left: `${((v - first) / span) * 100}%` }}>
              {v}
            </span>
          ))}
          {noData && noDataOnTrack && <span class="tl-nodata">no flow data yet</span>}
        </div>
      </div>
      <button class="tl-close" onClick={toggleHistory} aria-label="Close history timeline">
        <CloseIcon />
      </button>
      <div class="tl-cap" aria-live="polite">
        <span>
          Flows shown for <b class="num">{cur}</b> · CEPII BACI
        </span>
        {sea.map((s) => (
          <span class="tl-sea" key={s.label} title={sourceLabel(s.s)}>
            Seaborne trade, {s.label}, {cur}:{' '}
            <b class="num">
              {fmt(s.v)} {s.u}
            </b>
          </span>
        ))}
        {noData && !noDataOnTrack && <span class="tl-note">{noData}: events only, no flow data yet</span>}
        {k && metric.value !== 'none' && y != null && choroInfo.value && !String(choroInfo.value.year).startsWith(String(cur)) && (
          <span class="tl-note">Country colours: {choroInfo.value.year}, no series for {cur}</span>
        )}
        {!TOUCH && <span class="tl-hint">Arrow keys step the year · ticks mark events</span>}
        {k && ticks.length === 0 && events.length > 0 && <span class="tl-note">No event names {lowerName(commodityMeta(k)?.name ?? k)}: choose All commodities to see them all</span>}
        {ticks.length > 0 && (
          <div class="tl-step">
            <button class="tl-step-btn" disabled={prevIdx < 0} aria-label="Previous event" onClick={() => openEvent(ticks[prevIdx].e)}>
              <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
            </button>
            <span class="tl-step-cur">
              {selTick ? (
                <>
                  <span class="num">{selTick.e.date}</span> · {selTick.e.title}
                </>
              ) : (
                `${ticks.length} event${ticks.length > 1 ? 's' : ''}${k ? ` for ${lowerName(commodityMeta(k)?.name ?? k)}, with the general shipping and market events` : ''}: pick a tick or step through them`
              )}
            </span>
            <button class="tl-step-btn" disabled={nextIdx < 0 || nextIdx >= ticks.length} aria-label="Next event" onClick={() => openEvent(ticks[nextIdx].e)}>
              <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M4.5 2.5 8 6 4.5 9.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
