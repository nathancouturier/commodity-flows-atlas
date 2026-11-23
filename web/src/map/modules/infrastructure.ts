/**
 * Infrastructure layer: mines, smelters, ports, fields, refineries, LNG terminals (icons)
 * and pipelines (lines), from data/infrastructure/*.geojson.
 *
 * - filters: commodity (feature.k), infrastructure types (side panel), selected country
 * - every asset is drawn at its true position at every zoom; icons at the same place simply overlap
 * - hover tooltip with operator, capacity, output and source; click selects the asset (InfraView)
 * - History: an asset that opens after the selected year is drawn dimmed (never hidden), and a status dated
 *   after that year is not applied
 */
import { effect } from '@preact/signals';
import type { Map as MLMap, GeoJSONSource, ExpressionSpecification } from 'maplibre-gl';
import type { Feature, FeatureCollection, Geometry, LineString, Point } from 'geojson';
import type { Family, InfraProps, InfraType } from '../../types';
import { registerLayerModule } from '../layers';
import { isMarkerHover, registerInteractiveLayer, registerPointLayer } from '../controller';
import { commodity, family, hovered, infraAvailable, infraHidden, layers, select, selection, year } from '../../lib/store';
import { commodities, commodityMeta, countryName, loadOptional, sourceLabel, sources } from '../../lib/data';
import { FAMILY_COLOR, escapeHtml as esc, fmt } from '../../lib/format';
import { figuresOf } from '../../lib/capacity';
import { OUTPUT_LABEL, figureText, isOperating, monthYear, stateAt, statusClassOf, statusText, yearText, type Figure, type StatusClass } from '../../lib/infra';
import { INFRA_META, infraSvg } from '../../components/ui';

// ---------------------------------------------------------------- data access (shared with the detail views)

export interface InfraFeature {
  p: InfraProps;
  geom: Geometry;
  /** anchor [lon, lat]: the point itself, or a point along the line */
  at: [number, number];
}

// lng.geojson holds both 'lng-export' and 'lng-import' features (told apart by properties.type)
const FILES = ['mines', 'smelters', 'ports', 'fields', 'refineries', 'lng', 'pipelines'];
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
        out.push({ p: { ...props, k: props.k ?? [] }, geom: f.geometry, at });
      }
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

/** Does an asset belong to the active family tab? Freight shows the shipping endpoints (ports, LNG terminals). */
export function infraInTab(f: InfraFeature, tab: string): boolean {
  if (tab === 'all') return true;
  if (tab === 'freight') return f.p.type === 'port' || f.p.type === 'lng-export' || f.p.type === 'lng-import';
  return f.p.k.some((k) => (k === 'coal' ? 'energy' : commodityMeta(k)?.family) === tab);
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

export { isOperating };
export type { StatusClass };

/** Visual class of an asset status: damaged = red, idle / suspended = amber, construction / planned = dashed ring, closed = grey. */
export const statusClass = statusClassOf;

export const STATUS_COLOR: Record<Exclude<StatusClass, 'ok'>, string> = {
  damaged: '#ff4d5e',
  idle: '#ffc233',
  construction: '#e6edf5',
  planned: '#9aa7b5',
  closed: '#6f7b88',
};

export function infraRef(f: InfraFeature) {
  return { kind: 'infra' as const, id: f.p.id, layer: f.p.type };
}

/** One tooltip line of a figure: "Capacity 1,950 kt/y · 2025 · concentrate". */
function figureLine(label: string, f: Figure): string {
  const bits = [yearText(f), f.n, f.orig ? `source: ${f.orig}` : ''].filter(Boolean).join(' · ');
  return `<div class="num">${esc(label)} ${esc(figureText(f, fmt))}</div><div class="muted">${esc(bits)}</div>`;
}

/** Tooltip HTML for an asset (already escaped). */
export function infraTooltip(f: InfraFeature): string {
  const p = f.p;
  const figs = figuresOf(p);
  const st = stateAt(p, year.value);
  const status = st.status;
  // an operating asset needs no word; the others, and "not stated", are named
  const statusLine = st.notOpen
    ? st.opensIn != null ? `Opens in ${st.opensIn}` : 'Not open yet'
    : status && status !== 'operating' && !st.statusLater ? statusText(status, p.statusAsOf) : '';
  const source = `${esc(sourceLabel(p.s))}${p.read ? ` · read ${esc(monthYear(p.read))}` : ''}`;
  return (
    `<div><b>${esc(p.name)}</b></div>` +
    `<div class="muted">${esc(INFRA_META[p.type]?.label ?? p.type)} · ${esc(countryName(p.c))}${statusLine ? ` · ${esc(statusLine)}` : ''}</div>` +
    (p.coord === 'approx' ? '<div class="muted">Approximate location</div>' : '') +
    (p.operator ? `<div class="muted">${esc(p.operator)}</div>` : '') +
    (figs.capacity ? figureLine('Capacity', figs.capacity) : '') +
    (figs.output ? figureLine(OUTPUT_LABEL[figs.output.kind as keyof typeof OUTPUT_LABEL], figs.output) : '') +
    `<div class="src-line">${source}</div>`
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

/** Status decoration drawn over the base 28x28 icon (inserted before the closing </svg>). */
function statusSvg(st: StatusClass): string {
  if (st === 'ok') return '';
  const c = STATUS_COLOR[st];
  if (st === 'planned') return `<circle cx="14" cy="14" r="12.9" fill="none" stroke="${c}" stroke-width="2.2" stroke-dasharray="0.1 3.2" stroke-linecap="round"/>`;
  if (st === 'construction') return `<circle cx="14" cy="14" r="12.9" fill="none" stroke="${c}" stroke-width="2.2" stroke-dasharray="3 2.4"/>`;
  if (st === 'closed')
    return (
      `<circle cx="14" cy="14" r="12.9" fill="none" stroke="${c}" stroke-width="1.6"/>` +
      `<circle cx="23" cy="5" r="4.6" fill="${c}" stroke="#05090f" stroke-width="1"/>` +
      '<path d="M21.2 3.2l3.6 3.6M24.8 3.2l-3.6 3.6" stroke="#05090f" stroke-width="1.4" stroke-linecap="round"/>'
    );
  const ring = `<circle cx="14" cy="14" r="12.9" fill="none" stroke="${c}" stroke-width="${st === 'damaged' ? 2.4 : 1.8}"/>`;
  const badge =
    `<circle cx="23" cy="5" r="4.6" fill="${c}" stroke="#05090f" stroke-width="1"/>` +
    (st === 'damaged'
      ? '<path d="M23 2.6v3M23 7.1v.3" stroke="#05090f" stroke-width="1.5" stroke-linecap="round"/>'
      : '<path d="M21.7 3.2v3.6M24.3 3.2v3.6" stroke="#05090f" stroke-width="1.4" stroke-linecap="round"/>');
  return ring + badge;
}

function ensureIcon(m: MLMap, type: InfraType, color: string, st: StatusClass): Promise<string> {
  const name = `infra-${type}-${color.slice(1)}-${st}`;
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
      const svg = infraSvg(type, color, ICON_PX).replace('</svg>', `${statusSvg(st)}</svg>`);
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    });
    iconPending.set(name, p);
  }
  return p.then(() => name);
}

type PointProps = { key: string; id: string; type: InfraType; icon: string; op: number; sel: boolean };
type LineProps = { key: string; id: string; type: InfraType; color: string; op: number; sel: boolean; dash: boolean; label: string };

const SRC_PTS = 'infra-pts';
const SRC_SEL = 'infra-pts-sel'; // the opened asset, drawn on top
const SRC_LINES = 'infra-lines';

const sizeExpr: ExpressionSpecification = ['interpolate', ['linear'], ['zoom'], 0.5, 0.72, 2.2, 0.82, 4, 1, 7, 1.2];
const empty = (): FeatureCollection => ({ type: 'FeatureCollection', features: [] });

registerLayerModule((m) => {
  m.addSource(SRC_PTS, { type: 'geojson', data: empty() });
  m.addSource(SRC_SEL, { type: 'geojson', data: empty() });
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

  const iconLayout = {
    'icon-image': ['get', 'icon'],
    'icon-size': sizeExpr,
    'icon-allow-overlap': true,
    'icon-ignore-placement': true,
    // dimmed assets first, so highlighted ones are drawn on top
    'symbol-sort-key': ['get', 'op'],
  } as const;

  m.addLayer({
    id: 'infra-pts-all',
    type: 'symbol',
    source: SRC_PTS,
    layout: iconLayout as never,
    paint: { 'icon-opacity': ['get', 'op'] },
  });
  // selection halo and the opened asset (own source, on top)
  m.addLayer({
    id: 'infra-halo',
    type: 'circle',
    source: SRC_SEL,
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 13, 6, 20],
      'circle-color': 'rgba(62,230,255,0.12)',
      'circle-stroke-color': '#3ee6ff',
      'circle-stroke-width': 1.5,
    },
  });
  m.addLayer({
    id: 'infra-pts-sel',
    type: 'symbol',
    source: SRC_SEL,
    layout: iconLayout as never,
    paint: { 'icon-opacity': ['get', 'op'] },
  });

  const hitLayers = ['infra-pts-all', 'infra-pts-sel', 'infra-lines-hit'];
  hitLayers.forEach(registerInteractiveLayer);
  // icons win the hover over the routes and flows drawn under them
  ['infra-pts-all', 'infra-pts-sel'].forEach(registerPointLayer);

  // ---- interaction
  let byKey = new Map<string, InfraFeature>();
  void loadInfra().then((all) => (byKey = new Map(all.map((f) => [`${f.p.type}:${f.p.id}`, f]))));
  for (const layer of hitLayers) {
    m.on('mousemove', layer, (e) => {
      if ((e.originalEvent.target as HTMLElement | null)?.closest?.('.cp, .share-label')) return;
      const key = e.features?.[0]?.properties?.key as string | undefined;
      const f = key ? byKey.get(key) : undefined;
      if (!f) return;
      m.getCanvas().style.cursor = 'pointer';
      hovered.value = { x: e.point.x, y: e.point.y, html: infraTooltip(f) };
    });
    m.on('mouseleave', layer, () => {
      m.getCanvas().style.cursor = '';
      if (!isMarkerHover()) hovered.value = null;
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
    const tab = family.value;
    const hidden = infraHidden.value;
    const sel = selection.value;
    const hy = year.value;
    void [commodities.value, sources.value];
    const selInfra = sel?.kind === 'infra' ? `${sel.layer}:${sel.id}` : null;
    const selCountry = sel?.kind === 'country' ? sel.id : null;
    const my = ++seq;

    if (!on && !selInfra) {
      (m.getSource(SRC_PTS) as GeoJSONSource).setData(empty());
      (m.getSource(SRC_SEL) as GeoJSONSource).setData(empty());
      (m.getSource(SRC_LINES) as GeoJSONSource).setData(empty());
      return;
    }

    loadInfra().then(async (all) => {
      if (my !== seq) return;
      const pts: Feature<Point, PointProps>[] = [];
      const lines: Feature<LineString, LineProps>[] = [];
      // what the user is looking at decides which assets are relevant: the selected commodity,
      // otherwise the family tab (no gas fields on the Metals tab, no mines on Freight...)
      const relevant = (f: InfraFeature) => (k ? infraMatches(f.p.k, k) : infraInTab(f, tab));
      const available = new Set(all.filter(relevant).map((f) => f.p.type));
      infraAvailable.value = available;
      // type chips that do not exist for this selection are ignored rather than emptying the map
      for (const f of all) {
        const key = `${f.p.type}:${f.p.id}`;
        const isSelected = key === selInfra;
        if (!on) {
          if (!isSelected) continue; // layer off: only the opened asset
        } else if (!isSelected) {
          if (!relevant(f)) continue;
          if (hidden.has(f.p.type)) continue;
        }
        const mine = selCountry ? f.p.c === selCountry || (f.p.cs?.includes(selCountry) ?? false) : true;
        // a selected country is isolated: other countries' assets are hidden
        if (!mine && !isSelected) continue;
        // History: an asset that opens after the selected year is dimmed, not hidden; a status dated after it does not apply
        const at = stateAt(f.p, hy);
        const st = statusClass(at.status);
        const op = (st === 'ok' || st === 'damaged' ? 1 : 0.85) * (mine ? 1 : 0.25) * (at.notOpen ? 0.3 : 1);
        if (f.p.type === 'pipeline') {
          for (const coords of f.geom.type === 'LineString' ? [f.geom.coordinates] : f.geom.type === 'MultiLineString' ? f.geom.coordinates : []) {
            lines.push({
              type: 'Feature',
              geometry: { type: 'LineString', coordinates: coords as [number, number][] },
              properties: {
                key,
                id: f.p.id,
                type: f.p.type,
                color: st === 'damaged' || st === 'idle' || st === 'closed' ? STATUS_COLOR[st] : pipelineColor(f.p.k),
                op,
                sel: isSelected,
                dash: st !== 'ok' || at.notOpen,
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
            },
          });
        }
      }
      // rasterise the icons needed
      const featByKey = new Map(all.map((f) => [`${f.p.type}:${f.p.id}`, f]));
      await Promise.all(
        pts.map(async (p) => {
          const f = featByKey.get(p.properties.key)!;
          p.properties.icon = await ensureIcon(m, f.p.type, infraColor(f), statusClass(stateAt(f.p, hy).status));
        }),
      );
      if (my !== seq) return;
      (m.getSource(SRC_PTS) as GeoJSONSource).setData({ type: 'FeatureCollection', features: pts.filter((p) => !p.properties.sel) });
      (m.getSource(SRC_SEL) as GeoJSONSource).setData({ type: 'FeatureCollection', features: pts.filter((p) => p.properties.sel) });
      (m.getSource(SRC_LINES) as GeoJSONSource).setData({ type: 'FeatureCollection', features: lines });
    });
  });
});
