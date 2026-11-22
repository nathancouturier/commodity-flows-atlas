/** One infrastructure asset: mine, smelter, port, field, refinery, LNG terminal or pipeline. */
import { useEffect } from 'preact/hooks';
import type { InfraType } from '../../types';
import { countryName, sourceLabel, commodityMeta } from '../../lib/data';
import { fmt } from '../../lib/format';
import { splitUnit } from '../../lib/capacity';
import { flyToBounds, flyToLine } from '../../map/controller';
import { infraColor, infraCapacity, loadInfra, type InfraFeature } from '../../map/modules/infrastructure';
import { select } from '../../lib/store';
import { Section, SourceLine, Kpi, Skeleton, Placeholder, InfraIcon, INFRA_META, StatusBadge } from '../ui';
import { CommodityChips, useLoaded } from './shared';

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
  const cap = infraCapacity(p);
  // "1 billion lb" and "60.5 million short tons" keep their whole unit in the headline figure
  const [capU, capRest] = splitUnit(p.capacity?.u ?? '');
  const crossed = (p.cs ?? []).filter((c) => c !== p.c);
  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker infra-kicker">
          <InfraIcon type={p.type} color={color} size={20} />
          {meta.label} · {countryName(p.c)}
        </div>
        <h2 class="detail-title">{p.name}</h2>
        <div class="badges">
          <StatusBadge status={p.status} />
          {p.type === 'pipeline' && crossed.length > 0 && <span class="badge">Crosses {crossed.map(countryName).join(' · ')}</span>}
        </div>
      </div>
      <div class="panel-scroll">
        <div class="kpis">
          {p.capacity && (
            <Kpi
              label="Capacity"
              value={`${fmt(p.capacity.v)} ${capU}`}
              sub={`${capRest ? capRest + ' · ' : ''}${sourceLabel(p.s)} · ${p.y}`}
              title={`${cap} · ${p.s} · ${p.y}`}
              span
            />
          )}
          {p.opened != null && <Kpi label="Opened" value={String(p.opened)} sub={`${sourceLabel(p.s)}`} title={`${p.s} · ${p.y}`} span />}
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
        <SourceLine s={p.s} y={p.y} />
        {p.url && (
          <div class="src-line">
            <a href={p.url} target="_blank" rel="noopener">Open source page ↗</a>
          </div>
        )}
      </div>
    </>
  );
}
