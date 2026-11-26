/**
 * Colour-vision helpers of the colour screens test (scripts/colour-screens.test.mjs). Pure, no import, no dependency.
 *
 * Three things are written here and nowhere else: the matrices that simulate a dichromacy, the thresholds the atlas
 * holds its colours to, and the conversions that turn a hex colour into a distance or a contrast ratio. The conversions
 * are written from their definitions (sRGB transfer function, OKLab, WCAG 2.x relative luminance).
 */

/**
 * Machado, Oliveira & Fernandes (2009) CVD transforms at severity 1.0 (linear RGB), as read in the validator of the
 * `dataviz` skill on 26 November 2026. Each matrix takes a linear sRGB vector to the vector a dichromat sees. They were copied from
 * that file by a script; scripts/colour-screens.test.mjs checks that each row sums to 1, so a hand edit shows.
 */
export const MATRICES = {
  protan: [
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281, 0.099216],
    [-0.003882, -0.048116, 1.051998],
  ],
  deutan: [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.01182, 0.04294, 0.968881],
  ],
  tritan: [
    [1.255528, -0.076749, -0.178779],
    [-0.078411, 0.930809, 0.147602],
    [0.004733, 0.691367, 0.3039],
  ],
};

/**
 * The thresholds the atlas holds its colours to. They are the constants of that validator, which the atlas takes as its own
 * rule; they are not a standard. The distances are OKLab distances times 100, the contrast is WCAG 2.x against a surface.
 *  - NORMAL_FLOOR: two colours of one screen are at least this far apart for unsimulated vision;
 *  - CVD_TARGET: and at least this far apart under each of the three simulations;
 *  - CVD_FLOOR: a pair between this and CVD_TARGET is acceptable only with a second cue that does not rest on colour;
 *  - CONTRAST_MIN: a data colour against the map's ocean and land.
 */
export const NORMAL_FLOOR = 15.0;
export const CVD_TARGET = 8.0;
export const CVD_FLOOR = 6.0;
export const CONTRAST_MIN = 3.0;

/**
 * Simulates a dichromacy on a colour given as `#rrggbb`: the matrix times the linear sRGB vector, each channel clamped to 0..1.
 * It returns a linear sRGB vector.
 */
export function simulate(hex, kind) {
  const m = MATRICES[kind];
  if (!m) throw new Error(`no such simulation: ${kind}`);
  const v = hexToLinear(hex);
  return m.map((row) => clamp01(row[0] * v[0] + row[1] * v[1] + row[2] * v[2]));
}

/** `#rrggbb` to a linear sRGB vector (each channel 0..1). */
export function hexToLinear(hex) {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) throw new Error(`not a #rrggbb colour: ${hex}`);
  return [m[1], m[2], m[3]].map((h) => srgbToLinear(parseInt(h, 16) / 255));
}

function srgbToLinear(c) {
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function clamp01(x) {
  return Math.min(1, Math.max(0, x));
}

/** A linear sRGB vector to OKLab [L, a, b]. */
export function linearToOklab([r, g, b]) {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

/**
 * The distance between two colours, 100 times the Euclidean distance in OKLab. With `kind` (protan, deutan or tritan) both
 * colours are simulated first; without it the colours are taken as they are.
 */
export function deltaE(a, b, kind) {
  const lab = (hex) => linearToOklab(kind ? simulate(hex, kind) : hexToLinear(hex));
  const [A, B] = [lab(a), lab(b)];
  return 100 * Math.hypot(A[0] - B[0], A[1] - B[1], A[2] - B[2]);
}

/** WCAG 2.x relative luminance of a `#rrggbb` colour. */
export function luminance(hex) {
  const [r, g, b] = hexToLinear(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2.x contrast ratio of two colours (1 to 21), whichever is lighter. */
export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
