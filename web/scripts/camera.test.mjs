/**
 * Tests of the first view and the camera limits (src/map/camera.ts) and of the way the map controller uses them:
 * `node --test web/scripts/camera.test.mjs`. The module is pure, so it runs as it is.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WORLD_BOUNDS, MAX_ZOOM, MAX_LATITUDE, minZoomFor, fitZoomFor, constrainCamera } from '../src/map/camera.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const controller = fs.readFileSync(path.join(here, '../src/map/controller.ts'), 'utf8');

// the floor a desktop has always had: the option `minZoom: 0.5` and the library's pole constraint
const desktopFloor = (w, h) => Math.max(0.5, Math.log2(h / 512));
const DESKTOPS = [[1440, 900], [1920, 1080], [1280, 720], [1024, 768]];

test('on a desktop the floor is the one it has always been', () => {
  for (const [w, h] of DESKTOPS) assert.equal(minZoomFor(w, h), desktopFloor(w, h), `${w}x${h}`);
});

test('the floor is never above the desktop floor', () => {
  for (let w = 280; w <= 2560; w += 20) for (let h = 280; h <= 1600; h += 20) assert.ok(minZoomFor(w, h) <= desktopFloor(w, h), `${w}x${h}`);
});

// Portrait sizes only. A landscape or square phone is outside: the band the panels leave is too short for the box
// (a phone held sideways stays cut), and the floor does not claim otherwise.
test('the frame fits every portrait screen with the phone sheet padding', () => {
  let n = 0;
  for (let w = 320; w <= 1024; w += 1) {
    for (let h = 568; h <= 1366; h += 10) {
      if (h < 1.3 * w) continue;
      const pad = { top: 64, bottom: 0.55 * h, left: 16, right: 16 };
      assert.ok(minZoomFor(w, h) <= fitZoomFor(w, h, pad), `${w}x${h}: floor ${minZoomFor(w, h)} above fit ${fitZoomFor(w, h, pad)}`);
      n++;
    }
  }
  assert.ok(n > 1000);
});

test('fitZoomFor: the box has the width it should at the zoom it returns', () => {
  const z = fitZoomFor(1000, 10000, { top: 0, bottom: 0, left: 0, right: 0 });
  const [[west], [east]] = [WORLD_BOUNDS[0], WORLD_BOUNDS[1]];
  assert.ok(Math.abs(((east - west) / 360) * 512 * 2 ** z - 1000) < 1e-6);
});

// the centre latitude at which the top (or bottom) edge of an h pixel tall canvas is at the pole of the Mercator world
const latAtWorldY = (y, world) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / world))) * 180) / Math.PI;

test('constrainCamera keeps the poles out of the canvas while the world is as tall as the canvas', () => {
  const [w, h, zoom] = [1440, 900, 3];
  const world = 512 * 2 ** zoom;
  const north = constrainCamera(10, 89, zoom, w, h);
  const south = constrainCamera(10, -89, zoom, w, h);
  assert.ok(Math.abs(north.lat - latAtWorldY(h / 2, world)) < 1e-9, `north ${north.lat}`);
  assert.ok(Math.abs(south.lat - latAtWorldY(world - h / 2, world)) < 1e-9, `south ${south.lat}`);
  assert.ok(north.lat < MAX_LATITUDE && south.lat > -MAX_LATITUDE);
  assert.equal(north.lng, 10);
  assert.equal(north.zoom, zoom);
  // a centre that is already inside is left alone
  assert.ok(Math.abs(constrainCamera(10, 20, zoom, w, h).lat - 20) < 1e-9);
});

test('constrainCamera leaves the centre where it is while the world is shorter than the canvas', () => {
  const r = constrainCamera(5, 40, -0.2, 390, 844);
  assert.ok(Math.abs(r.lat - 40) < 1e-12);
  assert.equal(r.zoom, -0.2);
});

test('constrainCamera clamps the zoom to the floor and the maximum zoom, and never the longitude', () => {
  assert.equal(constrainCamera(0, 0, 12, 1440, 900).zoom, MAX_ZOOM);
  assert.equal(constrainCamera(0, 0, -5, 1440, 900).zoom, minZoomFor(1440, 900));
  assert.equal(constrainCamera(0, 0, -5, 390, 844).zoom, minZoomFor(390, 844));
  assert.equal(constrainCamera(-400, 0, 3, 1440, 900).lng, -400);
});

test('the latitude limit is the library\'s own', () => {
  const lib = path.join(here, '../node_modules/maplibre-gl/dist/maplibre-gl-dev.js');
  const m = /const MAX_VALID_LATITUDE = ([0-9.]+);/.exec(fs.readFileSync(lib, 'utf8'));
  assert.ok(m, 'MAX_VALID_LATITUDE not found in the library');
  assert.equal(MAX_LATITUDE, Number(m[1]));
});

test('the controller imports WORLD_BOUNDS from the module and declares none', () => {
  assert.match(controller, /import \{[^}]*\bWORLD_BOUNDS\b[^}]*\} from '\.\/camera'/);
  assert.doesNotMatch(controller, /(const|let|var)\s+WORLD_BOUNDS\b/);
});

test('the controller passes transformConstrain to the map', () => {
  assert.match(controller, /\btransformConstrain:/);
});

test('the controller moves the floor when the canvas is resized', () => {
  assert.match(controller, /map\.on\('resize',[\s\S]{0,200}setMinZoom\(/);
});

test('the controller adds the Reset view control', () => {
  assert.match(controller, /addControl\(new ResetViewControl\(/);
});
