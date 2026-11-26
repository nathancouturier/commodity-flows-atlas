/**
 * The page of an id the atlas does not have (a mistyped or outdated link) says what every unknown page says, under its own kicker and the id,
 * and shows no heading of another page: an unknown board used to carry the heading of the passages' status board.
 *
 *     node web/scripts/unknown-pages.test.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.join(here, '../src', rel), 'utf8');

test('every page of the freight family that can be unknown says "This <kind> is not in the atlas catalogue." under its kicker and the id', () => {
  for (const [file, kicker, kind] of [
    ['components/views/RouteView.tsx', 'Freight route', 'route'],
    ['components/views/ChokepointView.tsx', 'Chokepoint', 'chokepoint'],
    ['components/views/EventView.tsx', 'Event', 'event'],
    ['components/views/VesselView.tsx', 'Vessel class', 'vessel class'],
    ['components/views/BoardView.tsx', 'Board', 'board'],
  ]) {
    const src = read(file);
    const re = new RegExp(`<div class="detail-kicker">${kicker}</div><h2 class="detail-title">\\{id\\}</h2></div>\\s*<div class="panel-scroll"><Placeholder>This ${kind} is not in the atlas catalogue\\.`);
    assert.match(src, re, file);
  }
});

test('the status board shows its heading only for its own id: an unknown board is decided before the heading is used', () => {
  const src = read('components/views/BoardView.tsx');
  const unknown = src.indexOf("if (id !== 'chokepoints' || rows === null) return");
  assert.ok(unknown > 0, 'the unknown board is decided from the id, before any loading state');
  assert.ok(unknown < src.indexOf('if (rows === undefined) return'), 'the unknown board comes before the loading state of the status board');
  const line = src.slice(unknown, src.indexOf('\n', unknown));
  assert.ok(!line.includes('{head}'), 'the unknown board does not carry the heading of the status board');
  assert.ok(!/This page is not in the atlas catalogue/.test(src), 'no page of the atlas says "This page is not in the atlas catalogue"');
  // the heading of the status board is that of the id "chokepoints" and of no other
  assert.ok(src.includes('<h2 class="detail-title">All passages: traffic against 2023</h2>'));
});

test('the two real boards are routed as before: the market page for freight-now, the status board for any other id', () => {
  const panel = read('components/DetailPanel.tsx');
  assert.match(panel, /s\.kind === 'board' && s\.id === 'freight-now' \? \(\s*<FreightNowView \/>\s*\) : s\.kind === 'board' \? \(\s*<BoardView id=\{s\.id\} \/>/);
});
