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
 * The paint of the country names while a colouring is on: they then sit on a coloured fill, where the grey of `LABEL_COLOR.country` is about 1.3 to 1
 * and the dark halo alone kept them legible. A white text and a wider halo read better on the three colourings looked at (crude oil, wheat exports,
 * copper); no contrast of a glyph against a fill is claimed, the legibility is the text against its halo and the halo against the fill.
 */
export const LABEL_ON_FILL = { color: '#ffffff', opacity: 0.95, haloWidth: 2 } as const;

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

/** The size of a country name in px as a function of the zoom: pairs of a zoom and a size, joined linearly, flat outside the first and last. */
export const COUNTRY_SIZE_STOPS = [0.5, 9, 3, 11, 6, 14] as const;

/** The size of a country name at this zoom, read from `COUNTRY_SIZE_STOPS` as the layer's interpolation reads it. */
export function countrySizeAt(zoom: number): number {
  const s = COUNTRY_SIZE_STOPS;
  if (zoom <= s[0]) return s[1];
  for (let i = 2; i < s.length; i += 2) {
    if (zoom <= s[i]) return s[i - 1] + ((zoom - s[i - 2]) / (s[i] - s[i - 2])) * (s[i + 1] - s[i - 1]);
  }
  return s[s.length - 1];
}

/** The width at which a country name wraps, in ems of its size. */
export const COUNTRY_TEXT = { maxWidth: 6 } as const;

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

/** How the sea names are set: the size of the oceans and of the other ranks, the width at which a name wraps, and the spacing, the last two in ems of the size. */
export const SEA_TEXT = { oceanSize: 12, size: 10.5, maxWidth: 6, letterSpacing: 0.16 } as const;

export type SeaRank = 0 | 1 | 2 | 3;

export interface Sea {
  n: string;
  r: number;
  at: [number, number];
}

/** The names of one rank of seas, less the names that are left out (an ocean that the edge of the canvas would cut). */
export function seaFilter(r: number, leftOut: readonly string[] = []): ExpressionSpecification {
  return ['all', ['==', ['get', 'r'], r], ['!', ['in', ['get', 'n'], ['literal', [...leftOut]]]]];
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
export function seaLayerSpecs(oceansLeftOut: readonly string[] = []): SymbolLayerSpecification[] {
  return ([3, 2, 1, 0] as const).map((r) => {
    const layer: SymbolLayerSpecification = {
      id: `names-seas-${r}`,
      type: 'symbol',
      source: 'names-seas',
      filter: seaFilter(r, r === 0 ? oceansLeftOut : []),
      layout: {
        'text-field': ['get', 'n'],
        'text-font': LABEL_FONT,
        'text-transform': 'uppercase',
        'text-letter-spacing': SEA_TEXT.letterSpacing,
        'text-max-width': SEA_TEXT.maxWidth,
        'text-padding': 3,
        'text-size': r === 0 ? SEA_TEXT.oceanSize : SEA_TEXT.size,
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
        'text-max-width': COUNTRY_TEXT.maxWidth,
        'text-padding': 3,
        'text-size': ['interpolate', ['linear'], ['zoom'], ...COUNTRY_SIZE_STOPS],
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
export function labelLayerSpecs(hiddenIds: readonly string[] = [], oceansLeftOut: readonly string[] = []): SymbolLayerSpecification[] {
  return [...seaLayerSpecs(oceansLeftOut), ...countryLayerSpecs(hiddenIds)];
}

/** The four layers of the country names, in the order they are stacked (the smallest class at the bottom: MapLibre places the top layer first). */
export const COUNTRY_NAME_LAYERS = ['names-countries-3', 'names-countries-2', 'names-countries-1', 'names-countries-0'] as const;

/** The four layers of the overland flows (the line set `land`: `ls-land-` and glow, line, alt, hit), in the order the controller adds them. */
export const LAND_FLOW_LAYERS = ['ls-land-glow', 'ls-land-line', 'ls-land-alt', 'ls-land-hit'] as const;

/**
 * What the layers of names are stacked on, bottom to top, among the layers they share the map with (the ids that are in a style are
 * checked, the others skipped). MapLibre places the top layer first, so the lower a layer is the sooner it gives way: the sea names give
 * way to everything, the asset names to the country names, and every name is under the overland flows, the icons, the opened asset and
 * the sea lanes and routes.
 */
export const NAME_STACK = [
  'names-seas-3', 'names-seas-2', 'names-seas-1', 'names-seas-0',
  'infra-lines-glow', 'infra-lines-solid', 'infra-lines-dash', 'infra-lines-hit',
  'infra-names',
  ...COUNTRY_NAME_LAYERS,
  ...LAND_FLOW_LAYERS,
  'infra-pts-all', 'infra-halo', 'infra-pts-sel',
] as const;

/** The layer of the icons: the country names and the overland flows are put under it, on top of the asset names. */
export const ICON_LAYER = 'infra-pts-all';

/** The part of a map's style that the order of the layers needs: a layer's presence and its move. */
export interface LayerOrder {
  getLayer(id: string): unknown;
  moveLayer(id: string, beforeId?: string): void;
}

/**
 * Puts the layers of `ids` that the style holds, in this order, directly under `before` (`moveLayer` puts a layer under the one it is
 * given, so each one lands between the one before it and `before`). Idempotent.
 */
export function moveUnder(m: LayerOrder, ids: readonly string[], before: string): void {
  for (const id of ids) if (m.getLayer(id)) m.moveLayer(id, before);
}

/** The layer the overland flows are added under: the icons when they are there already, else the top of the style (their module then moves them). */
export function landFlowBefore(m: Pick<LayerOrder, 'getLayer'>): string | undefined {
  return m.getLayer(ICON_LAYER) ? ICON_LAYER : undefined;
}

/** The pairs of layers of `NAME_STACK` that a style holds in the wrong order (empty when it follows the stack). */
export function stackViolations(ids: readonly string[]): string[] {
  const at = new Map(ids.map((id, i) => [id, i]));
  const present = NAME_STACK.filter((id) => at.has(id));
  const bad: string[] = [];
  for (let i = 1; i < present.length; i++) if (at.get(present[i - 1])! > at.get(present[i])!) bad.push(`${present[i - 1]} above ${present[i]}`);
  return bad;
}

/** The box of a text on the canvas, centred on its point: width and height in px. */
export interface TextBox {
  w: number;
  h: number;
}

/**
 * The advances the estimate below takes, in ems. A capital 0.72: above the mean of the capitals A to Z (0.69) and of the letters of every
 * ocean name (0.64 to 0.70, name by name), under the widest, W (1.0). A lower-case letter 0.64: above the mean of the letters of the country names (0.52)
 * and of the letters of each of the largest names (0.40 to 0.59). The space is 0.25 in the file, the estimate takes 0.3. The means are read from the
 * advances of the glyph file; a test checks that the estimate is wider than the lettering word by word.
 */
export const CAPITAL_ADVANCE = 0.72;
export const LOWER_ADVANCE = 0.64;
export const SPACE_ADVANCE = 0.3;
/** MapLibre's line height, in ems. */
const LINE_HEIGHT = 1.2;
/** Px added on every side of a box: the halo and the rounding of the estimate. */
export const BOX_MARGIN = 2;

/**
 * An estimate of the box of a name as a layer sets it (wrapped at `maxWidth` ems, spaced by `letterSpacing` ems; the text is given as it is
 * drawn, so a sea name in upper case), on the wide side: every letter is taken at the advance of its case. The lines are counted by a
 * greedy break. The width is the most a line can be: the whole name if it fits `maxWidth`, else `maxWidth`, and never less than the
 * widest word, which keeps its own line as in the library. So a name that the estimate wraps and the library does not is still covered.
 */
export function textBox(text: string, size: number, maxWidth: number, letterSpacing: number): TextBox {
  const em = (word: string) => [...word].reduce((a, ch) => a + (ch === ch.toLowerCase() ? LOWER_ADVANCE : CAPITAL_ADVANCE) + letterSpacing, 0);
  const gap = SPACE_ADVANCE + letterSpacing;
  let lines = 1;
  let line = 0;
  let total = 0;
  let widest = 0;
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const w = em(word);
    widest = Math.max(widest, w);
    total += (total ? gap : 0) + w;
    if (line === 0) line = w;
    else if (line + gap + w <= maxWidth) line += gap + w;
    else {
      line = w;
      lines++;
    }
  }
  return { w: Math.max(widest, Math.min(total, maxWidth)) * size + 2 * BOX_MARGIN, h: lines * LINE_HEIGHT * size + 2 * BOX_MARGIN };
}

/** A rectangle in the canvas's own coordinates (px from its top left corner). */
export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/**
 * Whether a box centred on (x, y) crosses the border of `r`: it overlaps it and is not wholly inside it. A box wholly outside is not
 * touched, and one wholly inside is not seen (a panel hides it, or the canvas shows it), so neither is cut. Touching is not overlapping.
 */
export function boxCrossesRect(x: number, y: number, box: TextBox, r: Rect): boolean {
  const x1 = x - box.w / 2;
  const x2 = x + box.w / 2;
  const y1 = y - box.h / 2;
  const y2 = y + box.h / 2;
  const outside = x2 <= r.left || x1 >= r.right || y2 <= r.top || y1 >= r.bottom;
  const inside = x1 >= r.left && x2 <= r.right && y1 >= r.top && y2 <= r.bottom;
  return !outside && !inside;
}

/** Whether a box centred on (x, y) is partly on the canvas and partly off it: a box wholly inside or wholly outside is not cut. */
export function boxCrossesEdge(x: number, y: number, box: TextBox, canvasW: number, canvasH: number): boolean {
  return boxCrossesRect(x, y, box, { left: 0, top: 0, right: canvasW, bottom: canvasH });
}

/** The copies of the world on each side of the one the point is on, whose names are tested (a canvas shows three at the most at the lowest zoom of a wide screen). */
export const EDGE_COPIES = 3;

/** A name to test against the edge: an id, the point it is drawn at and the box of its text. */
export interface EdgeName {
  id: string;
  at: readonly [number, number];
  box: TextBox;
}

/** The ocean names as `EdgeName`s (the id is the name). */
export function oceanEdgeNames(seas: readonly Sea[]): EdgeName[] {
  return seas
    .filter((s) => s.r === 0)
    .map((s) => ({ id: s.n, at: s.at, box: textBox(s.n.toUpperCase(), SEA_TEXT.oceanSize, SEA_TEXT.maxWidth, SEA_TEXT.letterSpacing) }));
}

/** The names of the largest class of countries as `EdgeName`s at this zoom (the id is the country code). */
export function countryEdgeNames(list: readonly NamedCountry[], zoom: number): EdgeName[] {
  const size = countrySizeAt(zoom);
  return list
    .filter((r) => r.at && r.bb && countryTier(r.bb) === 0)
    .map((r) => ({ id: r.c, at: r.at!, box: textBox(r.name, size, COUNTRY_TEXT.maxWidth, 0) }));
}

/**
 * The ids of the names that the edge of the canvas, or a panel drawn over it (`covers`), would cut, from where the map projects their
 * points: a name is listed when its box crosses the edge or the border of a rectangle on any copy of the world in view. A name wholly in
 * view or wholly out of it, or wholly under a panel, is not listed. Pure: the map is only asked for `project`.
 */
export function namesAtEdge(
  names: readonly EdgeName[],
  project: (lng: number, lat: number) => { x: number; y: number },
  canvasW: number,
  canvasH: number,
  covers: readonly Rect[] = [],
): string[] {
  const out: string[] = [];
  if (canvasW <= 0 || canvasH <= 0) return out;
  for (const n of names) {
    for (let k = -EDGE_COPIES; k <= EDGE_COPIES; k++) {
      const p = project(n.at[0] + 360 * k, n.at[1]);
      if (boxCrossesEdge(p.x, p.y, n.box, canvasW, canvasH) || covers.some((r) => boxCrossesRect(p.x, p.y, n.box, r))) {
        out.push(n.id);
        break;
      }
    }
  }
  return out;
}

/**
 * What is drawn over the map, as the selectors of its elements: the boxes of the top bar (brand, search, tools), the Controls panel or its button, the Legend and its
 * button, the open page (a column, or the sheet), the price drawer and the History bar. The three that are always in the page and hidden when
 * closed (`OVERLAYS_WHEN_OPEN`) count only with the class `open`; the others count when they are displayed.
 */
export const OVERLAYS = ['.topbar > .glass', '.topbar > .search', '.side-panel', '.legend-dock > *', '.detail-panel', '.pd', '.tl'] as const;
export const OVERLAYS_WHEN_OPEN = ['.detail-panel', '.pd', '.tl'] as const;

/**
 * The elements whose size is watched: the overlays, and the wrapper of the Legend, which grows when the legend opens beside its button (the box
 * that comes is not in the page yet when the rule last ran, so its own size cannot be watched).
 */
export const OVERLAYS_WATCHED = [...OVERLAYS, '.legend-dock'] as const;

/** What the rectangles of the overlays are measured from: the element's box and whether it is drawn. */
export interface OverlayBox {
  selector: string;
  open: boolean;
  shown: boolean;
  rect: { left: number; top: number; right: number; bottom: number };
}

/**
 * The rectangles of the overlays that count, in the canvas's own coordinates: those that are drawn, with a box of some size, and, for
 * the elements that are always in the page, open. `origin` is the canvas's top left corner in the same coordinates as the boxes.
 */
export function overlayRects(boxes: readonly OverlayBox[], origin: { left: number; top: number }): Rect[] {
  return boxes
    .filter((b) => b.shown && (b.open || !(OVERLAYS_WHEN_OPEN as readonly string[]).includes(b.selector)) && b.rect.right > b.rect.left && b.rect.bottom > b.rect.top)
    .map((b) => ({ left: b.rect.left - origin.left, top: b.rect.top - origin.top, right: b.rect.right - origin.left, bottom: b.rect.bottom - origin.top }));
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
