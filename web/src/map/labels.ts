/**
 * Country names on the map: symbol layers over the atlas's own glyph files (public/glyphs), added before any module
 * layer so that the lanes, routes and icons are drawn over the names. The layers are not interactive: a click or a
 * hover on a name is a click or a hover on the country under it.
 */
import type { Map as MLMap, GeoJSONSource } from 'maplibre-gl';
import { load } from '../lib/data';
import type { CountryMeta } from '../types';
import { countryFilter, countryLayerSpecs, countryPoints } from './labelRules';

const SOURCE = 'names-countries';
const TIERS = [0, 1, 2, 3] as const;

let hidden: string[] = [];

export function installLabels(m: MLMap) {
  m.addSource(SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  for (const spec of countryLayerSpecs(hidden)) m.addLayer(spec);
  // the rows of the index file, not the signal of the pages: that one holds the European Union as a row of its own
  load<CountryMeta[]>('countries/index.json')
    .then((list) => (m.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(countryPoints(list)))
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
