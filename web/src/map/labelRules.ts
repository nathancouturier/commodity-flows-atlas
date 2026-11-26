/**
 * The rules of the lettering on the map, as values and pure functions only (a type import at most, so that a test and
 * the glyph builder run this file as it is). The builder of the glyph file, the tests and the map read the same constants.
 */

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
