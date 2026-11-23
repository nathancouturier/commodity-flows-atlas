/** Seaborne lane (origin -> destination for one commodity group). */
import { useEffect } from 'preact/hooks';
import type { CaveatsFile, HistFlag, LaneFile, Lane, PortRef, Route } from '../../types';
import { countryName, commodityMeta } from '../../lib/data';
import { fmt, fmtEst, pct, FAMILY_COLOR } from '../../lib/format';
import { laneGroup, loadCaveats, loadLaneFile, loadRoutes } from '../../lib/freight';
import { flyToLine } from '../../map/controller';
import { select, year } from '../../lib/store';
import { Section, SourceLine, Kpi, Skeleton, Placeholder, AlertBanners, shortSource } from '../ui';
import { AltBox, CommodityChips, HistoryChart, ViaSection, VesselChip, publisher, useFreightCatalogue, useLoaded } from './shared';
import '../../styles/lane-engine.css';

interface Loaded { file: LaneFile; lane: Lane }

/** The page a gateway row was read from; a port the atlas used before the tables were sourced says so. */
function PortSource({ p }: { p?: PortRef }) {
  if (!p?.s) return <span class="le-src muted"> · no source page yet</span>;
  const name = shortSource(p.s).replace(/\s*\(.*\)$/, '');
  return (
    <span class="le-src">
      {' · '}
      {p.url ? <a href={p.url} target="_blank" rel="noopener">{name}</a> : name}
    </span>
  );
}

/** Years of a history flag, in order. */
const flagYears = (flags: Record<string, HistFlag> | undefined, f: HistFlag) =>
  Object.entries(flags ?? {}).filter(([, v]) => v === f).map(([y]) => y).sort();

/** One line per kind of flagged year under the history chart (estimated, no record, hidden, checked, kept). */
function HistFlagNotes({ lane }: { lane: Lane }) {
  const flags = lane.histFlags;
  const notes = lane.histNotes ?? {};
  const est = flagYears(flags, 'est');
  const nodata = flagYears(flags, 'nodata');
  const kept = flagYears(flags, 'kept');
  const lines: [string, string][] = [];
  if (est.length) lines.push(['Atlas estimate', `tonnage computed from the declared value: ${est.join(', ')}`]);
  for (const y of flagYears(flags, 'suspect')) lines.push(['Not shown', notes[y] ?? `${y}: the declared value does not fit the tonnage`]);
  if (nodata.length) lines.push(['No customs record', nodata.join(', ')]);
  for (const y of flagYears(flags, 'check')) lines.push([`${y}, checked`, notes[y] ?? 'checked against a national statistic']);
  if (kept.length) lines.push(['Kept as reported', `the declared value moved with the tonnage: ${kept.join(', ')}`]);
  if (!lines.length) return null;
  return (
    <ul class="le-flags">
      {lines.map(([k, t]) => <li key={k + t}><b>{k}</b>: {t}</li>)}
    </ul>
  );
}

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
  const caveats = useLoaded<CaveatsFile>(() => loadCaveats(), []);

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
  const mixed = lane.mode === 'mixed';
  const kicker = `${mixed ? 'Sea and overland lane' : 'Seaborne lane'} · ${file.label ?? meta?.name ?? file.group}`;
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
  // the note on the flow describes the latest year, not the one the timeline shows (a past year has its own, if any)
  const n = past ? lane.histNotes?.[String(yr)] : lane.flow.n;
  const flowV = past ? lane.hist[yi] : lane.flow.v;
  const flowY = past ? yr! : lane.flow.y;
  // an estimated tonnage is an Atlas estimate: labelled as one and printed with two significant digits
  const est = past ? lane.histFlags?.[String(yr)] === 'est' : !!lane.flow.est;
  const seaV = past ? file.seaborne[yi] : null;
  const share = past ? (flowV != null && seaV ? flowV / seaV : null) : lane.share;
  const shareY = past ? yr! : file.y;
  const flowLabel = `Flow${mixed ? ', all modes' : ''} · ${flowY}`;
  const caveat = lane.caveat ? caveats?.[lane.caveat] : undefined;
  const transitEnd = lane.transit ? (lane.load.includes(lane.transit.port) ? lane.o : lane.discharge.includes(lane.transit.port) ? lane.d : null) : null;
  const tport = lane.transit ? file.ports[lane.transit.port] : undefined;
  // coast options: "9,251 nm from New Orleans, or 4,352 nm from Kalama"
  const opts = lane.opts ?? [];
  const loadsDiffer = opts.some((o) => !lane.load.includes(o.load));
  const disDiffer = opts.some((o) => !lane.discharge.includes(o.discharge));
  const where = (l: string[], t: string[]) => [loadsDiffer && `from ${portNames(l).join(' / ')}`, disDiffer && `to ${portNames(t).join(' / ')}`].filter(Boolean).join(' ');
  const distances = opts.length
    ? [
        { nm: lane.distanceNm, at: where(lane.load, lane.discharge), w: null as number | null },
        ...opts.map((o) => ({ nm: o.nm, at: where([o.load], [o.discharge]), w: o.w })),
      ]
    : [];
  const basisNote =
    lane.portBasis === 'open'
      ? 'No source says how this trade splits between ports: the first of each is the principal gateway, drawn on the map.'
      : lane.portBasis === 'measured'
        ? 'The split between ports comes from a measured source.'
        : lane.portBasis === 'rule'
          ? 'Ports chosen by a coast rule (Atlas assumption).'
          : null;

  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker">{kicker}</div>
        <h2 class="detail-title">{countryName(lane.o)} → {countryName(lane.d)}</h2>
      </div>
      <div class="panel-scroll">
        <AlertBanners chokepoints={lane.via} status={lane.status} />
        {caveat && (
          <div class="alert alert-medium le-caveat" role="note">
            <div class="alert-head"><b>Note on the customs data</b></div>
            <p>{caveat.text}</p>
          </div>
        )}
        <div class="kpis">
          {flowV == null ? (
            <Kpi label={flowLabel} value="—" sub={`${pub} · ${flowY}`} note={n ?? lane.histNote ?? `No figure for ${flowY}`} span />
          ) : flowV === 0 ? (
            <Kpi label={flowLabel} value="—" sub={`${pub} · ${flowY}`} note={`No flow recorded in ${flowY}.${lane.set === 'history' ? ' The lane is drawn on the map only in the years when it was among the largest pairs of its group.' : ''}`} span />
          ) : est ? (
            <Kpi label={flowLabel} value={`${fmtEst(flowV, true)} ${file.unit}`} sub={`Atlas estimate · ${flowY}`} title={`Atlas estimate, ${flowY}`} note={n ?? 'Atlas estimate: tonnage computed from the declared value (CEPII BACI).'} span />
          ) : (
            <Kpi label={flowLabel} f={past ? { v: flowV, u: file.unit, y: flowY, s: file.s } : lane.flow} note={n} span={!!n} />
          )}
          {!mixed && (
            <Kpi label="Share of seaborne trade" value={pct(share, (flowV ?? 0) > 0)} sub={`${pub} · ${shareY}`} title={`Share of seaborne ${groupName} trade (${file.s}, ${shareY}); Atlas calc`} />
          )}
          {lane.shareDest != null && (
            <Kpi label={`Share of ${countryName(lane.d)} imports${past ? ` · ${file.y}` : ''}`} value={pct(lane.shareDest, (flowV ?? 0) > 0)} sub={`${pub} · ${file.y}`} title={`Share of ${countryName(lane.d)}'s imports of ${groupName} (${file.s}, ${file.y}); Atlas calc`} />
          )}
          <Kpi label="Distance" value={`${fmt(lane.distanceNm)} nm`} sub={opts.length ? 'Atlas routing · main ports' : 'Atlas routing'} title={mixed ? 'Along the sea route the atlas draws; this trade also moves overland' : 'Along the mapped sea route'} />
          <Kpi label="Laden days" value={`${fmt(lane.days)} d`} sub="Atlas estimate" title="At the typical laden speed of the primary vessel class" />
        </div>
        {lane.vclass.length > 0 && (
          <Section title="Typical vessels">
            <div class="chips">{lane.vclass.map((v) => <VesselChip key={v} id={v} />)}</div>
            <div class="muted small" style={{ marginTop: '6px' }}>Typical (Atlas assumption), primary class first.</div>
          </Section>
        )}
        {(loadP.length > 0 || disP.length > 0) && (
          <Section title="Typical ports (Atlas assumption)">
            {lane.transit && (
              <div class="le-transit">
                Sea via <b>{tport?.name ?? lane.transit.port}</b>, {countryName(lane.transit.c)}.
                {transitEnd && <> {countryName(transitEnd)} is landlocked.</>}
                <PortSource p={{ id: lane.transit.port, name: '', c: lane.transit.c, at: [0, 0], s: lane.transit.s, url: lane.transit.url }} />
              </div>
            )}
            <div class="ft">
              {loadP.length > 0 && (
                <div class="ft-row"><span class="ft-k">Load</span><span>{lane.load.map((p, i) => <span class="le-port" key={p}>{loadP[i]}<PortSource p={file.ports[p]} /></span>)}</span></div>
              )}
              {disP.length > 0 && (
                <div class="ft-row"><span class="ft-k">Discharge</span><span>{lane.discharge.map((p, i) => <span class="le-port" key={p}>{disP[i]}<PortSource p={file.ports[p]} /></span>)}</span></div>
              )}
            </div>
            {distances.length > 0 && (
              <div class="le-dist">
                {distances.map((x, i) => (
                  <span key={i}>
                    {i > 0 && ', or '}
                    <span class="num">{fmt(x.nm)} nm</span>{x.at && ` ${x.at}`}{x.w != null && ` (${Math.round(x.w * 100)}% of the trade)`}
                  </span>
                ))}
              </div>
            )}
            {basisNote && <div class="muted small" style={{ marginTop: '6px' }}>{basisNote}</div>}
          </Section>
        )}
        <ViaSection from={loadP[0] ?? countryName(lane.o)} to={disP[0] ?? countryName(lane.d)} via={lane.via} viaAlt={lane.viaAlt} />
        <AltBox alts={lane.alts} alt={lane.alt} note={lane.altNote} />
        {lane.hist.length > 1 && (
          <Section title={`Volume ${file.years[0]}–${file.years[file.years.length - 1]}`}>
            <HistoryChart years={file.years} values={lane.hist} unit={file.unit} color={color} flags={lane.histFlags} />
            <HistFlagNotes lane={lane} />
            <SourceLine s={file.s} y={`${file.years[0]}–${file.years[file.years.length - 1]}`} n={lane.histNote && !lane.histFlags ? `${file.unit} · ${lane.histNote}` : file.unit} />
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
