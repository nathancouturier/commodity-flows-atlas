/** Vessel size class: dimensions, cargoes, constraints, canal limits, routes served. */
import type { Route, VesselClass } from '../../types';
import { fmt } from '../../lib/format';
import { loadRoutes, loadVesselClasses, SEGMENT_COLOR, SEGMENT_LABEL } from '../../lib/freight';
import { select } from '../../lib/store';
import { Section, SourceLine, Kpi, Skeleton, Placeholder } from '../ui';
import { CommodityChips, publisher, useFreightCatalogue, useLoaded } from './shared';

export default function VesselView({ id }: { id: string }) {
  useFreightCatalogue();
  const v = useLoaded<VesselClass>(() => loadVesselClasses().then((l) => l.find((c) => c.id === id) ?? null), [id]);
  const routes = useLoaded<Route[]>(() => loadRoutes(), []);
  if (v === undefined)
    return (<><div class="detail-head"><div class="detail-kicker">Vessel class</div><h2 class="detail-title">{id}</h2></div><div class="panel-scroll"><Skeleton lines={6} /></div></>);
  if (v === null)
    return (<><div class="detail-head"><div class="detail-kicker">Vessel class</div><h2 class="detail-title">{id}</h2></div><div class="panel-scroll"><Placeholder>This vessel class is not in the atlas catalogue.</Placeholder></div></>);
  const u = v.size.u === 'teu' ? 'TEU' : v.size.u;
  const pub = publisher(v.s);
  const byId = new Map((routes ?? []).map((r) => [r.id, r]));
  const served = v.routes.map((rid) => byId.get(rid)).filter((r): r is Route => !!r);
  const d = v.dims;
  return (
    <>
      <div class="detail-head" style={{ '--kicker': SEGMENT_COLOR[v.segment] }}>
        <div class="detail-kicker">Vessel class · {SEGMENT_LABEL[v.segment]}</div>
        <h2 class="detail-title">{v.name}</h2>
      </div>
      <div class="panel-scroll">
        <div class="kpis">
          <Kpi
            label="Typical size"
            value={`${fmt(v.size.typical)} ${u}`}
            sub={v.size.typicalS === 'atlas' ? 'Atlas convention: middle of the size range' : pub}
            title={`Typical size (${v.size.typicalS ?? v.s})`}
          />
          <Kpi label="Size range" value={v.size.min > 0 ? `${fmt(v.size.min)}–${fmt(v.size.max)}` : `up to ${fmt(v.size.max)}`} sub={`${u} · ${pub}`} title={`Size range (${v.s})`} />
          {v.speed ? (
            <Kpi label="Assumed laden service speed" value={`${fmt(v.speed.v)} ${v.speed.u}`} sub={`Atlas assumption · ${v.speed.y}`} title={`${v.speed.s} · ${v.speed.y}`} note={v.speed.n} span />
          ) : v.speedKn ? (
            <Kpi label="Assumed laden service speed" value={`${fmt(v.speedKn)} kn`} sub="Atlas assumption" note={v.speedNote} span />
          ) : null}
          {v.fleet && <Kpi label="Fleet" f={v.fleet} note={v.fleet.n} span />}
        </div>
        {d && (d.loa || d.beam || d.draft) && (
          <Section title="Typical dimensions">
            <div class="dims">
              {d.loa != null && <div><span class="num">{fmt(d.loa)} m</span><small>Length overall</small></div>}
              {d.beam != null && <div><span class="num">{fmt(d.beam)} m</span><small>Beam</small></div>}
              {d.draft != null && <div><span class="num">{fmt(d.draft)} m</span><small>Draft</small></div>}
            </div>
            <SourceLine s={d.s ?? v.s} />
          </Section>
        )}
        {v.cargoes.length > 0 && (
          <Section title="Cargoes">
            <CommodityChips ids={v.cargoes} />
          </Section>
        )}
        {v.constraints.length > 0 && (
          <Section title="Constraints">
            <ul class="bullets">{v.constraints.map((c) => <li key={c}>{c}</li>)}</ul>
          </Section>
        )}
        <Section title="Canals">
          <div class="ft">
            <div class="ft-row"><span class="ft-k">Suez</span><span>{v.canals.suez}</span></div>
            <div class="ft-row"><span class="ft-k">Panama</span><span>{v.canals.panama}</span></div>
          </div>
          <SourceLine s={v.s} />
        </Section>
        {served.length > 0 && (
          <Section title={`Routes served (${served.length})`}>
            {served.map((r) => (
              <button class="list-btn" key={r.id} onClick={() => select({ kind: 'route', id: r.id })}>
                {r.benchmark && <span class="code-badge sm">{r.id}</span>}
                <span class="grow">{r.name}</span>
                {r.standIn && <span class="meta" title={r.standIn}>stand-in</span>}
                <span class="meta num">{fmt(r.distanceNm)} nm</span>
              </button>
            ))}
          </Section>
        )}
        {v.notes && (
          <Section title="Notes">
            <p class="prose">{v.notes}</p>
          </Section>
        )}
      </div>
    </>
  );
}
