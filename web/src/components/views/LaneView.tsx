/** Seaborne lane (origin -> destination for one commodity group). */
import { useEffect } from 'preact/hooks';
import type { LaneFile, Lane, Route } from '../../types';
import { countryName, commodityMeta } from '../../lib/data';
import { fmt, pct, FAMILY_COLOR } from '../../lib/format';
import { laneGroup, loadLaneFile, loadRoutes } from '../../lib/freight';
import { flyToLine } from '../../map/controller';
import { select } from '../../lib/store';
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
  const n = lane.flow.n;

  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker">{kicker}</div>
        <h2 class="detail-title">{countryName(lane.o)} → {countryName(lane.d)}</h2>
      </div>
      <div class="panel-scroll">
        <AlertBanners chokepoints={lane.via} status={lane.status} />
        <div class="kpis">
          <Kpi label={`Flow · ${lane.flow.y}`} f={lane.flow} note={n} span={!!n} />
          <Kpi label="Share of seaborne trade" value={pct(lane.share)} sub={`${pub} · ${file.y}`} title={`Share of seaborne ${groupName} trade (${file.s}, ${file.y}); Atlas calc`} />
          {lane.shareDest != null && (
            <Kpi label={`Share of ${countryName(lane.d)} imports`} value={pct(lane.shareDest)} sub={`${pub} · ${file.y}`} title={`Share of ${countryName(lane.d)}'s imports of ${groupName} (${file.s}, ${file.y}); Atlas calc`} />
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
