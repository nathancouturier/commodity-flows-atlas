/**
 * Country colouring by a commodity metric (production, reserves, consumption,
 * exports, imports). Opacity encodes the country's share of the world total.
 */
import { effect } from '@preact/signals';
import type { Map as MLMap } from 'maplibre-gl';
import type { CommodityData, Ranked } from '../../types';
import { registerLayerModule } from '../layers';
import { setCountryTooltipExtra } from '../controller';
import { commodity, metric } from '../../lib/store';
import { loadOptional, commodityMeta, sourceLabel } from '../../lib/data';
import { FAMILY_COLOR, fmt, pct, escapeHtml } from '../../lib/format';

let painted: string[] = [];

registerLayerModule((m: MLMap) => {
  effect(() => {
    const k = commodity.value;
    const met = metric.value;
    clear(m);
    if (!k || met === 'none') {
      m.setLayoutProperty('choropleth', 'visibility', 'none');
      setCountryTooltipExtra(null);
      return;
    }
    const meta = commodityMeta(k);
    const color = meta ? FAMILY_COLOR[meta.family] : '#3ee6ff';
    loadOptional<CommodityData>(`commodities/${k}.json`).then((d) => {
      // ignore stale responses
      if (commodity.value !== k || metric.value !== met) return;
      const table = d?.[met as keyof CommodityData] as Ranked | undefined;
      if (!table) {
        m.setLayoutProperty('choropleth', 'visibility', 'none');
        return;
      }
      const world = table.world ?? table.rows.reduce((a, r) => a + r.v, 0);
      const byC = new Map(table.rows.map((r) => [r.c, r]));
      for (const r of table.rows) {
        m.setFeatureState({ source: 'countries', id: r.c }, { v: r.v / world, col: color });
        painted.push(r.c);
      }
      m.setLayoutProperty('choropleth', 'visibility', 'visible');
      setCountryTooltipExtra((iso) => {
        const r = byC.get(iso);
        if (!r) return '';
        return `<div>${escapeHtml(met)}: <span class="num">${fmt(r.v)} ${escapeHtml(table.u)}</span> · ${pct(r.v / world)} of world</div>
          <div class="src-line">${escapeHtml(sourceLabel(table.s))} · ${escapeHtml(String(table.y))}</div>`;
      });
    });
  });
});

function clear(m: MLMap) {
  for (const id of painted) m.setFeatureState({ source: 'countries', id }, { v: 0 });
  painted = [];
}
