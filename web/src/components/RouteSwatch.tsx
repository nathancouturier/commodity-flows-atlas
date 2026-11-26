/** A short line drawn as a freight route of the vessel segment is on the map: its colour and its dash pattern. */
import { ROUTE_DASH, SEGMENT_COLOR } from '../lib/palette';
import type { Segment } from '../types';

/**
 * A pattern is in multiples of the line width, so the dashes are the pattern times the stroke width in px: what the map
 * draws at that width. `px` is the stroke width, `length` the length of the line; the butt caps are those of the map's.
 */
export function RouteSwatch({ segment, px = 2, length = 34 }: { segment: Segment; px?: number; length?: number }) {
  const dash = ROUTE_DASH[segment].map((n) => +(n * px).toFixed(2)).join(' ');
  const h = Math.ceil(px) + 2;
  return (
    <svg class="route-swatch" width={length} height={h} viewBox={`0 0 ${length} ${h}`} aria-hidden="true">
      <path d={`M0 ${h / 2} H${length}`} stroke={SEGMENT_COLOR[segment]} stroke-width={px} stroke-dasharray={dash} stroke-linecap="butt" fill="none" />
    </svg>
  );
}
