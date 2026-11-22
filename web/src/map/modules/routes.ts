/**
 * Freight routes layer: Baltic benchmark and other heavy-traffic routes drawn from
 * data/freight/routes.geo.json, coloured by vessel segment.
 * Visible when the "Freight routes" layer is on or the Freight tab is active.
 */
import { effect } from '@preact/signals';
import type { Feature, LineString } from 'geojson';
import type { Route } from '../../types';
import { registerLayerModule } from '../layers';
import { flyToBounds, setLineSet, flyToLine, type LineFeatureProps } from '../controller';
import { layers, routeVia, selection, vesselClasses } from '../../lib/store';
import { commodities, commodityMeta, sourceLabel, sources } from '../../lib/data';
import { SEGMENT_COLOR, loadRoutes, loadRouteGeo, routeTouches, segmentOf, vesselClassList, vesselMatches, vesselName } from '../../lib/freight';
import { escapeHtml as esc, fmt } from '../../lib/format';

function routeLabel(r: Route): string {
  const share = r.shares?.[0];
  const what = share ? (commodityMeta(share.k)?.name ?? share.k).toLowerCase() : '';
  return (
    `<div>${r.benchmark ? `<b>${esc(r.id)}</b> ` : '<b>'}${esc(r.name)}${r.benchmark ? '' : '</b>'}</div>` +
    `<div class="muted">${esc(vesselName(r.vclass))} · ${fmt(r.distanceNm)} nm · ${fmt(r.days)} days</div>` +
    (share ? `<div class="num">${fmt(share.f.v)}% of seaborne ${esc(what)} (${esc(String(share.f.y))})</div>` : '') +
    `<div class="src-line">${esc(r.s === 'atlas' ? 'Atlas estimate' : sourceLabel(r.s))}${r.discontinued ? ` · discontinued ${esc(r.discontinued)}` : ''}</div>`
  );
}

registerLayerModule(() => {
  let seq = 0;
  let flown: string | null = null;
  let framed = '';

  effect(() => {
    const vc = vesselClasses.value;
    // the Freight routes switch decides (Freight and a vessel-class pick switch it on)
    const on = layers.value.routes;
    const sel = selection.value;
    const selId = sel?.kind === 'route' ? sel.id : null;
    const iso = sel?.kind === 'country' ? sel.id : null;
    void [vesselClassList.value, commodities.value, sources.value];
    if (!iso) routeVia.value = null;

    const my = ++seq;
    if (!on && !selId) {
      setLineSet('routes', []);
      if (iso) routeVia.value = new Set();
      return;
    }
    Promise.all([loadRoutes(), loadRouteGeo()])
      .then(([routes, geo]) => {
        if (my !== seq) return;
        const byId = new Map(routes.map((r) => [r.id, r]));
        const features: Feature<LineString, LineFeatureProps>[] = [];
        for (const f of geo.features) {
          const id = f.properties.id.replace(/:alt$/, '');
          const r = byId.get(id);
          if (!r) continue;
          const isAlt = f.properties.kind === 'alt';
          const isSel = id === selId;
          // alternatives are only drawn for the selected route
          if (isAlt && !isSel) continue;
          if (!isSel) {
            if (!on || r.discontinued) continue;
            if (!vesselMatches(r.vclass, vc)) continue;
            // a selected country is isolated: only routes that load or discharge there
            if (iso && !routeTouches(r, iso)) continue;
          }
          features.push({
            type: 'Feature',
            geometry: f.geometry,
            properties: {
              id: f.properties.id,
              kind: isAlt ? 'alt' : 'route',
              color: SEGMENT_COLOR[segmentOf(r.vclass)],
              w: isSel ? 0.85 : r.benchmark ? 0.45 : 0.3,
              dim: !!selId && !isSel,
              hl: isSel && !isAlt,
              dash: isAlt,
              label: isAlt && r.alt ? `<div><b>${esc(id)} alternative</b></div><div class="muted">${esc(r.alt.label)}</div>` : routeLabel(r),
            },
          });
        }
        setLineSet('routes', features);
        if (iso) routeVia.value = new Set(features.flatMap((f) => byId.get(f.properties.id.replace(/:alt$/, ''))?.via ?? []));
        // a new vessel-class selection frames all its routes
        const key = [...vc].sort().join(',');
        if (key && key !== framed && !selId && features.length) {
          let w = Infinity, so = Infinity, e = -Infinity, n = -Infinity;
          for (const f of features) for (const [x, y] of f.geometry.coordinates) {
            w = Math.min(w, x); e = Math.max(e, x); so = Math.min(so, y); n = Math.max(n, y);
          }
          if (e - w < 340) flyToBounds([[w, so], [e, n]], 4);
        }
        framed = key;
        const main = features.find((f) => f.properties.hl);
        if (selId && main && flown !== selId) flyToLine(main.geometry.coordinates as [number, number][]);
        flown = selId;
      })
      .catch((e) => console.error('routes failed to load', e));
  });
});
