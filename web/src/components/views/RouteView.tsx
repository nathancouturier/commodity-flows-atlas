/** Freight route card: Baltic benchmark or heavy-traffic route. */
import { useEffect, useMemo } from 'preact/hooks';
import type { Route } from '../../types';
import { commodityMeta, countryName } from '../../lib/data';
import { fmt, fig as fmtFig } from '../../lib/format';
import { GROUP_LABEL, loadRoutes, loadRouteGeo, SEGMENT_LABEL, segmentOf, SEGMENT_COLOR } from '../../lib/freight';
import { lowerName } from '../../lib/prices';
import { flyToLine } from '../../map/controller';
import { Section, SourceLine, Kpi, Skeleton, Placeholder, AlertBanners } from '../ui';
import { AltBox, CommodityChips, HistoryChart, ViaSection, VesselChip, publisher, useFreightCatalogue, useLoaded } from './shared';
import { EventList } from '../EventList';

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
    const add = (k: string, f: NonNullable<Route['shareCommodity']>, g?: string) => {
      const key = `${k}:${g ?? ''}:${f.v}`;
      if (seen.has(key)) return;
      seen.add(key);
      // customs codes do not separate thermal from metallurgical coal: both shares are computed on all coal
      // (a generated corridor names its customs group: alumina and DAP are not bauxite and phosphate rock)
      const name = k === 'thermal-coal' || k === 'met-coal' ? 'coal (all types)' : lowerName((g && GROUP_LABEL[g]) || (commodityMeta(k)?.name ?? k));
      out.push({ label: `Corridor share of seaborne ${name}`, f });
    };
    if (r.shareCommodity) {
      const match = r.shares?.find((s) => s.f.v === r.shareCommodity!.v);
      add(match?.k ?? r.cargoes[0], r.shareCommodity, match?.g);
    }
    for (const s of r.shares ?? []) add(s.k, s.f, s.g);
    return out;
  }, [r]);
  // a corridor whose customs total includes overland and pipeline trade says so in its history note
  const allModes = /^all modes/i.test(r.historyNote ?? '');
  const leg = !!(r.roundVoyage || r.drawnAs);
  const parcel = r.parcel != null ? `${fmt(r.parcel)} ${r.parcelUnit ?? 't'}` : null;
  const fromPort = r.from.ports.join(' / ') || r.from.region;
  const toPort = r.to.ports.join(' / ') || r.to.region;
  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker">{r.generated ? `Atlas corridor · ${SEGMENT_LABEL[seg]}` : r.benchmark ? `Baltic benchmark · ${SEGMENT_LABEL[seg]}` : 'Heavy-traffic route'}</div>
        <h2 class="detail-title">{r.name}</h2>
        <div class="badges">
          {r.benchmark && <span class="code-badge" title="Baltic Exchange route code">{r.id}</span>}
          {r.discontinued && <span class="badge badge-warn">Discontinued {r.discontinued}</span>}
          {r.generated && <span class="badge" title="Not a market benchmark: a corridor of the customs pairs table, drawn between the typical ports of its largest pair">Generated from customs pairs</span>}
          {r.roundVoyage && <span class="badge" title="Benchmark is quoted for a round voyage">Round voyage</span>}
          {r.standIn && <span class="badge badge-warn" title={r.standIn}>Stand-in trace</span>}
        </div>
        {r.generated && (
          <div class="muted small" style={{ marginTop: '6px' }}>
            Atlas corridor, generated from customs pairs. It is not a market benchmark: its ports, vessel class, distance and passages are those of its largest pair.
          </div>
        )}
        {r.roundVoyage && !r.standIn && <div class="muted small" style={{ marginTop: '6px' }}>Benchmark is a round voyage (delivery → redelivery); distance shown is the typical laden leg.</div>}
        {r.standIn ? (
          <div class="muted small" style={{ marginTop: '6px' }}>{r.standIn}</div>
        ) : (
          r.drawnAs && <div class="muted small" style={{ marginTop: '6px' }}>Drawn as its {r.drawnAs}.</div>
        )}
      </div>
      <div class="panel-scroll">
        <AlertBanners route={r.id} chokepoints={r.via} status={r.status} />
        <div class="kpis">
          <Kpi label={r.standIn ? 'Distance · stand-in trace' : leg ? 'Distance · laden leg only' : 'Distance'} value={`${fmt(r.distanceNm)} nm`} sub={r.standIn ? 'Not a distance of this benchmark' : 'SeaRoute network · Atlas routing'} title="Sea-route distance between the representative ports, computed on Eurostat's SeaRoute maritime network" />
          <Kpi label={r.standIn ? 'Laden days · stand-in trace' : leg ? 'Laden days · laden leg only' : 'Laden days'} value={`${fmt(r.days)} d`} sub={`at ${fmt(r.speedKn)} kn · Atlas assumption`} title={`Distance divided by the assumed laden service speed of the class, ${fmt(r.speedKn)} kn (Atlas assumption)`} />
          {shares.map((s) => (
            <Kpi key={s.label} label={s.label} f={s.f} value={fmtFig(s.f)} note={s.f.n} span={!!s.f.n} />
          ))}
          {!r.shareCommodity && r.shareNa && <Kpi label="Corridor share" value="n/a" note={r.shareNa} span />}
          {r.shareClass && (
            <Kpi label="Share of class tonne-miles" f={r.shareClass} sub={`Atlas estimate · ${r.shareClass.y}`} note={r.shareClass.n} span />
          )}
          {parcel && <Kpi label="Standard parcel" value={parcel} sub={pub} title={`Parcel size per route definition (${r.s})`} />}
        </div>
        <Section title="From → To">
          <div class="ft">
            <div class="ft-row"><span class="ft-k">From</span><span><b>{r.from.region}</b>{r.from.ports.length > 0 && <span class="muted"> · {r.from.ports.join(', ')}</span>}</span></div>
            <div class="ft-row"><span class="ft-k">To</span><span><b>{r.to.region}</b>{r.to.ports.length > 0 && <span class="muted"> · {r.to.ports.join(', ')}</span>}</span></div>
          </div>
        </Section>
        {r.finder && (
          <Section title="In the Route finder">
            <p class="prose">
              The distance above is for this route's own ports. The Route finder shows the largest recorded pair of this corridor, {countryName(r.finder.o)} to {countryName(r.finder.d)} ({fmt(r.finder.mt)} Mt in {r.finder.y}), between that pair's typical ports, {r.finder.from} and {r.finder.to}: {fmt(r.finder.nm)} nm.
              {(r.finder.nm > 1.5 * r.distanceNm || r.finder.nm < r.distanceNm / 1.5) && ' The two distances differ by more than half: that pair does not use this route\'s ports.'}
            </p>
            <p class="prose">The corridor figures on this page (share of seaborne trade, volume history, tonne-miles) count every port of the countries of the corridor, not only this route's ports.</p>
          </Section>
        )}
        <Section title="Vessel class">
          <div class="chips"><VesselChip id={r.vclass} /></div>
        </Section>
        {r.cargoes.length > 0 && (
          <Section title="Cargoes">
            <CommodityChips ids={r.cargoes} />
            {r.cargoNote && <div class="muted small" style={{ marginTop: '6px' }}>{r.cargoNote}</div>}
          </Section>
        )}
        <ViaSection from={fromPort} to={toPort} via={r.via} viaAlt={r.viaAlt} />
        <AltBox alt={r.alt} alts={r.alts} note={r.altNote} />
        {r.history && r.history.length > 1 && (
          <Section title={`Corridor volume${allModes ? ', all modes' : ''} ${r.history[0].y}–${r.history[r.history.length - 1].y}`}>
            <HistoryChart years={r.history.map((h) => h.y)} values={r.history.map((h) => h.v)} unit={r.historyUnit ?? ''} color={color} />
            <div class="muted small">All cargoes of the corridor{allModes ? ', every mode of transport' : ''}, {r.historyUnit}.</div>
            <SourceLine s={r.historySrc} y={`${r.history[0].y}–${r.history[r.history.length - 1].y}`} n={r.historyNote} />
          </Section>
        )}
        {r.notes && (
          <Section title="Notes">
            <p class="prose">{r.notes}</p>
          </Section>
        )}
        <EventList route={r.id} />
        <Section title="Definition">
          <SourceLine s={r.s} />
        </Section>
      </div>
    </>
  );
}
