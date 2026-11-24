/** A page that no longer exists says so and gives a way back (GV6D.7): the route page, the lane page and the unknown commodity page. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.join(here, '../src', rel), 'utf8');

test('the page of a route that no longer exists links to the Freight view, the list of routes by vessel class', () => {
  const route = read('components/views/RouteView.tsx');
  assert.match(route, /This route is not in the atlas catalogue\.<FreightWayBack \/><\/Placeholder>/);
  const shared = read('components/views/shared.tsx');
  assert.match(shared, /FreightWayBack = \(\) => <WayBack onClick=\{openFreightView\}>Routes by vessel class<\/WayBack>/);
  // what the link does is what "All routes" of the list does: the Freight view, no filter, no page open
  const freight = read('lib/freight.ts');
  const fn = freight.slice(freight.indexOf('export function openFreightView'), freight.indexOf('// a link that opens a vessel class without its filter'));
  for (const call of ["setFamily('freight')", 'commodity.value = null', 'vesselClasses.value = new Set()', 'select(null)']) assert.ok(fn.includes(call), call);
});

test('a lane that no longer exists links to the page of its commodity, an unknown commodity to the whole list', () => {
  const lane = read('components/views/LaneView.tsx');
  assert.match(lane, /This lane is not in the atlas\.\{page && <WayBack onClick=\{\(\) => openCommodity\(page\)\}>/);
  const panel = read('components/DetailPanel.tsx');
  assert.match(panel, /kind === 'commodity' && <WayBack onClick=\{\(\) => select\(null\)\}>All commodities<\/WayBack>/);
});

test('the link is inside the placeholder, so that a page with only that message still takes the tab title "Unknown ..."', () => {
  // DetailPanel.readTitle looks for a placeholder that is the only child of .panel-scroll
  assert.match(read('components/DetailPanel.tsx'), /\.panel-scroll > \.placeholder:only-child/);
  assert.match(read('components/ui.tsx'), /export function WayBack/);
});
