/**
 * Tests of the copies of a path that a view shows (src/map/copies.ts), over the real lane files:
 * `node --test web/scripts/world-copies.test.mjs`. The module is pure, so it runs as it is.
 *
 * MapLibre draws the world again on each side; a lane that crosses the antimeridian continues past 180 degrees and
 * is seen on the copy it was drawn for and on the next one. The flow overlay draws its particles on every copy the
 * view shows, so the shifts must be exactly the copies whose longitudes meet the view.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { copyShifts, pathCopies } from '../src/map/copies.ts';
import { WORLD_BOUNDS, fitZoomFor } from '../src/map/camera.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const lanesDir = path.join(here, '../../data/freight/lanes');
const routesFile = path.join(here, '../../data/freight/routes.geo.json');

const lanes = fs
  .readdirSync(lanesDir)
  .filter((f) => f.endsWith('.json'))
  .flatMap((f) => JSON.parse(fs.readFileSync(path.join(lanesDir, f), 'utf8')).lanes.map((l) => ({ id: l.id, set: l.set, g: l.g })));
const box = (g) => ({ lo: Math.min(...g.map((c) => c[0])), hi: Math.max(...g.map((c) => c[0])) });
const beyond = (g) => g.some((c) => c[0] > 180 || c[0] < -180);

// the copies a view meets, found by trying every k that could matter
const brute = (g, west, east) => {
  const { lo, hi } = box(g);
  const out = [];
  for (let k = -3; k <= 3; k++) if (lo + 360 * k <= east && hi + 360 * k >= west) out.push(360 * k);
  return out;
};

test('the lane files are read', () => {
  assert.ok(lanes.length > 3000, `${lanes.length} lanes`);
  assert.ok(lanes.every((l) => l.g.length >= 2));
});

test('the shifts are the copies whose longitudes meet the view, for every lane and every view of one turn', () => {
  let checked = 0;
  for (const l of lanes) {
    for (let c = -360; c <= 360; c += 30) {
      assert.deepEqual(copyShifts(l.g, c - 180, c + 180), brute(l.g, c - 180, c + 180), `${l.id} view centred on ${c}`);
      checked++;
    }
  }
  assert.ok(checked > 100000);
});

test('the shifts are right for views wider than a turn (the lowest zoom of a desktop) and narrower', () => {
  for (const l of lanes) {
    for (const [w, e] of [[-289, 289], [-100, 100], [-20, 20], [150, 190], [-190, -150]]) {
      assert.deepEqual(copyShifts(l.g, w, e), brute(l.g, w, e), `${l.id} [${w}, ${e}]`);
    }
  }
});

test('a view one turn less than the width of the lane shows at most one copy of it', () => {
  for (const l of lanes) {
    const { lo, hi } = box(l.g);
    const span = 360 - (hi - lo) - 1e-6;
    for (let c = -360; c <= 360; c += 30) {
      const n = copyShifts(l.g, c - span / 2, c + span / 2).length;
      assert.ok(n <= 1, `${l.id} view centred on ${c} got ${n}`);
    }
  }
});

test('a path with nothing in view has no copy, and a path wider than the view meets one or two', () => {
  assert.deepEqual(copyShifts([[10, 0], [20, 5]], 100, 200), []);
  assert.deepEqual(copyShifts([[10, 0], [20, 5]], 360, 400), [360]);
  assert.deepEqual(copyShifts([[170, 0], [200, 5]], -190, 190), [-360, 0]);
});

test('the copies of a path are its coordinates moved by each shift, latitudes as they were, and the path itself is not changed', () => {
  const path_ = [[170, -10], [185, 0], [200, 12.5]];
  const before = JSON.stringify(path_);
  // a view of one turn centred on the antimeridian meets the path on the copy it was drawn for and on the one before it
  assert.deepEqual(copyShifts(path_, -190, 190), [-360, 0]);
  assert.deepEqual(pathCopies(path_, -190, 190), [
    [[-190, -10], [-175, 0], [-160, 12.5]],
    [[170, -10], [185, 0], [200, 12.5]],
  ]);
  assert.equal(JSON.stringify(path_), before, 'the made-up path is left as it was');
  // one copy when only one is in view, none when none is
  assert.deepEqual(pathCopies([[10, 1], [20, 2]], 360, 400), [[[370, 1], [380, 2]]]);
  assert.deepEqual(pathCopies([[10, 1], [20, 2]], 100, 200), []);
  assert.deepEqual(pathCopies([], -180, 180), []);
  // a path a view meets on two copies gives two lists of the same length, as many points as the path has, the second moved 360 degrees from the first
  const two = pathCopies([[-175, 5], [175, 6], [179, 7]], -180, 300);
  assert.equal(two.length, 2);
  assert.deepEqual(two.map((c) => c.length), [3, 3]);
  assert.deepEqual(two[1].map(([x, y]) => [x - 360, y]), two[0].map(([x, y]) => [x, y]));
  // the shift list and the copies agree for every lane of the files and a view of one turn
  for (const l of lanes.slice(0, 400)) {
    const shifts = copyShifts(l.g, -180, 180);
    const copies = pathCopies(l.g, -180, 180);
    assert.equal(copies.length, shifts.length, l.id);
    copies.forEach((c, k) => assert.deepEqual(c, l.g.map(([x, y]) => [x + shifts[k], y]), l.id));
  }
});

test('the lanes that continue past 180 degrees are counted, and those that get two copies at the first view', () => {
  const main = lanes.filter((l) => l.set === 'main');
  const cross = main.filter((l) => beyond(l.g));
  assert.ok(cross.length > 100, `${cross.length} main lanes cross`);
  const routes = JSON.parse(fs.readFileSync(routesFile, 'utf8')).features;
  const routesCross = routes.filter((f) => beyond(f.geometry.coordinates));

  // the first view of a 1440 x 900 screen: the box of the trading world fitted in the area the panels leave
  // (the side panel's right edge measured at 286 px, plus 24; the right margin 24, top 70, bottom 40)
  const W = 1440;
  const pad = { top: 70, bottom: 40, left: 310, right: 24 };
  const z = Math.min(2.4, fitZoomFor(W, 900, pad, WORLD_BOUNDS));
  const degPerPx = 360 / (512 * 2 ** z);
  const centre = (WORLD_BOUNDS[0][0] + WORLD_BOUNDS[1][0]) / 2;
  const x0 = pad.left + (W - pad.left - pad.right) / 2;
  const west = centre - x0 * degPerPx;
  const east = centre + (W - x0) * degPerPx;
  const two = cross.filter((l) => copyShifts(l.g, west, east).length === 2);
  const twoAll = main.filter((l) => copyShifts(l.g, west, east).length >= 2);
  console.log(
    `main lanes ${main.length}, with a vertex beyond 180: ${cross.length}; routes ${routes.length}, beyond 180: ${routesCross.length}; ` +
      `first view of 1440 x 900 at zoom ${z.toFixed(4)}, longitudes ${west.toFixed(1)} to ${east.toFixed(1)}: ` +
      `${two.length} of the crossing lanes get two copies, ${twoAll.length} main lanes get two or more`,
  );
  assert.ok(two.length <= cross.length);
  assert.ok(Number.isFinite(west) && east - west > 300 && east - west < 400);
});
