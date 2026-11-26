/**
 * The copies of a path that the screen shows. MapLibre draws the world again on each side, so a path lives at
 * every longitude + k * 360; this gives the k * 360 whose copy has a point between `west` and `east`.
 */
export function copyShifts(coords: readonly (readonly number[])[], west: number, east: number): number[] {
  if (!coords.length) return [];
  let lo = Infinity;
  let hi = -Infinity;
  for (const c of coords) {
    if (c[0] < lo) lo = c[0];
    if (c[0] > hi) hi = c[0];
  }
  const out: number[] = [];
  // `+ 0` turns the -0 that `ceil` gives for a small negative fraction into 0
  for (let k = Math.ceil((west - hi) / 360) + 0; k <= Math.floor((east - lo) / 360); k++) out.push(k * 360);
  return out;
}

/**
 * The copies of a path that the screen shows, as coordinate lists: one for each shift of `copyShifts`, every longitude moved by it and every
 * latitude as it was. None when no copy has a point in view.
 */
export function pathCopies(coords: readonly (readonly number[])[], west: number, east: number): [number, number][][] {
  return copyShifts(coords, west, east).map((shift) => coords.map((c): [number, number] => [c[0] + shift, c[1]]));
}
