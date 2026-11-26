/**
 * Tests of the scale bar of the map (nautical miles, from the zoom in camera.ts): `node --test web/scripts/scale-bar.test.mjs`.
 *
 * The control is the map library's own, so what the atlas owns is read as text: how the controller adds it, when it
 * shows it, and what the stylesheet does with it. The two figures that METHODOLOGY prints about the length per pixel
 * are recomputed here from the Mercator formula.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCALE_MIN_ZOOM, MAX_ZOOM, WORLD_BOUNDS, fitZoomFor, minZoomFor } from '../src/map/camera.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.join(here, rel), 'utf8');
const controller = read('../src/map/controller.ts');
const css = read('../src/styles/app.css');
const camera = read('../src/map/camera.ts');
const methodology = read('../../METHODOLOGY.md').replace(/\s+/g, ' ');

const scaleAdd = controller.indexOf('new maplibregl.ScaleControl(');
const resetAdd = controller.indexOf('new ResetViewControl(');

test('the zoom from which the bar is shown is above every view the map opens on', () => {
  assert.ok(Number.isFinite(SCALE_MIN_ZOOM));
  // the first view of a desktop and of a phone, and the floor of the smallest screens, are all below it
  const pad = { top: 64, bottom: 0, left: 16, right: 16 };
  for (const [w, h] of [[1440, 900], [1920, 1080], [390, 844], [360, 740]]) {
    assert.ok(fitZoomFor(w, h, pad, WORLD_BOUNDS) < SCALE_MIN_ZOOM, `${w}x${h} first view`);
    assert.ok(minZoomFor(w, h) < SCALE_MIN_ZOOM, `${w}x${h} floor`);
  }
  assert.ok(SCALE_MIN_ZOOM > 3, 'a view of 3 or less spans more than a third of the world: no single length is right');
  assert.ok(SCALE_MIN_ZOOM < MAX_ZOOM);
});

test('the controller adds the library scale control in nautical miles, 100 px at most, to the top right', () => {
  assert.ok(scaleAdd > 0, 'a ScaleControl is added');
  const call = controller.slice(scaleAdd, controller.indexOf(';', scaleAdd));
  assert.match(call, /unit:\s*'nautical'/);
  assert.match(call, /maxWidth:\s*100\b/);
  const line = controller.slice(controller.lastIndexOf('map.addControl(', scaleAdd), controller.indexOf('\n', scaleAdd));
  assert.match(line, /'top-right'\)/);
});

test('it sits below the reset button, so after it in the column', () => {
  assert.ok(resetAdd > 0);
  assert.ok(scaleAdd > resetAdd, 'ScaleControl is added after ResetViewControl');
  // and nothing else of the column moved: the navigation control is still the first
  assert.ok(controller.indexOf('new maplibregl.NavigationControl(') < resetAdd);
});

test('the controller toggles the class from the zoom in camera.ts, on every zoom event, and once at the start', () => {
  assert.match(controller, /import \{[^}]*\bSCALE_MIN_ZOOM\b[^}]*\} from '\.\/camera'/);
  const m = controller.match(/const syncScale = \(\) =>([^\n]*)\n/);
  assert.ok(m, 'syncScale is defined');
  assert.match(m[1], /classList\.toggle\('scale-on',\s*map!?\.getZoom\(\)\s*>=\s*SCALE_MIN_ZOOM\)/);
  assert.match(controller, /map\.on\('zoom',\s*syncScale\)/);
  assert.match(controller, /\n\s*syncScale\(\);/);
  // the number is the constant's, nowhere retyped for this rule
  assert.ok(!/getZoom\(\)\s*>=\s*[\d.]+/.test(controller.slice(scaleAdd, scaleAdd + 700)), 'no literal threshold next to the scale control');
});

test('no unit switch and no new element of the atlas for the bar', () => {
  assert.ok(!/setUnit\(/.test(controller));
  const block = controller.slice(scaleAdd, controller.indexOf('syncScale();', scaleAdd));
  assert.ok(!/createElement|innerHTML|appendChild/.test(block));
});

// the rules of app.css that name the scale control: [selector, declarations]
const rules = [...css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g)]
  .map((m) => [m[1].trim().replace(/\s+/g, ' '), m[2]])
  .filter(([sel]) => sel.includes('maplibregl-ctrl-scale'));

test('the stylesheet hides the scale by default and shows it only under scale-on', () => {
  assert.ok(rules.length >= 2, 'the scale has its rules');
  const base = rules.filter(([sel]) => !sel.includes('scale-on'));
  const shown = rules.filter(([sel]) => sel.includes('scale-on'));
  assert.ok(base.some(([, d]) => /display:\s*none\b/.test(d)), 'a rule without scale-on hides it');
  assert.ok(base.every(([, d]) => !/display:\s*(?!none\b)[a-z-]+/.test(d)), 'no rule without scale-on shows it');
  assert.ok(shown.some(([, d]) => /display:\s*block\b/.test(d)), 'a rule under scale-on shows it');
  for (const [sel] of shown) assert.match(sel, /\.scale-on \.maplibregl-ctrl-scale$/);
});

test('the bar takes no pointer, so a drag that starts on it moves the map', () => {
  const base = rules.filter(([sel]) => !sel.includes('scale-on'));
  assert.ok(base.some(([, d]) => /pointer-events:\s*none\b/.test(d)));
  assert.ok(rules.every(([, d]) => !/pointer-events:\s*(?!none\b)[a-z-]+/.test(d)));
});

test('the other stylesheets do not show the scale', () => {
  const dir = path.join(here, '../src/styles');
  for (const f of fs.readdirSync(dir).filter((n) => n.endsWith('.css') && n !== 'app.css')) {
    assert.ok(!fs.readFileSync(path.join(dir, f), 'utf8').includes('maplibregl-ctrl-scale'), f);
  }
});

test('the bar uses the colours of the panels', () => {
  const body = rules.filter(([sel]) => !sel.includes('scale-on')).map(([, d]) => d).join(';');
  assert.match(body, /background:\s*var\(--panel\)/);
  assert.match(body, /color:\s*var\(--ink-2\)/);
  assert.match(body, /font-size:\s*11px/);
  assert.match(body, /border-top:\s*0/, 'the open-top shape of a scale bar');
});

test('nothing is stored for the bar', () => {
  const newCode = [controller.slice(scaleAdd, controller.indexOf('syncScale();', scaleAdd)), camera, rules.map(([, d]) => d).join('')].join('\n');
  assert.ok(!/localStorage|sessionStorage|indexedDB|document\.cookie/.test(newCode));
});

// ---- the figures METHODOLOGY prints

const rad = Math.PI / 180;
const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * rad) / 2));
const latOf = (y) => (2 * Math.atan(Math.exp(y)) - Math.PI / 2) / rad;
/** The largest difference, in percent, of the length per pixel on the top and bottom edges of a canvas `h` px high from that on the middle line. */
function edgeDifference(lat0, zoom, h) {
  const dy = (h / 2 / (512 * 2 ** zoom)) * 2 * Math.PI;
  return Math.max(...[latOf(mercY(lat0) + dy), latOf(mercY(lat0) - dy)].map((la) => Math.abs(Math.cos(la * rad) / Math.cos(lat0 * rad) - 1) * 100));
}

test('METHODOLOGY prints the figures the formula gives', () => {
  const at4 = Math.round(edgeDifference(45, 4, 900));
  const at6 = Math.round(edgeDifference(45, 6, 900));
  assert.ok(methodology.includes(`by about ${at4}% at zoom 4`), `zoom 4: ${at4}%`);
  assert.ok(methodology.includes(`by about ${at6}% at zoom 6`), `zoom 6: ${at6}%`);
  assert.ok(at4 > 3 * at6, 'the bar is far better at zoom 6 than at zoom 4');
});

test('METHODOLOGY states the unit and the radius, and the radius is the library\'s', () => {
  assert.ok(methodology.includes('1,852 metres'));
  assert.ok(methodology.includes('6,371,008.8 m'));
  const lib = path.join(here, '../node_modules/maplibre-gl/dist/maplibre-gl-dev.js');
  if (!fs.existsSync(lib)) return;
  assert.match(fs.readFileSync(lib, 'utf8'), /^const earthRadius = 6371008\.8;$/m);
});
