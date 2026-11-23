/** "Events": the dated events linked to a commodity, a route or a country, near the end of the page; the first three, the rest on request. */
import { useEffect, useState } from 'preact/hooks';
import type { FreightEvent } from '../types';
import { loadEvents } from '../lib/freight';
import { eventShownFor, useAlertEvents, type AlertEvents } from '../lib/events';
import { select } from '../lib/store';
import { EVENT_COLOR, EVENT_KIND_LABEL, fmtEventDate } from './views/EventView';
import { Section } from './ui';
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

/**
 * The events of a commodity, a country or a route. A country or a route: the events that link to it. A commodity: the events
 * that name it, name no commodity at all, or belong to an alert that covers it (eventShownFor).
 */
export function eventsFor(
  list: FreightEvent[],
  q: { commodity?: string; country?: string; route?: string },
  byEvent?: AlertEvents,
): FreightEvent[] {
  return list.filter(
    (e) =>
      (q.commodity != null && eventShownFor(e, q.commodity, byEvent)) ||
      (q.country != null && !!e.countries?.includes(q.country)) ||
      (q.route != null && !!e.routes?.includes(q.route)),
  );
}

const FOLDED = 3;

export function EventList(props: { commodity?: string; country?: string; route?: string }) {
  const all = useEvents();
  const byEvent = useAlertEvents();
  const [open, setOpen] = useState(false);
  const key = `${props.commodity ?? ''}|${props.country ?? ''}|${props.route ?? ''}`;
  useEffect(() => setOpen(false), [key]);
  const list = eventsFor(all, props, byEvent);
  if (!list.length) return null;
  const shown = open ? list : list.slice(0, FOLDED);
  return (
    <Section title="Events" aside={<span class="muted num">{list.length}</span>}>
      <ul class="evl-list">
        {shown.map((e) => (
          <li key={e.id}>
            <button class="evl-row" onClick={() => select({ kind: 'event', id: e.id })}>
              <span class="evl-dot" style={{ background: EVENT_COLOR[e.kind] }} title={EVENT_KIND_LABEL[e.kind]} />
              <span class="evl-date num">{fmtEventDate(e.date)}{e.end ? ` – ${fmtEventDate(e.end)}` : ''}</span>
              <span class="evl-title">{e.title}</span>
            </button>
          </li>
        ))}
      </ul>
      {list.length > FOLDED && (
        <button class="evl-more" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? 'Show fewer' : `Show all (${list.length})`}
        </button>
      )}
    </Section>
  );
}
