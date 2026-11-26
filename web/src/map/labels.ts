/**
 * Country and sea names on the map: symbol layers over the atlas's own glyph files (public/glyphs), added before any module
 * layer so that the lanes, routes and icons are drawn over the names; the module of the icons then raises the country
 * names, and the overland flows, above the asset names (`raiseAboveAssetNames`). The layers are not interactive: a click or a hover on a
 * name is a click or a hover on the country under it.
 */
import { effect } from '@preact/signals';
import type { Map as MLMap, GeoJSONSource } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { load } from '../lib/data';
import { choroInfo, historyOpen, layers, panelCollapsed, priceDrawer, selection, sheetSnap } from '../lib/store';
import type { CountryMeta } from '../types';
import { COUNTRY_NAME_LAYERS, ICON_LAYER, LABEL_COLOR, LABEL_ON_FILL, LAND_FLOW_LAYERS, OVERLAYS, OVERLAYS_WATCHED, countryEdgeNames, countryFilter, countryPoints, labelLayerSpecs, moveUnder, namesAtEdge, oceanEdgeNames, overlayRects, seaFilter, seaPoints } from './labelRules';
import type { EdgeName, Rect, Sea } from './labelRules';

const SOURCE = 'names-countries';
const SEA_SOURCE = 'names-seas';
const OCEANS = 'names-seas-0';
const LARGEST = 'names-countries-0';
const TIERS = [0, 1, 2, 3] as const;

let hidden: string[] = [];
/** The oceans of the sea table (their boxes do not depend on the zoom) and the rows of the country index, kept for the edge rule. */
let oceans: EdgeName[] = [];
let countryRows: CountryMeta[] = [];
/** The oceans and the largest country names left out of their layer now, because the edge of the canvas would cut them. */
let cutOceans: string[] = [];
let cutCountries: string[] = [];

const empty = (): FeatureCollection => ({ type: 'FeatureCollection', features: [] });

export function installLabels(m: MLMap) {
  m.addSource(SOURCE, { type: 'geojson', data: empty() });
  m.addSource(SEA_SOURCE, { type: 'geojson', data: empty() });
  for (const spec of labelLayerSpecs(hidden)) m.addLayer(spec);
  // when the asset names are already there the country names go above them; if they come later, their module does it
  if (m.getLayer(ICON_LAYER)) raiseAboveAssetNames(m, ICON_LAYER);
  // the oceans are the largest names and the ones the edge of a phone cuts: tested when the camera comes to rest, never during a move
  m.on('moveend', () => leaveOutCut(m));
  m.on('resize', () => leaveOutCut(m));
  watchOverlays(m);
  // the rows of the index file, not the signal of the pages: that one holds the European Union as a row of its own
  load<CountryMeta[]>('countries/index.json')
    .then((list) => {
      countryRows = list;
      (m.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(countryPoints(list));
      leaveOutCut(m);
    })
    .catch(() => undefined);
  // a missing file leaves the seas without names and the countries with theirs
  load<{ seas: Sea[] }>('geo/seas.json')
    .then((d) => {
      oceans = oceanEdgeNames(d.seas);
      (m.getSource(SEA_SOURCE) as GeoJSONSource | undefined)?.setData(seaPoints(d.seas));
      leaveOutCut(m);
    })
    .catch(() => undefined);
}

const same = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((x, i) => x === b[i]);

/** The rectangles of what is drawn over the map now, in the canvas's own coordinates: the elements of `OVERLAYS` that are displayed (and open, where they have to be). */
function coveredBy(m: MLMap): Rect[] {
  const origin = m.getContainer().getBoundingClientRect();
  const boxes = OVERLAYS.flatMap((selector) =>
    [...document.querySelectorAll(selector)].map((el) => {
      const style = getComputedStyle(el);
      return {
        selector,
        open: el.classList.contains('open'),
        shown: style.display !== 'none' && style.visibility !== 'hidden',
        rect: el.getBoundingClientRect(),
      };
    }),
  );
  return overlayRects(boxes, origin);
}

/**
 * A name of the first rank (an ocean, a country of the largest class) is never drawn cut by an edge of the canvas, or by a panel drawn over
 * it, when the map is at rest: the names whose box (an estimate, see `textBox`) crosses an edge or the border of a panel are left out by
 * their layer's filter, the others are untouched. The smaller names are left as on any map that is panned. A filter is set only when its
 * list changes.
 */
function leaveOutCut(m: MLMap) {
  const box = m.getContainer();
  const project = (lng: number, lat: number) => m.project([lng, lat]);
  const covers = coveredBy(m);
  if (oceans.length && m.getLayer(OCEANS)) {
    const now = namesAtEdge(oceans, project, box.clientWidth, box.clientHeight, covers);
    if (!same(now, cutOceans)) {
      cutOceans = now;
      m.setFilter(OCEANS, seaFilter(0, cutOceans));
    }
  }
  if (countryRows.length && m.getLayer(LARGEST)) {
    const now = namesAtEdge(countryEdgeNames(countryRows, m.getZoom()), project, box.clientWidth, box.clientHeight, covers);
    if (!same(now, cutCountries)) {
      cutCountries = now;
      m.setFilter(LARGEST, countryFilter(0, [...hidden, ...cutCountries]));
    }
  }
}

/** The properties of a transition that move or resize a panel (the others, a colour above all, change nothing the rule reads). */
const GEOMETRY = new Set(['transform', 'height', 'max-height', 'width', 'top', 'right', 'bottom', 'left']);

/**
 * The panels change without the map moving: a page opens or closes, the Controls and the Legend fold, the sheet takes another snap, the
 * price drawer and the History bar open. The rule runs again one frame after a change of what decides them (the signals; the size of
 * the elements and of the Legend's wrapper, for the Legend, whose fold is its own state, and for a panel that grows with its contents) and when a panel has finished
 * moving (a panel slides in over 280 ms). Nothing runs while nothing changes.
 */
function watchOverlays(m: MLMap) {
  let frame = 0;
  const later = () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      observeNew();
      leaveOutCut(m);
    });
  };
  const resized = new ResizeObserver(later);
  const seen = new Set<Element>();
  // an element that comes later (the Legend is drawn only while something is shown) is picked up at the next run
  const observeNew = () => {
    for (const el of document.querySelectorAll(OVERLAYS_WATCHED.join(','))) {
      if (seen.has(el)) continue;
      seen.add(el);
      resized.observe(el);
    }
  };
  effect(() => {
    void [selection.value, panelCollapsed.value, sheetSnap.value, priceDrawer.value, historyOpen.value, layers.value, choroInfo.value];
    later();
  });
  (m.getContainer().closest('.app') ?? document.body).addEventListener('transitionend', (e) => {
    if (GEOMETRY.has((e as TransitionEvent).propertyName) && (e.target as Element).matches?.(OVERLAYS.join(','))) later();
  });
}

/**
 * The country names, then the overland flows, are put on top of the asset names and under the icons: a country name wins a collision with
 * the name of an asset, and an overland flow is drawn over the names, as every flow is. MapLibre places the top layer first. Idempotent;
 * the order of the layers inside each group is kept.
 */
export function raiseAboveAssetNames(m: MLMap, before: string) {
  moveUnder(m, [...COUNTRY_NAME_LAYERS, ...LAND_FLOW_LAYERS], before);
}

/** While a colouring is on the country names are drawn in the paint of `LABEL_ON_FILL`; switched off, they go back to `LABEL_COLOR`. */
export function colourNamesOnFill(m: MLMap, on: boolean) {
  for (const t of TIERS) {
    const id = `names-countries-${t}`;
    if (!m.getLayer(id)) continue;
    m.setPaintProperty(id, 'text-color', on ? LABEL_ON_FILL.color : LABEL_COLOR.country);
    m.setPaintProperty(id, 'text-opacity', on ? LABEL_ON_FILL.opacity : LABEL_COLOR.countryOpacity);
    m.setPaintProperty(id, 'text-halo-width', on ? LABEL_ON_FILL.haloWidth : LABEL_COLOR.haloWidth);
  }
}

/** Leaves the names of these countries out (the ones that carry a share label while a colouring is on); an empty list brings them back. */
export function hideCountryNames(m: MLMap, ids: readonly string[]) {
  hidden = [...ids];
  for (const t of TIERS) {
    const id = `names-countries-${t}`;
    if (m.getLayer(id)) m.setFilter(id, countryFilter(t, t === 0 ? [...hidden, ...cutCountries] : hidden));
  }
}
