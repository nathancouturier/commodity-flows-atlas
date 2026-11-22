/** Chokepoint: published flows, Atlas estimates, PortWatch transit chart, events. */
import { useEffect, useMemo } from 'preact/hooks';
import type { Chokepoint, Fig, FreightEvent, PortwatchSeries } from '../../types';
import { commodityMeta } from '../../lib/data';
import { fig as fmtFig, fmt as fmtNum } from '../../lib/format';
import { loadChokepoints, loadEvents, loadPortwatch, SHARE_LABEL } from '../../lib/freight';
import { getMap } from '../../map/controller';
import { select } from '../../lib/store';
import { Section, SourceLine, Kpi, Skeleton, Placeholder, AlertBanners } from '../ui';
import { TimeChart, DAY, YEAR, parseDate } from '../charts/TimeChart';
import type { TimeMarker } from '../charts/TimeChart';
import { EVENT_COLOR, EVENT_KIND_LABEL, fmtEventDate } from './EventView';
import { publisher, useFreightCatalogue, useLoaded } from './shared';
import { sources } from '../../lib/data';

const RANGES = [
  { label: '1Y', seconds: YEAR },
  { label: '3Y', seconds: 3 * YEAR },
  { label: 'All', seconds: null },
];
const PW_COLORS = { tanker: '#ffb547', dry: '#9db7ff', container: '#c7a3ff', other: '#7d8a99' };

const shareLabel = (k: string) => SHARE_LABEL[k] ?? commodityMeta(k)?.name ?? k;

export default function ChokepointView({ id }: { id: string }) {
  useFreightCatalogue();
  const cp = useLoaded<Chokepoint>(() => loadChokepoints().then((l) => l.find((c) => c.id === id) ?? null), [id]);
  const events = useLoaded<FreightEvent[]>(() => loadEvents(), []);
  const pw = useLoaded<PortwatchSeries>(() => loadPortwatch(id), [id]);

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
    const series = [
      { label: 'Tanker', values: pw.tanker, color: PW_COLORS.tanker },
      { label: 'Dry bulk', values: pw.dry, color: PW_COLORS.dry },
      { label: 'Container', values: pw.container, color: PW_COLORS.container },
      { label: 'Other', values: pw.other, color: PW_COLORS.other },
    ];
    return { x, series };
  }, [pw]);

  const markers = useMemo<TimeMarker[]>(
    () =>
      related.map((e) => ({
        t: parseDate(e.date),
        end: e.end ? parseDate(e.end) : undefined,
        title: `${fmtEventDate(e.date)} · ${e.title}`,
        color: EVENT_COLOR[e.kind],
      })),
    [related],
  );

  if (cp === undefined)
    return (<><div class="detail-head"><div class="detail-kicker">Chokepoint</div><h2 class="detail-title">{id}</h2></div><div class="panel-scroll"><Skeleton lines={7} /></div></>);
  if (cp === null)
    return (<><div class="detail-head"><div class="detail-kicker">Chokepoint</div><h2 class="detail-title">{id}</h2></div><div class="panel-scroll"><Placeholder>This chokepoint is not in the atlas catalogue.</Placeholder></div></>);

  const FlowRow = ({ k, f }: { k: string; f: Fig }) => (
    <div class="flow-row" title={`${sources.value[f.s]?.name ?? f.s} · ${f.y}`}>
      <div class="flow-main">
        <span class="flow-k">{shareLabel(k)}</span>
        <span class="flow-v num">{fmtFig(f)}</span>
      </div>
      <div class="flow-sub">
        <span class="num">{f.y}</span> · {publisher(f.s)}
        {f.n ? ` · ${f.n}` : ''}
      </div>
    </div>
  );

  return (
    <>
      <div class="detail-head" style={{ '--kicker': 'var(--chokepoint)' }}>
        <div class="detail-kicker">Chokepoint · {cp.kind}</div>
        <h2 class="detail-title">{cp.name}</h2>
      </div>
      <div class="panel-scroll">
        <AlertBanners chokepoints={[cp.id]} />
        <p class="prose" style={{ margin: '8px 0 0' }}>{cp.summary}</p>
        {(cp.traffic || cp.trafficRef) && (
          <div class="kpis">
            {cp.traffic && <Kpi label="Traffic, last 28 days" f={cp.traffic} note={cp.traffic.n} span />}
            {cp.trafficRef && <Kpi label="Transits, official statistics" f={cp.trafficRef} note={cp.trafficRef.n} span />}
          </div>
        )}
        {pw === undefined ? (
          <Section title="Weekly transits"><Skeleton lines={5} /></Section>
        ) : pw && chart ? (
          <Section title="Weekly transits by ship type">
            <TimeChart
              x={chart.x}
              series={chart.series}
              unit="vessels/day"
              stacked
              ranges={RANGES}
              defaultRange="3Y"
              markers={markers}
              height={190}
              ariaLabel={`${cp.name} weekly vessel transits`}
            />
            <SourceLine s={pw.s} y={`data to ${pw.y}`} n={pw.unit} />
          </Section>
        ) : null}

        {cp.shares && cp.shares.length > 0 && (
          <Section title="Published flows">
            {cp.shares.map((s, i) => <FlowRow key={i} k={s.k} f={s.f} />)}
          </Section>
        )}
        {cp.estimates && cp.estimates.length > 0 && (
          <Section title="Atlas estimates">
            <div class="muted small" style={{ marginBottom: '6px' }}>Share of seaborne trade on the lanes mapped in the atlas: a lower-bound estimate, not a published statistic.</div>
            {cp.estimates.map((s, i) => <FlowRow key={i} k={s.k} f={s.f} />)}
          </Section>
        )}
        {cp.limits && (
          <Section title="Physical limits">
            <p class="prose">{cp.limits}</p>
            <SourceLine s={cp.s} />
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
        <SourceLine s={cp.s} />
      </div>
    </>
  );
}
