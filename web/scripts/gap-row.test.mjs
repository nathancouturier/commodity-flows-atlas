/** The gap row of a ranked table: a table with its own total has one name and one reason on the page, in the tooltip and in the CSV; a world table keeps its words. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { gapLabel, gapTitle } from '../src/lib/gapRow.ts';

const own = { shareOf: "Australia's LNG exports", norank: true };
const world = { norank: true };
const ranked = {};

test('a table with its own total: the same name on the page and in the CSV', () => {
  assert.equal(gapLabel(own), 'Countries not listed');
  assert.equal(gapLabel(own, true), 'Countries not listed');
  assert.equal(gapLabel({ shareOf: "China's declared imports" }, true), gapLabel({ shareOf: "China's declared imports" }));
});

test('a table with its own total: the reason is the rows it does not list, not places and regions', () => {
  const t = gapTitle(own, 'total', false);
  assert.equal(t, 'The total minus the rows listed: the part of it that the table does not list by country, and rounding');
  assert.ok(!/places and regions/.test(t));
  assert.ok(/"Other countries" line/.test(gapTitle(own, 'total', true)));
});

test('a world table keeps its words', () => {
  assert.equal(gapLabel(world), 'Countries not listed');
  assert.equal(gapLabel(world, true), 'Not given by country');
  assert.equal(gapLabel(ranked), 'Not given by country');
  assert.equal(gapLabel({ norank: true, scope: 'EU' }), 'Not given by country');
  assert.equal(gapTitle(ranked, 'world total', false), 'The world total minus the countries listed: places and regions the source does not give as a country of the atlas, and rounding');
});

test('the page and the CSV take their words from the same functions', async () => {
  const { readFileSync } = await import('node:fs');
  for (const file of ['../src/components/ui.tsx', '../src/lib/rankedCsv.ts']) {
    const src = readFileSync(new URL(file, import.meta.url), 'utf8');
    assert.ok(src.includes('gapLabel('), file);
    assert.ok(!src.includes("'Not given by country'") && !src.includes("'Countries not listed'"), `${file} words the row on its own`);
  }
  assert.ok(readFileSync(new URL('../src/components/ui.tsx', import.meta.url), 'utf8').includes('gapTitle('));
});
