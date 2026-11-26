/**
 * What the particle overlay decides, as pure functions: whether a frame draws, what asks for a new frame under reduced motion, the longitudes
 * a view shows and the phase of the particles. The overlay (`flowOverlay.ts`) only carries them out; a test runs them.
 */

/** Whether the particle overlay redraws this frame: always, unless the system asks for reduced motion, then only when something changed. */
export function shouldDraw(s: { reduced: boolean; dirty: boolean; repaint: boolean }): boolean {
  return !s.reduced || s.dirty || s.repaint;
}

/** What the overlay holds between two frames: `dirty` the screen-space paths are out of date, `repaint` a frame must be drawn although nothing moved. */
export interface Flags {
  dirty: boolean;
  repaint: boolean;
}

/** The overlay as it starts: nothing is projected and nothing has been drawn. */
export const INITIAL_FLAGS: Flags = { dirty: true, repaint: true };

export interface FrameState extends Flags {
  visible: boolean;
  reduced: boolean;
}

/** What one animation frame does: project the paths again, draw, and whether a repaint is still owed afterwards. */
export interface FrameStep {
  project: boolean;
  draw: boolean;
  repaint: boolean;
}

export function frameStep(s: FrameState): FrameStep {
  // a hidden overlay does nothing, and keeps owing the frame it could not draw
  if (!s.visible) return { project: false, draw: false, repaint: s.repaint };
  const draw = shouldDraw(s);
  return { project: s.dirty, draw, repaint: draw ? false : s.repaint };
}

/**
 * The things that happen to the overlay between frames. `move`: the camera moved (the projection is out of date). `resize`: the canvas
 * was resized. `paths`: the paths changed. `shown`: the overlay was made visible again. `tab-shown`: the page came back to the front.
 * `motion-setting`: the system's reduced-motion setting changed. A move or a change of paths is drawn by the next frame whatever the setting.
 */
export type OverlayEvent = 'move' | 'resize' | 'paths' | 'shown' | 'tab-shown' | 'motion-setting';

export function afterEvent(f: Flags, e: OverlayEvent): Flags {
  switch (e) {
    case 'move':
    case 'paths':
      return { dirty: true, repaint: f.repaint };
    case 'resize':
      return { dirty: true, repaint: true };
    case 'shown':
    case 'tab-shown':
    case 'motion-setting':
      return { dirty: f.dirty, repaint: true };
  }
}

/**
 * The longitudes a view shows, with a margin in px all round: the extremes of the four corners of the canvas, unprojected. `unproject` does
 * not wrap the longitudes, so a camera centred beyond +-180 (a selected trans-Pacific lane) gives a range beyond +-180.
 */
export function lngRange(unproject: (x: number, y: number) => number, width: number, height: number, margin: number): { west: number; east: number } {
  const lngs = [[-margin, -margin], [width + margin, -margin], [-margin, height + margin], [width + margin, height + margin]].map(([x, y]) => unproject(x, y));
  return { west: Math.min(...lngs), east: Math.max(...lngs) };
}

/** How far along its path a particle is, in px: nil under reduced motion (the particles stand still), else it moves at `speed` px a second, over `spacing`. */
export function particlePhase(reduced: boolean, seconds: number, speed: number, spacing: number): number {
  return reduced ? 0 : (seconds * speed) % spacing;
}
