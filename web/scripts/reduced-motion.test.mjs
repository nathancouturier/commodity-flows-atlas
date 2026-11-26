/**
 * Tests of what the map does under the system's reduced-motion setting:
 * `node --test web/scripts/reduced-motion.test.mjs`.
 *
 * MapLibre makes a camera move jump instead of fly under the setting unless the move is passed `essential: true`;
 * the particle overlay stops redrawing a still frame, and follows the setting when it changes while the page is open.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { shouldDraw } from '../src/map/overlayRules.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.join(here, '../src');
const read = (rel) => fs.readFileSync(path.join(src, rel), 'utf8');

const sourceFiles = (dir) =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? sourceFiles(path.join(dir, e.name)) : [path.join(dir, e.name)]));

test('the overlay draws every frame unless the system asks for reduced motion', () => {
  for (const dirty of [false, true]) for (const repaint of [false, true]) assert.equal(shouldDraw({ reduced: false, dirty, repaint }), true);
});

test('a reduced-motion overlay draws when something changed and not otherwise', () => {
  assert.equal(shouldDraw({ reduced: true, dirty: false, repaint: false }), false);
  assert.equal(shouldDraw({ reduced: true, dirty: true, repaint: false }), true);
  assert.equal(shouldDraw({ reduced: true, dirty: false, repaint: true }), true);
  assert.equal(shouldDraw({ reduced: true, dirty: true, repaint: true }), true);
});

test('the overlay follows the setting while the page is open and asks shouldDraw before it draws', () => {
  const overlay = read('map/flowOverlay.ts');
  assert.match(overlay, /prefers-reduced-motion: reduce/);
  assert.match(overlay, /addEventListener\('change'/, 'the media query is listened to');
  assert.match(overlay, /shouldDraw\(/, 'loop() asks shouldDraw');
  assert.match(overlay, /from '\.\/overlayRules'/);
  assert.match(overlay, /from '\.\/copies'/);
});

test('no camera move is marked essential: the library then flies, whatever the setting', () => {
  const files = sourceFiles(src).filter((f) => /\.(ts|tsx)$/.test(f));
  assert.ok(files.length > 50, `${files.length} source files read`);
  const hits = files.filter((f) => /essential\s*:\s*true/.test(fs.readFileSync(f, 'utf8'))).map((f) => path.relative(src, f));
  assert.deepEqual(hits, []);
});

test('the two moves that opened a page by a flight are still flights', () => {
  const flyToBounds = read('map/controller.ts').match(/export function flyToBounds[\s\S]*?\n\}/)?.[0] ?? '';
  assert.match(flyToBounds, /duration: 1600/);
  assert.match(read('components/views/ChokepointView.tsx'), /\.flyTo\(\{[\s\S]*?duration: 1600/);
});
