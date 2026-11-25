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
  'naturalearth', 'usgs-mcs', 'usgs-myb', 'baci', 'wb-pink', 'bls', 'dallasfed', 'nyfed', 'usda-psd', 'portwatch', 'portwatch-ports', 'portwatch-port-traffic', 'atlas', 'eia-chokepoints', 'eia-tie',
  'eia-spot', 'eia-intl', 'faostat', 'wikipedia', 'wikipedia-vessel-classes', 'vessel-size-conventions', 'eia-ng', 'eia-cab-russia',
  'eia-refinery-capacity', 'eia-storage-capacity', 'unctadstat-fleet', 'eia-dpr', 'eia-todayinenergy', 'openstreetmap', 'wikidata', 'faostat-rfb', 'eia-cab', 'eia-company-imports',
  'eia-exports-destination', 'disr-req', 'qld-coal-sales', 'eia-coal',
  // the Census Bureau's Public-Use Statement allows an estimate of one's own made from the data, citing the Census Bureau as the source of the original data
  // (the registry quotes it with its page and date): the LPG page's estimate of the United States to Mexico is exactly that
  'census-exports',
]);
const refused = [];
for (const s of registry) {
  const ok = licenceAllows(s.licence);
  if (!ok) refused.push(s.id);
  assert.equal(ok, allowed.has(s.id), `source ${s.id}: licence text "${s.licence}" gives ${ok}, expected ${allowed.has(s.id)}`);
}
// the World Nuclear Association table is one that is not offered
assert.ok(refused.includes('wna'));
// the World Port Index: the terms of the file used were not read, so its figures are cited and never offered as a file, and no text says "public domain" of it
const wpi = registry.find((s) => s.id === 'nga-wpi');
assert.ok(wpi && refused.includes('nga-wpi'));
assert.ok(/terms to be confirmed/.test(wpi.licence) && /not read/.test(wpi.licence));
assert.ok(!/public domain|open licen[cs]e|free to reuse/i.test(wpi.licence), 'the World Port Index licence text must not say public domain, open or free to reuse');

// The three PortWatch entries carry the same permission, so that the CSV of a port series is offered as the CSV of a chokepoint series is: the IMF's
// special terms for statistical data, which the atlas applies to PortWatch (the page lists examples and does not name it). None says that the data
// are in the public domain, openly licensed or free to reuse; the port series also states the sentence on bulk download and that applying the terms is the atlas's reading.
const pw = ['portwatch', 'portwatch-ports', 'portwatch-port-traffic'].map((id) => {
  const s = registry.find((x) => x.id === id);
  assert.ok(s, `${id} is in the registry`);
  return s;
});
for (const s of pw) {
  assert.ok(licenceAllows(s.licence), `${s.id} must carry the IMF permission`);
  assert.equal(licenceShort(s.licence), 'IMF terms of use for statistical data', s.id);
  assert.ok(s.licence.startsWith('IMF terms of use for statistical data'), `${s.id} licence text starts with the words of the IMF permission`);
  assert.ok(/commercial reuse needs IMF permission/.test(s.licence) && /no Creative Commons licence stated/i.test(s.licence), `${s.id} states the commercial limit and that no Creative Commons licence is stated`);
  assert.ok(/IMF PortWatch \(IMF and University of Oxford\)/.test(s.licence), `${s.id} carries the credit words`);
  assert.ok(!/public domain|open licen[cs]e|\bCC BY|\bCC0\b|free to reuse/i.test(s.licence), `${s.id}: the IMF data are not called public domain, openly licensed, CC BY or free to reuse`);
}
const traffic = pw[2];
assert.ok(/prohibits bulk download of information by automated technology without explicit permission/.test(traffic.licence), 'the port series quotes the IMF sentence on bulk download');
assert.ok(/does not name PortWatch/.test(traffic.licence) && /atlas's reading/.test(traffic.licence));
assert.ok(/Copyright-and-Terms/.test(traffic.licence) && /25 November 2026/.test(traffic.licence), 'the port series cites the page and the date it was read');
assert.ok(/Daily_Ports_Data/.test(traffic.name) && /83b1bbc7b3354c5fb1f40673bb8f852e/.test(traffic.url), 'the port series carries the dataset name and the address of its item');
assert.equal(traffic.update, 'weekly');

// The Public-Use Statement of the Census Bureau covers an estimate made from its data, not a row of its file: no table or file of the site
// may carry a row whose own source (`s`) is census-exports. The estimate names it as an input only (the lanes' histSrc, a note).
const census = registry.find((s) => s.id === 'census-exports');
assert.ok(census && /Public-Use Statement/.test(census.licence) && /citing-our-data|citation\.html/.test(census.licence) && /24 February 2026/.test(census.licence));
assert.ok(!/public domain|no copyright is claimed/i.test(census.licence), 'the Census licence text must not say public domain or that no copyright is claimed');
assert.equal(licenceShort(census.licence), 'U.S. Census Bureau Public-Use Statement');
const own = [];
const walk = (v, where) => {
  if (Array.isArray(v)) v.forEach((x, i) => walk(x, `${where}[${i}]`));
  else if (v && typeof v === 'object') {
    for (const [k, x] of Object.entries(v)) {
      if (k === 's' && x === 'census-exports') own.push(where);
      else walk(x, `${where}.${k}`);
    }
  }
};
const files = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? files(path.join(d, e.name)) : e.name.endsWith('.json') ? [path.join(d, e.name)] : []));
for (const f of files(root)) {
  if (f === path.join(root, 'sources.json')) continue;
  walk(JSON.parse(fs.readFileSync(f, 'utf8')), path.relative(root, f));
}
assert.deepEqual(own, [], `a row of the site has the Census file as its own source: ${own.join(', ')}`);
console.log('licence: all checks passed; no download for', refused.join(', '));
