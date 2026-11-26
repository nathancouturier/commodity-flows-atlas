/**
 * Country and sea names on the map: symbol layers over the atlas's own glyph files (public/glyphs), added before any module
 * layer so that the lanes, routes and icons are drawn over the names; the module of the icons then raises the country
 * names above the asset names (`raiseCountryNames`). The layers are not interactive: a click or a hover on a name is a
 * click or a hover on the country under it.
 */
import type { Map as MLMap, GeoJSONSource } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { load } from '../lib/data';
import type { CountryMeta } from '../types';
import { ICON_LAYER, LABEL_COLOR, LABEL_ON_FILL, countryEdgeNames, countryFilter, countryPoints, labelLayerSpecs, namesAtEdge, oceanEdgeNames, seaFilter, seaPoints } from './labelRules';
import type { EdgeName, Sea } from './labelRules';

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
  if (m.getLayer(ICON_LAYER)) raiseCountryNames(m, ICON_LAYER);
  // the oceans are the largest names and the ones the edge of a phone cuts: tested when the camera comes to rest, never during a move
  m.on('moveend', () => leaveOutCut(m));
  m.on('resize', () => leaveOutCut(m));
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

/**
 * A name of the first rank (an ocean, a country of the largest class) is never drawn cut by an edge of the canvas when the map is at rest:
 * the names whose box (an estimate, see `textBox`) crosses an edge are left out by their layer's filter, the others are untouched. The
 * smaller names are left as on any map that is panned. A filter is set only when its list changes.
 */
function leaveOutCut(m: MLMap) {
  const box = m.getContainer();
  const project = (lng: number, lat: number) => m.project([lng, lat]);
  if (oceans.length && m.getLayer(OCEANS)) {
    const now = namesAtEdge(oceans, project, box.clientWidth, box.clientHeight);
    if (!same(now, cutOceans)) {
      cutOceans = now;
      m.setFilter(OCEANS, seaFilter(0, cutOceans));
    }
  }
  if (countryRows.length && m.getLayer(LARGEST)) {
    const now = namesAtEdge(countryEdgeNames(countryRows, m.getZoom()), project, box.clientWidth, box.clientHeight);
    if (!same(now, cutCountries)) {
      cutCountries = now;
      m.setFilter(LARGEST, countryFilter(0, [...hidden, ...cutCountries]));
    }
  }
}

/**
 * The country names are put on top of the asset names and under the icons: a country name wins a collision with the name of an asset.
 * MapLibre places the top layer first. Idempotent; the order of the four layers is kept.
 */
export function raiseCountryNames(m: MLMap, before: string) {
  for (const t of [...TIERS].reverse()) {
    const id = `names-countries-${t}`;
    if (m.getLayer(id)) m.moveLayer(id, before);
  }
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
