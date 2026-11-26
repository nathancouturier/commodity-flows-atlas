/**
 * The rules of the lettering on the map, as values and pure functions only (a type import at most, so that a test and
 * the glyph builder run this file as it is). The builder of the glyph file, the tests and the map read the same constants.
 */
import type { ExpressionSpecification, SymbolLayerSpecification } from 'maplibre-gl';
import type { Feature, FeatureCollection, Point } from 'geojson';

/** The font stack of the glyph file: the folder `web/public/glyphs/<stack>/`, named without a space so that no URL holds one. */
export const GLYPH_STACK = 'inter-medium';

/** The range of the glyph file: characters U+0000 to U+00FF (ASCII and Latin-1). */
export const GLYPH_RANGE = '0-255';

/** The `text-font` of every name layer. */
export const LABEL_FONT: string[] = [GLYPH_STACK];

/**
 * The name of a port or an asset as it is written on the map: without the list of places in brackets that ends some
 * names ("Stabroek Block (Liza, Payara, Yellowtail)" is "Stabroek Block"). Idempotent.
 */
export function assetLabel(name: string): string {
  return name.replace(/\s*\(.*\)\s*$/, '').trim();
}

/** The colours of the names. Text is drawn at its opacity over the layer it sits on; the contrast of each is tested from these values. */
export const LABEL_COLOR = {
  /** country names, over the land colour */
  country: '#9fb2c8',
  countryOpacity: 0.75,
  /** sea names, over the ocean colour */
  sea: '#6f9bc7',
  seaOpacity: 0.9,
  /** asset names, over the land colour */
  asset: '#c8d4e2',
  /** the halo of every name: the ocean colour of the base map */
  halo: '#05090f',
  haloWidth: 1.2,
} as const;

/**
 * Size class of a country's name from the area of its box in square degrees: 0 the largest names, 3 the smallest.
 * An Atlas convention, chosen to show the largest countries at the world view; not an area of land.
 */
export const COUNTRY_TIERS = [300, 40, 6] as const;

/**
 * First zoom at which each class of country names is drawn. Class 0 has none: a layer's `minzoom` cannot be below 0 and the first view
 * of a phone is below it; the size stops of the text clamp below their first stop.
 */
export const COUNTRY_MINZOOM = [null, 2.0, 3.2, 4.4] as const;

export type CountryTier = 0 | 1 | 2 | 3;

const boxArea = (bb: [number, number, number, number]) => (bb[2] - bb[0]) * (bb[3] - bb[1]);

export function countryTier(bb: [number, number, number, number]): CountryTier {
  const a = boxArea(bb);
  return a > COUNTRY_TIERS[0] ? 0 : a > COUNTRY_TIERS[1] ? 1 : a > COUNTRY_TIERS[2] ? 2 : 3;
}

interface NamedCountry {
  c: string;
  name: string;
  at?: [number, number];
  bb?: [number, number, number, number];
}

/** One point per row of the country index, carrying its name, its size class, the area of its box and its code. A row with no anchor or no box has no name. */
export function countryPoints(list: readonly NamedCountry[]): FeatureCollection<Point> {
  const features: Feature<Point>[] = [];
  for (const r of list) {
    if (!r.at || !r.bb) continue;
    features.push({
      type: 'Feature',
      properties: { n: r.name, t: countryTier(r.bb), a: boxArea(r.bb), c: r.c },
      geometry: { type: 'Point', coordinates: r.at },
    });
  }
  return { type: 'FeatureCollection', features };
}

/** The names of one size class, less the countries whose name is left out (the ones that carry a share label). */
export function countryFilter(t: number, hiddenIds: readonly string[]): ExpressionSpecification {
  return ['all', ['==', ['get', 't'], t], ['!', ['in', ['get', 'c'], ['literal', [...hiddenIds]]]]];
}

/**
 * The four layers of country names, in the order they are added: MapLibre places the last layer of the style first, so
 * the largest names win a collision with the smaller ones; inside a layer the larger box goes first.
 */
export function countryLayerSpecs(hiddenIds: readonly string[] = []): SymbolLayerSpecification[] {
  return ([3, 2, 1, 0] as const).map((t) => {
    const layer: SymbolLayerSpecification = {
      id: `names-countries-${t}`,
      type: 'symbol',
      source: 'names-countries',
      filter: countryFilter(t, hiddenIds),
      layout: {
        'text-field': ['get', 'n'],
        'text-font': LABEL_FONT,
        'text-max-width': 6,
        'text-padding': 3,
        'text-size': ['interpolate', ['linear'], ['zoom'], 0.5, 9, 3, 11, 6, 14],
        'symbol-sort-key': ['-', 0, ['get', 'a']],
      },
      paint: {
        'text-color': LABEL_COLOR.country,
        'text-opacity': LABEL_COLOR.countryOpacity,
        'text-halo-color': LABEL_COLOR.halo,
        'text-halo-width': LABEL_COLOR.haloWidth,
      },
    };
    const minzoom = COUNTRY_MINZOOM[t];
    if (minzoom !== null) layer.minzoom = minzoom;
    return layer;
  });
}
