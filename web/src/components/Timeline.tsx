/**
 * History timeline: a year slider (years from the lane files) that drives `year`, which the lanes layer
 * uses to scale flow widths. Play animates one year per 1.2 s; freight events appear as clickable ticks.
 */
import { useEffect, useMemo, useState } from 'preact/hooks';
import { commodity, historyOpen, metric, select, year } from '../lib/store';
import { commodityMeta, sourceLabel } from '../lib/data';
import { LANE_GROUPS, loadEvents, loadLaneFile } from '../lib/freight';
import { toggleHistory } from '../lib/prices';
import { fmt, TOUCH } from '../lib/format';
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

export function Timeline() {
  const open = historyOpen.value;
  const y = year.value;
  const k = commodity.value;
  const [years, setYears] = useState<number[]>([]);
  const [events, setEvents] = useState<FreightEvent[]>([]);
  const [playing, setPlaying] = useState(false);
  const [files, setFiles] = useState<LaneFile[]>([]);

  // year range from any lane file
  useEffect(() => {
    if (!open || years.length) return;
    loadLaneFile('iron-ore')
      .then((f) => setYears(f.years))
      .catch(() => undefined);
    loadEvents().then(setEvents).catch(() => undefined);
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
    Promise.all(groups.map(loadLaneFile))
      .then((f) => alive && setFiles(f))
      .catch(() => alive && setFiles([]));
    return () => {
      alive = false;
    };
  }, [k, open]);

  const ticks = useMemo(() => {
    if (first == null) return [];
    const span = last - first;
    return events
      .map((e) => {
        const t = parseDate(e.date);
        const frac = new Date(t * 1000).getUTCFullYear() + (t - Date.UTC(new Date(t * 1000).getUTCFullYear(), 0, 1) / 1000) / (365.25 * 86400);
        return { e, pos: (frac - first) / span };
      })
      .filter((x) => x.pos >= 0 && x.pos <= 1);
  }, [events, first, last]);

  const cur = y ?? last;
  const pctPos = first == null || last === first ? 0 : ((cur - first) / (last - first)) * 100;
  const labelYears = years.filter((v) => v === first || v === last || v % 5 === 0);

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
      const label = files.length === 1 && f.group === k ? (commodityMeta(k)?.name ?? pretty(f.group)).toLowerCase() : pretty(f.label ?? f.group).toLowerCase();
      return { label, v: f.seaborne[i], u: f.unit, s: f.s };
    })
    .filter(Boolean) as { label: string; v: number; u: string; s: string }[];

  return (
    <section class={`tl glass${open ? ' open' : ''}`} aria-label="History timeline" aria-hidden={!open}>
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
      <div class="tl-track">
        <div class="tl-ticks">
          {ticks.map(({ e, pos }) => (
            <button
              key={e.id}
              class="tl-tick"
              style={{ left: `${pos * 100}%`, '--tc': KIND_COLOR[e.kind] ?? '#8d9fb3' }}
              title={`${e.date}${e.end ? ' to ' + e.end : ''} · ${e.title}`}
              aria-label={`Event ${e.date}: ${e.title}`}
              onClick={() => {
                // the event opens and the map jumps to its year (clamped to the years with flow data)
                const ey = Number(e.date.slice(0, 4));
                if (first != null && last != null && Number.isFinite(ey)) year.value = Math.min(Math.max(ey, first), last);
                select({ kind: 'event', id: e.id });
              }}
            />
          ))}
        </div>
        {first != null && (
          <input
            class="tl-range"
            type="range"
            min={first}
            max={last}
            step={1}
            value={cur}
            style={{ '--p': `${pctPos}%` }}
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
            <span key={v} class={v === cur ? 'on' : ''} style={{ left: `${((v - first) / (last - first)) * 100}%` }}>
              {v}
            </span>
          ))}
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
            Seaborne {s.label} {cur}:{' '}
            <b class="num">
              {fmt(s.v)} {s.u}
            </b>
          </span>
        ))}
        {k && metric.value !== 'none' && <span class="tl-note">Country colours: latest data, not by year</span>}
        <span class="tl-hint">{TOUCH ? 'Drag the slider to change the year · tap a tick for its event' : 'Arrow keys step the year · ticks mark events'}</span>
      </div>
    </section>
  );
}
