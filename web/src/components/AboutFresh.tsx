/** The "Data freshness" tab of the About window, beyond the table of sources: a plain sentence per family of data and the calendar of the updates. */
import type { Alert } from '../types';
import { sources } from '../lib/data';
import { fmtDate, jobOf, nextRun, type Changes, type Freshness, type StatusView } from '../lib/status';
import { shortSource } from './ui';
import '../styles/changes.css';

/** The families of data, each with the update jobs (keys of updates.json) that feed it. */
const FAMILIES: { name: string; keys: string[] }[] = [
  { name: 'Prices', keys: ['eia-spot', 'wb-pink', 'fred'] },
  { name: 'Chokepoint traffic', keys: ['portwatch'] },
  { name: 'Trade flows between countries', keys: ['baci'] },
  { name: 'Production, reserves and consumption', keys: ['usgs-mcs', 'usda-psd', 'eia-intl'] },
  { name: 'Cocoa, uranium and fertilisers', keys: ['faostat-wna'] },
];

/** Latest of several ISO dates ("2026-11-22T12:05:20Z"), or null. */
const latest = (xs: (string | null)[]): string | null => xs.filter((x): x is string => !!x).sort().pop() ?? null;

function dataTo(r: Freshness, vintages: Record<string, string>): string | null {
  if (r.dataTo) return r.dataTo;
  const shown = r.sources.map((s) => vintages[s]).filter(Boolean);
  return shown.length ? [...new Set(shown.map((v) => fmtDate(v)))].join(', ') : null;
}

/** One sentence per family: what the data run to, and the last successful update. */
export function FamilySummary(props: { status: StatusView; vintages: Record<string, string>; alerts: Alert[] }) {
  const { status: st, vintages, alerts } = props;
  const rows = (keys: string[]) => st.rows.filter((r) => keys.includes(r.key));
  const alertTo = latest(alerts.flatMap((a) => a.measures.map((m) => m.to)));
  const reviewed = alerts.map((a) => a.reviewed).sort()[0] ?? null;
  return (
    <ul class="fresh-fam">
      {FAMILIES.map((f) => {
        const rs = rows(f.keys);
        if (!rs.length) return null;
        const runs = rs
          .map((r) => {
            const to = dataTo(r, vintages);
            return to ? `${to} (${shortSource(r.sources[0])})` : null;
          })
          .filter(Boolean);
        const upd = latest(rs.map((r) => r.checked));
        return (
          <li key={f.name} data-family={f.name}>
            <b>{f.name}:</b> {runs.length ? <>run to <span class="num">{runs.join(', ')}</span>.</> : 'no end date recorded.'}{' '}
            {upd ? <>Last successful update <span class="num">{fmtDate(upd)}</span>.</> : 'No successful update recorded.'}
          </li>
        );
      })}
      {alerts.length > 0 && (
        <li data-family="Disruption banners">
          <b>Disruption banners:</b> traffic figures run to <span class="num">{fmtDate(alertTo)}</span> (IMF PortWatch); texts reviewed on{' '}
          <span class="num">{fmtDate(reviewed)}</span>. {st.alertsBuilt ? <>Last successful update <span class="num">{fmtDate(st.alertsBuilt)}</span>.</> : null}
        </li>
      )}
    </ul>
  );
}

/** When each source is read: the job, when it runs, the next run, and the cadence the publisher states. */
export function Calendar({ changes }: { changes: Changes | null | undefined }) {
  const list = Object.values(sources.value).filter((s) => s.id !== 'atlas');
  if (!list.length) return null;
  const jobs = changes?.jobs ?? [];
  // without the job list (no digest yet) only the cadence the registry states can be shown
  if (!jobs.length) {
    return (
      <>
        <h3>Publication calendar</h3>
        <table class="about-table about-cal">
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Published</th>
            </tr>
          </thead>
          <tbody>
            {list.map((s) => (
              <tr key={s.id} data-source={s.id}>
                <th scope="row">{s.name}</th>
                <td data-label="Published">{s.update}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    );
  }
  const now = Date.now();
  const sched = list.filter((s) => jobOf(jobs, s.id));
  const hand = list.filter((s) => !jobOf(jobs, s.id));
  return (
    <>
      <h3>Publication calendar</h3>
      <p>
        Each source is read by one of the scheduled jobs below, which check for new data and rebuild what depends on it. The publisher's own
        cadence is the one the registry states.
      </p>
      <table class="about-table about-cal">
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col">Published</th>
            <th scope="col">Read by</th>
            <th scope="col">Next check</th>
          </tr>
        </thead>
        <tbody>
          {sched.map((s) => {
            const j = jobOf(jobs, s.id)!;
            const next = nextRun(j.runs, now);
            return (
              <tr key={s.id} data-source={s.id}>
                <th scope="row">{s.name}</th>
                <td data-label="Published">{s.update}</td>
                <td data-label="Read by">
                  {j.name}
                  <small>{j.runs.map((r) => r.text).join('; ')}</small>
                </td>
                <td data-label="Next check" class="num">{next ? fmtDate(next.toISOString()) : ''}</td>
              </tr>
            );
          })}
          {hand.map((s) => (
            <tr key={s.id} data-source={s.id}>
              <th scope="row">{s.name}</th>
              <td data-label="Published">{s.update}</td>
              <td data-label="Read by">By hand<small>No scheduled job: read when the entry is added or revised</small></td>
              <td data-label="Next check">—</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
