/**
 * The words that name the tables a shared note covers (src/lib/commodityTables.ts, coverText), read on the built data of the pages that
 * have further tables: the EU member states and the stocks of the crops are not "kinds" (GV6C.2), and a list mixes labels a reader can
 * match to the titles on the page (GV6D.2): `node --test web/scripts/table-covers.test.mjs`.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { allTables, coverText, pageTables, tableLabel } from '../src/lib/commodityTables.ts';

const page = (id) => {
  const d = JSON.parse(readFileSync(new URL(`../../data/commodities/${id}.json`, import.meta.url), 'utf8'));
  return allTables(pageTables(d, id));
};
const all = (id, lead = 'Series by year of') => coverText(page(id), lead, lead);

test('barley, wheat, sorghum, corn, soybeans, sunflower, rapeseed, coffee: the EU member states and stocks are not kinds', () => {
  assert.equal(all('barley'), 'Series by year of production, consumption, exporters and importers, and of the EU member states and ending stocks');
  assert.equal(all('coffee', 'Tables of'), 'Tables of production, consumption, exporters and importers, and of the EU member states and ending stocks');
  for (const id of ['barley', 'sorghum', 'coffee', 'rice', 'sugar', 'palm-oil', 'soyoil', 'soymeal']) {
    // only the EU member states and the stocks stand beside the main tables: nothing is said "by kind" or "by product"
    assert.doesNotMatch(all(id), /by kind|by product/, id);
    assert.match(all(id), /and of the EU member states and ending stocks$/, id);
  }
  // wheat, corn, sunflower and rapeseed also have tables of a further product (flour, dregs, oil and meal): they are tables of exporters and importers
  assert.equal(all('wheat'), 'Series by year of production, consumption, exporters and importers, and of the EU member states and ending stocks');
});

test('pulses: the total tables and the tables of its kinds are tables of exporters and importers', () => {
  assert.equal(all('pulses', 'Tables of'), 'Tables of exporters and importers');
});

test('ferro-alloys, urea, pig iron: tables of further products are not said to split the main one', () => {
  assert.equal(all('ferro-alloys'), 'Series by year of exporters and importers');
  assert.equal(all('urea'), 'Series by year of production, exporters and importers');
  assert.equal(all('pig-iron'), 'Series by year of production, exporters and importers');
});

test('a short list names the tables as their titles do', () => {
  const fa = page('ferro-alloys');
  const imports = fa.filter((t) => t.key.endsWith('imports'));
  assert.equal(tableLabel(fa.find((t) => t.key === 'imports')), 'importers');
  assert.equal(tableLabel(fa.find((t) => t.key === 'imports'), imports), 'importers of ferro-chromium', 'beside a table of the same kind');
  assert.equal(coverText([imports[0], imports[4]], 'Series by year of', 'Series by year of'), 'Series by year of importers of ferro-chromium and other ferro-alloys importers');
  assert.equal(coverText(imports.slice(1, 4), 'Series by year of', 'Series by year of'), 'Series by year of ferro-manganese importers, silico-manganese importers and ferro-silicon importers');
  // the main tables of a page whose main table is the total keep the kind words
  const pulses = page('pulses');
  assert.equal(coverText(pulses.filter((t) => t.key === 'exports' || t.key === 'imports'), 'In the tables of', 'Tables of'), 'In the tables of exporters and importers');
  const barley = page('barley');
  assert.equal(coverText(barley.filter((t) => t.key.startsWith('eu-')), 'In the tables of', 'Tables of'), 'In the tables of EU member states, exports (customs data) and EU member states, imports (customs data)');
});

test('chromium: the main tables only', () => {
  assert.equal(all('chromium'), 'Series by year of production, exporters, importers and reserves');
});

test('every page: the stocks and the EU member states are named, "by kind" is never said of them, and every kind word is of a table that is there', () => {
  const idx = JSON.parse(readFileSync(new URL('../../data/commodities/index.json', import.meta.url), 'utf8'));
  let n = 0;
  for (const { id } of idx) {
    const ts = page(id);
    if (ts.length < 4) continue;
    const text = all(id);
    n++;
    assert.doesNotMatch(text, /by kind|by product/, id);
    if (ts.some((t) => t.key === 'stocks')) assert.match(text, /ending stocks/, id);
    else assert.doesNotMatch(text, /ending stocks/, id);
    if (ts.some((t) => t.key.startsWith('eu-'))) assert.match(text, /the EU member states/, id);
    else assert.doesNotMatch(text, /EU member states/, id);
    for (const [word, key] of [['production', 'production'], ['consumption', 'consumption'], ['exporters', 'exports'], ['importers', 'imports'], ['reserves', 'reserves']]) {
      if (new RegExp(`\\b${word}\\b`).test(text)) assert.ok(ts.some((t) => t.key === key || t.key.endsWith(`-${key}`)), `${id}: says ${word} without a table of it`);
    }
  }
  assert.ok(n >= 40, `${n} pages read`);
});

test('zinc and copper: a main table that counts ore says so, beside the refined-metal tables', () => {
  const zinc = page('zinc');
  const get = (k) => zinc.find((t) => t.key === k);
  assert.equal(
    coverText([get('exports'), get('metal-exports'), get('imports')], 'In the tables of', 'Tables of'),
    'In the tables of exporters of ores and concentrates, refined zinc exporters and importers',
  );
});

test('no two tables of a page have the same label, so a list can be matched to the titles', () => {
  const idx = JSON.parse(readFileSync(new URL('../../data/commodities/index.json', import.meta.url), 'utf8'));
  for (const { id } of idx) {
    const ts = page(id);
    const labels = ts.map((t) => tableLabel(t, ts));
    assert.equal(new Set(labels).size, labels.length, `${id}: ${labels.join(' | ')}`);
  }
});
