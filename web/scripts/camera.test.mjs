/**
 * Tests of the first view and the camera limits (src/map/camera.ts) and of the way the map controller uses them:
 * `node --test web/scripts/camera.test.mjs`. The module is pure, so it runs as it is.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  WORLD_BOUNDS, MAX_ZOOM, MAX_LATITUDE, minZoomFor, fitZoomFor, constrainCamera,
  canvasSizeOf, cameraLimits, hasPadding, passagePadding, centerForPadding, firstViewState,
} from '../src/map/camera.ts';

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

// ---- what the controller asks of the limits, run with made-up sizes

test('canvasSizeOf: the container when it has a size, the window while it has none; width and height never swapped', () => {
  assert.deepEqual(canvasSizeOf({ clientWidth: 390, clientHeight: 844 }, { innerWidth: 1, innerHeight: 2 }), { w: 390, h: 844 });
  assert.deepEqual(canvasSizeOf({ clientWidth: 0, clientHeight: 0 }, { innerWidth: 1440, innerHeight: 900 }), { w: 1440, h: 900 });
  assert.deepEqual(canvasSizeOf({ clientWidth: 0, clientHeight: 844 }, { innerWidth: 390, innerHeight: 1 }), { w: 390, h: 844 });
});

test('cameraLimits: the floor is the one of the canvas as it is when asked, width first, height second', () => {
  const size = { w: 1440, h: 900 };
  const limits = cameraLimits(() => size);
  assert.equal(limits.minZoom(), minZoomFor(1440, 900));
  assert.equal(limits.minZoom(), Math.max(0.5, Math.log2(900 / 512)), 'a desktop keeps the floor it has always had, not 0.5');
  size.w = 390; size.h = 844; // a resize: the same functions, a new answer
  assert.equal(limits.minZoom(), minZoomFor(390, 844));
  assert.notEqual(limits.minZoom(), minZoomFor(844, 390), 'width and height are not swapped');
  size.w = 844; size.h = 390;
  assert.equal(limits.minZoom(), minZoomFor(844, 390));
  assert.equal(limits.minZoom(), 0.5, 'a phone on its side has the desktop floor');
});

test('cameraLimits: the margin of the width term leaves the world a little narrower than the screen', () => {
  for (const [w, h] of [[390, 844], [360, 740], [412, 915], [320, 568]]) {
    const ratio = (512 * 2 ** minZoomFor(w, h)) / w;
    assert.ok(ratio > 0.92 && ratio < 0.94, `${w}x${h}: the world is ${ratio} of the width at the floor`);
  }
});

test('cameraLimits: the constraint reads the width for the zoom floor and the height for the poles', () => {
  const size = { w: 1440, h: 900 };
  const limits = cameraLimits(() => size);
  const zoom = 3;
  const world = 512 * 2 ** zoom;
  const north = limits.constrain(10, 89, zoom);
  assert.ok(Math.abs(north.lat - latAtWorldY(900 / 2, world)) < 1e-9, `north ${north.lat}: half the height from the pole`);
  assert.ok(Math.abs(limits.constrain(10, -89, zoom).lat - latAtWorldY(world - 900 / 2, world)) < 1e-9);
  // the same camera on a canvas turned on its side is held at another latitude
  size.w = 900; size.h = 1440;
  assert.ok(Math.abs(limits.constrain(10, 89, zoom).lat - latAtWorldY(1440 / 2, world)) < 1e-9);
  assert.equal(limits.constrain(0, 0, -5).zoom, minZoomFor(900, 1440));
  size.w = 390; size.h = 844;
  assert.equal(limits.constrain(0, 0, -5).zoom, minZoomFor(390, 844));
  assert.equal(limits.constrain(0, 0, 20).zoom, MAX_ZOOM);
});

test('the controller gives the map the limits and nothing of its own', () => {
  assert.match(controller, /import \{[^}]*\bWORLD_BOUNDS\b[^}]*\} from '\.\/camera'/);
  assert.doesNotMatch(controller, /(const|let|var)\s+WORLD_BOUNDS\b/);
  assert.match(controller, /const limits = cameraLimits\(canvasSize\);/);
  assert.match(controller, /const canvasSize = \(\) => canvasSizeOf\(container, window\);/);
  assert.match(controller, /\n\s+minZoom: limits\.minZoom\(\),/, 'the map option is the floor of the canvas');
  assert.doesNotMatch(controller, /\bminZoom:\s*[-\d.]+/, 'no literal floor');
  assert.match(controller, /transformConstrain: \(c, z\) => \{\s*const r = limits\.constrain\(c\.lng, c\.lat, z\);/);
  assert.match(controller, /map\.on\('resize', \(\) => \{\s*map!\.setMinZoom\(limits\.minZoom\(\)\);/, 'the floor follows a resize');
  // the numbers come from camera.ts through those three calls only
  assert.doesNotMatch(controller, /\b(minZoomFor|constrainCamera)\(/);
});

test('the controller adds the Reset view control', () => {
  assert.match(controller, /addControl\(new ResetViewControl\(/);
});

// ---- the camera is not left with a padding

const padding = { top: 60, bottom: 40, left: 340, right: 420 };

test('hasPadding', () => {
  assert.equal(hasPadding({ top: 0, bottom: 0, left: 0, right: 0 }), false);
  assert.equal(hasPadding({ left: 0 }), false);
  assert.equal(hasPadding({ top: 0, bottom: 0, left: 0, right: 1 }), true);
  assert.equal(hasPadding(padding), true);
});

// the pixel at which a place is drawn on a w x h canvas whose camera is centred on `center` at `zoom` (Mercator, 512 px world)
const project = (at, center, zoom, w, h) => {
  const world = 512 * 2 ** zoom;
  const px = ([lng, lat]) => [((lng + 180) / 360) * world, (0.5 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / (2 * Math.PI)) * world];
  const [x, y] = px(at); const [cx, cy] = px(center);
  return [w / 2 + x - cx, h / 2 + y - cy];
};

test('centerForPadding puts the place in the middle of the free area, the way a padding does', () => {
  const places = JSON.parse(fs.readFileSync(path.join(here, '../../data/freight/chokepoints.json'), 'utf8')).map((c) => c.at);
  assert.ok(places.length >= 5);
  for (const [w, h] of [[1440, 900], [1920, 1080], [390, 844], [768, 1024]]) {
    const pad = passagePadding(w, h);
    for (const at of places) {
      const [x, y] = project(at, centerForPadding(at, 4.2, pad), 4.2, w, h);
      // the middle of the free area: left + (w - left - right) / 2, top + (h - top - bottom) / 2
      assert.ok(Math.abs(x - (pad.left + (w - pad.left - pad.right) / 2)) < 1e-6, `${w}x${h} ${at} x ${x}`);
      assert.ok(Math.abs(y - (pad.top + (h - pad.top - pad.bottom) / 2)) < 1e-6, `${w}x${h} ${at} y ${y}`);
    }
  }
  const none = centerForPadding([56.5, 26.55], 4.2, { top: 0, bottom: 0, left: 0, right: 0 });
  assert.ok(Math.abs(none[0] - 56.5) < 1e-9 && Math.abs(none[1] - 26.55) < 1e-9, 'no padding, no move');
});

test('passagePadding: the side panel and the page beside a wide window, the sheet under a narrow one', () => {
  const wide = passagePadding(1440, 900);
  assert.ok(wide.left > 0 && wide.right > 0 && wide.left + wide.right < 1440);
  assert.deepEqual(passagePadding(760, 900), wide, 'wide from 760');
  const narrow = passagePadding(759, 844);
  assert.equal(narrow.bottom, 844 * 0.5);
  assert.ok(narrow.left < 20 && narrow.right < 20);
});

test('no camera move of the site passes a padding, except the fit that leaves none behind', () => {
  const dir = path.join(here, '../src');
  const files = [];
  const walk = (d) => { for (const f of fs.readdirSync(d, { withFileTypes: true })) { const q = path.join(d, f.name); if (f.isDirectory()) walk(q); else if (/\.(ts|tsx)$/.test(f.name)) files.push(q); } };
  walk(dir);
  const hits = [];
  for (const f of files) {
    const text = fs.readFileSync(f, 'utf8');
    for (const m of text.matchAll(/\.(flyTo|easeTo|jumpTo|panTo|zoomTo|setPadding)\(/g)) {
      const call = text.slice(m.index, text.indexOf(');', m.index));
      if (m[1] === 'setPadding' || /\bpadding\s*:/.test(call)) hits.push(`${path.relative(dir, f)}: ${m[1]}`);
    }
  }
  // the one that sets a padding is the reset of it
  assert.deepEqual(hits, ['map/controller.ts: setPadding']);
  assert.match(controller, /m\.setPadding\(\{ top: 0, bottom: 0, left: 0, right: 0 \}\)/);
  const view = fs.readFileSync(path.join(dir, 'components/views/ChokepointView.tsx'), 'utf8');
  // the padding is the phone and desktop one, or on a tablet the controller's
  assert.match(view, /\.flyTo\(\{\s*center: centerForPadding\(cp\.at, zoom, pad\),/);
  assert.match(view, /const pad = isTabletLayout\(\) \? viewPadding\(\{ detail: true \}\) : passagePadding\(window\.innerWidth, window\.innerHeight\);/);
});

test('every fit of the controller clears a padding that was left on the camera first', () => {
  const fitCalls = [...controller.matchAll(/\.fitBounds\(/g)].map((m) => m.index);
  assert.equal(fitCalls.length, 2, 'two fits: fitWorld and flyToBounds');
  for (const at of fitCalls) {
    const before = controller.slice(Math.max(0, at - 400), at);
    assert.match(before, /clearPadding\(m\);|const fit = \(\) =>/);
  }
  const fitWorld = controller.match(/function fitWorld[\s\S]*?\n\}/)[0];
  assert.ok(fitWorld.includes('clearPadding(m)') && fitWorld.indexOf('clearPadding(m)') < fitWorld.indexOf('.fitBounds('));
  const toBounds = controller.match(/export function flyToBounds[\s\S]*?\n\}/)[0];
  assert.ok(toBounds.includes('clearPadding(m)') && toBounds.indexOf('clearPadding(m)') < toBounds.indexOf('.fitBounds('));
  assert.match(controller.match(/export function flyToWorld[\s\S]*?\n\}/)[0], /fitWorld\(m, detail, 1400\)/);
  assert.match(controller, /fitWorld\(map, selection\.peek\(\) !== null, 0\)/, 'the first load fits through the same function');
});

// ---- a resize and the first view

test('firstViewState: a fit of the first view, then a resize, fits it again', () => {
  const size = { w: 390, h: 844 };
  const s = firstViewState(() => ({ ...size }));
  assert.equal(s.atFirstView, false);
  const ret = s.fit(() => { s.moveStart(); return 'fitted'; }); // the library fires movestart inside the fit
  assert.equal(ret, 'fitted');
  assert.equal(s.atFirstView, true, 'its own move is not the visitor\'s');
  // a phone turned: the library fires movestart with the canvas already at its new size, then resize
  size.w = 844; size.h = 390;
  s.moveStart();
  assert.equal(s.atFirstView, true, 'a move that comes with a new size is a resize');
  assert.equal(s.resize(), true);
  s.fit(() => {});
  size.w = 390; size.h = 844;
  s.moveStart();
  assert.equal(s.resize(), true);
});

test('firstViewState: once anything else moves the camera, a resize leaves it', () => {
  const size = { w: 1440, h: 900 };
  const s = firstViewState(() => ({ ...size }));
  s.fit(() => {});
  s.moveStart(); // a drag, a wheel, a pinch, the zoom buttons, a page that flies: same size
  assert.equal(s.atFirstView, false);
  size.w = 1000;
  s.moveStart();
  assert.equal(s.resize(), false);
  size.w = 1440;
  s.moveStart();
  assert.equal(s.resize(), false);
  // a "Reset view" (a fit) gives it back
  s.fit(() => {});
  assert.equal(s.resize(), true);
});

test('firstViewState: a fit that throws still leaves the state consistent', () => {
  const s = firstViewState(() => ({ w: 1, h: 1 }));
  assert.throws(() => s.fit(() => { throw new Error('x'); }));
  s.moveStart();
  assert.equal(s.atFirstView, false);
});

test('the controller keeps the state in memory and wires it to the map\'s own events', () => {
  assert.match(controller, /first = firstViewState\(canvasSize\);/);
  assert.match(controller, /map\.on\('movestart', \(\) => first\?\.moveStart\(\)\);/);
  assert.match(controller, /if \(first\?\.resize\(\)\) fitWorld\(map!, !!document\.querySelector\('\.detail-panel\.open'\), 0\);/);
  assert.match(controller, /if \(first\) first\.fit\(fit\);/);
  assert.doesNotMatch(controller, /localStorage|sessionStorage|indexedDB/);
});

// ---- what METHODOLOGY says of the first view, recomputed from the formula

const methodology = fs.readFileSync(path.join(here, '../../METHODOLOGY.md'), 'utf8').replace(/\s+/g, ' ');

// the widest whole width, at a given height, at which the width term of the floor is the one that binds
const widestNarrow = (h) => { let w = 100; while (minZoomFor(w + 1, h) < desktopFloor(w + 1, h)) w++; return w; };
const thousands = (n) => n.toLocaleString('en-US');

test('METHODOLOGY: the widths at which the width term binds are the ones the formula gives', () => {
  const ratio = 2 ** 0.1;
  assert.ok(methodology.includes(`narrower than ${ratio.toFixed(2)} times the larger of its height and ${Math.round(512 * 2 ** 0.5)} px`));
  for (const h of [900, 1920]) {
    const w = widestNarrow(h);
    assert.ok(methodology.includes(`up to ${thousands(w)} px wide at ${thousands(h)} px high`), `${w} px at ${h}`);
    assert.ok(minZoomFor(w, h) < desktopFloor(w, h) && minZoomFor(w + 1, h) >= desktopFloor(w + 1, h));
  }
  // the two examples named: they open on the whole box, a desktop at 1440x900 does not
  for (const [w, h] of [[1080, 1920], [800, 900]]) assert.ok(minZoomFor(w, h) < desktopFloor(w, h), `${w}x${h}`);
  assert.ok(methodology.includes('a monitor turned upright (1,080 by 1,920)') && methodology.includes('a window 800 px wide and 900 px high'));
  for (const [w, h] of DESKTOPS) assert.equal(minZoomFor(w, h), desktopFloor(w, h), `${w}x${h} is not narrow`);
  assert.ok(methodology.includes('a choice made without the owner, listed in PROGRESS.md'));
});

test('METHODOLOGY: the icon bullet types no count of assets', () => {
  const bullet = /\*\*Icon size below zoom 0\.5\.\*\*[^*]*?Every asset/.exec(methodology)?.[0] ?? '';
  assert.ok(bullet.includes('the icons overlap less on a phone'), bullet);
  assert.ok(!/\d{3}/.test(bullet.replace('0.72', '').replace('0.5', '')), 'no count in the bullet');
});
