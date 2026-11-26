/**
 * Tests of what the map does under the system's reduced-motion setting:
 * `node --test web/scripts/reduced-motion.test.mjs`.
 *
 * MapLibre makes a camera move jump instead of fly under the setting unless the move is passed `essential: true`;
 * the particle overlay stops redrawing a still frame, and follows the setting when it changes while the page is open.
 *
 * The overlay's decisions are pure functions (src/map/overlayRules.ts) and are run here: a frame (project, draw, owe a repaint), what an
 * event does to the two flags, the longitudes a view shows, the phase of the particles. What the class does with them, that its handlers
 * pass the right event and that one chain of frames runs, is read as text: a mutation that deletes or changes one of those lines fails
 * a test here. What only a browser shows (a canvas that is drawn, a page opened in a hidden tab) is not run in this file.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { INITIAL_FLAGS, afterEvent, frameStep, lngRange, particlePhase, shouldDraw } from '../src/map/overlayRules.ts';

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
  assert.match(overlay, /frameStep\(\{ visible: this\.visible, reduced: this\.reduced, dirty: this\.dirty, repaint: this\.repaint \}\)/, 'loop() asks frameStep with the overlay\'s own state');
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

// ---------------------------------------------------------------- a frame

const frame = (o) => ({ visible: true, reduced: false, dirty: false, repaint: false, ...o });

test('a hidden overlay does not project or draw, and keeps owing the frame it could not draw', () => {
  for (const reduced of [false, true]) for (const dirty of [false, true]) for (const repaint of [false, true]) {
    assert.deepEqual(frameStep(frame({ visible: false, reduced, dirty, repaint })), { project: false, draw: false, repaint });
  }
});

test('without the setting every frame draws, and the paths are projected again only when they are out of date', () => {
  assert.deepEqual(frameStep(frame({})), { project: false, draw: true, repaint: false });
  assert.deepEqual(frameStep(frame({ dirty: true })), { project: true, draw: true, repaint: false });
  assert.deepEqual(frameStep(frame({ repaint: true })), { project: false, draw: true, repaint: false });
});

test('under reduced motion a frame draws only for a change, and a repaint that was owed is paid once', () => {
  assert.deepEqual(frameStep(frame({ reduced: true })), { project: false, draw: false, repaint: false });
  assert.deepEqual(frameStep(frame({ reduced: true, dirty: true })), { project: true, draw: true, repaint: false });
  assert.deepEqual(frameStep(frame({ reduced: true, repaint: true })), { project: false, draw: true, repaint: false });
});

test('every combination agrees with shouldDraw, and a frame that draws never owes a repaint', () => {
  for (const visible of [false, true]) for (const reduced of [false, true]) for (const dirty of [false, true]) for (const repaint of [false, true]) {
    const s = frame({ visible, reduced, dirty, repaint });
    const step = frameStep(s);
    assert.equal(step.draw, visible && shouldDraw(s));
    assert.equal(step.project, visible && dirty);
    if (step.draw) assert.equal(step.repaint, false);
  }
});

// ---------------------------------------------------------------- what asks for a frame

test('what an event does to the flags', () => {
  for (const repaint of [false, true]) {
    assert.deepEqual(afterEvent({ dirty: false, repaint }, 'move'), { dirty: true, repaint }, 'a move makes the projection stale and asks for no repaint of its own');
    assert.deepEqual(afterEvent({ dirty: false, repaint }, 'paths'), { dirty: true, repaint });
  }
  for (const dirty of [false, true]) {
    assert.deepEqual(afterEvent({ dirty, repaint: false }, 'resize'), { dirty: true, repaint: true });
    for (const e of ['shown', 'tab-shown', 'motion-setting']) assert.deepEqual(afterEvent({ dirty, repaint: false }, e), { dirty, repaint: true }, e);
  }
});

test('under reduced motion: one frame at the start, none at rest, one after a pan, one for each thing that needs a repaint', () => {
  let flags = { ...INITIAL_FLAGS };
  const draws = (n, reduced = true) => {
    let drawn = 0;
    for (let i = 0; i < n; i++) {
      const step = frameStep({ visible: true, reduced, ...flags });
      if (step.project) flags = { ...flags, dirty: false };
      flags = { ...flags, repaint: step.repaint };
      if (step.draw) drawn++;
    }
    return drawn;
  };
  assert.equal(draws(10), 1, 'the first frame, then nothing');
  assert.equal(draws(10), 0, 'at rest');
  for (const e of ['move', 'paths', 'resize', 'shown', 'tab-shown', 'motion-setting']) {
    flags = afterEvent(flags, e);
    assert.equal(draws(10), 1, `${e}: one frame`);
    assert.equal(draws(10), 0, `${e}: then rest`);
  }
  flags = afterEvent(flags, 'move');
  assert.equal(draws(10, false), 10, 'without the setting every frame draws');
});

// ---------------------------------------------------------------- the longitudes in view

test('the longitudes in view are the extremes of the four corners with the margin, whichever corner holds them', () => {
  const calls = [];
  const skew = (x, y) => {
    calls.push([x, y]);
    return -90 + x * 0.2 - y * 0.05;
  };
  const r = lngRange(skew, 400, 300, 20);
  assert.deepEqual(calls.sort((a, b) => a[0] - b[0] || a[1] - b[1]), [[-20, -20], [-20, 320], [420, -20], [420, 320]]);
  assert.equal(r.west, skew(-20, 320), 'the west edge is the bottom left corner here');
  assert.equal(r.east, skew(420, -20), 'the east edge is the top right corner here');
  const flipped = lngRange((x, y) => -90 + x * 0.2 + y * 0.05, 400, 300, 20);
  assert.equal(flipped.west, -90 - 4 - 1, 'top left');
  assert.equal(flipped.east, -90 + 84 + 16, 'bottom right');
  const beyond = lngRange((x) => 175 + x * 0.1, 400, 300, 0);
  assert.ok(beyond.east > 180, 'a range beyond +-180 is not wrapped');
});

// ---------------------------------------------------------------- the particles

test('the particles stand still under reduced motion and otherwise move at their speed, wrapping at their spacing', () => {
  for (const t of [0, 0.5, 12.3]) assert.equal(particlePhase(true, t, 50, 30), 0);
  assert.equal(particlePhase(false, 0, 50, 30), 0);
  assert.equal(particlePhase(false, 0.5, 50, 30), 25);
  assert.equal(particlePhase(false, 1, 50, 30), 20);
  assert.ok(particlePhase(false, 12.3, 50, 30) >= 0 && particlePhase(false, 12.3, 50, 30) < 30);
});

// ---------------------------------------------------------------- the overlay carries the decisions out

test('every handler of the overlay passes the event it is for, and the frame, the range and the phase come from the rules', () => {
  const o = read('map/flowOverlay.ts').replace(/\s+/g, ' ');
  assert.match(o, /map\.on\('move', \(\) => this\.on\('move'\)\)/);
  assert.match(o, /map\.on\('resize', \(\) => \{ this\.resize\(\); this\.on\('resize'\); \}\)/);
  assert.match(o, /this\.reduced = this\.motionQuery\.matches; this\.on\('motion-setting'\);/);
  assert.match(o, /this\.on\('paths'\);/);
  assert.match(o, /if \(v\) this\.on\('shown'\);/);
  assert.match(o, /if \(step\.project\) this\.project\(\); this\.repaint = step\.repaint; if \(step\.draw\) this\.draw\(/);
  assert.match(o, /const \{ west, east \} = lngRange\(\(x, y\) => this\.map\.unproject\(\[x, y\]\)\.lng, w, h, 20\);/);
  assert.match(o, /const phase = particlePhase\(this\.reduced, t, speed, spacing\);/);
  assert.ok(!/this\.repaint = (true|false)|this\.dirty = true/.test(o), 'a flag is raised by afterEvent only (project() clears `dirty`, a frame clears `repaint`)');
});

test('the setting is read when the overlay is made, a projection clears the flag it answers, the copies are the ones of the pure function and a hidden overlay stays hidden', () => {
  const o = read('map/flowOverlay.ts').replace(/\s+/g, ' ');
  // the state at load is the setting's: an overlay made under reduced motion does not animate until the setting changes
  assert.match(o, /private reduced = this\.motionQuery\.matches;/);
  // the paths are projected again only once after a move: the projection clears `dirty` at its end
  assert.match(o, /this\.projected = out; this\.dirty = false; \}/);
  // the world is drawn again on each side: one projection for every copy the pure function returns, each point projected as the copy has it
  assert.match(o, /for \(const copy of pathCopies\(path\.coords, west, east\)\) \{/);
  assert.match(o, /this\.map\.project\(copy\[i\]\)/);
  assert.ok(!/copyShifts/.test(o), 'the shifts are taken in copies.ts only');
  // the flag that frameStep reads is the one setVisible sets
  assert.match(o, /setVisible\(v: boolean\) \{ this\.visible = v;/);
});

test('destroy() removes the two listeners the overlay added to the document and to the media query, the same functions it added', () => {
  const o = read('map/flowOverlay.ts').replace(/\s+/g, ' ');
  // the handlers are fields, not functions written where they are added
  assert.match(o, /private onMotionSetting = \(\) => \{ this\.reduced = this\.motionQuery\.matches; this\.on\('motion-setting'\); \};/);
  assert.match(o, /private onVisibility = \(\) => \{ cancelAnimationFrame\(this\.raf\);/);
  assert.equal([...o.matchAll(/this\.motionQuery\.addEventListener\('change', this\.onMotionSetting\);/g)].length, 1);
  assert.equal([...o.matchAll(/document\.addEventListener\('visibilitychange', this\.onVisibility\);/g)].length, 1);
  assert.equal([...o.matchAll(/addEventListener\(/g)].length, 2, 'no other listener is added to the document or the query');
  const destroy = o.match(/destroy\(\) \{(.*?)\n?\}\s*$/)?.[1] ?? o.slice(o.indexOf('destroy() {'));
  assert.ok(destroy.includes("this.motionQuery.removeEventListener('change', this.onMotionSetting);"), destroy);
  assert.ok(destroy.includes("document.removeEventListener('visibilitychange', this.onVisibility);"), destroy);
  assert.ok(destroy.includes('cancelAnimationFrame(this.raf);') && destroy.includes('this.canvas.remove();'), destroy);
});

test('a page first opened in a hidden tab runs one chain of frames: the frame already asked for is cancelled before another is', () => {
  const o = read('map/flowOverlay.ts').replace(/\s+/g, ' ');
  const handler = o.match(/private onVisibility = \(\) => \{(.*?)\};/)?.[1] ?? '';
  const cancel = handler.indexOf('cancelAnimationFrame(this.raf)');
  const hidden = handler.indexOf('if (document.hidden) return;');
  const tab = handler.indexOf("this.on('tab-shown')");
  const loop = handler.indexOf('this.loop()');
  assert.ok(cancel >= 0 && cancel < hidden && hidden < tab && tab < loop, handler);
});
