/** Small map legend: only describes what is currently drawn. */
import { commodity, family, layers, selection } from '../lib/store';
import { commodityMeta } from '../lib/data';
import { SEGMENT_COLOR, SEGMENT_LABEL } from '../lib/freight';
import { FAMILY_COLOR, FAMILY_LABEL } from '../lib/format';
import type { Family, Segment } from '../types';

const SEGMENTS: Segment[] = ['dry', 'tanker', 'gas'];

export function Legend() {
  const fam = family.value;
  const k = commodity.value;
  const sel = selection.value;

  const flowsOn = layers.value.flows && (!!k || fam !== 'freight');
  const routesOn = layers.value.routes || fam === 'freight';
  const chokeOn =
    layers.value.chokepoints || fam === 'freight' || sel?.kind === 'route' || sel?.kind === 'lane' || sel?.kind === 'chokepoint';

  let families: Family[] = [];
  if (flowsOn) {
    const own = k ? commodityMeta(k)?.family : undefined;
    families = own ? [own] : fam === 'all' || fam === 'freight' ? ['energy', 'metals', 'softs'] : [fam];
  }
  if (!flowsOn && !routesOn && !chokeOn) return null;

  return (
    <div class="legend glass" aria-label="Map legend">
      {families.map((f) => (
        <span class="legend-item">
          <span class="legend-swatch" style={{ background: FAMILY_COLOR[f] }} />
          {FAMILY_LABEL[f]}
        </span>
      ))}
      {routesOn &&
        SEGMENTS.map((s) => (
          <span class="legend-item">
            <span class="legend-swatch" style={{ background: SEGMENT_COLOR[s] }} />
            {SEGMENT_LABEL[s]}
          </span>
        ))}
      {(flowsOn || routesOn) && (
        <span class="legend-item legend-width" title={flowsOn ? 'Line width scales with the square root of volume' : 'Benchmark routes are drawn thicker'}>
          <svg width="30" height="10" viewBox="0 0 30 10" aria-hidden="true">
            <path d="M0 5 L30 1.5 L30 8.5 Z" fill="currentColor" opacity="0.7" />
          </svg>
          {flowsOn ? 'Line width = volume' : 'Benchmarks thicker'}
        </span>
      )}
      {chokeOn && (
        <span class="legend-item">
          <span class="legend-cp" />
          Chokepoint
        </span>
      )}
    </div>
  );
}
