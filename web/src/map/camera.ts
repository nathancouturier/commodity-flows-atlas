/**
 * The first view and the limits of the camera, as numbers only (no import of the map library, so that a test runs
 * this file as it is). The map is Mercator, a 512 px world at zoom 0.
 */

/** Bounds of the trading world framed on first load (Americas to Japan): west, south, east, north. */
export const WORLD_BOUNDS: [[number, number], [number, number]] = [[-125, -45], [150, 65]];

/** The map's highest zoom. */
export const MAX_ZOOM = 9;

/** The zoom from which the scale bar is shown: below it one length per pixel is right on no more than a thin band of the view (METHODOLOGY, "The map: first view, names and scale"). */
export const SCALE_MIN_ZOOM = 4;

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

/** The size of the canvas the camera works on, in pixels. */
export interface Size {
  w: number;
  h: number;
}

/** The canvas is the map's container, which a screen's panels overlay, so the whole screen counts; the window stands in while the container has no size yet. */
export function canvasSizeOf(box: { clientWidth: number; clientHeight: number }, win: { innerWidth: number; innerHeight: number }): Size {
  return { w: box.clientWidth || win.innerWidth, h: box.clientHeight || win.innerHeight };
}

/**
 * The three things the map controller asks of the camera limits, each read from the canvas as it is when asked (a
 * phone turned on its side, a window made narrower): the floor given to the map as its `minZoom` and again on every
 * resize, and the constraint given as `transformConstrain`.
 */
export function cameraLimits(size: () => Size) {
  return {
    minZoom: (): number => {
      const { w, h } = size();
      return minZoomFor(w, h);
    },
    constrain: (lng: number, lat: number, zoom: number) => {
      const { w, h } = size();
      return constrainCamera(lng, lat, zoom, w, h);
    },
  };
}

/** A padding that was left on the camera: the next fit would add its own to it, and the box could stop fitting. */
export function hasPadding(p: { top?: number; bottom?: number; left?: number; right?: number }): boolean {
  return Boolean(p.top || p.bottom || p.left || p.right);
}

/** The padding that the flight to a passage keeps it clear of the open page with (a window of 760 px or more: the side panel and the page; a narrower one: the sheet). */
export function passagePadding(innerWidth: number, innerHeight: number): { top: number; bottom: number; left: number; right: number } {
  return innerWidth >= 760 ? { top: 60, bottom: 40, left: 340, right: 420 } : { top: 80, bottom: innerHeight * 0.5, left: 10, right: 10 };
}

/**
 * The centre to give the camera at `zoom` so that the place `at` stands where the middle of the free area of `pad`
 * is, without leaving a padding on the camera: the middle of the free area is `[(left - right) / 2, (top - bottom) / 2]`
 * from the middle of the canvas, and the centre is the place moved back by that many pixels.
 */
export function centerForPadding(at: [number, number], zoom: number, pad: { top: number; bottom: number; left: number; right: number }): [number, number] {
  const world = TILE * 2 ** zoom;
  const x = ((at[0] + 180) / 360) * world - (pad.left - pad.right) / 2;
  const y = mercY(at[1]) * world - (pad.top - pad.bottom) / 2;
  return [(x / world) * 360 - 180, latFromY(y / world)];
}

/**
 * Whether the camera is still where the atlas put it. A fit of the first view (the first load, a "Reset view", the
 * world shown again when a page closes) makes it so; any other move (a drag, a wheel, a pinch, the zoom buttons, a page
 * that flies somewhere) ends it; the move that the library fires for a resize does not count, because the canvas has
 * a new size when it fires (a move that comes with a new size is taken for a resize). Only while it holds does a resize
 * fit the first view again. Kept in memory only.
 */
export function firstViewState(size: () => Size) {
  let atFirstView = false;
  let seen = size();
  return {
    get atFirstView() {
      return atFirstView;
    },
    /** Runs the call that fits the first view: the move it fires (at once, whatever its duration) is not the visitor's. */
    fit<T>(run: () => T): T {
      try {
        return run();
      } finally {
        atFirstView = true;
        seen = size();
      }
    },
    /** The map's `movestart`. */
    moveStart() {
      const now = size();
      const resized = now.w !== seen.w || now.h !== seen.h;
      seen = now;
      if (!resized) atFirstView = false;
    },
    /** The map's `resize`: true when the first view is to be fitted again. */
    resize(): boolean {
      seen = size();
      return atFirstView;
    },
  };
}
