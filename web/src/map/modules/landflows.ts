/**
 * Overland and pipeline flows of the selected commodity, from data/commodities/<id>.json
 * (flows with mode land / pipeline / rail / mixed; customs data, no route geometry).
 * Drawn as curved, dashed great-circle arcs between the two countries' anchor points, in the
 * commodity's family colour and slightly fainter than the seaborne lanes. Click selects the
 * destination country. A mixed (sea and overland) flow that has a lane is not drawn here: the
 * lanes layer draws it, dashed, on its sea route.
 */
import { effect, signal } from '@preact/signals';
import type { Feature, LineString } from 'geojson';
import type { CommodityData, Flow } from '../../types';
import { registerLayerModule } from '../layers';
import { setLineSet, type LineFeatureProps } from '../controller';
import { commodity, landFlowsShown, layers, mapNotice, selection, year } from '../../lib/store';
import { commodities, commodityMeta, countries, countryName, loadOptional, sourceLabel, sources } from '../../lib/data';
import { LANE_GROUPS, loadLaneFile } from '../../lib/freight';
import { FAMILY_COLOR, escapeHtml as esc, fmtEst } from '../../lib/format';

const LAND_MODES = new Set(['land', 'pipeline', 'rail', 'mixed']);
/** Arcs now drawn that stand for a mixed (sea and overland) flow, for the legend. */
export const mixedArcsShown = signal(0);

/** What the tooltip calls a flow: its own mode word (the data say `land` for rail, road and pipeline alike). */
const MODE_WORD: Record<string, string> = {
  land: 'overland or pipeline',
  pipeline: 'pipeline',
  rail: 'rail',
  mixed: 'by sea and overland, split not known',
};

const rad = (d: number) => (d * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

/** Curved great-circle arc [lon, lat][] from a to b; the bulge is a lateral offset of `bow` x length. */
export function arc(a: [number, number], b: [number, number], bow = 0.14, n = 48): [number, number][] {
  const [lo1, la1, lo2, la2] = [rad(a[0]), rad(a[1]), rad(b[0]), rad(b[1])];
  const d = 2 * Math.asin(Math.sqrt(Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2));
  const out: [number, number][] = [];
  if (!d) return [a, b];
  let prevLon = a[0];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const A = Math.sin((1 - t) * d) / Math.sin(d);
    const B = Math.sin(t * d) / Math.sin(d);
    const x = A * Math.cos(la1) * Math.cos(lo1) + B * Math.cos(la2) * Math.cos(lo2);
    const y = A * Math.cos(la1) * Math.sin(lo1) + B * Math.cos(la2) * Math.sin(lo2);
    const z = A * Math.sin(la1) + B * Math.sin(la2);
    const lat = deg(Math.atan2(z, Math.hypot(x, y)));
    let lon = deg(Math.atan2(y, x));
    // keep the longitude continuous with the previous point (unwrapped, like the lane geometries)
    while (lon - prevLon > 180) lon -= 360;
    while (lon - prevLon < -180) lon += 360;
    prevLon = lon;
    out.push([lon, lat]);
  }
  // lateral bulge so that arcs between neighbours (e.g. Canada -> USA) read as curves, not as borders
  const dx = out[out.length - 1][0] - out[0][0];
  const dy = out[out.length - 1][1] - out[0][1];
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const amp = Math.min(Math.max(len * bow, 1.2), 14);
  return out.map(([lon, lat], i) => {
    const s = Math.sin(Math.PI * (i / n));
    return [lon + nx * amp * s, Math.max(-84, Math.min(84, lat + ny * amp * s))] as [number, number];
  });
}

function label(f: Flow, name: string): string {
  return (
    `<div><b>${esc(countryName(f.o))} → ${esc(countryName(f.d))}</b> · ${esc(name)}</div>` +
    `<div class="num">${fmtEst(f.v, f.est)} ${esc(f.u)}${f.est ? ' · Atlas estimate' : ''} · ${MODE_WORD[f.mode ?? 'land'] ?? 'overland'} (customs)</div>` +
    `<div class="src-line">${esc(sourceLabel(f.s))} · ${esc(String(f.y))}</div>`
  );
}

registerLayerModule(() => {
  let seq = 0;
  effect(() => {
    const on = layers.value.flows;
    const k = commodity.value;
    const yr = year.value;
    const sel = selection.value;
    void [commodities.value, countries.value, sources.value];
    const my = ++seq;

    const clear = () => {
      setLineSet('land', []);
      landFlowsShown.value = 0;
      mixedArcsShown.value = 0;
      mapNotice.value = null;
    };
    if (!on || !k) return clear();

    Promise.all([
      loadOptional<CommodityData>(`commodities/${k}.json`),
      Promise.all(
        (LANE_GROUPS[k] ?? []).map((g) =>
          loadLaneFile(g)
            .then((f) => ({ n: f.lanes.length, mixed: f.lanes.filter((l) => l.mode === 'mixed').map((l) => `${l.o}-${l.d}`) }))
            .catch(() => ({ n: 0, mixed: [] as string[] })),
        ),
      ),
    ]).then(([d, laneInfo]) => {
      if (my !== seq) return;
      // the lanes layer draws these pairs (dashed, on their sea route): no second line here, whatever mode the flow table gives (its
      // older shape says `land` for them)
      const drawnAsLane = new Set(laneInfo.flatMap((i) => i.mixed));
      const meta = commodityMeta(k);
      const color = meta ? FAMILY_COLOR[meta.family] : '#8aa0b8';
      const all = (d?.flows ?? []).filter(
        (f) => f.mode && LAND_MODES.has(f.mode) && f.v > 0 && !(f.mode === 'mixed' && f.lane) && !drawnAsLane.has(`${f.o}-${f.d}`),
      );
      const flows = yr != null ? all.filter((f) => String(f.y) === String(yr)) : all;
      const max = Math.max(...flows.map((f) => f.v), 1e-9);
      const features: Feature<LineString, LineFeatureProps>[] = [];
      let mixedArcs = 0;
      for (const f of flows.sort((a, b) => b.v - a.v)) {
        const a = countries.value[f.o]?.at;
        const b = countries.value[f.d]?.at;
        if (!a || !b) continue;
        // a selected country is isolated: only its own overland / pipeline flows
        if (sel?.kind === 'country' && f.o !== sel.id && f.d !== sel.id) continue;
        const bright = true;
        if (f.mode === 'mixed') mixedArcs++;
        features.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: arc(a, b) },
          properties: {
            id: `land:${k}:${f.o}-${f.d}`,
            kind: 'land',
            to: f.d,
            soft: true,
            dash: true,
            color,
            w: Math.sqrt(f.v / max),
            dim: !bright,
            label: label(f, meta?.name ?? k),
          },
        });
      }
      setLineSet('land', features);
      landFlowsShown.value = features.length;
      mixedArcsShown.value = mixedArcs;
      const hasLanes = laneInfo.some((i) => i.n > 0);
      const cur = selection.peek();
      // A commodity outside the lane model (uranium, gold...) has no sea routes: its sea flows are listed on
      // the commodity page, not drawn, and so are flows whose transport mode the atlas does not model (precious
      // metals). The notice says that, not "no flows"; overland flows are still drawn as arcs.
      const listed = d?.flows ?? [];
      const seaListed = listed.some((f) => f.mode === 'sea' && f.v > 0);
      const unmodelled = listed.some((f) => !f.mode && f.v > 0);
      const name = meta?.name ?? k;
      const onPage = cur && (cur.kind === 'lane' || cur.kind === 'route');
      mapNotice.value =
        hasLanes || onPage
          ? null
          : seaListed
            ? `${name} flows are listed in the panel; sea routes are not drawn for this commodity.`
            : unmodelled
              ? `${name} customs flows are listed in the panel's tables, not drawn: the atlas draws sea and overland lanes only.`
              : features.length
                ? null
                : `No mapped seaborne or overland flows for ${name} in the open data${yr != null ? ` for ${yr}` : ''}.`;
    });
  });
});
