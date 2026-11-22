/**
 * Country colouring by a commodity metric (production, reserves, consumption,
 * exports, imports). Opacity encodes the country's share of the world total.
 * The EU27 aggregate row is painted on every member state.
 */
import { effect } from '@preact/signals';
import type { Map as MLMap } from 'maplibre-gl';
import type { CommodityData, Ranked } from '../../types';
import { registerLayerModule } from '../layers';
import { setCountryTooltipExtra } from '../controller';
import { choroInfo, commodity, metric } from '../../lib/store';
import { loadOptional, commodityMeta, sourceLabel } from '../../lib/data';
import { FAMILY_COLOR, fmt, pct, escapeHtml } from '../../lib/format';

let painted: string[] = [];

export const EU27 = [
  'AUT', 'BEL', 'BGR', 'HRV', 'CYP', 'CZE', 'DNK', 'EST', 'FIN', 'FRA', 'DEU', 'GRC', 'HUN', 'IRL',
  'ITA', 'LVA', 'LTU', 'LUX', 'MLT', 'NLD', 'POL', 'PRT', 'ROU', 'SVK', 'SVN', 'ESP', 'SWE',
];

registerLayerModule((m: MLMap) => {
  effect(() => {
    const k = commodity.value;
    const met = metric.value;
    clear(m);
    choroInfo.value = null;
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
      if (!table || !table.rows?.length) {
        m.setLayoutProperty('choropleth', 'visibility', 'none');
        setCountryTooltipExtra(null);
        return;
      }
      const world = table.world ?? table.rows.reduce((a, r) => a + r.v, 0);
      const byC = new Map<string, { v: number; eu: boolean }>();
      for (const r of table.rows) {
        if (r.c === 'EU27') continue;
        byC.set(r.c, { v: r.v, eu: false });
      }
      const eu = table.rows.find((r) => r.c === 'EU27');
      // the aggregate is shown on each member state that has no row of its own
      if (eu) for (const c of EU27) if (!byC.has(c)) byC.set(c, { v: eu.v, eu: true });
      let lo = Infinity;
      let hi = 0;
      for (const [c, r] of byC) {
        const share = r.v / world;
        m.setFeatureState({ source: 'countries', id: c }, { v: share, col: color });
        painted.push(c);
        if (share > 0) {
          lo = Math.min(lo, share);
          hi = Math.max(hi, share);
        }
      }
      if (eu) {
        lo = Math.min(lo, eu.v / world);
        hi = Math.max(hi, eu.v / world);
      }
      m.setLayoutProperty('choropleth', 'visibility', 'visible');
      choroInfo.value = {
        metric: met,
        unit: table.u,
        year: table.y,
        source: sourceLabel(table.s),
        color,
        min: Number.isFinite(lo) ? lo : 0,
        max: hi,
        commodity: meta?.name ?? k,
      };
      setCountryTooltipExtra((iso) => {
        const r = byC.get(iso);
        if (!r) return '';
        return `<div>${escapeHtml(met)}: <span class="num">${fmt(r.v)} ${escapeHtml(table.u)}</span> · ${pct(r.v / world)} of world</div>
          ${r.eu ? '<div class="muted">EU27 aggregate (shown on each member state)</div>' : ''}
          <div class="src-line">${escapeHtml(sourceLabel(table.s))} · ${escapeHtml(String(table.y))}</div>`;
      });
    });
  });
});

function clear(m: MLMap) {
  for (const id of painted) m.setFeatureState({ source: 'countries', id }, { v: 0 });
  painted = [];
}
