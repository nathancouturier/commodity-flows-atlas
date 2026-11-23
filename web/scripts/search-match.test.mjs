/**
 * Tests of the search field's matching (src/lib/searchMatch.ts): `node web/scripts/search-match.test.mjs`.
 * The module has no import, so Node runs the TypeScript file as it is.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { TIE_ORDER, distance, groupKinds, matchKind, norm, prepare, rank, score, tokens } from '../src/lib/searchMatch.ts';

const S = (q, names, codes = [], extra = []) => score(tokens(q), prepare(names, codes, extra));

// normalisation
assert.equal(norm("Côte d'Ivoire"), 'cote d ivoire');
assert.equal(norm('  Tubarao – Qingdao '), 'tubarao qingdao');
assert.equal(norm('TC2_37'), 'tc2 37');
assert.equal(norm('Curaçao'), 'curacao');

// edit distance: insertion, deletion, replacement, swap
assert.equal(distance('hormuz', 'hormuz'), 0);
assert.equal(distance('hormz', 'hormuz'), 1);
assert.equal(distance('hormoz', 'hormuz'), 1);
assert.equal(distance('hrmuoz', 'hormuz', 2), 2);
assert.equal(distance('abcdef', 'uvwxyz', 2), 3);
assert.equal(distance('singapoer', 'singapore'), 1);

// exact code beats everything, case and accents ignored
const td3c = prepare(['Middle East Gulf – China'], ['TD3C']);
assert.ok(score(tokens('TD3C'), td3c) >= 100);
assert.ok(score(tokens('td3c'), td3c) > score(tokens('middle'), td3c));
assert.ok(S('c5', ['West Australia – Qingdao'], ['C5']) > S('c5', ['Strait of Hormuz'], ['hormuz'], ['c5 something']));

// words may be typed in part, in any order, accents or not
assert.ok(S('hor', ['Strait of Hormuz'], ['hormuz']) > 0);
assert.ok(S('hormuz strait', ['Strait of Hormuz']) > 0);
assert.ok(S('cote', ["Côte d'Ivoire"]) > 0);
assert.ok(S('curacao', ['Curaçao']) > 0);
assert.ok(S('zürich', ['Zurich']) > 0);

// a wrong, missing or swapped letter is tolerated from four letters on
assert.ok(S('hormz', ['Strait of Hormuz']) > 0);
assert.ok(S('hormoz', ['Strait of Hormuz']) > 0);
assert.ok(S('singapor', ['Singapore Strait']) > 0);
assert.ok(S('jurng', ['Jurong']) > 0);
assert.ok(S('braizl', ['Brazil']) > 0);
assert.ok(S('jpn', ['Japan'], ['JPN']) >= 100);
assert.equal(S('jpx', ['Japan'], ['JPN']), 0, 'short words are not fuzzy');
assert.equal(S('xyzzy', ['Strait of Hormuz']), 0);

// a word that is far from every word of the item matches nothing (no fuzzy match through the cap of the prefix test)
assert.equal(S('hormuz', ['Afghanistan'], ['AFG', 'AF'], ['Southern Asia']), 0);
assert.equal(S('abadan', ['Afghanistan'], ['AFG', 'AF'], ['Southern Asia']), 0);

// the secondary text tolerates one wrong letter, not two ("hedland" is not "zealand")
assert.equal(S('hedland', ['Tauranga'], [], ['New Zealand']), 0);
assert.ok(S('zealnd', ['Tauranga'], [], ['New Zealand']) > 0);

// every word has to match; a word may match the secondary text
assert.equal(S('japan crude', ['Japan']), 0);
assert.ok(S('abadan refinery', ['Abadan'], [], ['refinery', 'iran']) > 0);
assert.ok(S('iran', ['Abadan'], [], ['iran']) > 0);

// an exact name or code is ahead of a longer name that merely contains it
assert.ok(S('oman', ['Oman']) > S('oman', ['Gulf of Oman']));
assert.ok(S('india', ['India']) > S('india', ['British Indian Ocean Territory'], [], ['india']));
assert.ok(S('port hedland', ['Port Hedland']) > S('port hedland', ['Port of Hedland Pilot']));
// the name beats the secondary text
assert.ok(S('japan', ['Japan']) > S('japan', ['Strait of Korea'], [], ['japan']));



// the whole word beats the beginning of a longer word, and a word found inside another is not a match under four letters
assert.ok(S('gas', ['Natural gas']) > S('gas', ['Gasoline, New York Harbor, daily spot']));
assert.equal(S('gas', ['Antofagasta']), 0);
assert.equal(S('usa', ['Husab']), 0);
// a typo-tolerant match is on the lowest tier: below an exact word of the secondary text
const tier = (q, names, codes = [], extra = []) => rank(tokens(q), prepare(names, codes, extra)).tier;
assert.equal(tier('hormoz', ['Strait of Hormuz']), 1);
assert.equal(tier('copper', ['Koper']), 0, 'a typo keeps the first letter');
assert.equal(tier('copper', ['Amamapare'], [], ['Copper concentrate']), 2);
assert.equal(tier('copper', ['Copper']), 4);
assert.equal(tier('canal', ['Rapeseed & canola']), 1);
assert.equal(tier('cobalt', ['Thermal coal']), 0, '"coal" is not a typo of "cobalt"');
assert.equal(tier('panama canal', ['Panama Canal']), 4);
assert.equal(tier('hormuz', ['Strait of Hormuz'], ['hormuz']), 4);
assert.equal(tier('td3c', ['Middle East Gulf \u2013 China'], ['TD3C']), 4);

// ---- ranking on the atlas's own names: the queries of the review, with the catalogues of data/
// The Searchables are made as src/lib/search.ts makes them (names, codes, secondary text), from the published files.
const DATA = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../data');
const json = (f) => JSON.parse(fs.readFileSync(path.join(DATA, f), 'utf8'));
const countries = json('countries/index.json');
const cname = (iso) => countries.find((c) => c.c === iso)?.name ?? iso;
const commodities = json('commodities/index.json');
const items = [];
const add = (kind, id, label, d, order = label) => items.push({ kind, key: `${kind}:${id}`, label, d, order });
for (const c of commodities) add('commodity', c.id, c.name, prepare([c.name], [c.id], [c.family, 'commodity']), c.rank);
const ALIAS = { USA: ['us', 'usa', 'america', 'united states of america'], GBR: ['uk', 'britain', 'great britain', 'england'], IRN: ['persia'] };
for (const c of countries) add('country', c.c, c.name, prepare([c.name, ...(ALIAS[c.c] ?? [])], [c.c, c.a2 ?? ''], [c.region ?? '', 'country']));
for (const r of json('freight/routes.json')) {
  const code = r.benchmark ? r.id.split('_')[0] : '';
  add('route', r.id, r.name, prepare([r.name], code ? [r.id, code] : [], [r.from.region, r.to.region, ...r.from.ports, ...r.to.ports, 'freight route']));
}
for (const c of json('freight/chokepoints.json')) add('chokepoint', c.id, c.name, prepare([c.name], [c.id], [c.kind, 'chokepoint']));
for (const v of json('freight/vessel-classes.json')) add('vessel', v.id, v.name, prepare([v.name], [v.id], [v.segment, 'vessel class', 'ship']));
for (const f of fs.readdirSync(path.join(DATA, 'infrastructure')).filter((x) => x.endsWith('.geojson'))) {
  for (const ft of json(`infrastructure/${f}`).features) {
    const p = ft.properties;
    if (p?.name) add('infra', `${p.id}:${p.type}`, p.name, prepare([p.name], [p.id], [p.operator ?? '', cname(p.c), p.type ?? '', ...(p.cs ?? []).map(cname)]));
  }
}
for (const p of json('freight/ports.json').ports) add('port', p.id, p.name, prepare([p.name], [p.id], [cname(p.c), ...p.g, 'port']));
const kname = (k) => commodities.find((c) => c.id === k)?.name ?? k;
for (const e of json('freight/events.json')) add('event', e.id, e.title, prepare([e.title], [e.id], [e.id, e.kind, 'event', ...(e.countries ?? []).map(cname), ...(e.commodities ?? []).map(kname)]));
for (const m of json('prices/index.json')) if (!m.hidden && !m.realOf) add('price', m.id, m.name, prepare([m.name], [m.id], [m.unit, 'price']));

const top = (q, n = 1) => groupKinds(tokens(q), items, 5).slice(0, n).map((g) => `${g.kind}:${g.items[0].label}`);
const groups = (q) => groupKinds(tokens(q), items, 5);
// the order of the kinds for equal tiers is written once
assert.deepEqual([...TIE_ORDER].slice(0, 2), ['commodity', 'country']);
const first = { oil: 'commodity:Crude oil', gas: 'commodity:Natural gas', us: 'country:United States', iran: 'country:Iran', coal: 'commodity:Thermal coal', 'panama canal': 'chokepoint:Panama Canal', suez: 'chokepoint:Suez Canal', copper: 'commodity:Copper' };
for (const [q, want] of Object.entries(first)) assert.equal(top(q)[0], want, `"${q}" leads with ${top(q)[0]}, not ${want}`);
// an event, an asset or a price series that holds the word is never in front of the commodity, country or chokepoint it names
for (const q of ['oil', 'gas', 'coal', 'copper', 'iran']) {
  const g = groups(q).map((x) => x.kind);
  for (const weak of ['infra', 'event', 'price', 'port']) if (g.includes(weak)) assert.ok(g.indexOf(weak) > 0, `"${q}": ${weak} leads`);
}
// a typo never outranks an exact match: the exact one comes first inside its group
assert.equal(groups('copper').find((g) => g.kind === 'port')?.items[0].label !== 'Koper', true, 'the port Koper is not the best match of "copper"');
// the groups never mix tiers upside down: a group of a lower tier is not in front of a higher one
for (const q of ['oil', 'gas', 'us', 'iran', 'coal', 'panama canal', 'suez', 'copper', 'brazil', 'hormz', 'singapor']) {
  const g = groups(q);
  for (let i = 1; i < g.length; i++) assert.ok(g[i - 1].tier >= g[i].tier, `"${q}": tier order`);
}

// the release review's cases: a word with a digit is matched whole or as the beginning of a word, never with a typo
const labels = (q, kind) => groups(q).filter((g) => !kind || g.kind === kind).flatMap((g) => g.items.map((x) => x.label));
const everyLabel = (q, kind) => matchKind(tokens(q), items, kind).map((x) => x.item.label);
assert.equal(S('2026', ['Cadia Valley'], [], ['as stated in 2023']), 0);
assert.ok(S('2026', ['Some event'], ['some-event-2026'], ['some-event-2026']) > 0);
for (const x of items.filter((it) => rank(tokens('2026'), it.d).s > 0)) assert.ok([...x.d.n, ...x.d.c, ...x.d.x].some((t) => / 2026|^2026/.test(t)), `"2026" finds ${x.label}`);
assert.ok(!labels('2026', 'infra').includes('Cadia Valley'), '"2026" finds Cadia Valley');
// "cobalt" is not "coast", "houthi" is not "south", "iran" is not "Iraq"
assert.equal(S('cobalt', ['Hurricane Harvey hits US Gulf Coast']), 0);
assert.ok(!labels('cobalt').some((l) => /coast/i.test(l)), '"cobalt" finds a coast');
assert.ok(!labels('houthi', 'country').some((l) => /^South/.test(l)), '"houthi" finds South Africa or South Korea');
assert.deepEqual(labels('iran', 'country'), ['Iran'], '"iran" finds another country');
// the typos that still work: the first letter right, fewer edits than a third of the word
for (const [q, want] of [['coper', 'commodity:Copper'], ['sugr', 'commodity:Sugar'], ['kazakstan', 'country:Kazakhstan'], ['singapor', 'country:Singapore'], ['hormz', 'chokepoint:Strait of Hormuz'], ['braizl', 'country:Brazil']])
  assert.ok(groups(q).some((g) => `${g.kind}:${g.items[0].label}` === want), `"${q}" does not find ${want}`);
// several words: each may match the title, a code, the kind, a country or a commodity of the item
assert.ok(labels('iran war', 'event').length >= 2, '"iran war" finds the wars with Iran');
assert.ok(labels('iran war', 'event').some((l) => /2026|strikes on Iran/i.test(l)), '"iran war" finds the 2026 war');
// a short query is not flooded: every event "iran war" finds names Iran and a war
for (const l of everyLabel('iran war', 'event')) assert.ok(/iran/i.test(l), `"iran war" finds ${l}`);

console.log('search-match: all checks passed');
