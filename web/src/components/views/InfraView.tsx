/** One infrastructure asset: mine, smelter, port, storage hub, field, refinery, LNG terminal or pipeline. */
import { useEffect } from 'preact/hooks';
import type { InfraType, PortLimits, Route } from '../../types';
import { countryName, sourceLabel, sources, commodityMeta } from '../../lib/data';
import { fmt } from '../../lib/format';
import { GROUP_LABEL, loadRoutes } from '../../lib/freight';
import { loadPriceIndex, openPrices, type PriceMeta } from '../../lib/prices';
import { figuresOf } from '../../lib/capacity';
import { OUTPUT_LABEL, STATUS_LABEL, figureText, loadPortIndex, monthYear, sourceText, stateAt, yearText, type Figure, type PortIndexRow } from '../../lib/infra';
import { flyToBounds, flyToLine } from '../../map/controller';
import { infraColor, loadInfra, type InfraFeature } from '../../map/modules/infrastructure';
import { select, year } from '../../lib/store';
import { Section, Kpi, Skeleton, Placeholder, InfraIcon, INFRA_META, StatusBadge, shortSource } from '../ui';
import { CommodityChips, VesselChip, useLoaded } from './shared';
import '../../styles/infra.css';

/** "Crude oil, Saudi Arabia to China": a lane id `<group>:<origin>-<destination>` in the words of the lane page. */
function laneName(id: string): string {
  const [g, ends = ''] = id.split(':');
  const [o, d] = ends.split('-');
  const what = GROUP_LABEL[g] ?? commodityMeta(g)?.name ?? g;
  return `${what[0].toUpperCase()}${what.slice(1)}, ${countryName(o)} to ${countryName(d)}`;
}

const LIMIT_LABEL: [keyof PortLimits, string, string][] = [
  ['draught', 'Max draught', 'm'],
  ['loa', 'Max length', 'm'],
  ['beam', 'Max beam', 'm'],
  ['dwt', 'Max deadweight', 'dwt'],
];

/** The limits a page states (largest ship or deepest berth) and the largest class of the atlas they allow. */
function PortLimitsSection({ lim, maxClass }: { lim: PortLimits; maxClass?: { dry?: string; tanker?: string; gas?: string; n: string } }) {
  const classes = maxClass ? (['dry', 'tanker', 'gas'] as const).filter((k) => maxClass[k]) : [];
  return (
    <Section title="Limits">
      <div class="kpis">
        {LIMIT_LABEL.filter(([k]) => typeof lim[k] === 'number').map(([k, label, u]) => (
          <Kpi
            key={k}
            label={k === 'draught' && lim.depth ? 'Depth' : label}
            value={`${k === 'dwt' ? fmt(lim[k] as number) : (lim[k] as number).toLocaleString('en-US', { maximumFractionDigits: 3 })} ${u}`}
            sub={`${lim.y ?? 'year not stated'} · ${shortSource(lim.s)}`}
            note={lim.at}
          />
        ))}
      </div>
      <p class="infra-limits-note">{lim.n}</p>
      {classes.length > 0 && (
        <div class="infra-maxclass">
          <div class="muted small">Largest class by the published limits; derived by the atlas</div>
          <div class="chips">
            {classes.map((k) => (
              <VesselChip key={k} id={maxClass![k]!} />
            ))}
          </div>
          <div class="muted small">{maxClass!.n}</div>
        </div>
      )}
      <div class="src-line">
        Source:{' '}
        <a href={lim.url} target="_blank" rel="noopener">
          {sourceText(sourceLabel(lim.s), lim.url)} ↗
        </a>
      </div>
    </Section>
  );
}

interface Uses {
  routes: Route[];
  lanes: string[];
  groups: string[];
  prices: PriceMeta[];
}

/** The routes that name this asset, the lanes of its trade-engine code, and the price series quoted there. */
function useUses(key: string, locode: string | undefined, priceIds: string[] | undefined): Uses | null | undefined {
  return useLoaded<Uses>(
    () =>
      Promise.all([
        key ? loadRoutes().catch(() => [] as Route[]) : Promise.resolve([] as Route[]),
        locode ? loadPortIndex().catch(() => [] as PortIndexRow[]) : Promise.resolve([] as PortIndexRow[]),
        priceIds?.length ? loadPriceIndex().catch(() => [] as PriceMeta[]) : Promise.resolve([] as PriceMeta[]),
      ]).then(([routes, ports, prices]) => {
        const row = locode ? ports.find((p) => p.id === locode) : undefined;
        return {
          routes: key ? routes.filter((r) => r.from.assets?.includes(key) || r.to.assets?.includes(key)) : [],
          lanes: row ? (row.lanes ?? (row.lane ? [row.lane] : [])) : [],
          groups: row?.g ?? [],
          prices: (priceIds ?? []).map((id) => prices.find((m) => m.id === id)).filter((m): m is PriceMeta => !!m),
        };
      }),
    [key, locode, (priceIds ?? []).join()],
  );
}

function UsesSections({ uses }: { uses: Uses }) {
  return (
    <>
      {uses.routes.length > 0 && (
        <Section title="Routes" aside={<span class="muted num">{uses.routes.length}</span>}>
          {uses.routes.map((r) => (
            <button class="list-btn" key={r.id} onClick={() => select({ kind: 'route', id: r.id })}>
              <span class="grow">{r.name}</span>
              <span class="meta">{r.benchmark ? r.id : 'route'}</span>
            </button>
          ))}
        </Section>
      )}
      {uses.lanes.length > 0 && (
        <Section title="Lanes">
          {uses.lanes.map((id) => (
            <button class="list-btn" key={id} onClick={() => select({ kind: 'lane', id })}>
              <span class="grow">{laneName(id)}</span>
            </button>
          ))}
          <p class="infra-limits-note">The atlas's lanes that load or discharge here, largest first (Atlas estimate of the typical ports of each pair).</p>
        </Section>
      )}
      {uses.prices.length > 0 && (
        <Section title="Price series quoted at this place">
          {uses.prices.map((m) => (
            <button class="list-btn" key={m.id} onClick={() => openPrices({ series: [m.id] })}>
              <span class="grow">{m.name}</span>
              <span class="meta">{m.unit}</span>
            </button>
          ))}
        </Section>
      )}
    </>
  );
}

/** A figure with its own year, what it counts and, when it was converted, the source's own figure. */
function FigureKpi({ label, fig, s }: { label: string; fig: Figure; s: string }) {
  const note = [fig.n, fig.orig ? `source: ${fig.orig}` : ''].filter(Boolean).join(' · ');
  return (
    <Kpi
      label={label}
      value={figureText(fig, fmt)}
      sub={`${yearText(fig)} · ${shortSource(s)}`}
      note={note || undefined}
      title={`${figureText(fig, fmt)} · ${yearText(fig)} · ${sourceLabel(s)}`}
      span
    />
  );
}

export default function InfraView({ id, layer }: { id: string; layer?: InfraType }) {
  const f = useLoaded<InfraFeature>(
    () => loadInfra().then((all) => all.find((x) => x.p.id === id && (!layer || x.p.type === layer)) ?? all.find((x) => x.p.id === id) ?? null),
    [id, layer],
  );
  const uses = useUses(f ? `${f.p.type}:${f.p.id}` : '', f?.p.locode, f?.p.prices);

  useEffect(() => {
    if (!f) return;
    if (f.geom.type === 'Point') {
      const [x, y] = f.at;
      flyToBounds([[x - 0.6, y - 0.4], [x + 0.6, y + 0.4]], 6.5);
    } else {
      const cs = f.geom.type === 'LineString' ? f.geom.coordinates : f.geom.type === 'MultiLineString' ? f.geom.coordinates.flat() : [];
      flyToLine(cs as [number, number][]);
    }
  }, [f]);

  if (f === undefined)
    return (
      <>
        <div class="detail-head"><div class="detail-kicker">Infrastructure</div><h2 class="detail-title">Loading…</h2></div>
        <div class="panel-scroll"><Skeleton lines={6} /></div>
      </>
    );
  if (f === null)
    return (
      <>
        <div class="detail-head"><div class="detail-kicker">Infrastructure</div><h2 class="detail-title">{id}</h2></div>
        <div class="panel-scroll"><Placeholder>This asset is not in the infrastructure files.</Placeholder></div>
      </>
    );

  const p = f.p;
  const color = infraColor(f);
  const meta = INFRA_META[p.type];
  const figs = figuresOf(p);
  const srcUrl = p.url ?? sources.value[p.s]?.url;
  const crossed = (p.cs ?? []).filter((c) => c !== p.c);
  // History: the page follows the year of the timeline, as the map does. The status of the file is the present one: it is the
  // state of a past year only if it is not dated after it, and an asset that opens later is not open yet
  const yr = year.value;
  const at = stateAt(p, yr);
  const notApplied = at.notOpen || at.statusLater;
  const statusLabel = STATUS_LABEL[p.status ?? ''] ?? p.status ?? '';
  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker infra-kicker">
          <InfraIcon type={p.type} color={color} size={20} />
          {meta.label} · {countryName(p.c)}
        </div>
        <h2 class="detail-title">{p.name}</h2>
        <div class="badges">
          {at.notOpen ? (
            <span class="badge badge-plain">{at.opensIn != null ? `Not open yet in ${yr} (opens in ${at.opensIn})` : `Not open yet in ${yr}`}</span>
          ) : at.statusLater && p.statusAsOf ? (
            <span class="badge badge-plain">{`Status of ${monthYear(p.statusAsOf)}, after ${yr}: ${statusLabel.toLowerCase()}`}</span>
          ) : (
            <StatusBadge status={p.status} asOf={p.statusAsOf} />
          )}
          {p.type === 'pipeline' && crossed.length > 0 && <span class="badge">Crosses {crossed.map(countryName).join(' · ')}</span>}
        </div>
        {p.statusNote && !notApplied && <p class="infra-status-note">{p.statusNote}</p>}
      </div>
      <div class="panel-scroll">
        <div class="kpis">
          {figs.capacity && <FigureKpi label={figs.capacity.planned ? 'Planned capacity' : 'Capacity'} fig={figs.capacity} s={p.s} />}
          {figs.output && <FigureKpi label={OUTPUT_LABEL[figs.output.kind as keyof typeof OUTPUT_LABEL]} fig={figs.output} s={p.s} />}
          {p.opened != null && <Kpi label="Opened" value={String(p.opened)} />}
          {p.length_km != null && <Kpi label="Length" value={`${fmt(p.length_km)} km`} />}
          {p.product && <Kpi label="Carries" value={p.product} />}
        </div>
        {p.operator && (
          <Section title="Operator / owners">
            <p class="prose">{p.operator}</p>
          </Section>
        )}
        {p.k.length > 0 && (
          <Section title="Commodities">
            <CommodityChips ids={p.k.filter((k) => commodityMeta(k))} />
          </Section>
        )}
        {p.note && (
          <Section title="Note">
            <p class="prose">{p.note}</p>
          </Section>
        )}
        {p.limits && <PortLimitsSection lim={p.limits} maxClass={p.maxClass} />}
        {uses && <UsesSections uses={uses} />}
        <Section title="Location">
          {p.coord === 'approx' && <p class="infra-approx">Approximate location</p>}
          <button class="list-btn" onClick={() => select({ kind: 'country', id: p.c })}>
            <span class="grow">{countryName(p.c)}</span>
            <span class="meta">Country profile →</span>
          </button>
          {crossed.map((c) => (
            <button class="list-btn" key={c} onClick={() => select({ kind: 'country', id: c })}>
              <span class="grow">{countryName(c)}</span>
              <span class="meta">crossed</span>
            </button>
          ))}
        </Section>
        <div class="src-line">
          Source:{' '}
          {srcUrl ? (
            <a href={srcUrl} target="_blank" rel="noopener" title={p.url ? 'Open the page read' : sources.value[p.s]?.publisher}>
              {sourceText(sourceLabel(p.s), p.url)} ↗
            </a>
          ) : (
            sourceText(sourceLabel(p.s))
          )}
          {p.read && <> · read {monthYear(p.read)}</>}
        </div>
      </div>
    </>
  );
}
