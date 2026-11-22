/**
 * Map controller: owns the MapLibre instance, the base layers, the flow overlay,
 * and generic helpers (camera moves, line/point layers) used by feature modules.
 */
import maplibregl, { type Map as MLMap, type GeoJSONSource, type LngLatBoundsLike } from 'maplibre-gl';
import { feature } from 'topojson-client';
import type { FeatureCollection, Feature, LineString, Point } from 'geojson';
import { baseStyle } from './basemap';
import { FlowOverlay, type FlowPath } from './flowOverlay';
import { load, countryName, countries } from '../lib/data';
import { hovered, select, selection } from '../lib/store';
import { escapeHtml } from '../lib/format';

export interface LineFeatureProps {
  id: string;
  color: string;
  /** 0..1 relative weight (width) */
  w: number;
  /** what a click selects */
  kind: 'lane' | 'route' | 'pipeline' | 'alt';
  dim?: boolean;
  label?: string;
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

export function initMap(container: HTMLElement) {
  if (map) return map;
  const small = window.innerWidth < 760;
  map = new maplibregl.Map({
    container,
    style: baseStyle(),
    center: [60, 18],
    zoom: small ? 0.6 : 1.55,
    minZoom: 0.5,
    maxZoom: 9,
    renderWorldCopies: true,
    attributionControl: false,
    dragRotate: false,
    pitchWithRotate: false,
    fadeDuration: 0,
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.addControl(
    new maplibregl.AttributionControl({
      compact: true,
      customAttribution: 'Borders: Natural Earth · Data: see sources panel',
    }),
    'bottom-right',
  );

  map.on('load', async () => {
    const m = map!;
    addFlowLayers(m);
    overlay = new FlowOverlay(m);
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
    if (!lineHover && id) {
      const extra = countryTooltipExtra?.(id) ?? '';
      hovered.value = { x: e.point.x, y: e.point.y, html: `<b>${escapeHtml(countryName(id))}</b>${extra}` };
    }
  });
  m.on('mouseleave', 'land', () => {
    if (hoverId) m.setFeatureState({ source: 'countries', id: hoverId }, { hover: false });
    hoverId = null;
    if (!lineHover) hovered.value = null;
  });
  m.on('click', (e) => {
    // lines and points take priority over countries
    const hits = m.queryRenderedFeatures(e.point, { layers: interactiveLayers.filter((l) => m.getLayer(l)) });
    if (hits.length) return; // handled by the layer's own click handler
    const land = m.queryRenderedFeatures(e.point, { layers: ['land'] })[0];
    const id = land?.properties?.c as string | undefined;
    if (id && id !== '-99') select({ kind: 'country', id });
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

// ---------------------------------------------------------------- flows (lines)

const interactiveLayers: string[] = ['flows-hit'];
let lineHover = false;

export function registerInteractiveLayer(id: string) {
  if (!interactiveLayers.includes(id)) interactiveLayers.push(id);
}

function addFlowLayers(m: MLMap) {
  m.addSource('flows', { type: 'geojson', data: { type: 'FeatureCollection', features: [] }, lineMetrics: true });
  m.addLayer({
    id: 'flows-glow',
    type: 'line',
    source: 'flows',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ['get', 'color'],
      'line-opacity': ['case', ['boolean', ['get', 'dim'], false], 0.03, 0.13],
      'line-width': ['interpolate', ['linear'], ['get', 'w'], 0, 4, 1, 16],
      'line-blur': 6,
    },
  });
  m.addLayer({
    id: 'flows-line',
    type: 'line',
    source: 'flows',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ['get', 'color'],
      'line-opacity': ['case', ['boolean', ['get', 'dim'], false], 0.12, ['boolean', ['feature-state', 'hover'], false], 1, 0.55],
      'line-width': ['interpolate', ['linear'], ['get', 'w'], 0, 0.8, 1, 4.5],
      'line-dasharray': ['case', ['==', ['get', 'kind'], 'alt'], ['literal', [2, 2]], ['literal', [1, 0]]],
    },
  });
  m.addLayer({
    id: 'flows-hit',
    type: 'line',
    source: 'flows',
    paint: { 'line-color': '#000', 'line-opacity': 0, 'line-width': 14 },
  });

  let hoverLine: string | number | undefined;
  m.on('mousemove', 'flows-hit', (e) => {
    const f = e.features?.[0];
    if (!f) return;
    lineHover = true;
    m.getCanvas().style.cursor = 'pointer';
    if (hoverLine !== undefined) m.setFeatureState({ source: 'flows', id: hoverLine }, { hover: false });
    hoverLine = f.id;
    if (f.id !== undefined) m.setFeatureState({ source: 'flows', id: f.id }, { hover: true });
    const label = (f.properties?.label as string) ?? '';
    hovered.value = { x: e.point.x, y: e.point.y, html: label };
  });
  m.on('mouseleave', 'flows-hit', () => {
    lineHover = false;
    m.getCanvas().style.cursor = '';
    if (hoverLine !== undefined) m.setFeatureState({ source: 'flows', id: hoverLine }, { hover: false });
    hoverLine = undefined;
    hovered.value = null;
  });
  m.on('click', 'flows-hit', (e) => {
    const p = e.features?.[0]?.properties as LineFeatureProps | undefined;
    if (!p) return;
    if (p.kind === 'route' || p.kind === 'alt') select({ kind: 'route', id: p.id.replace(/:alt$/, '') });
    else if (p.kind === 'lane') select({ kind: 'lane', id: p.id });
  });
}

/**
 * Replace the flow lines and their animated particles.
 * Each feature's `id` must be unique; tooltips come from `label` (HTML, already escaped).
 */
export function setFlows(features: Feature<LineString, LineFeatureProps>[]) {
  onMapReady((m) => {
    const fc: FeatureCollection<LineString, LineFeatureProps> = {
      type: 'FeatureCollection',
      features: features.map((f, i) => ({ ...f, id: i + 1 })),
    };
    (m.getSource('flows') as GeoJSONSource).setData(fc);
    const paths: FlowPath[] = features
      .filter((f) => f.properties.kind !== 'alt')
      .map((f) => ({
        id: f.properties.id,
        coords: f.geometry.coordinates as [number, number][],
        color: f.properties.color,
        weight: f.properties.w,
        dim: f.properties.dim,
      }));
    overlay?.setPaths(paths);
  });
}

export function setParticlesVisible(v: boolean) {
  overlay?.setVisible(v);
}

// ---------------------------------------------------------------- camera

export function flyToBounds(b: LngLatBoundsLike, maxZoom = 5) {
  const m = map;
  if (!m) return;
  const wide = window.innerWidth >= 760;
  m.fitBounds(b, {
    padding: wide
      ? { top: 90, bottom: 60, left: 360, right: 440 }
      : { top: 110, bottom: window.innerHeight * 0.5, left: 20, right: 20 },
    maxZoom,
    duration: 1600,
    essential: true,
  });
}

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
