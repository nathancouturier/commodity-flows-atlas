/**
 * Tests of the trade names the search finds the commodity pages by (COMMODITY_ALIASES of src/lib/search.ts), with the matching of
 * src/lib/searchMatch.ts: `node web/scripts/search-aliases.test.mjs` (package FNCC, reviews GNC1.8 and GNC3.4).
 * The list is read from the source file, so that the test follows the page ids and the order of data/commodities/index.json.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { matchKind, prepare, tokens } from '../src/lib/searchMatch.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(here, '../src/lib/search.ts'), 'utf8');
const literal = src.slice(src.indexOf('const COMMODITY_ALIASES'), src.indexOf('const cap ='));
const ALIASES = new Function(`return ${literal.slice(literal.indexOf('= {') + 2, literal.lastIndexOf('};') + 1)}`)();
const index = JSON.parse(fs.readFileSync(path.join(here, '../../data/commodities/index.json'), 'utf8'));
const items = (Array.isArray(index) ? index : index.commodities).map((c) => ({
  kind: 'commodity',
  id: c.id,
  label: c.name,
  order: c.rank,
  d: prepare([c.name, ...(ALIASES[c.id] ?? [])], [c.id], [c.family, 'commodity']),
}));
const find = (q) => matchKind(tokens(q), items, 'commodity').map((m) => m.item.id);

test('"fertiliser" and "fertilizer" find sulphur with the other fertiliser pages', () => {
  for (const q of ['fertiliser', 'fertilizer']) {
    const ids = find(q);
    for (const id of ['urea', 'phosphate', 'potash', 'npk', 'sulphur']) assert.ok(ids.includes(id), `${q}: ${id} in ${ids}`);
  }
});

test('the trade names of scrap find the scrap page and nothing else', () => {
  for (const q of ['HMS', 'heavy melting scrap', 'shredded scrap']) assert.deepEqual(find(q).slice(0, 1), ['ferrous-scrap'], q);
});

test('"HBI" and "hot briquetted iron" find pig iron and DRI', () => {
  for (const q of ['HBI', 'hot briquetted iron']) assert.deepEqual(find(q).slice(0, 1), ['pig-iron'], q);
});

test('"DRI" finds pig iron and DRI, not the pulses or the corn page through "dried"', () => {
  assert.deepEqual(find('DRI'), ['pig-iron']);
  assert.deepEqual(find('direct reduced iron'), ['pig-iron']);
});

test('the pages that lost "dried" are still found by their other names', () => {
  assert.ok(find('dry beans').includes('pulses'));
  assert.ok(find('lentils').includes('pulses'));
  assert.ok(find('DDGS').includes('corn'));
  assert.ok(find('distillers grains').includes('corn'));
});

test('the commodity list (index.json rank) has sulphur before NPK, as the finder and LANE_GROUPS now have', () => {
  const rank = Object.fromEntries(items.map((i) => [i.id, i.order]));
  assert.ok(rank.sulphur < rank.npk);
  const freight = fs.readFileSync(path.join(here, '../src/lib/freight.ts'), 'utf8');
  assert.ok(freight.indexOf("  sulphur: ['sulphur'],") < freight.indexOf("  npk: ['npk', 'npk-two-nutrient'],"));
});
