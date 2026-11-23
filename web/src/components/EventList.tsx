/** Dated events linked to a commodity, a route or a country: one collapsed row on the page, the list on request. */
import { useEffect, useState } from 'preact/hooks';
import type { FreightEvent } from '../types';
import { loadEvents } from '../lib/freight';
import { select } from '../lib/store';
import { EVENT_COLOR, EVENT_KIND_LABEL, fmtEventDate } from './views/EventView';
import '../styles/changes.css';

let eventsPromise: Promise<FreightEvent[]> | null = null;
/** The events of the atlas, loaded once, newest first. */
export function useEvents(): FreightEvent[] {
  const [list, setList] = useState<FreightEvent[]>([]);
  useEffect(() => {
    eventsPromise ??= loadEvents()
      .then((l) => [...l].sort((a, b) => b.date.localeCompare(a.date)))
      .catch(() => []);
    let live = true;
    eventsPromise.then((l) => live && setList(l));
    return () => {
      live = false;
    };
  }, []);
  return list;
}

/** Events that name this commodity, country or route in their own text (the links of data/freight/events.json). */
export function eventsFor(list: FreightEvent[], q: { commodity?: string; country?: string; route?: string }): FreightEvent[] {
  return list.filter(
    (e) =>
      (q.commodity != null && !!e.commodities?.includes(q.commodity)) ||
      (q.country != null && !!e.countries?.includes(q.country)) ||
      (q.route != null && !!e.routes?.includes(q.route)),
  );
}

export function EventList(props: { commodity?: string; country?: string; route?: string }) {
  const all = useEvents();
  const [open, setOpen] = useState(false);
  const key = `${props.commodity ?? ''}|${props.country ?? ''}|${props.route ?? ''}`;
  useEffect(() => setOpen(false), [key]);
  const list = eventsFor(all, props);
  if (!list.length) return null;
  const years = (e: FreightEvent) => e.date.slice(0, 4);
  return (
    <div class="evl">
      <button class="evl-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <b>Events ({list.length})</b>
        <span class="evl-peek">{open ? 'Dated events that name it in their text' : list.slice(0, 2).map((e) => `${years(e)} ${e.title}`).join(' · ')}</span>
        <span class="evl-more">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open && (
        <ul class="evl-list">
          {list.map((e) => (
            <li key={e.id}>
              <button class="evl-row" onClick={() => select({ kind: 'event', id: e.id })}>
                <span class="evl-dot" style={{ background: EVENT_COLOR[e.kind] }} title={EVENT_KIND_LABEL[e.kind]} />
                <span class="evl-date num">{fmtEventDate(e.date)}</span>
                <span class="evl-title">{e.title}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
