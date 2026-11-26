/**
 * Point-in-polygon for the builders of the map's label points (pure, no dependency).
 */

/**
 * Whether (x, y) is inside a ring (even-odd rule, the ring may or may not repeat its first point). The rule is not symmetric at an edge:
 * a point on the left or the bottom edge of a ring counts as inside, on the right or the top edge as outside (a corner follows the two
 * edges it is on), so a point on an edge is no evidence of anything; the rings of a hole are read the same way. `onEdge` tells such a point.
 */
export function inRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Whether a point is inside a GeoJSON Polygon or MultiPolygon (the rings after the first of a polygon are holes). */
export function inGeometry(point, geometry) {
  const [x, y] = point;
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
  return polygons.some(([outer, ...holes]) => inRing(x, y, outer) && !holes.some((h) => inRing(x, y, h)));
}

const round = (v, decimals) => Math.round(v * 10 ** decimals) / 10 ** decimals;

/** The distance, in degrees of the plane, from (x, y) to the segment from (x1, y1) to (x2, y2). */
function distanceToSegment(x, y, [x1, y1], [x2, y2]) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const length2 = dx * dx + dy * dy;
  const t = length2 === 0 ? 0 : Math.max(0, Math.min(1, ((x - x1) * dx + (y - y1) * dy) / length2));
  return Math.hypot(x - (x1 + t * dx), y - (y1 + t * dy));
}

/** Closer than this to a segment (degrees), a point is on the edge. */
export const EDGE_TOLERANCE = 1e-9;

/** Whether a point lies on an edge of a GeoJSON Polygon or MultiPolygon: closer than 1e-9 degree to a segment of any of its rings, holes included. */
export function onEdge(point, geometry) {
  const [x, y] = point;
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
  return polygons.some((rings) =>
    rings.some((ring) => ring.some((at, i) => distanceToSegment(x, y, ring[(i + ring.length - 1) % ring.length], at) < EDGE_TOLERANCE)),
  );
}

/**
 * The point rounded to the fewest decimals (from `from` to `to`) at which it is inside the geometry and not on an edge of it, with that
 * number of decimals; null when no rounding is (a point that is not inside to begin with has none either).
 */
export function roundInside(point, geometry, from = 1, to = 3) {
  for (let d = from; d <= to; d++) {
    const at = point.slice(0, 2).map((v) => round(v, d));
    if (inGeometry(at, geometry) && !onEdge(at, geometry)) return { at, decimals: d };
  }
  return null;
}
