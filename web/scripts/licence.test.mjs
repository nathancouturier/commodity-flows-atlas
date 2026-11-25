/**
 * Tests of the rule that decides whether a source's data may be offered as a CSV download (src/lib/licence.ts):
 * `node web/scripts/licence.test.mjs`. It also checks every source of data/sources.json against the list of
 * sources expected to be allowed, so a licence text that is edited in the registry changes the outcome here first.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { licenceAllows, licenceShort } from '../src/lib/licence.ts';

// the texts the rule is written for
assert.equal(licenceAllows('Public domain (US Government)'), true);
assert.equal(licenceAllows('CC BY 4.0 (attribution: Commodity Flows Atlas)'), true);
assert.equal(licenceAllows('CC BY-SA 4.0 (adapted; each item links its article)'), true);
assert.equal(licenceAllows('Etalab Open Licence 2.0'), true);
assert.equal(licenceAllows('ODbL 1.0: credit OpenStreetMap and its contributors'), true);
assert.equal(licenceAllows('CC0 1.0: structured data is in the public domain'), true);
// a text that names a licence and says the terms are not confirmed is no permission
assert.equal(licenceAllows('Package searoute-py: Apache 2.0. Eurostat SeaRoute network: EUPL 1.2 (terms to be confirmed)'), false);
assert.equal(licenceAllows('Copyright World Nuclear Association; figures cited with attribution (terms to be confirmed)'), false);
assert.equal(licenceAllows('Copyright World Steel Association; only the world total is cited'), false);
assert.equal(licenceAllows('No licence stated; facts cited with attribution (terms to be confirmed)'), false);
assert.equal(licenceAllows('Terms not read: the open-data page could not be opened, so no licence is stated here'), false);
assert.equal(licenceAllows('Index values are proprietary and not shown'), false);
assert.equal(licenceAllows('CC BY 4.0, but the terms were not read'), false);
assert.equal(licenceAllows(''), false);
assert.equal(licenceAllows(undefined), false);
// "no Creative Commons licence stated" is not a Creative Commons licence
assert.equal(licenceAllows('no Creative Commons licence stated'), false);
assert.equal(licenceShort('Public domain (US Government)'), 'Public domain');
assert.equal(licenceShort('CC BY 4.0 (FAO statistical database terms of use also apply)'), 'CC BY 4.0');
assert.equal(licenceShort('Etalab Open Licence 2.0'), 'Etalab Open Licence 2.0');

// every source of the registry
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../data');
const registry = JSON.parse(fs.readFileSync(path.join(root, 'sources.json'), 'utf8'));
const allowed = new Set([
  'naturalearth', 'usgs-mcs', 'usgs-myb', 'baci', 'wb-pink', 'bls', 'dallasfed', 'nyfed', 'usda-psd', 'portwatch', 'portwatch-ports', 'nga-wpi', 'atlas', 'eia-chokepoints', 'eia-tie',
  'eia-spot', 'eia-intl', 'faostat', 'wikipedia', 'wikipedia-vessel-classes', 'vessel-size-conventions', 'eia-ng', 'eia-cab-russia',
  'eia-refinery-capacity', 'eia-storage-capacity', 'unctadstat-fleet', 'eia-dpr', 'eia-todayinenergy', 'openstreetmap', 'wikidata', 'faostat-rfb', 'eia-cab', 'eia-company-imports',
  'eia-exports-destination', 'disr-req', 'qld-coal-sales', 'eia-coal',
]);
const refused = [];
for (const s of registry) {
  const ok = licenceAllows(s.licence);
  if (!ok) refused.push(s.id);
  assert.equal(ok, allowed.has(s.id), `source ${s.id}: licence text "${s.licence}" gives ${ok}, expected ${allowed.has(s.id)}`);
}
// the World Nuclear Association table is one that is not offered
assert.ok(refused.includes('wna'));
console.log('licence: all checks passed; no download for', refused.join(', '));
