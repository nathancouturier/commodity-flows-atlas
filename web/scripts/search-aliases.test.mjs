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
// the tie among the five fertiliser pages is read from the source as well (FNCI, GV8B.5)
const pagesLiteral = src.slice(src.indexOf('const FERTILISER_PAGES'), src.indexOf('/** Trade names of the products'));
const FERTILISER_PAGES = new Function(`return ${pagesLiteral.slice(pagesLiteral.indexOf('= [') + 2, pagesLiteral.lastIndexOf('];') + 1)}`)();
// and the words it is for (the matcher names no commodity: the words ride on the item)
const TIE_FOR = new Function(`return ${src.slice(src.indexOf('item.tieFor = ') + 14, src.indexOf(']', src.indexOf('item.tieFor = ')) + 1)}`)();
const index = JSON.parse(fs.readFileSync(path.join(here, '../../data/commodities/index.json'), 'utf8'));
const items = (Array.isArray(index) ? index : index.commodities).map((c) => ({
  kind: 'commodity',
  id: c.id,
  label: c.name,
  order: c.rank,
  tie: FERTILISER_PAGES.indexOf(c.id) >= 0 ? FERTILISER_PAGES.indexOf(c.id) : undefined,
  tieFor: FERTILISER_PAGES.indexOf(c.id) >= 0 ? TIE_FOR : undefined,
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
  d: prepare([r.name], [], [r.from.region, r.to.region, ...r.from.ports, ...r.to.ports, 'freight route', ...r.cargoes.map((k) => commodityName[k] ?? k)], r.cargoes.map((k) => commodityName[k] ?? k)),
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
  const mk = (kind, label, names, extra = [], cargo = []) => ({ kind, id: label, label, order: label, d: prepare(names, [], extra, cargo) });
  const items = [
    mk('route', 'Dried pulses: A to B', ['Dried pulses: A to B'], ['Pulses'], ['Pulses']),
    mk('route', 'Pig iron: C to D', ['Pig iron: C to D'], ['Pig iron & DRI'], ['Pig iron & DRI']),
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

// package FNCG (review GV7B.3): a whole word counts as a promotion only in the names, the codes and the cargo names of an item, not in its ports or regions
test('"chi": the routes of China come before the route whose port is Ho Chi Minh City', () => {
  const found = matchKind(tokens('chi'), routeItems, 'route');
  assert.ok(found.length > 3);
  assert.match(found[0].item.label, /^China/, found.slice(0, 5).map((m) => m.item.label).join(' | '));
  // the route of the review is still listed, after them
  assert.ok(found.some((m) => /Ho Chi Minh/i.test(m.item.d.x.join(' '))), 'a route with the port is found');
  const port = found.find((m) => /ho chi minh/.test(m.item.d.x.join(' ')));
  assert.equal(port.whole, false, 'a port does not make a whole-word match');
});

test('a whole word of a cargo name still counts: "DRI" finds the routes of the pig iron cargo first', () => {
  const found = matchKind(tokens('dri'), routeItems, 'route');
  assert.equal(found[0].whole, true);
  assert.ok(found[0].item.d.k.some((k) => /dri/.test(k)));
});

// ---- the queries of the review (GV6C.3, GV6C.4), on the catalogue and the aliases as the site builds them
const countries = JSON.parse(fs.readFileSync(path.join(here, '../../data/countries/index.json'), 'utf8'));
const countryItems = countries.map((c) => ({ kind: 'country', id: c.c, label: c.name, order: c.name, d: prepare([c.name], [c.c, c.a2 ?? ''], [c.region ?? '', 'country']) }));
const all = [...items, ...countryItems];
const groups = (q) => groupKinds(tokens(q), all, 6);

test('the trade abbreviations of the ferro-alloys find the ferro-alloys page', () => {
  for (const q of ['FeCr', 'FeMn', 'SiMn', 'FeSi', 'FeMo']) assert.deepEqual(find(q).slice(0, 1), ['ferro-alloys'], q);
});

test('"AN" finds the nitrogen page first, not the corn page through "brewing and distilling dregs"', () => {
  assert.deepEqual(find('AN').slice(0, 1), ['urea']);
  assert.equal(groups('AN')[0].items[0].id, 'urea');
  assert.ok(!ALIASES.corn.some((a) => /\band\b/.test(a)), 'no corn alias has the word "and"');
  assert.ok(ALIASES.corn.includes('brewing dregs') && ALIASES.corn.includes('distilling dregs'));
  assert.ok(find('dregs').includes('corn'));
});

test('"can": Canada comes first, the nitrogen page has no bare "CAN" alias, "calcium ammonium nitrate" is kept', () => {
  assert.ok(!ALIASES.urea.includes('CAN'));
  assert.deepEqual(find('calcium ammonium nitrate').slice(0, 1), ['urea']);
  for (const q of ['can', 'CAN']) {
    const g = groups(q);
    assert.equal(g[0].kind, 'country', q);
    assert.equal(g[0].items[0].id, 'CAN', q);
  }
});

test('"fertiliser" and "fertilizer" give the same pages in the same order', () => {
  assert.deepEqual(find('fertiliser'), find('fertilizer'));
  assert.deepEqual(find('fertiliser').slice(0, 5).sort(), ['npk', 'phosphate', 'potash', 'sulphur', 'urea']);
});

test('"fertiliser" and "fertilizer" give the five pages in the order of the seaborne tonnage of their groups, and the trade names keep their own page', () => {
  const root = path.join(here, '../../data/freight/pairs');
  const groups = { urea: ['urea', 'uan', 'ammonia', 'ammonium-nitrate', 'ammonium-nitrate-limestone', 'ammonium-sulphate'], phosphate: ['phosphate-rock', 'dap', 'monoammonium-phosphate', 'phosphoric-acid', 'tsp'], potash: ['potash', 'potassium-sulphate'], sulphur: ['sulphur'], npk: ['npk', 'npk-two-nutrient'] };
  const tonnes = Object.fromEntries(Object.entries(groups).map(([id, gs]) => [id, gs.filter((g) => fs.existsSync(path.join(root, `${g}.json`))).reduce((t, g) => t + JSON.parse(fs.readFileSync(path.join(root, `${g}.json`), 'utf8')).seaborne, 0)]));
  const byTonnes = Object.keys(tonnes).sort((a, b) => tonnes[b] - tonnes[a]);
  assert.deepEqual(FERTILISER_PAGES, byTonnes, JSON.stringify(tonnes));
  for (const q of ['fertiliser', 'fertilizer']) assert.deepEqual(find(q).slice(0, 5), byTonnes, q);
  for (const [q, id] of [['potash', 'potash'], ['DAP', 'phosphate'], ['sulfur', 'sulphur'], ['NPK', 'npk']]) assert.deepEqual(find(q).slice(0, 1), [id], q);
  // the tie decides nothing among pages that do not match alike, and nothing without a query
  assert.deepEqual(matchKind([], items, 'commodity').map((m) => m.item.id).filter((id) => FERTILISER_PAGES.includes(id)), ['potash', 'phosphate', 'urea', 'sulphur', 'npk']);
});

// review GV9B.1: the tie is for the queries "fertiliser" and "fertilizer" and their beginnings of four letters or more, and for no other
test('the tie is read from the source: the words fertiliser and fertilizer, and the matcher names no commodity', () => {
  assert.deepEqual(TIE_FOR, ['fertiliser', 'fertilizer']);
  const matcher = fs.readFileSync(path.join(here, '../src/lib/searchMatch.ts'), 'utf8');
  for (const id of FERTILISER_PAGES) assert.ok(!matcher.includes(`'${id}'`), `${id} is named in searchMatch.ts`);
});

test('"sulfate" and "sulphate" give the same first page, as before the tie: potash', () => {
  for (const q of ['sulfate', 'sulphate', 'sulfa', 'potassium sulphate', 'SOP']) assert.deepEqual(find(q).slice(0, 1), ['potash'], q);
  assert.deepEqual(find('sulfate'), find('sulphate'));
});

test('the fertiliser tie applies to the beginnings of the two words of four letters or more, and to no other query', () => {
  const firstUrea = (q) => assert.deepEqual(find(q).slice(0, 5), FERTILISER_PAGES, q);
  for (const q of ['fert', 'ferti', 'fertil', 'fertilis', 'fertiliser', 'fertiliz', 'fertilizer']) firstUrea(q);
  // three letters or two words: no tie
  const noTie = items.map((i) => ({ ...i, tie: undefined }));
  const same = (q) => assert.deepEqual(matchKind(tokens(q), items, 'commodity').map((m) => m.item.id), matchKind(tokens(q), noTie, 'commodity').map((m) => m.item.id), q);
  for (const q of ['fer', 'fe', 'sulfate', 'sulphate', 'so', 'su', 'sulf', 'co', 'com', 'mo', 'softs', 'fertiliser urea', 'potassium fertiliser']) same(q);
  // every beginning of every name or alias of the catalogue, up to five letters, but the fertiliser words: the tie changes nothing
  const words = new Set();
  for (const c of items) for (const w of [c.label, ...(ALIASES[c.id] ?? []), c.id]) for (const t of tokens(w)) for (let k = 2; k <= Math.min(5, t.length); k++) words.add(t.slice(0, k));
  const fert = (q) => q.length >= 4 && TIE_FOR.some((w) => w.startsWith(q));
  for (const q of words) if (!fert(q)) same(q);
});

test('the other queries of the review keep their first page: HMS, moly, sulfur, canola oil, lentils', () => {
  assert.deepEqual(find('HMS').slice(0, 1), ['ferrous-scrap']);
  assert.deepEqual(find('moly').slice(0, 1), ['molybdenum']);
  assert.deepEqual(find('sulfur').slice(0, 1), ['sulphur']);
  assert.deepEqual(find('canola oil').slice(0, 1), ['rapeseed']);
  assert.deepEqual(find('lentils').slice(0, 1), ['pulses']);
  assert.deepEqual(find('DRI'), ['pig-iron']);
});
