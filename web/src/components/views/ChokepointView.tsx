/** Chokepoint: PortWatch traffic chart, published flows, cargo on mapped lanes, events. */
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import type { Chokepoint, ChokepointLanes, Fig, FreightEvent, PortwatchSeries } from '../../types';
import { commodityMeta, countryName, load } from '../../lib/data';
import { fig as fmtFig, fmt as fmtNum, pctText } from '../../lib/format';
import { GROUP_LABEL, chokepointName, loadChokepoints, loadEvents, loadLaneFile, loadPortwatch, SHARE_LABEL } from '../../lib/freight';
import { getMap } from '../../map/controller';
import { select } from '../../lib/store';
import { Section, SourceLine, SourcesLine, Kpi, Skeleton, Placeholder, AlertBanners, FoldNote } from '../ui';
import { TimeChart, DAY, YEAR, parseDate, parseEnd } from '../charts/TimeChart';
import type { TimeMarker } from '../charts/TimeChart';
import { EVENT_COLOR, EVENT_KIND_LABEL, fmtEventDate } from './EventView';
import { publisher, useFreightCatalogue, useLoaded } from './shared';
import { sources } from '../../lib/data';
import '../../styles/lane-table.css';

const RANGES = [
  { label: '1Y', seconds: YEAR },
  { label: '3Y', seconds: 3 * YEAR },
  { label: 'All', seconds: null },
];
const PW_COLORS = { tanker: '#ffb547', dry: '#9db7ff', container: '#c7a3ff', other: '#7d8a99' };

const shareLabel = (k: string) => SHARE_LABEL[k] ?? commodityMeta(k)?.name ?? k;

const loadChokepointLanes = () => load<ChokepointLanes>('freight/chokepoint-lanes.json');

/** End of a published period as a decimal year, to order "2Q26", "1H25", "FY2025" and plain years. */
function periodEnd(y: number | string): number {
  const s = String(y);
  let m = /^([1-4])Q(\d{2})$/.exec(s);
  if (m) return 2000 + Number(m[2]) + Number(m[1]) / 4;
  m = /^([12])H(\d{2})$/.exec(s);
  if (m) return 2000 + Number(m[2]) + Number(m[1]) / 2;
  m = /^FY(\d{4})$/.exec(s);
  if (m) return Number(m[1]) + 0.75;
  m = /^(\d{4})$/.exec(s);
  return m ? Number(m[1]) + 1 : 0;
}

/** "Traffic, last 28 days" only for a figure that is one; a counter that is not the chokepoint itself is named. */
function trafficLabel(f: Fig, what: string, counter?: string): string {
  const recent = String(f.y).startsWith('28 days');
  const head = counter ? `${counter}: ${what.toLowerCase()}` : what;
  return recent ? `${head}, last 28 days` : head;
}

const GRID = { display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 62px 58px', gap: '8px', alignItems: 'baseline', width: '100%' };
const RIGHT = { textAlign: 'right' as const };
const TOP_GROUPS = 8;
const TOP_LANES = 10;

/**
 * What "at least" and "up to" mean (the one definition, also in the methodology). "at least" counts the pairs
 * whose assumed route has to cross the passage; "up to" adds the pairs that may cross it.
 */
const ESTIMATE_DEFINITION =
  'At least: customs tonnage of every recorded seaborne pair whose assumed route has to cross this passage. Up to: adds the pairs that may cross it, because they can use a parallel passage of similar length or load on another coast. Mixed sea-and-overland pairs and trades that customs data do not record are in neither.';

type Estimate = NonNullable<Chokepoint['estimates']>[number];

/** "at least 30.2%" when only the lower figure is known, "30.2% to 40.1%" for a range, "30.2%" when both agree. */
function estimateText(e: Estimate): string {
  const lo = pctText(e.f.v);
  if (e.hi && e.hi.v - e.f.v >= 0.05) return `${lo} to ${pctText(e.hi.v)}`;
  if (!e.hi && /^at least/i.test(e.f.n ?? '')) return `at least ${lo}`;
  return lo;
}

/** The tonnage behind an estimate, "564 to 749 Mt". */
function estimateMt(e: Estimate): string | null {
  if (!e.mt) return null;
  const [lo, hi] = e.mt;
  return hi - lo >= 0.5 ? `${fmtNum(lo)} to ${fmtNum(hi)} Mt` : `${fmtNum(lo)} Mt`;
}

/** Share of each commodity's seaborne trade that crosses the passage, as the atlas computes it: a floor and, where the route is not certain, a ceiling. */
function Estimates({ cp, withDefinition }: { cp: Chokepoint; withDefinition: boolean }) {
  const [all, setAll] = useState(false);
  useEffect(() => setAll(false), [cp.id]);
  const rows = useMemo(() => [...(cp.estimates ?? [])].sort((a, b) => (b.hi?.v ?? b.f.v) - (a.hi?.v ?? a.f.v)), [cp]);
  if (!rows.length) return null;
  const shown = all ? rows : rows.slice(0, TOP_GROUPS);
  const two = (e: Estimate) => e.p && e.p !== e.k && GROUP_LABEL[e.p];
  return (
    <Section title="Atlas estimates" aside={<span class="num">{rows[0].f.y}</span>}>
      {withDefinition && <div class="muted small" style={{ marginBottom: '6px' }}>{ESTIMATE_DEFINITION}</div>}
      {shown.map((e, i) => {
        const mt = estimateMt(e);
        const range = !!e.hi && e.hi.v - e.f.v >= 0.05;
        return (
          <div class="est-row" key={`${e.k}-${e.p ?? ''}-${i}`} title={`${sources.value[e.f.s]?.name ?? e.f.s} · ${e.f.y}`}>
            <div class="est-head">
              <span class="est-k">{shareLabel(e.k)}{two(e) ? ` · ${GROUP_LABEL[e.p!]}` : ''}</span>
              <span class="est-v num">{estimateText(e)}</span>
            </div>
            {mt && <div class="est-sub num">{mt}</div>}
            <FoldNote class="est-sub" style={{ marginTop: '2px' }} text={[e.f.n, range ? e.hi!.n : null].filter(Boolean).join(' · ')} />
          </div>
        );
      })}
      {rows.length > shown.length && (
        <button class="list-btn muted small" onClick={() => setAll(true)}>
          Show all {rows.length} commodities
        </button>
      )}
      <SourcesLine items={[{ s: rows[0].f.s, y: rows[0].f.y }, { s: 'baci', y: rows[0].f.y }]} n="Atlas routing of every recorded seaborne pair" />
    </Section>
  );
}

/** Cargo that crosses the chokepoint: one row per commodity group, opening its pairs. Pairs that only may cross it are marked. */
function LaneTable({ doc, id, definitionHere }: { doc: ChokepointLanes; id: string; definitionHere: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  const [allGroups, setAllGroups] = useState(false);
  const [allLanes, setAllLanes] = useState(false);
  const rows = doc.chokepoints[id] ?? [];
  // a fifth element tells a pair that has to cross (1) from one that may (0); files without it list mapped lanes only
  const sure = (r: (typeof rows)[number]) => r[4] !== 0;
  const fromPairs = rows.some((r) => r.length > 4);
  const hasMay = rows.some((r) => !sure(r));
  const groups = useMemo(() => {
    const by = new Map<string, { v: number; maybe: number }>();
    for (const r of rows) {
      const e = by.get(r[0]) ?? { v: 0, maybe: 0 };
      if (sure(r)) e.v += r[3];
      else e.maybe += r[3];
      by.set(r[0], e);
    }
    return [...by.entries()].map(([g, e]) => ({ g, ...e, meta: doc.groups[g] })).sort((a, b) => b.v - a.v || b.maybe - a.maybe);
  }, [rows, doc]);
  // only a pair with a lane has a page: the others are listed, not drawn
  const laneIds = useLoaded<Set<string>>(() => (open ? loadLaneFile(open).then((f) => new Set(f.lanes.map((l) => l.id))) : Promise.resolve(null)), [open]);
  useEffect(() => {
    setOpen(null);
    setAllGroups(false);
  }, [id]);
  if (!rows.length) return null;
  const label = (g: string) => doc.groups[g]?.label ?? commodityMeta(doc.groups[g]?.k ?? g)?.name ?? g;
  const share = (v: number, g: string) => {
    const tot = doc.groups[g]?.seaborne;
    if (!tot) return '—';
    const p = (100 * v) / tot;
    return pctText(p);
  };
  const shown = allGroups ? groups : groups.slice(0, TOP_GROUPS);
  const srcs = [...new Set(groups.map((x) => x.meta?.s).filter(Boolean))] as string[];
  return (
    <Section title={fromPairs ? 'Cargo through this passage' : 'Cargo on mapped lanes'} aside={<span class="num">{doc.y}</span>}>
      <div class="muted small" style={{ marginBottom: '6px' }}>
        {fromPairs
          ? `Recorded seaborne pairs whose assumed route crosses this passage, by commodity (Atlas routing, not a published statistic). ${hasMay ? 'A pair marked "may use" can cross it or a parallel passage: it counts in "up to" only. ' : ''}Select a commodity to list its pairs.`
          : 'Lanes mapped in the atlas whose route crosses this passage, by commodity: an Atlas estimate, not a published statistic. Select a commodity to list its lanes.'}
        {fromPairs && definitionHere && <> {ESTIMATE_DEFINITION}</>}
      </div>
      {/* how the rows were chosen, as the builder writes it */}
      {fromPairs && <FoldNote class="muted small" style={{ marginBottom: '6px' }} text={doc.n} />}
      <div class="muted small" style={{ ...GRID, padding: '0 8px' }}>
        <span>Commodity</span>
        <span style={RIGHT} title={hasMay ? 'Pairs whose route has to cross the passage; the pairs that may cross it are not in this figure' : undefined}>{hasMay ? 'At least, Mt' : 'Mt'}</span>
        <span style={RIGHT} title="Share of the commodity's seaborne trade">% seaborne</span>
      </div>
      {shown.map(({ g, v, maybe }) => {
        const lanes = open === g ? rows.filter((r) => r[0] === g) : [];
        const list = allLanes ? lanes : lanes.slice(0, TOP_LANES);
        return (
          <div key={g}>
            <button
              class="list-btn"
              aria-expanded={open === g}
              onClick={() => {
                setOpen(open === g ? null : g);
                setAllLanes(false);
              }}
              title={`${label(g)}: ${fmtNum(v)} Mt of ${fmtNum(doc.groups[g]?.seaborne)} Mt seaborne trade (${doc.groups[g]?.y})${maybe > 0 ? `; up to ${fmtNum(v + maybe)} Mt with the pairs that may cross it` : ''}`}
            >
              <span style={GRID}>
                <span>
                  {label(g)}
                  {maybe > 0 && <span class="est-sub" style={{ display: 'block', margin: 0 }}>up to {fmtNum(v + maybe)} Mt with the pairs that may cross it</span>}
                </span>
                <span class="num" style={RIGHT}>{v > 0 ? fmtNum(v) : '—'}</span>
                <span class="num" style={RIGHT}>{v > 0 ? share(v, g) : '—'}</span>
              </span>
            </button>
            {open === g && (
              <div style={{ margin: '0 0 6px 10px', borderLeft: '1px solid var(--hairline-strong)' }}>
                {list.map((r) => {
                  const [, o, d, lv] = r;
                  const lane = `${g}:${o}-${d}`;
                  const drawn = !laneIds || laneIds.has(lane);
                  const body = (
                    <span class="small" style={GRID}>
                      <span>
                        {countryName(o)} → {countryName(d)}
                        {!sure(r) && <span class="may-use"> · may use</span>}
                      </span>
                      <span class="num" style={RIGHT}>{fmtNum(lv)}</span>
                      <span class="num" style={RIGHT}>{share(lv, g)}</span>
                    </span>
                  );
                  return drawn ? (
                    <button class="list-btn" key={`${o}-${d}`} style={{ padding: '4px 8px' }} onClick={() => select({ kind: 'lane', id: lane })} title="Open this lane">
                      {body}
                    </button>
                  ) : (
                    <div class="pair-static" key={`${o}-${d}`} title="Not drawn on the map: below the lanes shown for this commodity">
                      {body}
                    </div>
                  );
                })}
                {lanes.length > list.length && (
                  <button class="list-btn muted small" style={{ padding: '4px 8px' }} onClick={() => setAllLanes(true)}>
                    Show all {lanes.length} {fromPairs ? 'pairs' : 'lanes'}
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
      {groups.length > shown.length && (
        <button class="list-btn muted small" onClick={() => setAllGroups(true)}>
          Show all {groups.length} commodities
        </button>
      )}
      <SourcesLine items={[{ s: doc.s, y: doc.y }, ...srcs.map((x) => ({ s: x, y: doc.y }))]} n={`${fromPairs ? 'pair' : 'lane'} tonnages from customs data; shares of each commodity's seaborne trade`} />
    </Section>
  );
}

export default function ChokepointView({ id }: { id: string }) {
  useFreightCatalogue();
  const cp = useLoaded<Chokepoint>(() => loadChokepoints().then((l) => l.find((c) => c.id === id) ?? null), [id]);
  const events = useLoaded<FreightEvent[]>(() => loadEvents(), []);
  // the series of the chokepoint's own PortWatch counter, or of the counter it points to (`seriesFrom`); none otherwise
  const seriesId = cp ? (cp.seriesFrom ?? (cp.portwatch ? cp.id : null)) : null;
  const pw = useLoaded<PortwatchSeries>(() => (seriesId ? loadPortwatch(seriesId) : Promise.resolve(null)), [seriesId]);
  const lanes = useLoaded<ChokepointLanes>(() => loadChokepointLanes(), []);
  const [mode, setMode] = useState<'count' | 'vol'>('count');
  // the chart's visible window survives the vessels / Mt toggle; a new chokepoint starts from the default again
  const win = useRef<{ min: number; max: number } | null>(null);
  useEffect(() => {
    setMode('count');
    win.current = null;
  }, [id]);

  useEffect(() => {
    if (!cp) return;
    const wide = window.innerWidth >= 760;
    getMap()?.flyTo({
      center: cp.at,
      zoom: 4.2,
      duration: 1600,
      essential: true,
      padding: wide ? { top: 60, bottom: 40, left: 340, right: 420 } : { top: 80, bottom: window.innerHeight * 0.5, left: 10, right: 10 },
    });
  }, [cp]);

  const related = useMemo(() => {
    if (!events || !cp) return [];
    const ids = new Set(cp.events ?? []);
    return events
      .filter((e) => e.chokepoints?.includes(cp.id) || ids.has(e.id))
      .sort((a, b) => (a.date < b.date ? 1 : -1));
  }, [events, cp]);

  const chart = useMemo(() => {
    if (!pw) return null;
    const t0 = parseDate(pw.start);
    const x = pw.total.map((_, i) => t0 + i * 7 * DAY);
    // vessel counts, or PortWatch's estimated trade volume of the same vessels
    const src = mode === 'vol' && pw.vol ? pw.vol : pw;
    const series = [
      { label: 'Tanker', values: src.tanker, color: PW_COLORS.tanker },
      { label: 'Dry bulk', values: src.dry, color: PW_COLORS.dry },
      { label: 'Container', values: src.container, color: PW_COLORS.container },
      { label: 'Other', values: src.other, color: PW_COLORS.other },
    ];
    return { x, series, vol: src !== pw };
  }, [pw, mode]);

  // published flows by period, latest first; rows of the latest period carry the earlier values of the same flow
  const periods = useMemo(() => {
    const by = new Map<string, { k: string; f: Fig }[]>();
    for (const s of cp?.shares ?? []) by.set(String(s.f.y), [...(by.get(String(s.f.y)) ?? []), s]);
    return [...by.entries()].map(([y, rows]) => ({ y, end: periodEnd(y), rows })).sort((a, b) => b.end - a.end);
  }, [cp]);

  const markers = useMemo<TimeMarker[]>(
    () =>
      related.map((e) => ({
        t: parseDate(e.date),
        end: e.end ? parseEnd(e.end) : undefined,
        title: `${fmtEventDate(e.date)} · ${e.title}`,
        color: EVENT_COLOR[e.kind],
      })),
    [related],
  );

  if (cp === undefined)
    return (<><div class="detail-head"><div class="detail-kicker">Chokepoint</div><h2 class="detail-title">{id}</h2></div><div class="panel-scroll"><Skeleton lines={7} /></div></>);
  if (cp === null)
    return (<><div class="detail-head"><div class="detail-kicker">Chokepoint</div><h2 class="detail-title">{id}</h2></div><div class="panel-scroll"><Placeholder>This chokepoint is not in the atlas catalogue.</Placeholder></div></>);

  const FlowRow = ({ k, f, before }: { k: string; f: Fig; before?: Fig[] }) => (
    <div class="flow-row" title={`${sources.value[f.s]?.name ?? f.s} · ${f.y}`}>
      <div class="flow-main">
        <span class="flow-k">{shareLabel(k)}</span>
        <span class="flow-v num">{fmtFig(f)}</span>
      </div>
      {before && before.length > 0 && (
        <div class="flow-main muted" style={{ marginTop: '2px' }}>
          <span>Before</span>
          <span class="num">{before.map((b) => `${fmtFig(b)} in ${b.y}`).join(' · ')}</span>
        </div>
      )}
      <div class="flow-sub">
        <span class="num">{f.y}</span> · {publisher(f.s)}
        {f.n ? ` · ${f.n}` : ''}
      </div>
    </div>
  );
  /** Earlier published values of the same flow (same key and unit), most recent first. When the latest period
   * holds several rows of that key (one per sub-passage, the note naming it) the note must match as well. */
  const earlier = (k: string, f: Fig) => {
    const twins = (periods[0]?.rows ?? []).filter((r) => r.k === k && r.f.u === f.u).length > 1;
    return periods.slice(1).flatMap((p) => p.rows.filter((r) => r.k === k && r.f.u === f.u && (!twins || r.f.n === f.n)).map((r) => r.f));
  };

  // PortWatch figures: the chokepoint's own counter, or the counter the page borrows (named, never under this name)
  const traffic = cp.seriesFrom ? pw?.headline : cp.traffic;
  const trafficVol = cp.seriesFrom ? pw?.headlineVol : cp.trafficVol;
  const counter = cp.seriesFrom ? pw?.name : cp.portwatchLabel ? cp.portwatchName : undefined;
  const seriesLabel = cp.seriesFrom ? (pw?.name ? `${pw.name} (PortWatch)` : undefined) : cp.portwatchLabel;
  const lastYears = pw?.annual ? pw.annual.years.map((y, i) => ({ y, n: pw.annual!.transits[i], mt: pw.annual!.mt[i] })).slice(-3).reverse() : [];
  const laneRows = lanes ? lanes.chokepoints[cp.id] : undefined;
  // estimates written with a ceiling or a tonnage (the "at least" / "up to" form) replace the old "mapped lanes" figures
  const estimatesNew = !!cp.estimates?.some((e) => e.hi || e.mt);

  return (
    <>
      <div class="detail-head" style={{ '--kicker': 'var(--chokepoint)' }}>
        <div class="detail-kicker">Chokepoint · {cp.kind}</div>
        <h2 class="detail-title">{cp.name}</h2>
      </div>
      <div class="panel-scroll">
        <AlertBanners chokepoints={[cp.id]} />
        <p class="prose" style={{ margin: '8px 0 0' }}>{cp.summary}</p>
        {(traffic || trafficVol || cp.trafficRef) && (
          <div class="kpis">
            {traffic && <Kpi label={trafficLabel(traffic, 'Traffic', counter)} f={traffic} note={traffic.n} span />}
            {trafficVol && <Kpi label={trafficLabel(trafficVol, 'Estimated trade volume', counter)} f={trafficVol} note={trafficVol.n} span />}
            {cp.trafficRef && <Kpi label="Transits, official statistics" f={cp.trafficRef} note={cp.trafficRef.n} span />}
          </div>
        )}
        {pw === undefined ? (
          <Section title="Weekly traffic"><Skeleton lines={5} /></Section>
        ) : pw && chart ? (
          <Section
            title="Weekly traffic by ship type"
            aside={
              pw.vol && (
                <span class="tc-ranges" role="group" aria-label="Measure">
                  <button class="tc-btn" aria-pressed={mode === 'count'} onClick={() => setMode('count')} title="Vessels per day">Vessels</button>
                  <button class="tc-btn" aria-pressed={mode === 'vol'} onClick={() => setMode('vol')} title="Estimated trade volume, million tonnes per day">Mt</button>
                </span>
              )
            }
          >
            {seriesLabel && <div class="small" style={{ marginBottom: '6px', color: 'var(--ink-0)' }}>{seriesLabel}</div>}
            {cp.portwatchNote && <div class="muted small" style={{ marginBottom: '6px' }}>{cp.portwatchNote}</div>}
            <TimeChart
              x={chart.x}
              series={chart.series}
              unit={chart.vol ? 'Mt/day' : 'vessels/day'}
              stacked
              ranges={RANGES}
              defaultRange="3Y"
              view={win.current}
              onRange={(min, max) => { win.current = { min, max }; }}
              markers={markers}
              height={190}
              ariaLabel={`${seriesLabel ?? cp.name} weekly ${chart.vol ? 'estimated trade volume' : 'vessel transits'}`}
            />
            {lastYears.length > 0 && (
              <div class="ft" style={{ margin: '4px 0 6px' }}>
                <div class="muted small">Calendar years: transits and estimated trade volume</div>
                {lastYears.map((r) => (
                  <div class="ft-row" key={r.y}>
                    <span class="ft-k num">{r.y}</span>
                    <span class="num">{r.n.toLocaleString('en-US')} transits · {fmtNum(r.mt)} Mt</span>
                  </div>
                ))}
              </div>
            )}
            <SourceLine
              s={pw.s}
              y={`data to ${pw.y}`}
              n={chart.vol && pw.vol ? `${pw.vol.unit}; PortWatch's estimate of the trade volume carried, not deadweight` : pw.unit}
            />
          </Section>
        ) : cp.portwatchNote ? (
          <Section title="Weekly traffic">
            <div class="muted small">{cp.portwatchNote}</div>
            {cp.seeAlso && cp.seeAlso.length > 0 && (
              <div class="chips" style={{ marginTop: '8px' }}>
                {cp.seeAlso.map((c) => (
                  <button class="chip" key={c} onClick={() => select({ kind: 'chokepoint', id: c })}>{chokepointName(c)}</button>
                ))}
              </div>
            )}
          </Section>
        ) : null}

        {periods.length > 0 && (
          <Section title="Published flows">
            {periods.map((p, pi) => (
              <div key={p.y} style={{ marginBottom: pi < periods.length - 1 ? '8px' : 0 }}>
                {periods.length > 1 && (
                  <div class="small num" style={{ color: 'var(--ink-1)', marginTop: pi ? '4px' : 0 }}>
                    {p.y}{pi === 0 ? ' · latest' : ''}
                  </div>
                )}
                {p.rows.map((s, i) => <FlowRow key={i} k={s.k} f={s.f} before={pi === 0 ? earlier(s.k, s.f) : undefined} />)}
              </div>
            ))}
          </Section>
        )}
        {/* the estimates in their new form (a ceiling beside the floor), or the old fallback when no lane rows exist */}
        {cp.estimates && cp.estimates.length > 0 && (estimatesNew || !(laneRows && laneRows.length > 0)) && lanes !== undefined && (
          <Estimates cp={cp} withDefinition={estimatesNew} />
        )}
        {lanes && laneRows && laneRows.length > 0 && <LaneTable doc={lanes} id={cp.id} definitionHere={!estimatesNew} />}
        {cp.limits && (
          <Section title="Physical limits">
            <p class="prose">{cp.limits}</p>
            <SourceLine s={cp.s} />
            {cp.limitsS && <SourceLine s={cp.limitsS} />}
          </Section>
        )}
        {((cp.alternatives && cp.alternatives.length > 0) || cp.detour) && (
          <Section title="Alternatives">
            {cp.detour && (
              <div class="alt-box" style={{ marginBottom: '8px' }} title={`${sources.value[cp.detour.s]?.name ?? cp.detour.s} · ${cp.detour.y}`}>
                <div class="alt-label">
                  Typical detour on mapped lanes: <b class="num">+{cp.detour.nm.toLocaleString('en-US')} nm / +{fmtNum(cp.detour.days)} days</b> (Atlas estimate)
                </div>
                {cp.detour.n && <div class="muted small" style={{ marginTop: '6px' }}>{cp.detour.n} · {cp.detour.y}</div>}
              </div>
            )}
            {(cp.alternatives ?? []).map((a, i) => (
              <div class="alt-box" key={i} style={{ marginBottom: '8px' }}>
                <div class="alt-label">{a.label}</div>
                {(a.extraDays != null || a.extraNm != null) && (
                  <div class="alt-stats num">
                    {a.extraDays != null && <span class="alt-days worse">{a.extraDays > 0 ? '+' : ''}{a.extraDays} days</span>}
                    {a.extraNm != null && <span>{a.extraNm > 0 ? '+' : ''}{a.extraNm.toLocaleString('en-US')} nm</span>}
                  </div>
                )}
                {a.note && <div class="muted small" style={{ marginTop: '6px' }}>{a.note}</div>}
              </div>
            ))}
          </Section>
        )}
        {related.length > 0 && (
          <Section title="Related events">
            {related.map((e) => (
              <button class="list-btn event-row" key={e.id} onClick={() => select({ kind: 'event', id: e.id })}>
                <i class="dot" style={{ background: EVENT_COLOR[e.kind] }} title={EVENT_KIND_LABEL[e.kind]} />
                <span class="grow">{e.title}</span>
                <span class="meta num">{fmtEventDate(e.date)}</span>
              </button>
            ))}
          </Section>
        )}
        {/* PortWatch is cited under its chart; the page-level line stays on a page that shows no PortWatch series */}
        {!(cp.s === 'portwatch' && pw) && <SourceLine s={cp.s} />}
      </div>
    </>
  );
}
