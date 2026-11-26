/**
 * Map controller: owns the MapLibre instance, the base layers, the flow overlay,
 * and generic helpers (camera moves, line/point layers) used by feature modules.
 */
import maplibregl, { type Map as MLMap, type MapMouseEvent, type GeoJSONSource, type LngLatBoundsLike, type ExpressionSpecification } from 'maplibre-gl';
import { feature } from 'topojson-client';
import type { FeatureCollection, Feature, LineString, Point } from 'geojson';
import { baseStyle } from './basemap';
import { WORLD_BOUNDS, MAX_ZOOM, SCALE_MIN_ZOOM, minZoomFor, constrainCamera } from './camera';
import { ResetViewControl } from './resetControl';
import { installLabels } from './labels';
import { FlowOverlay, type FlowPath } from './flowOverlay';
import { load, countryName, countries } from '../lib/data';
import { hovered, linkApplied, mapFailed, panelCollapsed, select, selection } from '../lib/store';
import { escapeHtml } from '../lib/format';

export interface LineFeatureProps {
  id: string;
  color: string;
  /** 0..1 relative weight (width) */
  w: number;
  /** what a click selects */
  kind: 'lane' | 'route' | 'pipeline' | 'alt' | 'land';
  /** destination country selected by a click on an overland / pipeline arc */
  to?: string;
  /** softer dashed line (overland / pipeline arcs) */
  soft?: boolean;
  dim?: boolean;
  /** highlighted (selected) line: full opacity, stronger glow */
  hl?: boolean;
  /** drawn dashed (alternative routing); no particles */
  dash?: boolean;
  label?: string;
}

/** Layout switches to bottom sheets at this width; keep in sync with the @media rules in styles/app.css. */
export const SHEET_BP = 1024;
/** Height of the side-panel sheet in its "peek" snap, px. */
export const SHEET_PEEK_PX = 96;
const sheetQuery = `(max-width: ${SHEET_BP}px)`;
export const isSheetLayout = () => window.matchMedia(sheetQuery).matches;

/** Padding that keeps a fitted area clear of the panels (measured from the real DOM). */
function viewPadding(opts: { detail: boolean }): { top: number; bottom: number; left: number; right: number } {
  const H = window.innerHeight;
  if (isSheetLayout()) {
    // short screens (a phone held sideways): the detail sheet is a column on the right, the map keeps the left
    if (opts.detail && window.matchMedia('(max-height: 500px)').matches) {
      const w = document.querySelector('.detail-panel')?.getBoundingClientRect().width || 340;
      return { top: 64, bottom: 16, left: 16, right: w + 24 };
    }
    const sheet = document.querySelector('.side-panel')?.getBoundingClientRect();
    const sheetH = sheet ? H - sheet.top : SHEET_PEEK_PX;
    const bottom = opts.detail ? H * 0.6 + 16 : Math.min(sheetH + 12, H * 0.55);
    return { top: 64, bottom, left: 16, right: 16 };
  }
  const panel = document.querySelector('.side-panel')?.getBoundingClientRect();
  const left = panelCollapsed.peek() ? 24 : (panel ? panel.right : 296) + 24;
  const detailW = opts.detail ? (document.querySelector('.detail-panel')?.getBoundingClientRect().width || 400) + 12 : 0;
  return { top: opts.detail ? 90 : 70, bottom: opts.detail ? 60 : 40, left, right: 24 + detailW };
}

let map: MLMap | null = null;
let overlay: FlowOverlay | null = null;
const readyCallbacks: Array<(m: MLMap) => void> = [];
let isReady = false;

export function getMap() {
  return map;
}

/** Run fn once the map style and base layers are ready. */
export function onMapReady(fn: (m: MLMap) => void) {
  if (isReady && map) fn(map);
  else readyCallbacks.push(fn);
}

/** Null when the map cannot start (no WebGL): the caller shows a message and the panels carry on. */
export function initMap(container: HTMLElement): MLMap | null {
  if (map) return map;
  // the canvas is the container: a screen's panels overlay it, so the whole screen counts
  const canvasSize = () => ({ w: container.clientWidth || window.innerWidth, h: container.clientHeight || window.innerHeight });
  try {
    const size = canvasSize();
    map = new maplibregl.Map({
      container,
      style: baseStyle(),
      center: [20, 22],
      zoom: 1.2,
      minZoom: minZoomFor(size.w, size.h),
      maxZoom: MAX_ZOOM,
      transformConstrain: (c, z) => {
        const { w, h } = canvasSize();
        const r = constrainCamera(c.lng, c.lat, z, w, h);
        return { center: new maplibregl.LngLat(r.lng, r.lat), zoom: r.zoom };
      },
      renderWorldCopies: true,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      fadeDuration: 0,
    });
  } catch (e) {
    // MapLibre throws when the browser gives it no WebGL context (switched off by policy, remote desktop)
    console.warn('the map could not start', e);
    map = null;
    mapFailed.value = true;
    return null;
  }
  // first-load framing: fit the trading world into the area the panels leave free; a link that opens a
  // page (a commodity above all, whose view does not move the map) keeps the world clear of that page too
  try {
    map.fitBounds(WORLD_BOUNDS, { padding: viewPadding({ detail: selection.peek() !== null }), maxZoom: 2.4, duration: 0 });
  } catch (e) {
    console.error('initial framing failed', e);
  }
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.addControl(new ResetViewControl(() => flyToWorld()), 'top-right');
  // under Mercator one pixel is a different length at each latitude: the bar reads the line through the middle of the
  // canvas, so it is only drawn from the zoom at which the view is narrow enough for that to be close (the control
  // stays mounted, the stylesheet shows it)
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 100, unit: 'nautical' }), 'top-right');
  const syncScale = () => map!.getContainer().classList.toggle('scale-on', map!.getZoom() >= SCALE_MIN_ZOOM);
  map.on('zoom', syncScale);
  syncScale();
  // a phone turned on its side, a desktop window made narrower: the floor follows the canvas
  map.on('resize', () => {
    const { w, h } = canvasSize();
    map!.setMinZoom(minZoomFor(w, h));
  });
  // no attribution box on the map: Natural Earth and every data source are credited in the About / Sources window

  map.on('load', async () => {
    const m = map!;
    overlay = new FlowOverlay(m);
    installLabels(m);
    await loadCountries(m);
    wireCountryInteraction(m);
    isReady = true;
    readyCallbacks.splice(0).forEach((fn) => fn(m));
  });
  return map;
}

// ---------------------------------------------------------------- countries

async function loadCountries(m: MLMap) {
  try {
    const topo = await load<any>('geo/countries.topo.json');
    const fc = feature(topo, topo.objects.countries) as unknown as FeatureCollection;
    (m.getSource('countries') as GeoJSONSource).setData(fc);
  } catch (e) {
    console.error('countries failed to load', e);
  }
}

let hoverId: string | null = null;
let selectedCountry: string | null = null;

function wireCountryInteraction(m: MLMap) {
  m.on('mousemove', 'land', (e) => {
    const f = e.features?.[0];
    const id = (f?.properties?.c as string) ?? null;
    if (id !== hoverId) {
      if (hoverId) m.setFeatureState({ source: 'countries', id: hoverId }, { hover: false });
      hoverId = id;
      if (id) m.setFeatureState({ source: 'countries', id }, { hover: true });
    }
    if (!lineHover() && !markerHover && id) {
      const extra = countryTooltipExtra?.(id) ?? '';
      hovered.value = { x: e.point.x, y: e.point.y, html: `<b>${escapeHtml(countryName(id))}</b>${extra}` };
    }
  });
  m.on('mouseleave', 'land', () => {
    if (hoverId) m.setFeatureState({ source: 'countries', id: hoverId }, { hover: false });
    hoverId = null;
    if (!lineHover() && !markerHover) hovered.value = null;
  });
  m.on('click', (e) => {
    // HTML markers (chokepoints, share labels) and lines take priority over countries
    if ((e.originalEvent.target as HTMLElement | null)?.closest?.('.cp, .share-label, .maplibregl-marker')) return;
    const hits = m.queryRenderedFeatures(e.point, { layers: interactiveLayers.filter((l) => m.getLayer(l)) });
    if (hits.length) return; // handled by the layer's own click handler
    const land = m.queryRenderedFeatures(e.point, { layers: ['land'] })[0];
    const id = land?.properties?.c as string | undefined;
    if (id && id !== '-99') select({ kind: 'country', id });
    // a click on empty sea closes the open selection (and the map zooms back out)
    else if (selection.peek()) select(null);
  });

  // reflect selected country on the map
  selectionHighlight(m);
}

/** Optional hook so the choropleth module can append "Production: 12% · 2024" to the tooltip. */
export let countryTooltipExtra: ((iso3: string) => string) | null = null;
export function setCountryTooltipExtra(fn: ((iso3: string) => string) | null) {
  countryTooltipExtra = fn;
}

function selectionHighlight(m: MLMap) {
  const apply = () => {
    const s = selection.value;
    const id = s?.kind === 'country' ? s.id : null;
    if (selectedCountry && selectedCountry !== id) m.setFeatureState({ source: 'countries', id: selectedCountry }, { selected: false });
    if (id) m.setFeatureState({ source: 'countries', id }, { selected: true });
    selectedCountry = id;
  };
  selection.subscribe(apply);
}

// ---------------------------------------------------------------- flows (line sets)
//
// Feature modules each own a named "line set" (e.g. 'lanes', 'routes'): a GeoJSON source
// with glow / line / alt (dashed) / hit layers, plus a key in the particle overlay.
// Hover, tooltip and click handling is generic and driven by feature properties.

const interactiveLayers: string[] = [];
const lineSets = new Set<string>();
/** Hit layers currently under the pointer (so the country tooltip yields to line tooltips). */
const hoverLayers = new Set<string>();
const lineHover = () => hoverLayers.size > 0;

export function registerInteractiveLayer(id: string) {
  if (!interactiveLayers.includes(id)) interactiveLayers.push(id);
}

/**
 * True while the pointer is over an HTML marker that shows its own tooltip (chokepoints): the map layers
 * underneath (countries, lines, icons) then leave the tooltip alone.
 */
let markerHover = false;
export function setMarkerHover(on: boolean) {
  markerHover = on;
}
export function isMarkerHover() {
  return markerHover;
}

/** Icon layers drawn over the lines: under the pointer they keep the tooltip (see the line hover). */
const pointLayers: string[] = [];
export function registerPointLayer(id: string) {
  if (!pointLayers.includes(id)) pointLayers.push(id);
}

/** True when an HTML marker (chokepoint, share label) or an icon sits under the pointer. */
function markerOrIconUnder(m: MLMap, e: MapMouseEvent): boolean {
  if ((e.originalEvent.target as HTMLElement | null)?.closest?.('.cp, .share-label, .maplibregl-marker')) return true;
  const ids = pointLayers.filter((l) => m.getLayer(l));
  return ids.length > 0 && m.queryRenderedFeatures(e.point, { layers: ids }).length > 0;
}

function ensureLineSet(m: MLMap, key: string) {
  if (lineSets.has(key)) return;
  lineSets.add(key);
  const src = `ls-${key}`;
  const hit = `${src}-hit`;
  const isDim: ExpressionSpecification = ['boolean', ['get', 'dim'], false];
  const isHl: ExpressionSpecification = ['boolean', ['get', 'hl'], false];
  const isSoft: ExpressionSpecification = ['boolean', ['get', 'soft'], false];
  const isHover: ExpressionSpecification = ['boolean', ['feature-state', 'hover'], false];
  m.addSource(src, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  // freight routes overlap heavily at world zoom: their glow fades in between zoom 2 and 3
  const glowOp: ExpressionSpecification = ['case', isDim, 0.03, isHl, 0.3, 0.13];
  m.addLayer({
    id: `${src}-glow`,
    type: 'line',
    source: src,
    filter: ['!', ['boolean', ['get', 'dash'], false]],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ['get', 'color'],
      'line-opacity': key === 'routes' ? ['interpolate', ['linear'], ['zoom'], 2, ['*', glowOp, 0.2], 3, glowOp] : glowOp,
      'line-width': ['interpolate', ['linear'], ['get', 'w'], 0, 4, 1, 16],
      'line-blur': 6,
    },
  });
  m.addLayer({
    id: `${src}-line`,
    type: 'line',
    source: src,
    filter: ['!', ['boolean', ['get', 'dash'], false]],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ['get', 'color'],
      'line-opacity': ['case', isHover, 1, isHl, 1, isDim, 0.12, 0.55],
      'line-width': ['interpolate', ['linear'], ['get', 'w'], 0, 0.8, 1, 4.5],
    },
  });
  // alternative routings are always dashed
  m.addLayer({
    id: `${src}-alt`,
    type: 'line',
    source: src,
    filter: ['boolean', ['get', 'dash'], false],
    layout: { 'line-cap': 'butt', 'line-join': 'round' },
    paint: {
      'line-color': ['get', 'color'],
      'line-opacity': ['case', isHover, 1, isDim, 0.12, isSoft, 0.55, 0.75],
      'line-width': ['interpolate', ['linear'], ['get', 'w'], 0, 1.2, 1, 3],
      'line-dasharray': [2, 2],
    },
  });
  m.addLayer({
    id: hit,
    type: 'line',
    source: src,
    paint: { 'line-color': '#000', 'line-opacity': 0, 'line-width': 14 },
  });
  registerInteractiveLayer(hit);

  let hoverFeature: string | number | undefined;
  const unhover = () => {
    if (hoverFeature !== undefined) m.setFeatureState({ source: src, id: hoverFeature }, { hover: false });
    hoverFeature = undefined;
  };
  m.on('mousemove', hit, (e) => {
    const f = e.features?.[0];
    if (!f) return;
    if (markerOrIconUnder(m, e)) {
      // the marker or icon on top owns the tooltip
      unhover();
      hoverLayers.delete(hit);
      return;
    }
    hoverLayers.add(hit);
    m.getCanvas().style.cursor = 'pointer';
    if (f.id !== hoverFeature) {
      unhover();
      hoverFeature = f.id;
      if (f.id !== undefined) m.setFeatureState({ source: src, id: f.id }, { hover: true });
    }
    hovered.value = { x: e.point.x, y: e.point.y, html: (f.properties?.label as string) ?? '' };
  });
  m.on('mouseleave', hit, () => {
    hoverLayers.delete(hit);
    m.getCanvas().style.cursor = '';
    unhover();
    if (!lineHover() && !markerHover) hovered.value = null;
  });
  m.on('click', hit, (e) => {
    const p = e.features?.[0]?.properties as LineFeatureProps | undefined;
    if (!p) return;
    if (p.kind === 'route' || p.kind === 'alt') select({ kind: 'route', id: p.id.replace(/:alt$/, '') });
    else if (p.kind === 'lane') select({ kind: 'lane', id: p.id });
    else if (p.kind === 'land' && p.to) select({ kind: 'country', id: p.to });
  });
}

/**
 * Replace the lines (and animated particles) of one named line set.
 * Each feature's `id` must be unique; tooltips come from `label` (HTML, already escaped).
 * Pass an empty array to hide the set.
 */
export function setLineSet(key: string, features: Feature<LineString, LineFeatureProps>[]) {
  onMapReady((m) => {
    ensureLineSet(m, key);
    const fc: FeatureCollection<LineString, LineFeatureProps> = {
      type: 'FeatureCollection',
      features: features.map((f, i) => ({ ...f, id: i + 1 })),
    };
    (m.getSource(`ls-${key}`) as GeoJSONSource).setData(fc);
    // feature ids are re-assigned: drop any stale hover tooltip from the previous data
    if (lineHover()) {
      hoverLayers.clear();
      hovered.value = null;
    }
    const paths: FlowPath[] = features
      .filter((f) => !f.properties.dash)
      .map((f) => ({
        id: f.properties.id,
        coords: f.geometry.coordinates as [number, number][],
        color: f.properties.color,
        weight: f.properties.w,
        dim: f.properties.dim,
      }));
    overlay?.setPaths(key, paths);
  });
}

export function setParticlesVisible(v: boolean) {
  overlay?.setVisible(v);
}

// ---------------------------------------------------------------- camera

export function flyToBounds(b: LngLatBoundsLike, maxZoom = 5, detail = true) {
  const m = map;
  if (!m) return;
  m.fitBounds(b, {
    padding: viewPadding({ detail }),
    maxZoom,
    duration: 1600,
  });
}

/** Back to the whole trading world (used when a commodity is picked, so its producers are visible). */
export function flyToWorld(detail = !!document.querySelector('.detail-panel.open')) {
  const m = map;
  if (!m) return;
  // a camera that drifted onto a wrapped copy of the world would fly to the Pacific-centred copy
  const c = m.getCenter();
  if (c.lng < -180 || c.lng > 180) m.jumpTo({ center: c.wrap() });
  m.fitBounds(WORLD_BOUNDS, { padding: viewPadding({ detail }), maxZoom: 2.4, duration: 1400 });
}

// Closing a selection (close button, Escape, tab change) zooms back out to the world view.
let hadSelection = selection.peek() !== null;
selection.subscribe((s) => {
  if (hadSelection && s === null) {
    // an action can close a selection and open another in one go: only zoom out if it stays closed
    queueMicrotask(() => {
      if (selection.peek() === null) flyToWorld(false);
    });
  }
  hadSelection = s !== null;
});

// A commodity link applied to the open atlas (pasted address, Back, Forward) shows the world beside its
// page, as a fresh load does; the other pages move the map themselves.
linkApplied.subscribe((link) => {
  if (link && selection.peek()?.kind === 'commodity') flyToWorld(true);
});

export function flyToCountry(iso3: string) {
  const c = countries.value[iso3];
  if (!c) return;
  const bb = c.bb;
  if (bb) flyToBounds([[bb[0], bb[1]], [bb[2], bb[3]]], 4.5);
  else map?.flyTo({ center: c.at, zoom: 3.5, duration: 1600 });
}

export function flyToLine(coords: [number, number][]) {
  if (!coords.length) return;
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  for (const [x, y] of coords) {
    w = Math.min(w, x); e = Math.max(e, x);
    s = Math.min(s, y); n = Math.max(n, y);
  }
  flyToBounds([[w, s], [e, n]], 5);
}

// ---------------------------------------------------------------- point layers helper

export function pointCollection<P>(items: { at: [number, number]; props: P }[]): FeatureCollection<Point, P> {
  return {
    type: 'FeatureCollection',
    features: items.map((it) => ({ type: 'Feature', properties: it.props, geometry: { type: 'Point', coordinates: it.at } })),
  };
}
