/** Global picture of one commodity: KPIs, ranked producers/exporters/importers, flows, companies. */
import { useEffect, useState } from 'preact/hooks';
import type { CommodityData } from '../../types';
import { loadOptional, commodityMeta } from '../../lib/data';
import { FAMILY_COLOR, FAMILY_LABEL } from '../../lib/format';
import { Section, Placeholder, Skeleton, Kpi, RankedBars } from '../ui';

export default function CommodityView({ id }: { id: string }) {
  const meta = commodityMeta(id);
  const [d, setD] = useState<CommodityData | null | undefined>(undefined);
  useEffect(() => {
    setD(undefined);
    loadOptional<CommodityData>(`commodities/${id}.json`).then(setD);
  }, [id]);
  const color = meta ? FAMILY_COLOR[meta.family] : undefined;
  return (
    <>
      <div class="detail-head" style={{ '--kicker': color }}>
        <div class="detail-kicker">{meta ? FAMILY_LABEL[meta.family] : 'Commodity'}</div>
        <h2 class="detail-title">{meta?.name ?? id}</h2>
        {meta?.blurb && <p class="muted" style={{ margin: '4px 0 0', fontSize: '13px' }}>{meta.blurb}</p>}
        {d?.summary && (
          <div class="kpis">
            {d.summary.production && <Kpi label="World production" f={d.summary.production} />}
            {d.summary.exports && <Kpi label="World exports" f={d.summary.exports} />}
            {d.summary.reserves && <Kpi label="World reserves" f={d.summary.reserves} />}
            {d.summary.consumption && <Kpi label="World consumption" f={d.summary.consumption} />}
            {d.summary.seaborne && <Kpi label="Seaborne trade" f={d.summary.seaborne} />}
          </div>
        )}
      </div>
      <div class="panel-scroll">
        {d === undefined ? (
          <Skeleton lines={8} />
        ) : d === null ? (
          <Placeholder>Data for this commodity is being compiled and will appear in a later release.</Placeholder>
        ) : (
          <>
            {d.production && (
              <Section title="Top producers">
                <RankedBars data={d.production} color={color} />
              </Section>
            )}
            {d.exports && (
              <Section title="Top exporters">
                <RankedBars data={d.exports} color={color} />
              </Section>
            )}
            {d.imports && (
              <Section title="Top importers">
                <RankedBars data={d.imports} color={color} />
              </Section>
            )}
            {d.reserves && (
              <Section title="Reserves">
                <RankedBars data={d.reserves} color={color} />
              </Section>
            )}
            {d.consumption && (
              <Section title="Top consumers">
                <RankedBars data={d.consumption} color={color} />
              </Section>
            )}
          </>
        )}
      </div>
    </>
  );
}
