/**
 * The CSV of the price drawer holds only the series whose source states a permission to reuse its data (src/lib/priceFile.ts,
 * src/lib/licence.ts, data/sources.json): `node web/scripts/price-file.test.mjs`. The daily EIA spot prices, which the EIA credits to
 * Refinitiv and whose terms are to be confirmed, stay on the chart and are never in the file.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { splitOffered } from '../src/lib/priceFile.ts';
import { licenceAllows } from '../src/lib/licence.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const registry = JSON.parse(fs.readFileSync(path.join(here, '../../data/sources.json'), 'utf8'));
const index = JSON.parse(fs.readFileSync(path.join(here, '../../data/prices/index.json'), 'utf8'));
const allowed = (id) => licenceAllows(registry.find((s) => s.id === id)?.licence);
const offer = (series) => splitOffered(series, (m) => [m.s], allowed);
const ids = (xs) => xs.map((m) => m.id);

// the rule on small cases
const brent = { id: 'brent-d', s: 'eia-spot' };
const wb = { id: 'brent-m', s: 'wb-pink' };
assert.deepEqual(ids(offer([wb]).offered), ['brent-m'], 'a World Bank series keeps its file');
assert.deepEqual(offer([brent]).offered, [], 'no file for a daily EIA series alone');
assert.deepEqual(ids(offer([brent]).withheld), ['brent-d']);
const mixed = offer([brent, wb]);
assert.deepEqual(ids(mixed.offered), ['brent-m'], 'a chart that mixes the two offers a file of the World Bank series only');
assert.deepEqual(ids(mixed.withheld), ['brent-d']);
// a spread names two sources: with one of them refused, no file
assert.deepEqual(splitOffered([{ id: 'x' }], () => ['wb-pink', 'eia-spot'], allowed).offered, []);
assert.deepEqual(splitOffered([], () => [], allowed), { offered: [], withheld: [] });

// every series of the price index
const daily = index.filter((m) => m.s === 'eia-spot');
assert.equal(daily.length, 8, 'the eight daily EIA series');
for (const m of index) {
  const { offered } = offer([m]);
  assert.equal(offered.length === 1, m.s !== 'eia-spot', `${m.id} (${m.s}): ${offered.length ? 'in the file' : 'not in the file'}`);
}
assert.deepEqual(offer(index).withheld.map((m) => m.s), daily.map(() => 'eia-spot'));

// the decision is made in src/lib/pricesCsv.ts and the drawer, which this test reads as text: the file is built from the offered series only,
// whoever calls it, and the button is the one of the other tables (it says why there is none)
const csv = fs.readFileSync(path.join(here, '../src/lib/pricesCsv.ts'), 'utf8');
assert.ok(/for \(const d of offeredPrices\(data\)\.offered\)/.test(csv), 'pricesCsv loops over the offered series only');
assert.ok(/const \{ offered \} = offeredPrices\(data\);\s*if \(!offered\.length\) return;/.test(csv), 'downloadPrices saves nothing when no series may be offered');
assert.ok(/splitOffered\(data, \(d\) => sourcesOf\(d\.meta\), \(id\) => termsNotConfirmed\(\[id\]\)\.length === 0\)/.test(csv), 'the rule is the one of the other CSV buttons');
const drawer = fs.readFileSync(path.join(here, '../src/components/PriceDrawer.tsx'), 'utf8');
assert.ok(/<CsvAction[\s\S]*?downloadPrices\(fileOf\.offered,/.test(drawer), 'the drawer downloads the offered series');
assert.ok(!/downloadPrices\(data,/.test(drawer), 'the drawer never hands the whole selection to the file');

// the credit of a daily series, wherever the page shows it: "EIA (source: Refinitiv)" (the short label of ui.tsx, the board's status line and footer)
const ui = fs.readFileSync(path.join(here, '../src/components/ui.tsx'), 'utf8');
assert.ok(/'eia-spot': 'EIA \(source: Refinitiv\)',/.test(ui), 'the short label of the daily EIA series names Refinitiv');
const board = fs.readFileSync(path.join(here, '../src/components/PriceBoard.tsx'), 'utf8');
assert.ok(/'eia-spot': \{ by: 'EIA \(source: Refinitiv\)'/.test(board) && /\(EIA, daily; source: Refinitiv\)/.test(board), 'the board names Refinitiv beside the EIA');
console.log('price file: all checks passed');
