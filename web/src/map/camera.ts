/**
 * The first view and the limits of the camera, as numbers only (no import of the map library, so that a test runs
 * this file as it is). The map is Mercator, a 512 px world at zoom 0.
 */

/** Bounds of the trading world framed on first load (Americas to Japan): west, south, east, north. */
export const WORLD_BOUNDS: [[number, number], [number, number]] = [[-125, -45], [150, 65]];

/** The map's highest zoom. */
export const MAX_ZOOM = 9;

/** The latitude the library cuts the Mercator world at (`MAX_VALID_LATITUDE` of maplibre-gl); a test compares it with the installed library. */
export const MAX_LATITUDE = 85.051129;

const TILE = 512;
const rad = Math.PI / 180;

/** Fraction of the world height, from the top, at which a latitude lies. */
const mercY = (lat: number) => 0.5 - Math.log(Math.tan(Math.PI / 4 + (lat * rad) / 2)) / (2 * Math.PI);
const latFromY = (y: number) => (2 * Math.atan(Math.exp((0.5 - y) * 2 * Math.PI)) - Math.PI / 2) / rad;

/**
 * The lowest zoom allowed on a canvas of w x h pixels. The first term is the floor a desktop has always had: the
 * option `minZoom: 0.5` and the library's pole constraint, which stops the world from being shorter than the canvas.
 * The second term lets the whole frame fit a narrow canvas (a phone), where the first would keep the world wider
 * than the screen.
 */
export function minZoomFor(w: number, h: number): number {
  return Math.min(Math.max(0.5, Math.log2(h / TILE)), Math.log2(w / TILE) - 0.1);
}

/** The zoom at which `bounds` fits a w x h canvas once the padding is taken off (before any maximum zoom). */
export function fitZoomFor(
  w: number,
  h: number,
  pad: { top: number; bottom: number; left: number; right: number },
  bounds: [[number, number], [number, number]] = WORLD_BOUNDS,
): number {
  const [[west, south], [east, north]] = bounds;
  const boxW = ((east - west) / 360) * TILE;
  const boxH = (mercY(south) - mercY(north)) * TILE;
  return Math.min(Math.log2((w - pad.left - pad.right) / boxW), Math.log2((h - pad.top - pad.bottom) / boxH));
}

/**
 * The camera the map is allowed to have (the library's `transformConstrain`): the zoom between the floor of the
 * canvas and the highest zoom, the latitude within the Mercator world, and, while the world is at least as tall as
 * the canvas, the centre kept so that the poles never enter the canvas, as the library's own constraint does. When
 * the world is shorter (a narrow canvas at the lowest zooms) the whole world is on show and the centre stays where it
 * is. The longitude is never clamped: the world is drawn again on each side.
 */
export function constrainCamera(lng: number, lat: number, zoom: number, w: number, h: number): { lng: number; lat: number; zoom: number } {
  const z = Math.max(minZoomFor(w, h), Math.min(MAX_ZOOM, zoom));
  let la = Math.max(-MAX_LATITUDE, Math.min(MAX_LATITUDE, lat));
  const world = TILE * 2 ** z;
  if (world >= h) {
    const y = Math.max(h / 2, Math.min(world - h / 2, mercY(la) * world));
    la = latFromY(y / world);
  }
  return { lng, lat: la, zoom: z };
}
