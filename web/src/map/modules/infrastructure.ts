/**
 * Infrastructure layer: mines, smelters, ports, fields, refineries, LNG terminals (icons)
 * and pipelines (lines), from data/infrastructure/*.geojson.
 *
 * - filters: commodity (feature.k), infrastructure types (side panel), selected country
 * - world view shows only primary (largest) assets; the rest appears from zoom 2.2
 * - hover tooltip with operator, capacity and source; click selects the asset (InfraView)
 */
import { effect } from '@preact/signals';
import type { Map as MLMap, GeoJSONSource, ExpressionSpecification } from 'maplibre-gl';
import type { Feature, FeatureCollection, Geometry, LineString, Point } from 'geojson';
import type { Family, InfraProps, InfraType } from '../../types';
import { registerLayerModule } from '../layers';
import { registerInteractiveLayer } from '../controller';
import { commodity, hovered, infraTypes, layers, select, selection } from '../../lib/store';
import { commodities, commodityMeta, countryName, loadOptional, sourceLabel, sources } from '../../lib/data';
import { FAMILY_COLOR, escapeHtml as esc, fmt } from '../../lib/format';
import { INFRA_META, infraSvg } from '../../components/ui';

// ---------------------------------------------------------------- data access (shared with the detail views)

export interface InfraFeature {
  p: InfraProps;
  geom: Geometry;
  /** anchor [lon, lat]: the point itself, or a point along the line */
  at: [number, number];
  /** 0 = primary (shown at world zoom), 1 = secondary */
  pri: 0 | 1;
}

const FILES = ['mines', 'smelters', 'ports', 'fields', 'refineries', 'lng', 'lng-export', 'lng-import', 'pipelines'];
let infraPromise: Promise<InfraFeature[]> | null = null;

function lineCoords(g: Geometry): [number, number][] {
  if (g.type === 'LineString') return g.coordinates as [number, number][];
  if (g.type === 'MultiLineString') return (g.coordinates as [number, number][][]).flat();
  return [];
}

/** All infrastructure features (cached). Missing files are skipped. */
export function loadInfra(): Promise<InfraFeature[]> {
  if (infraPromise) return infraPromise;
  const p = Promise.all(FILES.map((f) => loadOptional<FeatureCollection>(`infrastructure/${f}.geojson`))).then((files) => {
    const out: InfraFeature[] = [];
    const seen = new Set<string>();
    for (const fc of files) {
      if (!fc || !Array.isArray(fc.features)) continue;
      for (const f of fc.features) {
        const props = f.properties as InfraProps | null;
        if (!props || !props.id || !f.geometry) continue;
        const key = `${props.type}:${props.id}`;
        if (seen.has(key)) continue;
        seen.add(key);
        let at: [number, number];
        if (f.geometry.type === 'Point') at = f.geometry.coordinates as [number, number];
        else {
          const cs = lineCoords(f.geometry);
          if (!cs.length) continue;
          at = cs[Math.floor(cs.length / 2)];
        }
        out.push({ p: { ...props, k: props.k ?? [] }, geom: f.geometry, at, pri: 1 });
      }
    }
    // primary assets: the largest few of each type by stated capacity
    const byType = new Map<string, InfraFeature[]>();
    for (const f of out) byType.set(f.p.type, [...(byType.get(f.p.type) ?? []), f]);
    for (const list of byType.values()) {
      list
        .filter((f) => f.p.capacity)
        .sort((a, b) => b.p.capacity!.v - a.p.capacity!.v)
        .slice(0, 8)
        .forEach((f) => (f.pri = 0));
    }
    return out;
  });
  p.catch(() => (infraPromise = null));
  infraPromise = p;
  return p;
}

/** Does an asset belong to a commodity? Coal commodities also match generic "coal" assets. */
export function infraMatches(k: string[], id: string): boolean {
  if (k.includes(id)) return true;
  if ((id === 'thermal-coal' || id === 'met-coal') && k.includes('coal')) return true;
  return false;
}

export function infraFamily(f: InfraFeature): Family {
  for (const k of f.p.k) {
    const m = commodityMeta(k);
    if (m) return m.family;
  }
  return f.p.type === 'smelter' || f.p.type === 'mine' ? 'metals' : 'energy';
}

export function infraColor(f: InfraFeature): string {
  return FAMILY_COLOR[infraFamily(f)];
}

export function isOperating(status?: string): boolean {
  return !status || /operat|active|producing/i.test(status);
}

export function infraRef(f: InfraFeature) {
  return { kind: 'infra' as const, id: f.p.id, layer: f.p.type };
}

export function infraCapacity(p: InfraProps): string {
  return p.capacity ? `${fmt(p.capacity.v)} ${p.capacity.u}` : '';
}

/** Tooltip HTML for an asset (already escaped). */
export function infraTooltip(f: InfraFeature): string {
  const p = f.p;
  const cap = infraCapacity(p);
  const yr = p.y != null ? ` · ${esc(String(p.y))}` : '';
  return (
    `<div><b>${esc(p.name)}</b></div>` +
    `<div class="muted">${esc(INFRA_META[p.type]?.label ?? p.type)} · ${esc(countryName(p.c))}${p.status && !isOperating(p.status) ? ` · ${esc(p.status)}` : ''}</div>` +
    (p.operator ? `<div class="muted">${esc(p.operator)}</div>` : '') +
    (cap ? `<div class="num">${esc(cap)}</div>` : '') +
    `<div class="src-line">${esc(sourceLabel(p.s))}${yr}</div>`
  );
}

// ---------------------------------------------------------------- pipeline colours

const PIPE_CRUDE = '#b8741a';
const PIPE_PRODUCTS = '#ffd08a';
const PIPE_GAS = '#3ed8c3';

export function pipelineColor(k: string[]): string {
  if (k.includes('crude-oil')) return PIPE_CRUDE;
  if (k.includes('refined-products') || k.includes('lpg')) return PIPE_PRODUCTS;
  return PIPE_GAS;
}

// ---------------------------------------------------------------- map layer

const ICON_PX = 56; // 28 css px at pixelRatio 2
const iconPending = new Map<string, Promise<void>>();

function ensureIcon(m: MLMap, type: InfraType, color: string): Promise<string> {
  const name = `infra-${type}-${color.slice(1)}`;
  if (m.hasImage(name)) return Promise.resolve(name);
  let p = iconPending.get(name);
  if (!p) {
    p = new Promise<void>((resolve) => {
      const img = new Image(ICON_PX, ICON_PX);
      img.onload = () => {
        try {
          const cv = document.createElement('canvas');
          cv.width = cv.height = ICON_PX;
          const ctx = cv.getContext('2d')!;
          ctx.drawImage(img, 0, 0, ICON_PX, ICON_PX);
          if (!m.hasImage(name)) m.addImage(name, ctx.getImageData(0, 0, ICON_PX, ICON_PX), { pixelRatio: 2 });
        } catch (e) {
          console.error('infra icon failed', name, e);
        }
        resolve();
      };
      img.onerror = () => resolve();
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(infraSvg(type, color, ICON_PX));
    });
    iconPending.set(name, p);
  }
  return p.then(() => name);
}

type PointProps = { key: string; id: string; type: InfraType; icon: string; op: number; sel: boolean; pri: number };
type LineProps = { key: string; id: string; type: InfraType; color: string; op: number; sel: boolean; dash: boolean; label: string };

const SRC_PTS = 'infra-pts';
const SRC_LINES = 'infra-lines';
const sizeExpr: ExpressionSpecification = ['interpolate', ['linear'], ['zoom'], 0.5, 0.72, 2.2, 0.82, 4, 1, 7, 1.2];
const empty = (): FeatureCollection => ({ type: 'FeatureCollection', features: [] });

registerLayerModule((m) => {
  m.addSource(SRC_PTS, { type: 'geojson', data: empty() });
  m.addSource(SRC_LINES, { type: 'geojson', data: empty() });

  const isSel: ExpressionSpecification = ['boolean', ['get', 'sel'], false];
  const isDash: ExpressionSpecification = ['boolean', ['get', 'dash'], false];
  const lineWidth: ExpressionSpecification = ['interpolate', ['linear'], ['zoom'], 1, 0.9, 5, 1.8, 8, 2.6];

  const selWidth: ExpressionSpecification = [
    'interpolate', ['linear'], ['zoom'],
    1, ['case', isSel, 3, 0.9],
    5, ['case', isSel, 3.6, 1.8],
    8, ['case', isSel, 4.2, 2.6],
  ];
  m.addLayer({
    id: 'infra-lines-glow',
    type: 'line',
    source: SRC_LINES,
    filter: ['!', isDash],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'color'], 'line-opacity': ['*', ['get', 'op'], 0.18], 'line-width': 6, 'line-blur': 4 },
  });
  m.addLayer({
    id: 'infra-lines-solid',
    type: 'line',
    source: SRC_LINES,
    filter: ['!', isDash],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'color'], 'line-opacity': ['*', ['get', 'op'], 0.9], 'line-width': selWidth },
  });
  m.addLayer({
    id: 'infra-lines-dash',
    type: 'line',
    source: SRC_LINES,
    filter: isDash,
    layout: { 'line-cap': 'butt', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'color'], 'line-opacity': ['*', ['get', 'op'], 0.9], 'line-width': lineWidth, 'line-dasharray': [2.5, 2] },
  });
  m.addLayer({
    id: 'infra-lines-hit',
    type: 'line',
    source: SRC_LINES,
    paint: { 'line-color': '#000', 'line-opacity': 0, 'line-width': 12 },
  });

  // selection halo under the icons
  m.addLayer({
    id: 'infra-halo',
    type: 'circle',
    source: SRC_PTS,
    filter: isSel,
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 13, 6, 20],
      'circle-color': 'rgba(62,230,255,0.12)',
      'circle-stroke-color': '#3ee6ff',
      'circle-stroke-width': 1.5,
    },
  });
  const symbol = (id: string, pri: number, minzoom: number) =>
    m.addLayer({
      id,
      type: 'symbol',
      source: SRC_PTS,
      minzoom,
      filter: ['==', ['get', 'pri'], pri],
      layout: {
        'icon-image': ['get', 'icon'],
        'icon-size': sizeExpr,
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
      },
      paint: { 'icon-opacity': ['get', 'op'] },
    });
  symbol('infra-pts-pri', 0, 0);
  symbol('infra-pts-sec', 1, 2.2);

  const hitLayers = ['infra-pts-pri', 'infra-pts-sec', 'infra-lines-hit'];
  hitLayers.forEach(registerInteractiveLayer);

  // ---- interaction
  let byKey = new Map<string, InfraFeature>();
  void loadInfra().then((all) => (byKey = new Map(all.map((f) => [`${f.p.type}:${f.p.id}`, f]))));
  for (const layer of hitLayers) {
    m.on('mousemove', layer, (e) => {
      const key = e.features?.[0]?.properties?.key as string | undefined;
      const f = key ? byKey.get(key) : undefined;
      if (!f) return;
      m.getCanvas().style.cursor = 'pointer';
      hovered.value = { x: e.point.x, y: e.point.y, html: infraTooltip(f) };
    });
    m.on('mouseleave', layer, () => {
      m.getCanvas().style.cursor = '';
      hovered.value = null;
    });
    m.on('click', layer, (e) => {
      const key = e.features?.[0]?.properties?.key as string | undefined;
      const f = key ? byKey.get(key) : undefined;
      if (f) select(infraRef(f));
    });
  }

  // ---- data
  let seq = 0;
  effect(() => {
    const on = layers.value.infrastructure;
    const k = commodity.value;
    const types = infraTypes.value;
    const sel = selection.value;
    void [commodities.value, sources.value];
    const selInfra = sel?.kind === 'infra' ? `${sel.layer}:${sel.id}` : null;
    const selCountry = sel?.kind === 'country' ? sel.id : null;
    const my = ++seq;

    if (!on && !selInfra) {
      (m.getSource(SRC_PTS) as GeoJSONSource).setData(empty());
      (m.getSource(SRC_LINES) as GeoJSONSource).setData(empty());
      return;
    }

    loadInfra().then(async (all) => {
      if (my !== seq) return;
      const pts: Feature<Point, PointProps>[] = [];
      const lines: Feature<LineString, LineProps>[] = [];
      for (const f of all) {
        const key = `${f.p.type}:${f.p.id}`;
        const isSelected = key === selInfra;
        if (!on) {
          if (!isSelected) continue; // layer off: only the opened asset
        } else {
          if (types.size && !types.has(f.p.type)) continue;
          if (k && !infraMatches(f.p.k, k)) continue;
        }
        const mine = selCountry ? f.p.c === selCountry || (f.p.cs?.includes(selCountry) ?? false) : true;
        const op = (isOperating(f.p.status) ? 1 : 0.5) * (mine ? 1 : 0.25);
        if (f.p.type === 'pipeline') {
          for (const coords of f.geom.type === 'LineString' ? [f.geom.coordinates] : f.geom.type === 'MultiLineString' ? f.geom.coordinates : []) {
            lines.push({
              type: 'Feature',
              geometry: { type: 'LineString', coordinates: coords as [number, number][] },
              properties: {
                key,
                id: f.p.id,
                type: f.p.type,
                color: pipelineColor(f.p.k),
                op,
                sel: isSelected,
                dash: !isOperating(f.p.status),
                label: f.p.name,
              },
            });
          }
        } else if (f.geom.type === 'Point') {
          pts.push({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: f.at },
            properties: {
              key,
              id: f.p.id,
              type: f.p.type,
              icon: '',
              op,
              sel: isSelected,
              // a commodity or country focus is already uncluttered: show everything
              pri: k || (selCountry && mine) || isSelected ? 0 : f.pri,
            },
          });
        }
      }
      // rasterise the icons needed
      const featByKey = new Map(all.map((f) => [`${f.p.type}:${f.p.id}`, f]));
      await Promise.all(
        pts.map(async (p) => {
          const f = featByKey.get(p.properties.key)!;
          p.properties.icon = await ensureIcon(m, f.p.type, infraColor(f));
        }),
      );
      if (my !== seq) return;
      // draw dimmed / small ones first so highlighted icons stay on top (symbol sort via source order)
      pts.sort((a, b) => a.properties.op - b.properties.op);
      (m.getSource(SRC_PTS) as GeoJSONSource).setData({ type: 'FeatureCollection', features: pts });
      (m.getSource(SRC_LINES) as GeoJSONSource).setData({ type: 'FeatureCollection', features: lines });
    });
  });
});
