/**
 * Country colouring by a commodity metric (production, reserves, consumption,
 * exports, imports). Opacity encodes the country's share of the world total.
 * The EU27 aggregate row is painted on every member state; only a member production table (FAOSTAT) gives them a figure of their own.
 */
import { effect } from '@preact/signals';
import maplibregl, { type Map as MLMap, type Marker } from 'maplibre-gl';
import type { CommodityData, Ranked } from '../../types';
import { registerLayerModule } from '../layers';
import { setCountryTooltipExtra } from '../controller';
import { colourNamesOnFill, hideCountryNames } from '../labels';
import { choroInfo, commodity, metric, select, year } from '../../lib/store';
import { commodities } from '../../lib/data';
import { loadHistory, loadOptional, commodityMeta, countries, countryName, sourceLabel } from '../../lib/data';
import { tableAt } from '../../lib/tableYears';
import { FAMILY_COLOR, fmt, pct, escapeHtml } from '../../lib/format';

let painted: string[] = [];
let labels: Marker[] = [];
/** Where each label belongs on the world as drawn once; it is shown on the copy of the world nearest the camera. */
const labelAt = new Map<Marker, { el: HTMLElement; at: [number, number] }>();

/** Countries labelled with their share on the map: >= 1% of the world total, at most 16. */
/** The source of a table as the legend and the labels print it: a table that holds an Atlas conversion (the United States in EIA's LPG table) says so. */
const srcOf = (t: Ranked) => (t.conv ? `${sourceLabel(t.s)} (${t.conv}: Atlas conversion)` : sourceLabel(t.s));
const LABEL_MIN_SHARE = 0.01;
const LABEL_MAX = 16;
/**
 * The opacity of this share (SHARE_STOPS) is the floor for a country that has a value: under it the tint would not show.
 * Every share under it gets that one tint, which the legend shows as its own swatch ("under 0.25%").
 */
export const MIN_TINT_SHARE = 0.0025;
/** Where the EU27 aggregate label sits (central Europe). */
const EU_LABEL_AT: [number, number] = [11.5, 49.5];

const METRIC_WORD: Record<string, string> = {
  production: 'production', reserves: 'reserves', consumption: 'consumption', exports: 'exports', imports: 'imports',
};

export const EU27 = [
  'AUT', 'BEL', 'BGR', 'HRV', 'CYP', 'CZE', 'DNK', 'EST', 'FIN', 'FRA', 'DEU', 'GRC', 'HUN', 'IRL',
  'ITA', 'LVA', 'LTU', 'LUX', 'MLT', 'NLD', 'POL', 'PRT', 'ROU', 'SVK', 'SVN', 'ESP', 'SWE',
];

/**
 * Choosing a commodity colours its producing countries in the family colour (production, or
 * exports when no production table exists). An explicit choice (including "Off") is kept until
 * the commodity changes; a shared link with m=... is respected.
 */
let lastK: string | null | undefined;
effect(() => {
  const k = commodity.value;
  void commodities.value; // wait for the catalogue
  const meta = k ? commodityMeta(k) : undefined;
  if (k && !meta) return;
  if (k === lastK) return;
  const first = lastK === undefined;
  lastK = k;
  if (!k || !meta) {
    metric.value = 'none'; // a colouring needs a commodity: a link with a measure and no commodity colours nothing
    return;
  }
  const cur = metric.peek();
  // a link's own colouring is kept when the commodity has data for it; otherwise the usual choice below replaces it (no empty map)
  if (first && cur !== 'none' && meta.has.includes(cur)) return;
  if (cur === 'none' || !meta.has.includes(cur)) {
    const pick = (['production', 'exports', 'imports'] as const).find((x) => meta.has.includes(x));
    metric.value = pick ?? 'none';
  }
});

registerLayerModule((m: MLMap) => {
  // a camera that drifted onto a wrapped copy of the world (after a country view) must not leave the labels
  // on the copy beside it, where the detail panel covers them
  m.on('moveend', () => snapLabels(m));
  effect(() => {
    const k = commodity.value;
    const met = metric.value;
    const yr = year.value;
    clear(m);
    choroInfo.value = null;
    if (!k || met === 'none') {
      m.setLayoutProperty('choropleth', 'visibility', 'none');
      setCountryTooltipExtra(null);
      return;
    }
    const meta = commodityMeta(k);
    const color = meta ? FAMILY_COLOR[meta.family] : '#3ee6ff';
    // with a History year, the table of that year when the measure has a series that holds it (the latest table otherwise)
    Promise.all([loadOptional<CommodityData>(`commodities/${k}.json`), yr != null ? loadHistory(k) : Promise.resolve(null)]).then(([d, h]) => {
      // ignore stale responses
      if (commodity.value !== k || metric.value !== met || year.value !== yr) return;
      const latest = d?.[met as keyof CommodityData] as Ranked | undefined;
      const table = latest ? tableAt(latest, h?.t[met], yr).table : undefined;
      if (!table || !table.rows?.length) {
        m.setLayoutProperty('choropleth', 'visibility', 'none');
        setCountryTooltipExtra(null);
        return;
      }
      const world = table.world ?? table.rows.reduce((a, r) => a + r.v, 0);
      const byC = new Map<string, { v: number; eu: boolean; own?: boolean }>();
      for (const r of table.rows) {
        if (r.c === 'EU27') continue;
        byC.set(r.c, { v: r.v, eu: false });
      }
      const eu = table.rows.find((r) => r.c === 'EU27');
      // a member state shows its own figure when the commodity has a table of the member states for this measure that is on the basis of the
      // USDA table (FAOSTAT production; only for the latest table, it has no series by year); otherwise the aggregate's, on each member with no
      // row of its own. The customs trade tables of the members are `noMap`: they include trade between members, USDA's row does not
      const ownEntry = table === latest ? d?.extra?.find((x) => x.key === `eu-${met}`) : undefined;
      const own = ownEntry?.table;
      const members = own && !own.noMap ? own : undefined;
      const memberBase = members ? (members.worldAll ?? members.world) : undefined;
      if (eu && members && memberBase) {
        for (const r of members.rows) if (EU27.includes(r.c) && !byC.has(r.c)) byC.set(r.c, { v: r.v, eu: false, own: true });
      } else if (eu) for (const c of EU27) if (!byC.has(c)) byC.set(c, { v: eu.v, eu: true });
      let lo = Infinity;
      let hi = 0;
      for (const [c, r] of byC) {
        // a member state's own figure is a share of the world total of its own source and year
        const share = r.v / (r.own && memberBase ? memberBase : world);
        // every country with a value is coloured: a very small share still gets the faintest visible tint
        m.setFeatureState({ source: 'countries', id: c }, { v: Math.max(share, MIN_TINT_SHARE), col: color });
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
        source: members && memberBase ? `${sourceLabel(members.s)}, ${members.y} for the EU member states; ${sourceLabel(table.s)}` : srcOf(table),
        color,
        min: Number.isFinite(lo) ? lo : 0,
        max: hi,
        commodity: meta?.name ?? k,
      };
      // share labels on the map, e.g. "23%" on Brazil for sugar production
      const ranked = table.rows
        .map((r) => ({ c: r.c, v: r.v, share: r.v / world }))
        .filter((r) => r.share >= LABEL_MIN_SHARE)
        .slice(0, LABEL_MAX);
      for (const r of ranked) {
        const at = r.c === 'EU27' ? EU_LABEL_AT : countries.value[r.c]?.at;
        if (!at) continue;
        const name = r.c === 'EU27' ? 'European Union' : countryName(r.c);
        const el = document.createElement('button');
        el.className = 'share-label';
        el.style.setProperty('--c', color);
        el.textContent = pct(r.share);
        el.title = `${name}: ${fmt(r.v)} ${table.u}, ${pct(r.share)} of world ${METRIC_WORD[met] ?? met} (${srcOf(table)}, ${table.y})`;
        el.setAttribute('aria-label', el.title);
        el.addEventListener('click', (ev) => {
          ev.stopPropagation();
          if (r.c !== 'EU27') select({ kind: 'country', id: r.c });
        });
        labels.push(placeLabel(m, el, at as [number, number]));
      }
      // a share label sits on the point of the country's name: the name gives way to it
      hideCountryNames(m, ranked.map((r) => r.c).filter((c) => c !== 'EU27'));
      // the names that stay sit on the colouring: lighter text, wider halo
      colourNamesOnFill(m, true);
      setCountryTooltipExtra((iso) => {
        const r = byC.get(iso);
        if (!r) return '';
        const t = r.own && members ? members : table;
        return `<div>${escapeHtml(met)}: <span class="num">${fmt(r.v)} ${escapeHtml(t.u)}</span> · ${pct(r.v / (r.own && memberBase ? memberBase : world))} of world</div>
          ${r.eu ? `<div class="muted">European Union, one figure for all its members (shown on each member state)${ownEntry ? `. USDA gives the European Union as one entity: the member's own figures are in the table "${escapeHtml(ownEntry.title)}" of the commodity page` : ''}</div>` : ''}
          ${r.own ? '<div class="muted">EU member state: its own figure (the USDA row for the European Union is a single figure for all 27)</div>' : ''}
          <div class="src-line">${escapeHtml(srcOf(t))} · ${escapeHtml(String(t.y))}</div>`;
      });
    });
  });
});

/** A label on the copy of the world nearest the camera. */
function placeLabel(m: MLMap, el: HTMLElement, at: [number, number]): Marker {
  const lng = at[0] + 360 * Math.round((m.getCenter().lng - at[0]) / 360);
  const marker = new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([lng, at[1]]).addTo(m);
  labelAt.set(marker, { el, at });
  return marker;
}

// A marker follows the copy of the world it was on when the camera moved, and keeps that copy for good, so a
// label that is on another copy than the camera is replaced by a new marker, which starts from the nearest one.
function snapLabels(m: MLMap) {
  labels = labels.map((l) => {
    const p = labelAt.get(l);
    if (!p) return l;
    const want = p.at[0] + 360 * Math.round((m.getCenter().lng - p.at[0]) / 360);
    if (Math.abs(l.getLngLat().lng - want) < 1e-6) return l;
    l.remove();
    labelAt.delete(l);
    return placeLabel(m, p.el, p.at);
  });
}

function clear(m: MLMap) {
  for (const id of painted) m.setFeatureState({ source: 'countries', id }, { v: 0 });
  painted = [];
  hideCountryNames(m, []);
  colourNamesOnFill(m, false);
  for (const l of labels) l.remove();
  labels = [];
  labelAt.clear();
}
