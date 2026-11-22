/// <reference types="vite/client" />
/** Global picture of one commodity: KPIs, ranked countries, main flows, lanes, companies, infrastructure. */
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { Company, CommodityData, Fig, Flow, LaneFile, Ranked } from '../../types';
import { loadOptional, commodityMeta, countryName, sourceLabel } from '../../lib/data';
import { FAMILY_COLOR, FAMILY_LABEL, fmt } from '../../lib/format';
import { LANE_GROUPS, loadLaneFile } from '../../lib/freight';
import { layers, select, toggleLayer } from '../../lib/store';
import { infraCapacity, infraColor, infraMatches, loadInfra, infraRef, type InfraFeature } from '../../map/modules/infrastructure';
import { Section, Placeholder, Skeleton, Kpi, RankedBars, SourceLine, RowBtn, ModeBadge, InfraIcon, INFRA_META, CompanyRows, AlertBanners } from '../ui';
import { useLoaded } from './shared';
import { openPrices } from '../../lib/prices';

/** Opens the bottom price drawer on this commodity's series. */
function usePriceDrawer(): ((id: string) => void) | null {
  return (id: string) => openPrices({ commodity: id });
}

/** What the main trade tables measure when it is not the finished commodity. */
const TRADE_BASIS: Record<string, string> = {
  copper: 'ores and concentrates (gross weight)',
  nickel: 'ores (gross weight)',
  zinc: 'ores and concentrates (gross weight)',
  lead: 'ores and concentrates (gross weight)',
  bauxite: 'bauxite ore',
  'thermal-coal': 'thermal coal (EIA)',
};

type CompanyMap = Record<string, { producers?: Company[]; processors?: Company[]; traders?: Company[] }>;


/** USDA PSD marketing years (US basis where noted). */
const MARKETING_YEAR: Record<string, string> = {
  wheat: 'Jul–Jun',
  corn: 'Sep–Aug (US basis; local years vary)',
  soybeans: 'Sep–Aug',
  soymeal: 'Oct–Sep',
  soyoil: 'Oct–Sep',
  rice: 'Aug–Jul',
  sugar: 'Oct–Sep',
  coffee: 'Oct–Sep',
  cotton: 'Aug–Jul',
  'palm-oil': 'Oct–Sep',
  rapeseed: 'Jul–Jun',
};

/** Ranked table with a marketing-year caption under USDA PSD tables. */
function RankedBlock({ id, data, color }: { id: string; data: Ranked; color?: string }) {
  const my = data.s === 'usda-psd' ? MARKETING_YEAR[id] : undefined;
  return (
    <>
      <RankedBars data={data} color={color} />
      {my && <div class="muted small my-cap">Marketing year: {my} (USDA PSD local marketing years vary by country).</div>}
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

function FlowRows(props: { flows: Flow[] }) {
  const rows = [...props.flows].sort((a, b) => b.v - a.v).slice(0, 10);
  const first = rows[0];
  return (
    <>
      {rows.map((f, i) => (
        <RowBtn
          key={`${f.o}-${f.d}-${i}`}
          lead={<span class="bar-rank">{i + 1}</span>}
          title={<>{countryName(f.o)} <span class="arrow">→</span> {countryName(f.d)}</>}
          sub={<ModeBadge mode={f.mode === 'sea' ? 'sea' : f.mode ? 'land' : undefined} />}
          meta={<>{fmt(f.v)} {f.u}</>}
          tip={`${sourceLabel(f.s)} · ${f.y}${f.n ? ' · ' + f.n : ''}${f.mode && f.mode !== 'sea' ? ' · ' + f.mode : ''}`}
          onClick={() => (f.lane ? select({ kind: 'lane', id: f.lane }) : select({ kind: 'country', id: f.o }))}
        />
      ))}
      {first && <SourceLine s={first.s} y={first.y} n="bilateral flows, all transport modes" />}
    </>
  );
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
  return (
    <Section title="Seaborne lanes">
      <div class="lane-sum">
        <div class="lane-sum-n num" style={{ color }}>{total}</div>
        <div class="lane-sum-t">mapped lane{total === 1 ? '' : 's'}</div>
      </div>
      <div class="ft" style={{ marginTop: '8px' }}>
        {files.map((f) => {
          const last = f.seaborne[f.seaborne.length - 1];
          const yr = f.years[f.years.length - 1];
          return (
            <div class="ft-row ft-wide" key={f.group} title={`${sourceLabel(f.s)} · ${yr}`}>
              <span class="ft-k">{f.label ?? f.group}</span>
              <span class="num">
                {last != null ? `${fmt(last)} ${f.unit} seaborne` : '—'} <span class="muted">· {yr} · {f.lanes.length} lanes</span>
              </span>
            </div>
          );
        })}
      </div>
      <SourceLine s={files[0].s} y={files[0].y} n="Atlas lane method, seaborne subset of customs flows" />
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
  const openPrices = usePriceDrawer();
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
  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker">{meta ? FAMILY_LABEL[meta.family] : 'Commodity'}</div>
        <h2 class="detail-title">{meta?.name ?? id}</h2>
        {meta?.blurb && <p class="muted" style={{ margin: '4px 0 0', fontSize: '13px' }}>{meta.blurb}</p>}
      </div>
      <div class="panel-scroll">
        {d?.summary && (
          <div class="kpis">
            {d.summary.production && <Kpi label="World production" f={d.summary.production} note={d.summary.production.n} />}
            {d.summary.exports && <Kpi label={exportsLabel(d.summary.exports, d.exports)} f={d.summary.exports} note={d.summary.exports.n} />}
            {d.summary.reserves && <Kpi label="World reserves" f={d.summary.reserves} note={d.summary.reserves.n} />}
            {d.summary.consumption && <Kpi label="World consumption" f={d.summary.consumption} note={d.summary.consumption.n} />}
            {d.summary.seaborne && <Kpi label="Seaborne trade" f={d.summary.seaborne} note={d.summary.seaborne.n} />}
          </div>
        )}
        <AlertBanners commodity={id} />
        {openPrices && (
          <button class="act-btn act-prices" onClick={() => openPrices(id)}>
            Price history
          </button>
        )}
        {d === undefined ? (
          <Skeleton lines={8} />
        ) : d === null ? (
          <Placeholder>Data for this commodity is being compiled and will appear in a later release.</Placeholder>
        ) : (
          <>
            {d.production && (
              <Section title="Top producers">
                <RankedBlock id={id} data={d.production} color={color} />
              </Section>
            )}
            {d.refinery && (
              <Section title="Refinery / smelter output">
                <RankedBlock id={id} data={d.refinery} color={color} />
              </Section>
            )}
            {d.exports && (
              <Section title={`Top exporters${TRADE_BASIS[id] ? ` — ${TRADE_BASIS[id]}` : ''}`}>
                <RankedBlock id={id} data={d.exports} color={color} />
              </Section>
            )}
            {d.extra?.filter((x) => x.key.endsWith('exports')).map((x) => (
              <Section title={x.title} key={x.key}>
                <RankedBlock id={id} data={x.table} color={color} />
              </Section>
            ))}
            {d.imports && (
              <Section title={`Top importers${TRADE_BASIS[id] ? ` — ${TRADE_BASIS[id]}` : ''}`}>
                <RankedBlock id={id} data={d.imports} color={color} />
              </Section>
            )}
            {d.extra?.filter((x) => !x.key.endsWith('exports')).map((x) => (
              <Section title={x.title} key={x.key}>
                <RankedBlock id={id} data={x.table} color={color} />
              </Section>
            ))}
            {d.reserves && (
              <Section title="Reserves">
                <RankedBlock id={id} data={d.reserves} color={color} />
              </Section>
            )}
            {d.consumption && (
              <Section title="Top consumers">
                <RankedBlock id={id} data={d.consumption} color={color} />
              </Section>
            )}
            {d.flows && d.flows.length > 0 && (
              <Section title="Main flows">
                <FlowRows flows={d.flows} />
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
