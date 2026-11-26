/**
 * Point-in-polygon for the builders of the map's label points (pure, no dependency).
 */

/** Whether (x, y) is inside a ring (even-odd rule, the ring may or may not repeat its first point). */
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

/**
 * The point rounded to the fewest decimals (from `from` to `to`) at which it is still inside the geometry, with that number of
 * decimals; null when no rounding is inside (a point that is not inside to begin with has none either).
 */
export function roundInside(point, geometry, from = 1, to = 3) {
  for (let d = from; d <= to; d++) {
    const at = point.slice(0, 2).map((v) => round(v, d));
    if (inGeometry(at, geometry)) return { at, decimals: d };
  }
  return null;
}
