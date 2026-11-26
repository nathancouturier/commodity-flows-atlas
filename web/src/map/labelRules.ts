/**
 * The rules of the lettering on the map, as values and pure functions only (a type import at most, so that a test and
 * the glyph builder run this file as it is). The builder of the glyph file, the tests and the map read the same constants.
 */
import type { ExpressionSpecification, SymbolLayerSpecification } from 'maplibre-gl';
import type { Feature, FeatureCollection, Point } from 'geojson';
import type { InfraType } from '../types';

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
 * First zoom at which each rank of sea names is drawn (Natural Earth's scale rank, 0 the oceans). Rank 0 has none, for the reason
 * given for the largest country names. An Atlas convention.
 */
export const SEA_MINZOOM = [null, 1.8, 3.0, 4.2] as const;

export type SeaRank = 0 | 1 | 2 | 3;

export interface Sea {
  n: string;
  r: number;
  at: [number, number];
}

/** One point per row of the sea table, carrying its name and its rank. */
export function seaPoints(seas: readonly Sea[]): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: seas.map((s): Feature<Point> => ({
      type: 'Feature',
      properties: { n: s.n, r: s.r },
      geometry: { type: 'Point', coordinates: s.at },
    })),
  };
}

/**
 * The four layers of sea names, in the order they are added (rank 3 first, the oceans last). The names are upper case, which the
 * glyph file covers for the ASCII names of the table.
 */
export function seaLayerSpecs(): SymbolLayerSpecification[] {
  return ([3, 2, 1, 0] as const).map((r) => {
    const layer: SymbolLayerSpecification = {
      id: `names-seas-${r}`,
      type: 'symbol',
      source: 'names-seas',
      filter: ['==', ['get', 'r'], r],
      layout: {
        'text-field': ['get', 'n'],
        'text-font': LABEL_FONT,
        'text-transform': 'uppercase',
        'text-letter-spacing': 0.16,
        'text-max-width': 6,
        'text-padding': 3,
        'text-size': r === 0 ? 12 : 10.5,
      },
      paint: {
        'text-color': LABEL_COLOR.sea,
        'text-opacity': LABEL_COLOR.seaOpacity,
        'text-halo-color': LABEL_COLOR.halo,
        'text-halo-width': LABEL_COLOR.haloWidth,
      },
    };
    const minzoom = SEA_MINZOOM[r];
    if (minzoom !== null) layer.minzoom = minzoom;
    return layer;
  });
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

/**
 * Every layer of names in the order they are added. MapLibre places the last layer of the style first: the country layers come
 * after the sea layers so that a country name wins a collision with a sea name, and the oceans, placed last, are the ones dropped.
 */
export function labelLayerSpecs(hiddenIds: readonly string[] = []): SymbolLayerSpecification[] {
  return [...seaLayerSpecs(), ...countryLayerSpecs(hiddenIds)];
}

/**
 * The priority of the point assets for the collision of their names: the lower number is placed first and wins. The atlas has no one
 * measure of size across the types (capacities are in different units), so the order is a convention; inside a type, the assets keep the
 * order of the data files, which MapLibre keeps for equal sort keys. Pipelines are lines and have no name on the map.
 */
export const ASSET_ORDER: Record<Exclude<InfraType, 'pipeline'>, number> = {
  port: 0,
  'lng-export': 1,
  'lng-import': 2,
  refinery: 3,
  smelter: 4,
  mine: 5,
  field: 6,
  storage: 7,
};

/** First zoom at which the names of ports and assets are drawn (the icons are drawn at every zoom). An Atlas convention. */
export const ASSET_LABEL_MINZOOM = 4.2;

const ASSET_TEXT_LAYOUT: NonNullable<SymbolLayerSpecification['layout']> = {
  'text-field': ['get', 'label'],
  'text-font': LABEL_FONT,
  'text-size': 10,
  'text-anchor': 'left',
  'text-offset': [1.3, 0],
  // the icon is never given up for its name
  'text-optional': true,
  'text-max-width': 9,
};

/** The text properties of the opened asset's layer: its name is drawn at every zoom, even over another name. */
export function assetSelectedTextLayout(): NonNullable<SymbolLayerSpecification['layout']> {
  return { ...ASSET_TEXT_LAYOUT, 'text-allow-overlap': true };
}

/** The paint of an asset's name: a dimmed asset (History) keeps its dimming in its name. */
export function assetTextPaint(): NonNullable<SymbolLayerSpecification['paint']> {
  return {
    'text-color': LABEL_COLOR.asset,
    'text-opacity': ['get', 'op'],
    'text-halo-color': LABEL_COLOR.halo,
    'text-halo-width': LABEL_COLOR.haloWidth,
  };
}

/**
 * The layer of the names of ports and assets, read from the features of the icons' source (`label`, `rank`, `op`). It is added
 * under the icon layer, so that an icon always covers a name it overlaps.
 */
export function assetLayerSpec(source: string): SymbolLayerSpecification {
  return {
    id: 'infra-names',
    type: 'symbol',
    source,
    minzoom: ASSET_LABEL_MINZOOM,
    layout: { ...ASSET_TEXT_LAYOUT, 'symbol-sort-key': ['get', 'rank'] },
    paint: assetTextPaint(),
  };
}
