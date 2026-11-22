/** Freight route card: Baltic benchmark or heavy-traffic route. */
import { useEffect, useMemo } from 'preact/hooks';
import type { Route } from '../../types';
import { commodityMeta } from '../../lib/data';
import { fmt, fig as fmtFig } from '../../lib/format';
import { loadRoutes, loadRouteGeo, SEGMENT_LABEL, segmentOf, SEGMENT_COLOR } from '../../lib/freight';
import { flyToLine } from '../../map/controller';
import { Section, SourceLine, Kpi, Skeleton, Placeholder, AlertBanners } from '../ui';
import { AltBox, CommodityChips, HistoryChart, ViaSection, VesselChip, publisher, useFreightCatalogue, useLoaded } from './shared';

export default function RouteView({ id }: { id: string }) {
  useFreightCatalogue();
  const route = useLoaded<Route>(() => loadRoutes().then((rs) => rs.find((r) => r.id === id) ?? null), [id]);

  useEffect(() => {
    let live = true;
    loadRouteGeo()
      .then((g) => {
        if (!live) return;
        const f = g.features.find((f) => f.properties.id === id && f.properties.kind === 'route') ?? g.features.find((f) => f.properties.id === id);
        if (f) flyToLine(f.geometry.coordinates as [number, number][]);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [id]);

  if (route === undefined)
    return (
      <>
        <div class="detail-head"><div class="detail-kicker">Freight route</div><h2 class="detail-title">{id}</h2></div>
        <div class="panel-scroll"><Skeleton lines={7} /></div>
      </>
    );
  if (route === null)
    return (
      <>
        <div class="detail-head"><div class="detail-kicker">Freight route</div><h2 class="detail-title">{id}</h2></div>
        <div class="panel-scroll"><Placeholder>This route is not in the atlas catalogue.</Placeholder></div>
      </>
    );
  return <Body r={route} />;
}

function Body({ r }: { r: Route }) {
  const seg = segmentOf(r.vclass);
  const color = SEGMENT_COLOR[seg];
  const pub = publisher(r.s);
  const shares = useMemo(() => {
    const out: { label: string; f: NonNullable<Route['shareCommodity']> }[] = [];
    const seen = new Set<string>();
    const add = (k: string, f: NonNullable<Route['shareCommodity']>) => {
      const key = `${k}:${f.v}`;
      if (seen.has(key)) return;
      seen.add(key);
      // customs codes do not separate thermal from metallurgical coal: both shares are computed on all coal
      const name = k === 'thermal-coal' || k === 'met-coal' ? 'coal (all types)' : (commodityMeta(k)?.name ?? k).toLowerCase();
      out.push({ label: `Corridor share of seaborne ${name}`, f });
    };
    if (r.shareCommodity) {
      const match = r.shares?.find((s) => s.f.v === r.shareCommodity!.v);
      add(match?.k ?? r.cargoes[0], r.shareCommodity);
    }
    for (const s of r.shares ?? []) add(s.k, s.f);
    return out;
  }, [r]);
  const leg = !!(r.roundVoyage || r.drawnAs);
  const parcel = r.parcel != null ? `${fmt(r.parcel)} ${r.parcelUnit ?? 't'}` : null;
  const fromPort = r.from.ports.join(' / ') || r.from.region;
  const toPort = r.to.ports.join(' / ') || r.to.region;
  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker">{r.benchmark ? `Baltic benchmark · ${SEGMENT_LABEL[seg]}` : 'Heavy-traffic route'}</div>
        <h2 class="detail-title">{r.name}</h2>
        <div class="badges">
          {r.benchmark && <span class="code-badge" title="Baltic Exchange route code">{r.id}</span>}
          {r.discontinued && <span class="badge badge-warn">Discontinued {r.discontinued}</span>}
          {r.roundVoyage && <span class="badge" title="Benchmark is quoted for a round voyage">Round voyage</span>}
        </div>
        {r.roundVoyage && <div class="muted small" style={{ marginTop: '6px' }}>Benchmark is a round voyage (delivery → redelivery); distance shown is the typical laden leg.</div>}
        {r.drawnAs && <div class="muted small" style={{ marginTop: '6px' }}>Drawn as its {r.drawnAs}.</div>}
      </div>
      <div class="panel-scroll">
        <AlertBanners chokepoints={r.via} status={r.status} />
        <div class="kpis">
          <Kpi label={leg ? 'Distance · laden leg only' : 'Distance'} value={`${fmt(r.distanceNm)} nm`} sub="SeaRoute network · Atlas routing" title="Sea-route distance between the representative ports, computed on Eurostat's SeaRoute maritime network" />
          <Kpi label={leg ? 'Laden days · laden leg only' : 'Laden days'} value={`${fmt(r.days)} d`} sub={`at ${fmt(r.speedKn)} kn · Atlas calc`} title="Distance divided by the class's typical laden speed" />
          {shares.map((s) => (
            <Kpi key={s.label} label={s.label} f={s.f} value={fmtFig(s.f)} note={s.f.n} span={!!s.f.n} />
          ))}
          {r.shareClass && (
            <Kpi label="Share of class tonne-miles" f={r.shareClass} sub={`Atlas estimate · ${r.shareClass.y}`} />
          )}
          {parcel && <Kpi label="Standard parcel" value={parcel} sub={pub} title={`Parcel size per route definition (${r.s})`} />}
        </div>
        <Section title="From → To">
          <div class="ft">
            <div class="ft-row"><span class="ft-k">From</span><span><b>{r.from.region}</b>{r.from.ports.length > 0 && <span class="muted"> · {r.from.ports.join(', ')}</span>}</span></div>
            <div class="ft-row"><span class="ft-k">To</span><span><b>{r.to.region}</b>{r.to.ports.length > 0 && <span class="muted"> · {r.to.ports.join(', ')}</span>}</span></div>
          </div>
        </Section>
        <Section title="Vessel class">
          <div class="chips"><VesselChip id={r.vclass} /></div>
        </Section>
        {r.cargoes.length > 0 && (
          <Section title="Cargoes">
            <CommodityChips ids={r.cargoes} />
          </Section>
        )}
        <ViaSection from={fromPort} to={toPort} via={r.via} />
        {r.alt && <AltBox alt={r.alt} />}
        {r.history && r.history.length > 1 && (
          <Section title={`Corridor volume ${r.history[0].y}–${r.history[r.history.length - 1].y}`}>
            <HistoryChart years={r.history.map((h) => h.y)} values={r.history.map((h) => h.v)} unit={r.historyUnit ?? ''} color={color} />
            <div class="muted small">All cargoes of the corridor, {r.historyUnit}.</div>
            <SourceLine s={r.historySrc} y={`${r.history[0].y}–${r.history[r.history.length - 1].y}`} n={r.historyNote} />
          </Section>
        )}
        {r.notes && (
          <Section title="Notes">
            <p class="prose">{r.notes}</p>
          </Section>
        )}
        <Section title="Definition">
          <SourceLine s={r.s} />
        </Section>
      </div>
    </>
  );
}
