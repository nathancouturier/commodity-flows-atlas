/**
 * Tests of the match from a company to the assets of the infrastructure layer (src/lib/companyAssets.ts):
 * `node web/scripts/company-assets.test.mjs`. The module has no import, so Node runs the TypeScript file as it is.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { nameForms, operatorMatcher } from '../src/lib/companyAssets.ts';

const names = (company, operator) => operatorMatcher(company)(operator);

// the operator and the owners with a share count
assert.ok(names('Shell', 'Shell'));
assert.ok(names('Shell', 'Shell Nederland Raffinaderij'));
assert.ok(names('Glencore', 'Aster Chemicals and Energy (Chandra Asri / Glencore consortium); sold by Shell in April 2025'));
// a former owner does not: "sold by", "ex-", "formerly", "previously", "bought (from)" earlier in the same clause
assert.equal(names('Shell', 'Aster Chemicals and Energy (Chandra Asri / Glencore consortium); sold by Shell in April 2025'), false);
assert.equal(names('Shell', 'Aster, ex-Shell'), false);
assert.equal(names('Adaro Energy', 'AlamTri Resources (formerly Adaro Energy)'), false);
assert.equal(names('BP', 'Ineos; previously BP'), false);
assert.equal(names('Rio Tinto', 'Rumble Resources, bought from Rio Tinto in 2024'), false);
assert.equal(names('Mechel', 'Elga Coal (Elga company, which bought Mechel\'s stake)'), false);
assert.equal(names('Shell', 'Sold by Shell and Mitsui in 2020'), false);
assert.equal(names('Mitsui', 'Sold by Shell and Mitsui in 2020'), false);
// the clause ends at a semicolon, a comma or a bracket: the present owner after it still counts
assert.ok(names('Shell', 'sold by BP in 2019; Shell (operator)'));
assert.ok(names('Shell', 'Shell, formerly Royal Dutch Shell'));
// a name inside another word is not the company
assert.equal(names('BP', 'BPCL'), false);

// every company of the published lists: no asset whose operator field names it only as a former owner
const DATA = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../data');
const json = (f) => JSON.parse(fs.readFileSync(path.join(DATA, f), 'utf8'));
const infra = fs.readdirSync(path.join(DATA, 'infrastructure')).filter((f) => f.endsWith('.geojson'))
  .flatMap((f) => json(`infrastructure/${f}`).features.map((x) => x.properties).filter((p) => p?.operator));
const companies = new Set();
for (const groups of Object.values(json('commodities/companies.json'))) for (const list of Object.values(groups)) for (const c of list) companies.add(c.name);
for (const list of Object.values(json('freight/shipping-companies.json'))) for (const c of list) companies.add(c.name);
const shell = infra.filter((p) => names('Shell', p.operator)).map((p) => p.name);
assert.ok(shell.length > 0, 'Shell runs assets of the layer');
assert.ok(!shell.some((n) => /Pulau Bukom/.test(n)), 'Pulau Bukom (sold by Shell in April 2025) is not a Shell asset');
for (const c of companies) {
  for (const p of infra.filter((x) => names(c, x.operator))) {
    for (const form of nameForms(c)) {
      const esc = form.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      assert.ok(!new RegExp(`(sold by|ex-|formerly|previously|bought from) ${esc}$`, 'iu').test(p.operator), `${c}: ${p.name} (${p.operator})`);
    }
  }
}

console.log('company-assets: all checks passed');
