/** Vessel size class: size band, standard vessel, world fleet, cargoes, constraints, canal limits, routes served. */
import type { FleetFile, Route, VesselClass, VesselStd } from '../../types';
import { fmt } from '../../lib/format';
import { load, sourceLabel } from '../../lib/data';
import { loadRoutes, loadVesselClasses, SEGMENT_COLOR, SEGMENT_LABEL, vesselName } from '../../lib/freight';
import { select } from '../../lib/store';
import { Section, SourceLine, Kpi, Skeleton, Placeholder } from '../ui';
import { CommodityChips, publisher, useFreightCatalogue, useLoaded } from './shared';
import { ShippingCompaniesBlock } from '../Companies';

/** A figure's own page (an article or a service page) when it has one, else the registry entry. */
function PageLine(props: { s?: string; url?: string; y?: number }) {
  if (!props.s) return null;
  if (!props.url || props.s === 'atlas') return <SourceLine s={props.s} y={props.y} />;
  const wiki = props.url.match(/wikipedia\.org\/wiki\/([^#?]+)/);
  const baltic = props.url.match(/balticexchange\.com\/.*\/([^/]+)\.html$/);
  return (
    <div class="src-line" data-src={props.s} data-y={props.y != null ? String(props.y) : undefined}>
      Source:{' '}
      <a href={props.url} target="_blank" rel="noopener">
        {wiki
          ? `Wikipedia, ${decodeURIComponent(wiki[1]).replace(/_/g, ' ')} (CC BY-SA 4.0)`
          : baltic
            ? `The Baltic Exchange, ${baltic[1].replace(/-+$/, '').replace(/-+/g, ' ')} page`
            : sourceLabel(props.s)}
      </a>
      {props.y != null && <> · {props.y}</>}
    </div>
  );
}

const num = (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 3 });

function StdBlock({ std, u, assumed }: { std: VesselStd; u: string; assumed?: number }) {
  const pair = (p: { laden?: number; ballast?: number } | undefined, unit: string) =>
    p && (p.laden != null || p.ballast != null)
      ? p.laden === p.ballast
        ? `${num(p.laden!)} ${unit}`
        : [p.laden != null ? `${num(p.laden)} ${unit} laden` : null, p.ballast != null ? `${num(p.ballast)} ${unit} ballast` : null].filter(Boolean).join(' · ')
      : null;
  const cells: [string, string | null][] = [
    ['Deadweight', std.dwt != null ? `${num(std.dwt)} ${u === 'dwt' ? 't' : u}` : null],
    ['Length overall', std.loa != null ? `${num(std.loa)} m` : null],
    ['Beam', std.beam != null ? `${num(std.beam)} m` : null],
    ['Draught', std.draught != null ? `${num(std.draught)} m` : null],
    ['Grain capacity', std.cubic != null ? `${num(std.cubic)} cbm` : null],
    ['Speed', pair(std.speed, 'kn')],
    ['Fuel a day', pair(std.cons, 't')],
  ];
  return (
    <>
      <div class="dims">
        {cells.filter(([, v]) => v).map(([k, v]) => <div key={k}><span class="num">{v}</span><small>{k}</small></div>)}
      </div>
      <p class="prose small">
        {std.n}
        {assumed != null && std.speed && ` Laden days in the atlas use the assumed laden service speed of ${fmt(assumed)} kn above, not this speed.`}
      </p>
      <PageLine s={std.s} url={std.url} y={std.y} />
    </>
  );
}

function FleetBlock({ v }: { v: VesselClass }) {
  const fleet = useLoaded<FleetFile>(() => load<FleetFile>('freight/fleet.json'), []);
  const t = v.fleetType ? fleet?.types.find((x) => x.name === v.fleetType) : undefined;
  const free = 'The fleet, age and orderbook of a commercial class are not published for free.';
  if (fleet === undefined) return <Skeleton lines={2} />;
  if (!t || !fleet)
    return (
      <>
        <p class="prose">
          UNCTADstat counts the world fleet by ship type (oil tankers, bulk carriers, general cargo, container ships, other
          types of ships), and none of these is this kind of ship alone. {free}
        </p>
        {fleet && <PageLine s={fleet.s} url={fleet.url} />}
      </>
    );
  return (
    <>
      <div class="kpis">
        {t.ships && <Kpi label="Ships" f={t.ships} />}
        {t.dwt && <Kpi label="Deadweight" f={t.dwt} />}
        {t.age && <Kpi label="Average age" f={t.age} />}
      </div>
      <p class="prose small">
        All {t.name.toLowerCase()} of the world as UNCTADstat counts them, not the {v.name} class alone. {free}
      </p>
      <PageLine s={fleet.s} url={fleet.url} y={fleet.y} />
    </>
  );
}

export default function VesselView({ id }: { id: string }) {
  useFreightCatalogue();
  const v = useLoaded<VesselClass>(() => loadVesselClasses().then((l) => l.find((c) => c.id === id) ?? null), [id]);
  const routes = useLoaded<Route[]>(() => loadRoutes(), []);
  if (v === undefined)
    return (<><div class="detail-head"><div class="detail-kicker">Vessel class</div><h2 class="detail-title">{id}</h2></div><div class="panel-scroll"><Skeleton lines={6} /></div></>);
  if (v === null)
    return (<><div class="detail-head"><div class="detail-kicker">Vessel class</div><h2 class="detail-title">{id}</h2></div><div class="panel-scroll"><Placeholder>This vessel class is not in the atlas catalogue.</Placeholder></div></>);
  const u = v.size.u === 'teu' ? 'TEU' : v.size.u;
  const byId = new Map((routes ?? []).map((r) => [r.id, r]));
  const served = v.routes.map((rid) => byId.get(rid)).filter((r): r is Route => !!r);
  // ended benchmarks after the active ones (as in the side panel); a listed route whose own class is another one apart
  const activeFirst = (l: Route[]) => [...l].sort((a, b) => Number(!!a.discontinued) - Number(!!b.discontinued));
  const own = activeFirst(served.filter((r) => r.vclass === v.id));
  const also = activeFirst(served.filter((r) => r.vclass !== v.id));
  const routeRow = (r: Route, other: boolean) => (
    <button class="list-btn" key={r.id} style={r.discontinued ? { opacity: 0.45 } : undefined} onClick={() => select({ kind: 'route', id: r.id })}>
      {r.benchmark && <span class="code-badge sm">{r.id}</span>}
      <span class="grow">
        {r.name}
        {r.discontinued && <small> (discontinued)</small>}
      </span>
      {other ? (
        <span class="meta" title={`A route of the ${vesselName(r.vclass)} class`}>{vesselName(r.vclass)}</span>
      ) : r.standIn ? (
        <span class="meta" title={r.standIn}>stand-in trace</span>
      ) : (
        <span class="meta num">{fmt(r.distanceNm)} nm</span>
      )}
    </button>
  );
  const z = v.size;

  const short = (s: string) => (s === 'wikipedia' ? 'Wikipedia' : publisher(s));
  const rangeSub = z.s === 'atlas' ? `${u} · Atlas convention` : `${u} · ${short(z.s ?? v.s)}${z.y ? ` · ${z.y}` : ''}`;
  const typicalSub = z.typicalS === 'atlas' ? 'Atlas convention' : `${short(z.typicalS ?? v.s)}${z.typicalY ? ` · ${z.typicalY}` : ''}`;
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
            value={`${fmt(z.typical)} ${u}`}
            sub={typicalSub}
            title={`Typical size (${z.typicalS ?? v.s}${z.typicalY ? ` · ${z.typicalY}` : ''})`}
          />
          <Kpi label="Size range" value={z.min > 0 ? `${fmt(z.min)}–${fmt(z.max)}` : `up to ${fmt(z.max)}`} sub={rangeSub} title={`Size range (${z.s ?? v.s}${z.y ? ` · ${z.y}` : ''})`} />
          {v.speed ? (
            <Kpi label="Assumed laden service speed" value={`${fmt(v.speed.v)} ${v.speed.u}`} sub={`Atlas assumption · ${v.speed.y}`} title={`${v.speed.s} · ${v.speed.y}`} note={v.speed.n} span />
          ) : v.speedKn ? (
            <Kpi label="Assumed laden service speed" value={`${fmt(v.speedKn)} kn`} sub="Atlas assumption" note={v.speedNote} span />
          ) : null}
          {v.fleet && <Kpi label="Fleet" f={v.fleet} note={v.fleet.n} span />}
        </div>
        {z.n && (
          <Section title="Size band">
            <p class="prose small">{z.n}</p>
            <PageLine s={z.s} url={z.url} y={z.y} />
          </Section>
        )}
        {v.std && (
          <Section title={v.std.s === 'baltic' ? 'Standard vessel (Baltic Exchange)' : 'Typical ship'}>
            <StdBlock std={v.std} u={v.size.u} assumed={v.speed?.v ?? v.speedKn} />
          </Section>
        )}
        {v.bench && (
          <Section title="Benchmarks">
            <button class="list-btn" onClick={() => select({ kind: 'vessel', id: v.bench!.id })}>
              <span class="grow">{v.bench.n}</span>
              <span class="meta">{vesselName(v.bench.id)}</span>
            </button>
          </Section>
        )}
        <Section title="World fleet">
          <FleetBlock v={v} />
        </Section>
        <ShippingCompaniesBlock v={v} />
        {v.cargoes.length > 0 && (
          <Section title="Cargoes">
            <CommodityChips ids={v.cargoes} />
          </Section>
        )}
        {v.constraints.length > 0 && (
          <Section title="Constraints">
            <ul class="bullets">{v.constraints.map((c) => <li key={c}>{c}</li>)}</ul>
            <SourceLine s={v.s} />
          </Section>
        )}
        <Section title="Canals">
          <div class="ft">
            <div class="ft-row"><span class="ft-k">Suez</span><span>{v.canals.suez}</span></div>
            <div class="ft-row"><span class="ft-k">Panama</span><span>{v.canals.panama}</span></div>
          </div>
          {!v.canals.suez.startsWith('No restriction') && <SourceLine s="sca-rules" />}
          {!v.canals.panama.startsWith('No restriction') && <SourceLine s="pca-vessel-requirements" />}
        </Section>
        {served.length > 0 && (
          <Section title={`Routes served (${served.length})`}>
            {own.map((r) => routeRow(r, false))}
            {also.length > 0 && (
              <>
                <h4 class="route-sub">Also served by {v.name}</h4>
                {also.map((r) => routeRow(r, true))}
              </>
            )}
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
