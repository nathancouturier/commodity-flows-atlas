/// <reference types="vite/client" />
/** Global picture of one commodity: KPIs, ranked countries, main flows, lanes, companies, infrastructure. */
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { Company, CommodityData, Fig, Flow, LaneFile, Ranked } from '../../types';
import { loadOptional, commodityMeta, countryName, sourceLabel } from '../../lib/data';
import { FAMILY_COLOR, FAMILY_LABEL, fmt } from '../../lib/format';
import { LANE_GROUPS, loadLaneFile } from '../../lib/freight';
import { layers, select, toggleLayer, year } from '../../lib/store';
import { infraCapacity, infraColor, infraMatches, loadInfra, infraRef, type InfraFeature } from '../../map/modules/infrastructure';
import { Section, Placeholder, Skeleton, Kpi, RankedBars, SourceLine, RowBtn, ModeBadge, InfraIcon, INFRA_META, CompanyRows, AlertBanners, shortSource } from '../ui';
import { useLoaded } from './shared';
import '../../styles/history-year.css';
import { PRICE_COVERAGE_NOTE, loadPriceIndex, lowerName, openPrices, priceIndex, seriesForCommodity } from '../../lib/prices';

/**
 * Opens the bottom price drawer on this commodity's series. `none` is true once the price catalogue is
 * loaded and holds no series for the commodity: the button then says so instead of opening a chart.
 */
function usePriceDrawer(id: string): { open: () => void; none: boolean } {
  useEffect(() => {
    loadPriceIndex().catch(() => undefined);
  }, []);
  const idx = priceIndex.value;
  return { open: () => openPrices({ commodity: id }), none: idx.length > 0 && !seriesForCommodity(id, idx).length };
}

/** What the main trade tables measure when it is not the finished commodity (used when the data file has no `basis`). */
const TRADE_BASIS: Record<string, string> = {
  copper: 'ores and concentrates (gross weight)',
  nickel: 'ores (gross weight)',
  zinc: 'ores and concentrates (gross weight)',
  lead: 'ores and concentrates (gross weight)',
  bauxite: 'bauxite ore',
};

/** Section title: the wording set by the data file, else the default with what the table measures. */
function sectionTitle(d: CommodityData, key: 'production' | 'reserves' | 'consumption' | 'exports' | 'imports' | 'flows', base: string, fallback?: string): string {
  const basis = (key === 'flows' ? undefined : d[key]?.basis) ?? fallback;
  return d.labels?.[key] ?? (basis ? `${base} — ${basis}` : base);
}

/** Customs codes do not separate thermal from metallurgical coal: the flows of both coal pages are all coal. */
const isCoal = (id: string) => id === 'thermal-coal' || id === 'met-coal';

type CompanyMap = Record<string, { producers?: Company[]; processors?: Company[]; traders?: Company[] }>;


/**
 * Ranked table with a marketing-year caption under USDA PSD tables. The figures are PSD local marketing
 * years, which start in a different month in each country: no single month range describes them.
 */
function RankedBlock({ data, color }: { id: string; data: Ranked; color?: string }) {
  return (
    <>
      <RankedBars data={data} color={color} />
      {data.s === 'usda-psd' && (
        <div class="muted small my-cap">Marketing year {data.y}: USDA PSD local marketing years, which start in different months by country.</div>
      )}
    </>
  );
}

/** "World exports (concentrate, gross wt)" when the figure counts ore or concentrate rather than metal. */
function exportsLabel(f: Fig, tbl?: Ranked): string {
  const n = `${f.n ?? ''} ${tbl?.n ?? ''}`;
  const parts: string[] = [];
  if (/concentrate/i.test(n)) parts.push('concentrate');
  else if (/\bores?\b/i.test(n)) parts.push('ore');
  if (/gross weight/i.test(n)) parts.push('gross wt');
  return parts.length ? `World exports (${parts.join(', ')})` : 'World exports';
}

function FlowRows(props: { flows: Flow[]; tag?: string }) {
  const rows = [...props.flows].sort((a, b) => b.v - a.v).slice(0, 10);
  // the footer names the customs source; flows re-based by the atlas say so on their own row
  const first = rows.find((f) => f.s !== 'atlas') ?? rows[0];
  return (
    <>
      {rows.map((f, i) => (
        <RowBtn
          key={`${f.o}-${f.d}-${i}`}
          lead={<span class="bar-rank">{i + 1}</span>}
          title={<>{countryName(f.o)} <span class="arrow">→</span> {countryName(f.d)}</>}
          sub={
            <>
              <ModeBadge mode={f.mode === 'sea' ? 'sea' : f.mode ? 'land' : undefined} />
              {props.tag && <span class="muted-cap"> {props.tag}</span>}
              {f.s === 'atlas' && f.s !== first.s && <span class="muted-cap"> {shortSource(f.s)}</span>}
            </>
          }
          meta={<>{fmt(f.v)} {f.u}</>}
          tip={`${sourceLabel(f.s)} · ${f.y}${f.n ? ' · ' + f.n : ''}${f.mode && f.mode !== 'sea' ? ' · ' + f.mode : ''}`}
          onClick={() => (f.lane ? select({ kind: 'lane', id: f.lane }) : select({ kind: 'country', id: f.o }))}
        />
      ))}
      {first && <SourceLine s={first.s} y={first.y} n="bilateral flows, all transport modes" />}
    </>
  );
}

/** History timeline on another year: the year a block really shows, next to its title. */
function YearTag({ y }: { y?: number | string }) {
  const yr = year.value;
  if (yr == null || y == null || String(y) === String(yr)) return null;
  return <span class="year-tag">latest: {y}</span>;
}

/** KPI label with the figure's own year when the History timeline is on another year. */
function kpiLabel(label: string, f: Fig): string {
  const yr = year.value;
  return yr != null && String(f.y) !== String(yr) ? `${label} · ${f.y}` : label;
}

/**
 * Seaborne trade of the History year. The summary figure is the latest value of the yearly series of the
 * commodity's first lane group; the year replaces it only when that link holds (same source, unit and value).
 */
function seaborneAt(f: Fig | undefined, file: LaneFile | null | undefined, yr: number | null): Fig | undefined {
  if (!f || !file || yr == null || String(f.y) === String(yr)) return f;
  const i = file.years.indexOf(yr);
  const latest = file.seaborne[file.years.indexOf(Number(f.y))];
  if (i < 0 || file.seaborne[i] == null || latest == null) return f;
  if (file.s !== f.s || file.unit !== f.u || Math.abs(latest - f.v) > 0.005 * Math.abs(f.v)) return f;
  return { ...f, v: file.seaborne[i], y: yr };
}

function LaneSummary({ id, color }: { id: string; color?: string }) {
  const groups = LANE_GROUPS[id];
  const files = useLoaded<LaneFile[]>(
    () => (groups?.length ? Promise.all(groups.map((g) => loadLaneFile(g).catch(() => null))).then((r) => r.filter((x): x is LaneFile => !!x)) : Promise.resolve([])),
    [id],
  );
  if (!files || !files.length) return null;
  const on = layers.value.flows;
  const total = files.reduce((n, f) => n + f.lanes.length, 0);
  const hy = year.value;
  const shownY = hy != null && files[0].years.includes(hy) ? hy : files[0].y;
  return (
    <Section title="Seaborne lanes">
      <div class="lane-sum">
        <div class="lane-sum-n num" style={{ color }}>{total}</div>
        <div class="lane-sum-t">mapped lane{total === 1 ? '' : 's'}</div>
      </div>
      <div class="ft" style={{ marginTop: '8px' }}>
        {files.map((f) => {
          // the History year when the series has it, else the latest year
          const at = hy != null ? f.years.indexOf(hy) : -1;
          const i = at >= 0 ? at : f.years.length - 1;
          const last = f.seaborne[i];
          const yr = f.years[i];
          const active = at >= 0 ? f.lanes.filter((l) => (l.hist[i] ?? 0) > 0).length : f.lanes.length;
          return (
            <div class="ft-row ft-wide" key={f.group} title={`${sourceLabel(f.s)} · ${yr}`}>
              <span class="ft-k">{f.label ?? f.group}</span>
              <span class="num">
                {last != null ? `${fmt(last)} ${f.unit} seaborne` : '—'} <span class="muted">· {yr} · {active} lanes{at >= 0 ? ' with a flow' : ''}</span>
              </span>
            </div>
          );
        })}
      </div>
      <SourceLine s={files[0].s} y={shownY} n="Atlas lane method, seaborne subset of customs flows" />
      <button class="act-btn" disabled={on} onClick={() => toggleLayer('flows', true)}>
        {on ? 'Lanes shown on the map' : 'Show lanes on the map'}
      </button>
    </Section>
  );
}

function KeyInfra({ id }: { id: string }) {
  const all = useLoaded<InfraFeature[]>(() => loadInfra(), []);
  const on = layers.value.infrastructure;
  const mine = useMemo(
    () =>
      (all ?? [])
        .filter((f) => infraMatches(f.p.k, id))
        .sort((a, b) => a.pri - b.pri || (b.p.capacity?.v ?? 0) - (a.p.capacity?.v ?? 0)),
    [all, id],
  );
  if (!mine.length) return null;
  return (
    <Section title="Key infrastructure" aside={<span class="muted num">{mine.length}</span>}>
      {mine.slice(0, 8).map((f) => {
        const first = f.p.k[0];
        const own = first === id || ((id === 'thermal-coal' || id === 'met-coal') && first === 'coal');
        const other = commodityMeta(first)?.name ?? first;
        return (
          <RowBtn
            key={f.p.type + f.p.id}
            lead={<InfraIcon type={f.p.type} color={infraColor(f)} size={22} />}
            title={f.p.name}
            sub={
              <>
                {[INFRA_META[f.p.type].label, countryName(f.p.c), f.p.capacity && own ? infraCapacity(f.p) : null].filter(Boolean).join(' · ')}
                {f.p.capacity && !own && <span class="muted-cap"> · (capacity for {other})</span>}
              </>
            }
            tip={`${sourceLabel(f.p.s)} · ${f.p.y}`}
            onClick={() => select(infraRef(f))}
          />
        );
      })}
      <SourceLine s={mine[0].p.s} y={mine[0].p.y} n="capacity figures per asset in its own panel" />
      <button class="act-btn" disabled={on} onClick={() => toggleLayer('infrastructure', true)}>
        {on ? `${mine.length} asset${mine.length === 1 ? '' : 's'} shown on the map` : `Show ${mine.length} asset${mine.length === 1 ? '' : 's'} on the map`}
      </button>
    </Section>
  );
}

export default function CommodityView({ id }: { id: string }) {
  const meta = commodityMeta(id);
  const [d, setD] = useState<CommodityData | null | undefined>(undefined);
  const [co, setCo] = useState<CompanyMap | null>(null);
  const prices = usePriceDrawer(id);
  const seaFile = useLoaded<LaneFile>(() => (LANE_GROUPS[id]?.[0] ? loadLaneFile(LANE_GROUPS[id][0]) : Promise.resolve(null)), [id]);
  const yr = year.value;
  useEffect(() => {
    let live = true;
    setD(undefined);
    loadOptional<CommodityData>(`commodities/${id}.json`).then((x) => live && setD(x));
    return () => {
      live = false;
    };
  }, [id]);
  useEffect(() => {
    loadOptional<CompanyMap>('commodities/companies.json').then(setCo);
  }, []);
  const color = meta ? FAMILY_COLOR[meta.family] : undefined;
  const companies = d?.companies ?? co?.[id];
  const hasCo = !!companies && (companies.producers?.length || companies.processors?.length || companies.traders?.length);
  const seaborne = seaborneAt(d?.summary.seaborne, seaFile, yr);
  const seaFollows = !!seaborne && String(seaborne.y) === String(yr);
  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker">{meta ? FAMILY_LABEL[meta.family] : 'Commodity'}</div>
        <h2 class="detail-title">{meta?.name ?? id}</h2>
        {meta?.blurb && <p class="muted" style={{ margin: '4px 0 0', fontSize: '13px' }}>{meta.blurb}</p>}
      </div>
      <div class="panel-scroll">
        {yr != null && d && (
          <div class="year-note">
            History year <b class="num">{yr}</b>:{' '}
            {seaFollows
              ? 'the seaborne trade figure and the seaborne lanes follow it. Every other figure and table'
              : LANE_GROUPS[id]?.length
                ? 'only the seaborne lanes follow it. Every other figure and table'
                : 'no yearly series for this commodity. Every figure and table'}{' '}
            is the latest published and shows its own year.
          </div>
        )}
        {d?.summary && (
          <div class="kpis">
            {d.summary.production && <Kpi label={kpiLabel(d.kpis?.production ?? 'World production', d.summary.production)} f={d.summary.production} note={d.summary.production.n} />}
            {d.summary.exports && <Kpi label={kpiLabel(d.kpis?.exports ?? exportsLabel(d.summary.exports, d.exports), d.summary.exports)} f={d.summary.exports} note={d.summary.exports.n} />}
            {d.summary.reserves && <Kpi label={kpiLabel(d.kpis?.reserves ?? 'World reserves', d.summary.reserves)} f={d.summary.reserves} note={d.summary.reserves.n} />}
            {d.summary.consumption && <Kpi label={kpiLabel(d.kpis?.consumption ?? 'World consumption', d.summary.consumption)} f={d.summary.consumption} note={d.summary.consumption.n} />}
            {seaborne && <Kpi label={`${d.kpis?.seaborne ?? 'Seaborne trade'}${yr != null ? ` · ${seaborne.y}` : ''}`} f={seaborne} note={seaborne.n} />}
          </div>
        )}
        <AlertBanners commodity={id} />
        {prices.none ? (
          <button class="act-btn act-prices" disabled title="The atlas only charts prices from free sources; none is available for this commodity yet.">
            No free price series for {lowerName(meta?.name ?? id)} yet
          </button>
        ) : (
          <button class="act-btn act-prices" onClick={prices.open}>
            Price history
          </button>
        )}
        {!prices.none && PRICE_COVERAGE_NOTE[id] && <div class="muted small my-cap">{PRICE_COVERAGE_NOTE[id]}</div>}
        {d === undefined ? (
          <Skeleton lines={8} />
        ) : d === null ? (
          <Placeholder>Data for this commodity is being compiled and will appear in a later release.</Placeholder>
        ) : (
          <>
            {d.production && (
              <Section title={sectionTitle(d, 'production', 'Top producers')} aside={<YearTag y={d.production.y} />}>
                <RankedBlock id={id} data={d.production} color={color} />
              </Section>
            )}
            {d.extra?.filter((x) => x.key.endsWith('production')).map((x) => (
              <Section title={x.title} key={x.key} aside={<YearTag y={x.table.y} />}>
                <RankedBlock id={id} data={x.table} color={color} />
              </Section>
            ))}
            {d.refinery && (
              <Section title="Refinery / smelter output" aside={<YearTag y={d.refinery.y} />}>
                <RankedBlock id={id} data={d.refinery} color={color} />
              </Section>
            )}
            {d.exports && (
              <Section title={sectionTitle(d, 'exports', 'Top exporters', TRADE_BASIS[id])} aside={<YearTag y={d.exports.y} />}>
                <RankedBlock id={id} data={d.exports} color={color} />
              </Section>
            )}
            {d.extra?.filter((x) => x.key.endsWith('exports')).map((x) => (
              <Section title={x.title} key={x.key} aside={<YearTag y={x.table.y} />}>
                <RankedBlock id={id} data={x.table} color={color} />
              </Section>
            ))}
            {d.imports && (
              <Section title={sectionTitle(d, 'imports', 'Top importers', TRADE_BASIS[id])} aside={<YearTag y={d.imports.y} />}>
                <RankedBlock id={id} data={d.imports} color={color} />
              </Section>
            )}
            {d.extra?.filter((x) => !x.key.endsWith('exports') && !x.key.endsWith('production')).map((x) => (
              <Section title={x.title} key={x.key} aside={<YearTag y={x.table.y} />}>
                <RankedBlock id={id} data={x.table} color={color} />
              </Section>
            ))}
            {d.reserves && (
              <Section title={sectionTitle(d, 'reserves', 'Reserves')} aside={<YearTag y={d.reserves.y} />}>
                <RankedBlock id={id} data={d.reserves} color={color} />
              </Section>
            )}
            {d.consumption && (
              <Section title={sectionTitle(d, 'consumption', 'Top consumers')} aside={<YearTag y={d.consumption.y} />}>
                <RankedBlock id={id} data={d.consumption} color={color} />
              </Section>
            )}
            {d.flows && d.flows.length > 0 && (
              <Section title={sectionTitle(d, 'flows', 'Main flows')} aside={<YearTag y={d.flows[0].y} />}>
                <FlowRows flows={d.flows} tag={isCoal(id) ? 'all coal' : undefined} />
              </Section>
            )}
            <LaneSummary id={id} color={color} />
            {hasCo && (
              <Section title="Main companies">
                <CompanyRows title="Producers" list={companies!.producers ?? []} />
                <CompanyRows title="Processors" list={companies!.processors ?? []} />
                <CompanyRows title="Traders" list={companies!.traders ?? []} />
              </Section>
            )}
            <KeyInfra id={id} />
            {((d.notes?.length ?? 0) > 0 || (d.discrepancies?.length ?? 0) > 0) && (
              <Section title="Notes">
                <ul class="bullets small-print">
                  {d.notes?.map((n, i) => <li key={'n' + i}>{n}</li>)}
                  {d.discrepancies?.map((n, i) => <li key={'d' + i} class="disc">Discrepancy: {n}</li>)}
                </ul>
              </Section>
            )}
          </>
        )}
      </div>
    </>
  );
}
