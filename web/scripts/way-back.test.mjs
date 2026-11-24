/** A page that no longer exists says so and gives a way back (GV6D.7): the route page, the lane page and the unknown commodity page; the passage and the vessel class too (FNCI, GV8B.4). */
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

test('an unknown passage links to the list of passages and an unknown vessel class to the Freight view', () => {
  const cp = read('components/views/ChokepointView.tsx');
  assert.match(cp, /This chokepoint is not in the atlas catalogue\.<WayBack onClick=\{\(\) => select\(\{ kind: 'board', id: 'chokepoints' \}\)\}>All passages<\/WayBack><\/Placeholder>/);
  assert.match(cp, /import \{[^}]*\bWayBack\b[^}]*\} from '\.\.\/ui'/);
  // the button of the passage pages that it repeats opens the same board
  assert.match(cp, /onClick=\{\(\) => select\(\{ kind: 'board', id: 'chokepoints' \}\)\} title="Every passage[^"]*">All passages<\/button>/);
  const vessel = read('components/views/VesselView.tsx');
  assert.match(vessel, /This vessel class is not in the atlas catalogue\.<FreightWayBack \/><\/Placeholder>/);
  assert.match(vessel, /import \{[^}]*\bFreightWayBack\b[^}]*\} from '\.\/shared'/);
});

test('the source line of the estimates lists PortWatch whenever a ship-type line is printed or a shown figure is capped (FNCI, GV8B.1)', () => {
  const cp = read('components/views/ChokepointView.tsx');
  assert.match(cp, /const typeLines = TYPE_ORDER\.filter\(\(t\) => cp\.typeNotes\?\.\[t\]\);/);
  assert.match(cp, /typeLines\.map\(\(t\) =>/);
  assert.match(cp, /\.\.\.\(typeLines\.length \|\| shown\.some\(isCapped\) \? \[\{ s: 'portwatch'/);
  // the passages that print a type line, from the file: every one of them lists PortWatch
  const notes = JSON.parse(fs.readFileSync(path.join(here, '../../data/freight/chokepoints.json'), 'utf8')).filter((c) => Object.keys(c.typeNotes ?? {}).length);
  assert.ok(notes.length > 0, String(notes.length));
});
