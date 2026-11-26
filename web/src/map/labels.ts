/**
 * Country and sea names on the map: symbol layers over the atlas's own glyph files (public/glyphs), added before any module
 * layer so that the lanes, routes and icons are drawn over the names. The layers are not interactive: a click or a
 * hover on a name is a click or a hover on the country under it.
 */
import type { Map as MLMap, GeoJSONSource } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { load } from '../lib/data';
import type { CountryMeta } from '../types';
import { countryFilter, countryPoints, labelLayerSpecs, seaPoints } from './labelRules';
import type { Sea } from './labelRules';

const SOURCE = 'names-countries';
const SEA_SOURCE = 'names-seas';
const TIERS = [0, 1, 2, 3] as const;

let hidden: string[] = [];

const empty = (): FeatureCollection => ({ type: 'FeatureCollection', features: [] });

export function installLabels(m: MLMap) {
  m.addSource(SOURCE, { type: 'geojson', data: empty() });
  m.addSource(SEA_SOURCE, { type: 'geojson', data: empty() });
  for (const spec of labelLayerSpecs(hidden)) m.addLayer(spec);
  // the rows of the index file, not the signal of the pages: that one holds the European Union as a row of its own
  load<CountryMeta[]>('countries/index.json')
    .then((list) => (m.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(countryPoints(list)))
    .catch(() => undefined);
  // a missing file leaves the seas without names and the countries with theirs
  load<{ seas: Sea[] }>('geo/seas.json')
    .then((d) => (m.getSource(SEA_SOURCE) as GeoJSONSource | undefined)?.setData(seaPoints(d.seas)))
    .catch(() => undefined);
}

/** Leaves the names of these countries out (the ones that carry a share label while a colouring is on); an empty list brings them back. */
export function hideCountryNames(m: MLMap, ids: readonly string[]) {
  hidden = [...ids];
  for (const t of TIERS) {
    const id = `names-countries-${t}`;
    if (m.getLayer(id)) m.setFilter(id, countryFilter(t, hidden));
  }
}
