/** One infrastructure asset: mine, smelter, port, field, refinery, LNG terminal or pipeline. */
import { useEffect } from 'preact/hooks';
import type { InfraType } from '../../types';
import { countryName, sourceLabel, sources, commodityMeta } from '../../lib/data';
import { fmt } from '../../lib/format';
import { figuresOf } from '../../lib/capacity';
import { OUTPUT_LABEL, STATUS_LABEL, figureText, monthYear, sourceText, stateAt, yearText, type Figure } from '../../lib/infra';
import { flyToBounds, flyToLine } from '../../map/controller';
import { infraColor, loadInfra, type InfraFeature } from '../../map/modules/infrastructure';
import { select, year } from '../../lib/store';
import { Section, Kpi, Skeleton, Placeholder, InfraIcon, INFRA_META, StatusBadge, shortSource } from '../ui';
import { CommodityChips, useLoaded } from './shared';
import '../../styles/infra.css';

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
