/**
 * Which events belong to a commodity, in one place: the History timeline, the events section of the pages and the event
 * markers of the price chart all use `eventShownFor`.
 *
 * An event is linked to the commodities its own text names (data/freight/events.json, rule in pipeline/freight/event_links.py).
 * The events that an alert points to (one or several) also take the alert's commodities (the ones derived from the chokepoint estimates). With a
 * commodity chosen an event is shown when it names the commodity, or names no commodity at all (a shipping or market event of
 * no particular cargo), or is the event of an alert whose commodities include it.
 */
import { useEffect, useState } from 'preact/hooks';
import type { Alert, FreightEvent } from '../types';
import { load } from './data';

/** event id -> commodities of the alerts that point to it */
export type AlertEvents = Map<string, string[]>;

let promise: Promise<AlertEvents> | null = null;
/** The commodities of the alerts, by the event each alert points to (loaded once; empty when the alerts cannot be read). */
export function loadAlertEvents(): Promise<AlertEvents> {
  promise ??= load<Alert[]>('freight/alerts.json')
    .then((list) => {
      const m: AlertEvents = new Map();
      for (const a of list) for (const id of a.events ?? [a.event]) m.set(id, [...new Set([...(m.get(id) ?? []), ...a.commodities])]);
      return m;
    })
    .catch(() => new Map<string, string[]>());
  return promise;
}

/** The commodities of the alerts by event, as a hook; empty until loaded. */
export function useAlertEvents(): AlertEvents {
  const [m, setM] = useState<AlertEvents>(new Map());
  useEffect(() => {
    let live = true;
    loadAlertEvents().then((r) => live && setM(r));
    return () => {
      live = false;
    };
  }, []);
  return m;
}

/** The commodities of an event: those its text names and those of the alert that points to it. */
export function eventCommodities(e: FreightEvent, byEvent?: AlertEvents): string[] {
  return [...new Set([...(e.commodities ?? []), ...(byEvent?.get(e.id) ?? [])])];
}

/** Whether an event is shown with commodity `k`: it names it, or names no commodity, or its alert does. */
export function eventShownFor(e: FreightEvent, k: string, byEvent?: AlertEvents): boolean {
  const own = eventCommodities(e, byEvent);
  return own.length === 0 || own.includes(k);
}

/** Whether an event is shown on a chart of the commodities `charted`: it is shown with one of them (eventShownFor). */
export function eventShownForAny(e: FreightEvent, charted: Iterable<string>, byEvent?: AlertEvents): boolean {
  const own = eventCommodities(e, byEvent);
  if (own.length === 0) return true;
  for (const k of charted) if (own.includes(k)) return true;
  return false;
}

/** A text is "old" when its check is older than this many days. */
export const CHECK_STALE_DAYS = 90;

/** "Text checked against its source on 23 Nov 2026", with "(more than 90 days ago)" when the check is old; null when never checked. */
export function checkedLabel(checked: string | undefined | null, fmtDay: (iso: string) => string, now = Date.now()): string | null {
  if (!checked) return null;
  const t = Date.parse(checked + 'T00:00:00Z');
  const old = Number.isFinite(t) && (now - t) / 86_400_000 > CHECK_STALE_DAYS;
  return `Text checked against its source on ${fmtDay(checked)}${old ? ` (more than ${CHECK_STALE_DAYS} days ago)` : ''}`;
}
