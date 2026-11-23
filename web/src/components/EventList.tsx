/** "Events": the dated events linked to a commodity, a route or a country, near the end of the page; the first three, the rest on request. */
import { useEffect, useState } from 'preact/hooks';
import type { FreightEvent } from '../types';
import { loadEvents } from '../lib/freight';
import { eventCommodities, useAlertEvents, type AlertEvents } from '../lib/events';
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
 * The events of a commodity, a country or a route, in two lists. `own`: a country or a route, the events that link to it; a
 * commodity, the events that name it or belong to an alert that covers it. `general`: for a commodity only, the events that name no
 * commodity at all (a shipping or market event of no particular cargo), which the History timeline shows with every commodity
 * (eventShownFor).
 */
export function eventsFor(
  list: FreightEvent[],
  q: { commodity?: string; country?: string; route?: string },
  byEvent?: AlertEvents,
): { own: FreightEvent[]; general: FreightEvent[] } {
  const own: FreightEvent[] = [];
  const general: FreightEvent[] = [];
  for (const e of list) {
    if ((q.country != null && e.countries?.includes(q.country)) || (q.route != null && e.routes?.includes(q.route))) own.push(e);
    else if (q.commodity != null) {
      const ks = eventCommodities(e, byEvent);
      if (ks.includes(q.commodity)) own.push(e);
      else if (ks.length === 0) general.push(e);
    }
  }
  return { own, general };
}

const FOLDED = 3;

function Rows({ list }: { list: FreightEvent[] }) {
  return (
    <ul class="evl-list">
      {list.map((e) => (
        <li key={e.id}>
          <button class="evl-row" onClick={() => select({ kind: 'event', id: e.id })}>
            <span class="evl-dot" style={{ background: EVENT_COLOR[e.kind] }} title={EVENT_KIND_LABEL[e.kind]} />
            <span class="evl-date num">{fmtEventDate(e.date)}{e.end ? ` – ${fmtEventDate(e.end)}` : ''}</span>
            <span class="evl-title">{e.title}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** The events that name the page's commodity, country or route (three shown, the rest on request); on a commodity page, behind one more line, the general events. The count in the title is of the page's own events. */
export function EventList(props: { commodity?: string; country?: string; route?: string }) {
  const all = useEvents();
  const byEvent = useAlertEvents();
  const [open, setOpen] = useState(false);
  const [general, setGeneral] = useState(false);
  const key = `${props.commodity ?? ''}|${props.country ?? ''}|${props.route ?? ''}`;
  useEffect(() => {
    setOpen(false);
    setGeneral(false);
  }, [key]);
  const { own, general: other } = eventsFor(all, props, byEvent);
  if (!own.length && !other.length) return null;
  return (
    <Section title="Events" aside={own.length > 0 ? <span class="muted num">{own.length}</span> : undefined}>
      <Rows list={open ? own : own.slice(0, FOLDED)} />
      {own.length > FOLDED && (
        <button class="evl-more" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? 'Show fewer' : `Show all (${own.length})`}
        </button>
      )}
      {other.length > 0 && (
        <>
          <button class="evl-more evl-general" onClick={() => setGeneral(!general)} aria-expanded={general}>
            {`General shipping and market events (${other.length})`}
          </button>
          {general && <Rows list={other} />}
        </>
      )}
    </Section>
  );
}
