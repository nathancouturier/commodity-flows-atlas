/**
 * "Prices around this date" on the event page: for each commodity the event is linked to, the change of one of the atlas's price
 * series 1 and 3 months after the event. Arithmetic on the published prices (no model, no causal claim).
 *  - The series is the one the event names for the commodity (``series`` in events.json, where the catalogue has several markets:
 *    a European gas event reads the TTF), else the commodity's main non-annual series. Its name is printed in the line.
 *  - An annual series gives no figure: one value a year says nothing a month later.
 *  - A monthly series gives month averages: the first figure is the average of the month of the event (days before it included),
 *    the later ones are the averages of the following months. A later figure that is the same observation as the first is left out.
 */
import { useEffect, useState } from 'preact/hooks';
import type { FreightEvent } from '../types';
import { commodityMeta } from '../lib/data';
import { eventCommodities, useAlertEvents } from '../lib/events';
import { fmtObsDate, fmtPct, fmtPrice, loadPriceIndex, loadSeries, observationAt, openPrices, seriesForCommodity, type LoadedSeries, type PriceMeta } from '../lib/prices';
import { Section, SourceLine } from './ui';

/** Commodities shown before "Show all". */
const FOLDED = 4;

interface Point {
  /** price and the date of the observation it comes from */
  v: number;
  t: number;
  /** index of the observation in the series */
  i: number;
}
interface Row {
  k: string;
  s: LoadedSeries;
  start: Point;
  /** change in per cent after 1 and 3 months, with the price they come from */
  after: { months: 1 | 3; pct: number; p: Point }[];
}

/** First instant of the event date ("2026-02-28", "2008-01"), seconds since the epoch. */
export function eventStart(date: string): number {
  const [y, m = '1', d = '1'] = date.split('-');
  return Date.UTC(Number(y), Number(m) - 1, Number(d)) / 1000;
}

/** The same day n months later (the last day of the month when it has fewer days), seconds. */
export function addMonths(t: number, n: number): number {
  const d = new Date(t * 1000);
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth() + n;
  const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  return Date.UTC(y, m, Math.min(d.getUTCDate(), last)) / 1000;
}

/** The price the series gives at time t, or null when t is outside it or has no value (the series stands still on a day without a quote). */
function priceAt(s: LoadedSeries, t: number): Point | null {
  const o = observationAt(s, s.meta.freq, t);
  if (o.kind === 'exact' || o.kind === 'period' || o.kind === 'previous') return { v: s.v[o.i] as number, t: s.x[o.i], i: o.i };
  return null;
}

/**
 * The series that gives the prices of a commodity for an event: the one the event names (``series[k]``), else the commodity's first
 * series that is not annual (daily before monthly). Null when there is none.
 */
export function seriesFor(ev: Pick<FreightEvent, 'series'>, k: string, idx: PriceMeta[]): PriceMeta | null {
  const named = ev.series?.[k];
  const own = named ? idx.find((m) => m.id === named && m.freq !== 'A') : undefined;
  return own ?? seriesForCommodity(k, idx).find((m) => m.freq !== 'A') ?? null;
}

/**
 * The rows of one event from loaded series: only the commodities whose series has a value at the start and at least one later
 * date (1 or 3 months after) that is another observation than the first. An annual series gives nothing.
 */
export function priceRows(date: string, series: { k: string; s: LoadedSeries }[]): Row[] {
  const t0 = eventStart(date);
  const rows: Row[] = [];
  for (const { k, s } of series) {
    if (s.meta.freq === 'A') continue;
    const start = priceAt(s, t0);
    if (!start || !start.v) continue;
    const after: Row['after'] = [];
    for (const months of [1, 3] as const) {
      const p = priceAt(s, addMonths(t0, months));
      if (p && p.i !== start.i) after.push({ months, pct: (100 * (p.v - start.v)) / start.v, p });
    }
    if (after.length) rows.push({ k, s, start, after });
  }
  return rows;
}

export function EventPrices({ ev }: { ev: FreightEvent }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [all, setAll] = useState(false);
  const byAlert = useAlertEvents();
  const ks = eventCommodities(ev, byAlert);
  const key = ks.join();
  const sel = JSON.stringify(ev.series ?? {});
  useEffect(() => {
    let live = true;
    setRows(null);
    if (!ks.length) return;
    loadPriceIndex()
      .then((idx) => {
        const picks = ks.map((k) => ({ k, meta: seriesFor(ev, k, idx) })).filter((x): x is { k: string; meta: PriceMeta } => !!x.meta);
        return Promise.all(picks.map((p) => loadSeries(p.meta.id).then((s) => ({ k: p.k, s }))));
      })
      .then((all) => live && setRows(priceRows(ev.date, all)))
      .catch(() => live && setRows([]));
    return () => {
      live = false;
    };
  }, [ev.id, key, sel]);
  if (!rows || !rows.length) return null;
  const hasDay = ev.date.length > 7;
  // the event's own commodities come first; a long list (an event with an alert) is folded
  const shown = all ? rows : rows.slice(0, FOLDED);
  return (
    <Section title="Prices around this date">
      <div class="evp">
        {shown.map((r) => {
          const f = r.s.meta.freq;
          const monthly = f === 'M';
          const lastP = r.after[r.after.length - 1].p;
          return (
            <div class="evp-row" key={r.k}>
              <div class="evp-head">
                <b>{commodityMeta(r.k)?.name ?? r.k}</b>
                <span class="muted"> · {r.s.meta.name}, {r.s.meta.unit}{monthly ? ', monthly averages' : ''}</span>
              </div>
              <div class="evp-line num">
                {monthly ? 'Month of the event' : hasDay ? 'On the event date' : 'At the start of the month'}: <b>{fmtPrice(r.start.v)}</b>{' '}
                <span class="muted">({fmtObsDate(r.start.t, f)})</span>
              </div>
              {r.after.map((a) => (
                <div class="evp-line num" key={a.months}>
                  {a.months === 1 ? 'One month later' : 'Three months later'}: <b class={a.pct < 0 ? 'evp-dn' : 'evp-up'}>{fmtPct(a.pct)}</b>{' '}
                  <span class="muted">
                    ({fmtPrice(a.p.v)}, {fmtObsDate(a.p.t, f)})
                  </span>
                </div>
              ))}
              <SourceLine s={r.s.meta.s} y={`${fmtObsDate(r.start.t, f)} to ${fmtObsDate(lastP.t, f)}`} />
              <button class="evp-open" onClick={() => openPrices({ commodity: r.k, series: [r.s.meta.id], date: ev.date })}>
                Open the price chart on this date
              </button>
            </div>
          );
        })}
        {rows.length > FOLDED && (
          <button class="evp-open" onClick={() => setAll(!all)} aria-expanded={all}>
            {all ? 'Show fewer commodities' : `Show all ${rows.length} commodities`}
          </button>
        )}
        <div class="muted small">
          Change of the published series between these dates: arithmetic on the prices, not an estimate of the effect of the event.
          {rows.some((r) => r.s.meta.freq === 'M') && ' A monthly figure is the average of its month, so the month of the event also holds days before the event.'}
        </div>
      </div>
    </Section>
  );
}
