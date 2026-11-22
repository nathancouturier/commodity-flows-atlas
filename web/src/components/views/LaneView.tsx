/** Seaborne lane (origin -> destination for one commodity group). */
import { useEffect } from 'preact/hooks';
import type { LaneFile, Lane, Route } from '../../types';
import { countryName, commodityMeta } from '../../lib/data';
import { fmt, pct, FAMILY_COLOR } from '../../lib/format';
import { laneGroup, loadLaneFile, loadRoutes } from '../../lib/freight';
import { flyToLine } from '../../map/controller';
import { select, year } from '../../lib/store';
import { Section, SourceLine, Kpi, Skeleton, Placeholder, AlertBanners } from '../ui';
import { AltBox, CommodityChips, HistoryChart, ViaSection, VesselChip, publisher, useFreightCatalogue, useLoaded } from './shared';

interface Loaded { file: LaneFile; lane: Lane }

export default function LaneView({ id }: { id: string }) {
  useFreightCatalogue();
  const d = useLoaded<Loaded>(
    () =>
      loadLaneFile(laneGroup(id)).then((file) => {
        const lane = file.lanes.find((l) => l.id === id);
        return lane ? { file, lane } : null;
      }),
    [id],
  );
  const routes = useLoaded<Route[]>(() => loadRoutes(), []);

  useEffect(() => {
    if (d?.lane.g) flyToLine(d.lane.g);
  }, [d]);

  const [group, pair = ''] = id.split(':');
  const [o, dd] = pair.split('-');
  const head = (kicker: string) => (
    <div class="detail-head">
      <div class="detail-kicker">{kicker}</div>
      <h2 class="detail-title">{o && dd ? `${countryName(o)} → ${countryName(dd)}` : id}</h2>
    </div>
  );
  if (d === undefined)
    return (<>{head('Seaborne lane')}<div class="panel-scroll"><Skeleton lines={7} /></div></>);
  if (d === null)
    return (<>{head('Seaborne lane')}<div class="panel-scroll"><Placeholder>This lane is not available in the {group} lane file.</Placeholder></div></>);

  const { file, lane } = d;
  const meta = commodityMeta(lane.k);
  const color = meta ? FAMILY_COLOR[meta.family] : undefined;
  const kicker = file.label ?? meta?.name ?? file.group;
  const pub = publisher(file.s);
  const portNames = (ids: string[]) => ids.map((p) => file.ports[p]?.name ?? p);
  const loadP = portNames(lane.load);
  const disP = portNames(lane.discharge);
  const matching = (routes ?? []).filter((r) => r.corridor?.some((c) => c.k === lane.k && c.o.includes(lane.o) && c.d.includes(lane.d)));
  const groupName = file.label ?? meta?.name ?? file.group;
  // History timeline: the flow and its share of seaborne trade are those of the selected year
  const yr = year.value;
  const yi = yr != null ? file.years.indexOf(yr) : -1;
  const past = yi >= 0 && yr !== lane.flow.y;
  // the note on the flow describes the latest year, not the one the timeline shows
  const n = past ? undefined : lane.flow.n;
  const flowV = past ? lane.hist[yi] : lane.flow.v;
  const flowY = past ? yr! : lane.flow.y;
  const seaV = past ? file.seaborne[yi] : null;
  const share = past ? (flowV != null && seaV ? flowV / seaV : null) : lane.share;
  const shareY = past ? yr! : file.y;

  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker">{kicker}</div>
        <h2 class="detail-title">{countryName(lane.o)} → {countryName(lane.d)}</h2>
      </div>
      <div class="panel-scroll">
        <AlertBanners chokepoints={lane.via} status={lane.status} />
        <div class="kpis">
          {flowV != null ? (
            <Kpi label={`Flow · ${flowY}`} f={past ? { v: flowV, u: file.unit, y: flowY, s: file.s } : lane.flow} note={n} span={!!n} />
          ) : (
            <Kpi label={`Flow · ${flowY}`} value="—" sub={`${pub} · ${flowY}`} note={lane.histNote ?? `No figure for ${flowY}`} span />
          )}
          <Kpi label="Share of seaborne trade" value={pct(share, (flowV ?? 0) > 0)} sub={`${pub} · ${shareY}`} title={`Share of seaborne ${groupName} trade (${file.s}, ${shareY}); Atlas calc`} />
          {lane.shareDest != null && (
            <Kpi label={`Share of ${countryName(lane.d)} imports${past ? ` · ${file.y}` : ''}`} value={pct(lane.shareDest, (flowV ?? 0) > 0)} sub={`${pub} · ${file.y}`} title={`Share of ${countryName(lane.d)}'s imports of ${groupName} (${file.s}, ${file.y}); Atlas calc`} />
          )}
          <Kpi label="Distance" value={`${fmt(lane.distanceNm)} nm`} sub="Atlas routing" title="Along the mapped sea route" />
          <Kpi label="Laden days" value={`${fmt(lane.days)} d`} sub="Atlas estimate" title="At the typical laden speed of the primary vessel class" />
        </div>
        {lane.vclass.length > 0 && (
          <Section title="Typical vessels">
            <div class="chips">{lane.vclass.map((v) => <VesselChip key={v} id={v} />)}</div>
            <div class="muted small" style={{ marginTop: '6px' }}>Typical (Atlas assumption), primary class first.</div>
          </Section>
        )}
        {(loadP.length > 0 || disP.length > 0) && (
          <Section title="Ports">
            <div class="ft">
              {loadP.length > 0 && <div class="ft-row"><span class="ft-k">Load</span><span>{loadP.join(' · ')}</span></div>}
              {disP.length > 0 && <div class="ft-row"><span class="ft-k">Discharge</span><span>{disP.join(' · ')}</span></div>}
            </div>
          </Section>
        )}
        <ViaSection from={loadP[0] ?? countryName(lane.o)} to={disP[0] ?? countryName(lane.d)} via={lane.via} />
        {lane.alt && <AltBox alt={lane.alt} />}
        {lane.hist.length > 1 && (
          <Section title={`Volume ${file.years[0]}–${file.years[file.years.length - 1]}`}>
            <HistoryChart years={file.years} values={lane.hist} unit={file.unit} color={color} />
            <SourceLine s={file.s} y={`${file.years[0]}–${file.years[file.years.length - 1]}`} n={lane.histNote ? `${file.unit} · ${lane.histNote}` : file.unit} />
          </Section>
        )}
        {matching.length > 0 && (
          <Section title="Benchmark routes on this corridor">
            {matching.map((r) => (
              <button class="list-btn" key={r.id} onClick={() => select({ kind: 'route', id: r.id })}>
                {r.benchmark && <span class="code-badge sm">{r.id}</span>}
                <span class="grow">{r.name}</span>
                <span class="meta num">{fmt(r.distanceNm)} nm</span>
              </button>
            ))}
          </Section>
        )}
        <Section title="Commodity">
          <CommodityChips ids={[lane.k]} />
        </Section>
      </div>
    </>
  );
}
