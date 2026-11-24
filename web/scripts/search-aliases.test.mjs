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
import { groupKinds, matchKind, prepare, tokens } from '../src/lib/searchMatch.ts';

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

// package FNCE (review of FNCC): "DRI" is a whole word of the pig iron page's name and alias, and the beginning of "Dried"
const routes = JSON.parse(fs.readFileSync(path.join(here, '../../data/freight/routes.json'), 'utf8'));
const commodityName = Object.fromEntries((Array.isArray(index) ? index : index.commodities).map((c) => [c.id, c.name]));
// as search.ts makes a route item: the name, and the ends, the vessel class and the cargo pages' names as secondary text
const routeItems = routes.map((r) => ({
  kind: 'route',
  id: r.id,
  label: r.name,
  order: `${r.benchmark ? 0 : 1}${r.name}`,
  d: prepare([r.name], [], [r.from.region, r.to.region, ...r.from.ports, ...r.to.ports, 'freight route', ...r.cargoes.map((k) => commodityName[k] ?? k)]),
}));

test('"DRI": the routes that carry DRI come before the "Dried pulses" routes, which are still listed', () => {
  const found = matchKind(tokens('DRI'), routeItems, 'route');
  const ids = found.map((m) => m.item.label);
  const dried = ids.filter((l) => /^Dried /.test(l));
  const dri = found.filter((m) => !/^Dried /.test(m.item.label));
  assert.ok(dried.length >= 1, 'the Dried pulses routes are not hidden');
  assert.ok(dri.length >= 1 && dri.every((m) => m.whole), 'there are routes with DRI as a whole word');
  assert.ok(found.filter((m) => /^Dried /.test(m.item.label)).every((m) => !m.whole));
  assert.ok(ids.indexOf(dri.at(-1).item.label) < ids.indexOf(dried[0]), `${ids.join(' | ')}`);
});

test('a prefix of another word comes after every item that has the word whole, in every kind, and is not hidden', () => {
  const mk = (kind, label, names, extra = []) => ({ kind, id: label, label, order: label, d: prepare(names, [], extra) });
  const items = [
    mk('route', 'Dried pulses: A to B', ['Dried pulses: A to B'], ['Pulses']),
    mk('route', 'Pig iron: C to D', ['Pig iron: C to D'], ['Pig iron & DRI']),
    mk('route', 'DRI: E to F', ['DRI: E to F']),
  ];
  assert.deepEqual(matchKind(tokens('dri'), items, 'route').map((m) => m.item.label), ['DRI: E to F', 'Pig iron: C to D', 'Dried pulses: A to B']);
  // no whole-word item: the order is the one of the tiers, as before
  assert.deepEqual(matchKind(tokens('drie'), items, 'route').map((m) => m.item.label), ['Dried pulses: A to B']);
  // the group is as good as its best item, so a whole word found only in the secondary text does not lower the group
  const g = groupKinds(tokens('dri'), items, 5);
  assert.equal(g[0].kind, 'route');
  assert.equal(g[0].tier, 3);
  assert.equal(g[0].total, 3);
});
