/** A dated freight event: closure, attack, weather, policy... */
import type { FreightEvent } from '../../types';
import { loadEvents } from '../../lib/freight';
import { chokepointName } from '../../lib/freight';
import { commodityMeta, countryName } from '../../lib/data';
import { select } from '../../lib/store';
import { checkedLabel, eventCommodities, useAlertEvents } from '../../lib/events';
import { fmtDate } from '../../lib/status';
import { loadInfra, infraRef, type InfraFeature } from '../../map/modules/infrastructure';
import { EventPrices } from '../EventPrices';
import { Section, Skeleton, Placeholder } from '../ui';
import { useFreightCatalogue, useLoaded } from './shared';
import '../../styles/changes.css';

export const EVENT_COLOR: Record<FreightEvent['kind'], string> = {
  conflict: '#ff5c7a',
  canal: '#3ee6ff',
  weather: '#9db7ff',
  policy: '#c7a3ff',
  accident: '#ff7a59',
  market: '#ffb547',
  infrastructure: '#7ee0a1',
};

export const EVENT_KIND_LABEL: Record<FreightEvent['kind'], string> = {
  conflict: 'Conflict',
  canal: 'Canal',
  weather: 'Weather',
  policy: 'Policy',
  accident: 'Accident',
  market: 'Market',
  infrastructure: 'Infrastructure',
};

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function fmtEventDate(s: string): string {
  const [y, m, d] = s.split('-');
  if (!m) return y;
  return `${d ? `${Number(d)} ` : ''}${MON[Number(m) - 1]} ${y}`;
}

function host(u: string) {
  try {
    return new URL(u).hostname.replace(/^www\./, '');
  } catch {
    return u;
  }
}

/** The assets the event names, as chips that open their page. */
function EventAssets({ ids }: { ids: string[] }) {
  const all = useLoaded<InfraFeature[]>(() => loadInfra(), []);
  const items = ids.map((id) => all?.find((f) => f.p.id === id)).filter((f): f is InfraFeature => !!f);
  if (!items.length) return null;
  return (
    <Section title="Assets">
      <div class="chips">
        {items.map((f) => (
          <button class="chip" key={f.p.id} onClick={() => select(infraRef(f))}>{f.p.name}</button>
        ))}
      </div>
    </Section>
  );
}

export default function EventView({ id }: { id: string }) {
  useFreightCatalogue();
  const ev = useLoaded<FreightEvent>(() => loadEvents().then((l) => l.find((e) => e.id === id) ?? null), [id]);
  const byAlert = useAlertEvents();
  if (ev === undefined)
    return (<><div class="detail-head"><div class="detail-kicker">Event</div><h2 class="detail-title">…</h2></div><div class="panel-scroll"><Skeleton lines={6} /></div></>);
  if (ev === null)
    return (<><div class="detail-head"><div class="detail-kicker">Event</div><h2 class="detail-title">{id}</h2></div><div class="panel-scroll"><Placeholder>This event is not in the atlas catalogue.</Placeholder></div></>);
  const color = EVENT_COLOR[ev.kind];
  // the commodities of the event's text and those of the alert that points to it
  const ks = eventCommodities(ev, byAlert);
  const checked = checkedLabel(ev.checked, (d) => fmtDate(d));
  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker">Freight event</div>
        <h2 class="detail-title">{ev.title}</h2>
        <div class="badges">
          <span class="badge" style={{ color, borderColor: color }}>{EVENT_KIND_LABEL[ev.kind]}</span>
          <span class="num ev-date">{fmtEventDate(ev.date)}{ev.end ? ` → ${fmtEventDate(ev.end)}` : ''}</span>
        </div>
      </div>
      <div class="panel-scroll">
        <Section title="What happened">
          <p class="prose">{ev.summary}</p>
        </Section>
        {ev.impact && (
          <Section title="Impact on freight">
            <p class="prose">{ev.impact}</p>
          </Section>
        )}
        {ev.chokepoints && ev.chokepoints.length > 0 && (
          <Section title="Chokepoints">
            <div class="chips">
              {ev.chokepoints.map((c) => (
                <button class="chip" key={c} onClick={() => select({ kind: 'chokepoint', id: c })}>{chokepointName(c)}</button>
              ))}
            </div>
          </Section>
        )}
        {ev.routes && ev.routes.length > 0 && (
          <Section title="Routes">
            <div class="chips">
              {ev.routes.map((r) => (
                <button class="chip" key={r} onClick={() => select({ kind: 'route', id: r })}>{r}</button>
              ))}
            </div>
          </Section>
        )}
        {ks.length > 0 && (
          <Section title="Commodities">
            <div class="chips">
              {ks.map((k) => (
                <button class="chip" key={k} onClick={() => select({ kind: 'commodity', id: k })}>{commodityMeta(k)?.name ?? k}</button>
              ))}
            </div>
          </Section>
        )}
        {ev.countries && ev.countries.length > 0 && (
          <Section title="Countries">
            <div class="chips">
              {ev.countries.map((c) => (
                <button class="chip" key={c} onClick={() => select({ kind: 'country', id: c })}>{countryName(c)}</button>
              ))}
            </div>
          </Section>
        )}
        {ev.assets && ev.assets.length > 0 && <EventAssets ids={ev.assets} />}
        {ks.length > 0 && <EventPrices ev={ev} />}
        <div class="src-line">
          Source:{' '}
          <a href={ev.src} target="_blank" rel="noopener noreferrer">{host(ev.src)} ↗</a>
          {ev.also?.map((x) => (
            <span key={x.url}>
              {' · '}
              <a href={x.url} target="_blank" rel="noopener noreferrer">{x.label} ↗</a>
            </span>
          ))}
        </div>
        {checked && <div class="muted small">{checked}.</div>}
      </div>
    </>
  );
}
